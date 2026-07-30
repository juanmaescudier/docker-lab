"""Logging estructurado en JSON hacia stdout.

Mismo formato que el de la API (`app/logging_config.py`), para que las dos líneas
caigan en el mismo índice de Elasticsearch y se puedan filtrar juntas.

Antes esto era un `format` de `basicConfig` con las llaves escritas a mano. Se
cambia por dos motivos: un mensaje con comillas dentro rompía el JSON, y —lo
importante— un formato de texto **no puede llevar campos añadidos**, así que no
había dónde meter el consumo de tokens de cada llamada al modelo.
"""
import json
import logging
import os
import sys
import time

SERVICE_NAME = os.environ.get("SERVICE_NAME", "worker")


class JsonFormatter(logging.Formatter):
    """Serializa cada registro de logging como una línea JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "@timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)
            )
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "service": SERVICE_NAME,
            "logger": record.name,
            "message": record.getMessage(),
        }

        extras = getattr(record, "extra_fields", None)
        if extras:
            payload.update(extras)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


def configure():
    """Deja el logger raíz escribiendo JSON en stdout y lo devuelve."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())

    return logging.getLogger("worker")
