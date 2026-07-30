"""Cliente de la cola de trabajos.

Usa una instancia de Redis distinta a la de las sesiones: una caché de sesiones
se configura para expulsar claves al llenarse la memoria, lo que borraría
trabajos pendientes.
"""
import json
import os

import redis

# Contrato con el worker: ambos deben usar exactamente este nombre.
# Cambió de "queue:analysis" al generalizar los análisis a trabajos. No hay que
# migrar nada: los mensajes de la cola son efímeros y el formato del mensaje
# cambia también, así que uno antiguo sería ilegible de todas formas.
JOBS_QUEUE = "queue:jobs"

_client = None


def get_queue():
    """Devuelve el cliente de Redis de la cola, creándolo la primera vez."""
    global _client
    if _client is None:
        _client = redis.Redis(
            host=os.environ["QUEUE_REDIS_HOST"],
            port=int(os.environ.get("QUEUE_REDIS_PORT", "6379")),
            decode_responses=True,
        )
    return _client


def enqueue(job_type, job_id):
    """Añade un trabajo a la cola.

    El mensaje lleva **solo el tipo y el identificador**: la cola transporta,
    PostgreSQL recuerda (ADR-0008). Un mensaje mínimo nunca queda
    desincronizado con la fila real, y el `type` permite que un mismo worker
    despache varias clases de trabajo.

    Quien llama debe haber hecho ya el commit de la fila: al revés, el worker
    podría coger el mensaje y buscar una fila que todavía no existe.
    """
    message = json.dumps({"type": job_type, "job_id": job_id})

    # LPUSH empuja por la izquierda; el worker saca por la derecha (FIFO).
    get_queue().lpush(JOBS_QUEUE, message)


def queue_length():
    """Número de trabajos pendientes."""
    return get_queue().llen(JOBS_QUEUE)
