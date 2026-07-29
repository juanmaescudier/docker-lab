"""Cliente de la cola de trabajos.

Usa una instancia de Redis distinta a la de las sesiones: una caché de sesiones
se configura para expulsar claves al llenarse la memoria, lo que borraría
trabajos pendientes.
"""
import json
import os

import redis

# Contrato con el worker: ambos deben usar exactamente este nombre.
ANALYSIS_QUEUE = "queue:analysis"

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


def enqueue(job_type, payload):
    """Añade un trabajo a la cola.

    El campo 'type' permite que un mismo worker atienda varias clases de trabajo.
    """
    message = json.dumps({"type": job_type, **payload})

    # LPUSH empuja por la izquierda; el worker saca por la derecha (FIFO).
    get_queue().lpush(ANALYSIS_QUEUE, message)


def queue_length():
    """Número de trabajos pendientes."""
    return get_queue().llen(ANALYSIS_QUEUE)
