"""Consumidor de la cola de trabajos.

Proceso sin HTTP: lee identificadores de trabajo de una lista de Redis, los
procesa y actualiza su estado en PostgreSQL.

**A la cola va lo lento, lo poco fiable o lo que hay que reintentar.** Sumar seis
ingredientes son microsegundos y pertenece a la API; llamar a un modelo de
lenguaje tarda decenas de segundos y pertenece aquí. Por eso el worker ya no
calcula nutrición: eso lo hace `Recipe.nutrition_summary()` desde el catálogo,
con los números buenos.
"""
import json
import os
import signal
import threading

import redis

import db
import handlers
import logging_config
from llm import get_provider
from llm.errors import LLMError, LLMRateLimited

log = logging_config.configure()

# Contrato con la API: el nombre de la lista y el formato del mensaje tienen que
# coincidir exactamente con los de `app/queue.py`, o dejan de entenderse.
JOBS_QUEUE = "queue:jobs"

# Cada cuánto se comprueba si han pedido parar. Con espera indefinida en BRPOP el
# contenedor no podría apagarse limpiamente.
BRPOP_TIMEOUT_SECONDS = 5

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 2.0
DEFAULT_BACKOFF_MAX_SECONDS = 60.0

# Un Event y no un booleano suelto: `wait()` corta en cuanto se marca, así que la
# espera entre reintentos no retrasa el apagado hasta un minuto.
_stop = threading.Event()


def _handle_signal(signum, frame):
    log.info(
        "señal recibida: termino el trabajo actual y salgo",
        extra={"extra_fields": {"signal": signum}},
    )
    _stop.set()


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def _int_env(name, default):
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _float_env(name, default):
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def connect_redis():
    return redis.Redis(
        host=os.environ["QUEUE_REDIS_HOST"],
        port=int(os.environ.get("QUEUE_REDIS_PORT", "6379")),
        decode_responses=True,
    )


def _backoff_seconds(attempt, error):
    """Espera creciente: 2 s, 4 s, 8 s… con tope.

    Creciente y no fija porque los fallos que se reintentan son casi siempre de
    saturación: volver a golpear al mismo ritmo empeora justo lo que se espera
    que se arregle solo.
    """
    base = _float_env("JOB_RETRY_BACKOFF_SECONDS", DEFAULT_BACKOFF_SECONDS)
    top = _float_env("JOB_RETRY_BACKOFF_MAX_SECONDS", DEFAULT_BACKOFF_MAX_SECONDS)

    delay = min(base * (2 ** (attempt - 1)), top)

    # Si el proveedor dice cuánto esperar en un 429, se le hace caso: sabe mejor
    # que nosotros cuándo vuelve a aceptar peticiones.
    if isinstance(error, LLMRateLimited) and error.retry_after:
        delay = max(delay, min(error.retry_after, top))

    return delay


