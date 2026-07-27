"""Consumidor de la cola de análisis nutricionales.

Proceso sin HTTP: lee trabajos de una lista de Redis y actualiza su estado en
PostgreSQL. Usa SQL directo en lugar del ORM de la API para no depender de Flask
ni de SQLAlchemy.
"""
import json
import logging
import os
import signal
import sys
import time

import psycopg
import redis

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    stream=sys.stdout,
    format='{"@timestamp":"%(asctime)s","level":"%(levelname)s",'
           '"service":"worker","logger":"%(name)s","message":"%(message)s"}',
)
log = logging.getLogger("worker")

COLA_ANALISIS = "cola:analisis"

_parar = False


def _manejar_senal(signum, frame):
    """Marca la parada para terminar el trabajo en curso antes de salir."""
    global _parar
    log.info("recibida señal %s: termino el trabajo actual y salgo", signum)
    _parar = True


signal.signal(signal.SIGTERM, _manejar_senal)
signal.signal(signal.SIGINT, _manejar_senal)


def conectar_redis():
    return redis.Redis(
        host=os.environ["QUEUE_REDIS_HOST"],
        port=int(os.environ.get("QUEUE_REDIS_PORT", "6379")),
        decode_responses=True,
    )


def conectar_postgres():
    # autocommit para que los cambios de estado sean visibles de inmediato
    # para la API, sin esperar al final de una transacción.
    return psycopg.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        autocommit=True,
    )


# Marcador de posición hasta integrar el modelo de lenguaje.
CALORIAS_POR_100G = {
    "manzana": 52, "platano": 89, "pollo": 165, "arroz": 130,
    "huevo": 155, "salmon": 208, "pan": 265, "leche": 42,
    "pasta": 131, "atun": 132, "aguacate": 160, "yogur": 59,
}


def analizar_nutricion(entrada):
    """Calcula las calorías de una lista de alimentos.

    Acepta cada alimento como cadena ("manzana") o como diccionario
    ({"nombre": "manzana", "gramos": 150}).
    """
    alimentos = entrada.get("alimentos", [])

    detalle = []
    total = 0.0
    desconocidos = []

    for item in alimentos:
        if isinstance(item, dict):
            nombre = str(item.get("nombre", "")).lower()
            gramos = float(item.get("gramos", 100))
        else:
            nombre = str(item).lower()
            gramos = 100.0

        kcal_100 = CALORIAS_POR_100G.get(nombre)
        if kcal_100 is None:
            desconocidos.append(nombre)
            continue

        kcal = kcal_100 * gramos / 100
        total += kcal
        detalle.append({"nombre": nombre, "gramos": gramos, "kcal": round(kcal, 1)})

    # Latencia simulada: representa el coste de la futura llamada al modelo.
    time.sleep(float(os.environ.get("TRABAJO_SEGUNDOS", "5")))

    return {
        "detalle": detalle,
        "kcal_total": round(total, 1),
        "alimentos_desconocidos": desconocidos,
        "metodo": "tabla-estatica-simulada",
    }


def procesar_analisis(pg, analisis_id):
    """Ejecuta un análisis y refleja el resultado en su fila."""
    with pg.cursor() as cur:
        # El filtro por estado evita procesar dos veces el mismo trabajo si
        # llegara duplicado a la cola.
        cur.execute(
            """
            UPDATE analisis
               SET estado = 'procesando',
                   intentos = intentos + 1,
                   actualizado_en = NOW()
             WHERE id = %s AND estado IN ('pendiente', 'fallido')
         RETURNING entrada
            """,
            (analisis_id,),
        )
        fila = cur.fetchone()

    if fila is None:
        log.warning("analisis %s no está pendiente, lo ignoro", analisis_id)
        return

    entrada = fila[0]

    try:
        resultado = analizar_nutricion(entrada)
    except Exception as exc:
        # Un trabajo que falla no debe detener el consumidor.
        log.exception("analisis %s ha fallado", analisis_id)
        with pg.cursor() as cur:
            cur.execute(
                "UPDATE analisis SET estado='fallido', error=%s, actualizado_en=NOW() WHERE id=%s",
                (str(exc), analisis_id),
            )
        return

    with pg.cursor() as cur:
        cur.execute(
            """
            UPDATE analisis
               SET estado = 'completado',
                   resultado = %s,
                   error = NULL,
                   actualizado_en = NOW()
             WHERE id = %s
            """,
            (psycopg.types.json.Json(resultado), analisis_id),
        )

    log.info("analisis %s completado: %s kcal", analisis_id, resultado["kcal_total"])


def main():
    r = conectar_redis()
    pg = conectar_postgres()
    log.info("worker arrancado, esperando trabajos en %s", COLA_ANALISIS)

    while not _parar:
        # El timeout permite revisar la bandera de parada periódicamente;
        # con espera indefinida el contenedor no podría apagarse limpiamente.
        item = r.brpop(COLA_ANALISIS, timeout=5)
        if item is None:
            continue

        _, mensaje = item

        try:
            job = json.loads(mensaje)
        except json.JSONDecodeError:
            log.error("mensaje ilegible, lo descarto: %r", mensaje)
            continue

        tipo = job.get("tipo")

        if tipo == "analisis_nutricional":
            procesar_analisis(pg, job["analisis_id"])
        else:
            log.error("tipo de trabajo desconocido: %s", tipo)

    log.info("worker detenido limpiamente")
    pg.close()


if __name__ == "__main__":
    main()
