"""Logging estructurado en JSON hacia stdout.

Un log en JSON llega a Elasticsearch con los campos ya separados, así que se
puede filtrar por estado o agregar por ruta sin parsear texto.
"""
import json
import logging
import os
import sys
import time
import uuid

from flask import g, request
from werkzeug.exceptions import HTTPException

SERVICE_NAME = os.environ.get("SERVICE_NAME", "nutriapp")


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


def configurar_logging(app):
    """Configura la salida JSON y registra un log por petición."""

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    # Se reemplazan los handlers de Flask para no duplicar cada línea, y se
    # corta la propagación al logger raíz por el mismo motivo.
    app.logger.handlers = [handler]
    app.logger.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    app.logger.propagate = False

    @app.before_request
    def _iniciar_traza():
        # perf_counter es monótono: no le afectan los ajustes de reloj.
        g._inicio = time.perf_counter()
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]

    @app.after_request
    def _registrar_peticion(response):
        duracion_ms = (time.perf_counter() - getattr(g, "_inicio", 0)) * 1000

        campos = {
            "request_id": getattr(g, "request_id", None),
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "duration_ms": round(duracion_ms, 2),
            "remote_addr": request.remote_addr,
            "user_agent": request.headers.get("User-Agent"),
        }

        # El nivel se deriva del resultado para poder filtrar por level en Kibana.
        if response.status_code >= 500:
            nivel_log = logging.ERROR
        elif response.status_code >= 400:
            nivel_log = logging.WARNING
        else:
            nivel_log = logging.INFO

        app.logger.log(nivel_log, "peticion", extra={"extra_fields": campos})

        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        return response

    @app.errorhandler(Exception)
    def _registrar_excepcion(error):
        # Los errores HTTP normales (404, 401, 405...) se devuelven tal cual:
        # convertirlos aquí los transformaría en 500.
        if isinstance(error, HTTPException):
            return error

        app.logger.exception(
            "excepcion no controlada",
            extra={"extra_fields": {
                "request_id": getattr(g, "request_id", None),
                "path": request.path,
                "method": request.method,
            }},
        )
        raise error
