"""Cliente de la cola de trabajos.

Usa una instancia de Redis distinta a la de las sesiones: una caché de sesiones
se configura para expulsar claves al llenarse la memoria, lo que borraría
trabajos pendientes.
"""
import json
import os

import redis

# Contrato con el worker: ambos deben usar exactamente este nombre.
COLA_ANALISIS = "cola:analisis"

_cliente = None


def get_cola():
    """Devuelve el cliente de Redis de la cola, creándolo la primera vez."""
    global _cliente
    if _cliente is None:
        _cliente = redis.Redis(
            host=os.environ["QUEUE_REDIS_HOST"],
            port=int(os.environ.get("QUEUE_REDIS_PORT", "6379")),
            decode_responses=True,
        )
    return _cliente


def encolar(tipo, payload):
    """Añade un trabajo a la cola.

    El campo 'tipo' permite que un mismo worker atienda varias clases de trabajo.
    """
    mensaje = json.dumps({"tipo": tipo, **payload})

    # LPUSH empuja por la izquierda; el worker saca por la derecha (FIFO).
    get_cola().lpush(COLA_ANALISIS, mensaje)


def longitud_cola():
    """Número de trabajos pendientes."""
    return get_cola().llen(COLA_ANALISIS)
