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

# Contrato con la API: el nombre de la lista y el campo 'type' del mensaje tienen
# que coincidir exactamente con los de app/queue.py, o dejan de entenderse.
ANALYSIS_QUEUE = "queue:analysis"
JOB_NUTRITIONAL_ANALYSIS = "nutritional_analysis"

_stop = False


def _handle_signal(signum, frame):
    """Marca la parada para terminar el trabajo en curso antes de salir."""
    global _stop
    log.info("recibida señal %s: termino el trabajo actual y salgo", signum)
    _stop = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def connect_redis():
    return redis.Redis(
        host=os.environ["QUEUE_REDIS_HOST"],
        port=int(os.environ.get("QUEUE_REDIS_PORT", "6379")),
        decode_responses=True,
    )


def connect_postgres():
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
KCAL_PER_100G = {
    "manzana": 52, "platano": 89, "pollo": 165, "arroz": 130,
    "huevo": 155, "salmon": 208, "pan": 265, "leche": 42,
    "pasta": 131, "atun": 132, "aguacate": 160, "yogur": 59,
}


def analyze_nutrition(job_input):
    """Calcula las calorías de una lista de alimentos.

    Acepta cada alimento como cadena ("manzana") o como diccionario
    ({"name": "manzana", "grams": 150}).
    """
    foods = job_input.get("foods", [])

    details = []
    total = 0.0
    unknown = []

    for item in foods:
        if isinstance(item, dict):
            name = str(item.get("name", "")).lower()
            grams = float(item.get("grams", 100))
        else:
            name = str(item).lower()
            grams = 100.0

        kcal_100 = KCAL_PER_100G.get(name)
        if kcal_100 is None:
            unknown.append(name)
            continue

        kcal = kcal_100 * grams / 100
        total += kcal
        details.append({"name": name, "grams": grams, "kcal": round(kcal, 1)})

    # Latencia simulada: representa el coste de la futura llamada al modelo.
    time.sleep(float(os.environ.get("TRABAJO_SEGUNDOS", "5")))

    return {
        "details": details,
        "total_kcal": round(total, 1),
        "unknown_foods": unknown,
        "method": "static-table-stub",
    }


def process_analysis(pg, analysis_id):
    """Ejecuta un análisis y refleja el resultado en su fila."""
    with pg.cursor() as cur:
        # El filtro por estado evita procesar dos veces el mismo trabajo si
        # llegara duplicado a la cola.
        cur.execute(
            """
            UPDATE analyses
               SET state = 'processing',
                   attempts = attempts + 1,
                   updated_at = NOW()
             WHERE id = %s AND state IN ('pending', 'failed')
         RETURNING input
            """,
            (analysis_id,),
        )
        row = cur.fetchone()

    if row is None:
        log.warning("analisis %s no está pendiente, lo ignoro", analysis_id)
        return

    job_input = row[0]

    try:
        result = analyze_nutrition(job_input)
    except Exception as exc:
        # Un trabajo que falla no debe detener el consumidor.
        log.exception("analisis %s ha fallado", analysis_id)
        with pg.cursor() as cur:
            cur.execute(
                "UPDATE analyses SET state='failed', error=%s, updated_at=NOW() WHERE id=%s",
                (str(exc), analysis_id),
            )
        return

    with pg.cursor() as cur:
        cur.execute(
            """
            UPDATE analyses
               SET state = 'completed',
                   result = %s,
                   error = NULL,
                   updated_at = NOW()
             WHERE id = %s
            """,
            (psycopg.types.json.Json(result), analysis_id),
        )

    log.info("analisis %s completado: %s kcal", analysis_id, result["total_kcal"])


def main():
    r = connect_redis()
    pg = connect_postgres()
    log.info("worker arrancado, esperando trabajos en %s", ANALYSIS_QUEUE)

    while not _stop:
        # El timeout permite revisar la bandera de parada periódicamente;
        # con espera indefinida el contenedor no podría apagarse limpiamente.
        item = r.brpop(ANALYSIS_QUEUE, timeout=5)
        if item is None:
            continue

        _, message = item

        try:
            job = json.loads(message)
        except json.JSONDecodeError:
            log.error("mensaje ilegible, lo descarto: %r", message)
            continue

        job_type = job.get("type")

        if job_type == JOB_NUTRITIONAL_ANALYSIS:
            process_analysis(pg, job["analysis_id"])
        else:
            log.error("tipo de trabajo desconocido: %s", job_type)

    log.info("worker detenido limpiamente")
    pg.close()


if __name__ == "__main__":
    main()