def process_job(conn, job_id, provider):
    """Procesa un trabajo de principio a fin, con sus reintentos."""
    job = db.claim_job(conn, job_id)

    if job is None:
        # Ya está en curso o terminado: el mensaje llegó duplicado. No es un
        # error, es la protección funcionando.
        log.warning(
            "el trabajo no está pendiente, lo ignoro",
            extra={"extra_fields": {"job_id": job_id}},
        )
        return

    # Sin esta línea, un trabajo en vuelo no emite nada hasta que termina: una
    # generación de tres minutos parecía un worker muerto.
    log.info(
        "trabajo reclamado",
        extra={"extra_fields": {
            "job_id": job_id,
            "job_type": job["type"],
            "user_id": job["user_id"],
            "attempts": job["attempts"],
            "llm_provider": provider.name,
            "llm_model": provider.model,
        }},
    )

    handler = handlers.HANDLERS.get(job["type"])
    if handler is None:
        message = f"tipo de trabajo desconocido: {job['type']}"
        log.error(message, extra={"extra_fields": {"job_id": job_id}})
        db.fail_job(conn, job_id, message)
        return

    max_attempts = max(1, _int_env("JOB_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS))

    # Lo que ha cobrado el modelo en ESTE trabajo, sumando todos los intentos.
    #
    # **Un intento fallido se paga igual y no deja `result`**, así que sin esto el
    # gasto total que se ve en el panel se queda corto justo en los trabajos que
    # más han costado: el que acierta a la tercera cobra tres veces y solo declara
    # una. Y esos son precisamente los que hay que ver al tocar el prompt.
    spent = {"cost": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "calls": 0}

    def log_response(response):
        """Deja el consumo de cada llamada en el log JSON y lo va sumando.

        El log es lo que permite agregar por modelo en Kibana; la suma es lo que
        acaba en `jobs.result`, que es de donde lo lee el panel. Métricas de
        Prometheus todavía no: un proceso sin servidor HTTP no tiene por dónde
        exponerlas, y eso es una decisión de infraestructura aparte.
        """
        spent["cost"] += response.cost or 0.0
        spent["prompt_tokens"] += response.prompt_tokens or 0
        spent["completion_tokens"] += response.completion_tokens or 0
        spent["calls"] += 1

        log.info(
            "llamada al modelo completada",
            extra={"extra_fields": {
                "job_id": job_id,
                "job_type": job["type"],
                "llm_provider": provider.name,
                **response.usage_fields(),
            }},
        )

    def billed():
        """El consumo acumulado, para guardarlo termine como termine el trabajo."""
        return {
            "billed_cost": round(spent["cost"], 8),
            "billed_prompt_tokens": spent["prompt_tokens"],
            "billed_completion_tokens": spent["completion_tokens"],
            "billed_calls": spent["calls"],
        }

    for attempt in range(1, max_attempts + 1):
        try:
            result = handler(conn, job, provider, log_response)

        except LLMError as exc:
            error = f"{type(exc).__name__}: {exc}"
            will_retry = exc.retryable and attempt < max_attempts

            log.warning(
                "el trabajo ha fallado",
                extra={"extra_fields": {
                    "job_id": job_id,
                    "job_type": job["type"],
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "will_retry": will_retry,
                    "error": error,
                }},
            )

            if not will_retry:
                # El trabajo se da por fallido, pero lo que ya ha cobrado el
                # modelo se guarda igual: un trabajo que falla tres veces cuesta
                # dinero, y no anotarlo lo haría invisible en el gasto total.
                db.fail_job(conn, job_id, error, billed())
                return

            # Se anota el error aunque el trabajo siga vivo: si al final agota
            # los intentos, el mensaje ya está puesto, y mientras tanto se ve en
            # `GET /jobs/<id>` por qué está tardando.
            db.record_attempt(conn, job_id, error)

            # `wait` devuelve True si han pedido parar: se abandona el reintento
            # en lugar de hacer esperar al contenedor a que se agote la cuenta.
            if _stop.wait(_backoff_seconds(attempt, exc)):
                db.fail_job(
                    conn, job_id,
                    f"{error} (el worker se estaba apagando y no ha reintentado)",
                )
                return

        except Exception as exc:
            # Un fallo inesperado no debe tumbar al consumidor: se marca el
            # trabajo como fallido y se sigue atendiendo la cola.
            log.exception(
                "excepción no controlada procesando el trabajo",
                extra={"extra_fields": {"job_id": job_id, "job_type": job["type"]}},
            )
            db.fail_job(conn, job_id, f"{type(exc).__name__}: {exc}")
            return

        else:
            # `billed()` va DESPUÉS del resultado del manejador para que mande él:
            # el trabajo que acierta a la tercera declara el coste de las tres
            # llamadas, no el de la última.
            db.complete_job(conn, job_id, {**result, **billed()})
            log.info(
                "trabajo completado",
                extra={"extra_fields": {
                    "job_id": job_id,
                    "job_type": job["type"],
                    "attempts": attempt,
                    "plan_id": result.get("plan_id"),
                }},
            )
            return


def main():
    provider = get_provider()
    redis_client = connect_redis()
    conn = db.connect()

    log.info(
        "worker arrancado",
        extra={"extra_fields": {
            "queue": JOBS_QUEUE,
            "llm_provider": provider.name,
            "llm_model": provider.model,
        }},
    )

    while not _stop.is_set():
        item = redis_client.brpop(JOBS_QUEUE, timeout=BRPOP_TIMEOUT_SECONDS)
        if item is None:
            continue

        _, message = item

        try:
            job_id = json.loads(message)["job_id"]
        except (json.JSONDecodeError, KeyError, TypeError):
            # Un mensaje ilegible no tiene fila que marcar: se descarta y se
            # sigue. Se registra recortado porque es la única pista que queda.
            log.error(
                "mensaje ilegible, lo descarto",
                extra={"extra_fields": {"message": message[:500]}},
            )
            continue

        process_job(conn, job_id, provider)

    log.info("worker detenido limpiamente")
    conn.close()


if __name__ == "__main__":
    main()
