"""Logging estructurado en JSON.

Por qué JSON y no texto: un log de texto es una cadena que hay que descifrar con
expresiones regulares. Un log en JSON llega a Elasticsearch (o CloudWatch, o Loki)
con campos ya separados, así que se puede filtrar por 'status', agregar por 'path'
o calcular la latencia media sin parsear nada.

Este módulo es autocontenido: se activa con configurar_logging(app) desde el
factory y no toca ninguna ruta ni modelo. Todo va a stdout, que es lo que espera
un contenedor (la app no sabe ni le importa quién recoge sus logs).
"""
import json
import logging
import os
import sys
import time
import uuid

from flask import g, request
from werkzeug.exceptions import HTTPException

# Nombre del servicio. Se puede sobrescribir por variable de entorno, lo que
# resulta útil cuando la misma imagen se despliega con distintos roles.
SERVICE_NAME = os.environ.get("SERVICE_NAME", "nutriapp")


class JsonFormatter(logging.Formatter):
    """Convierte cada registro de logging de Python en una línea JSON.

    Un 'Formatter' es la pieza de la librería logging que decide el FORMATO del
    mensaje final. Aquí, en lugar de devolver texto, devolvemos JSON serializado.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Campos base, presentes en cualquier log que emita la app.
        payload = {
            # Formato ISO 8601 en UTC: es el que entiende Elasticsearch sin ayuda.
            "@timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)
            )
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,        # INFO, WARNING, ERROR...
            "service": SERVICE_NAME,          # estable entre reconstrucciones
            "logger": record.name,            # qué módulo lo emitió
            "message": record.getMessage(),
        }

        # 'extra' permite añadir campos propios al hacer logger.info(..., extra={...}).
        # Los recogemos aquí para que acaben como campos de primer nivel en el JSON.
        extras = getattr(record, "extra_fields", None)
        if extras:
            payload.update(extras)

        # Si el log viene de un 'except', incluimos la traza completa.
        # exc_info lo rellena logging cuando se usa logger.exception(...).
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # default=str evita que un objeto no serializable rompa el log.
        return json.dumps(payload, default=str, ensure_ascii=False)


def configurar_logging(app):
    """Deja el logging de la app en JSON y registra un log por cada petición."""

    # ---------- 1. Salida en JSON hacia stdout ----------
    handler = logging.StreamHandler(sys.stdout)   # 'handler' = a dónde van los logs
    handler.setFormatter(JsonFormatter())         # 'formatter' = con qué formato

    nivel = os.environ.get("LOG_LEVEL", "INFO").upper()

    # Reemplazamos los handlers que Flask trae por defecto para no duplicar
    # cada línea (una en texto y otra en JSON).
    app.logger.handlers = [handler]
    app.logger.setLevel(nivel)
    # propagate=False corta la subida al logger raíz: sin esto, el mensaje se
    # escribiría otra vez con el formato del root logger.
    app.logger.propagate = False

    # ---------- 2. Un log estructurado por petición ----------

    @app.before_request
    def _iniciar_traza():
        # 'g' es un almacén por petición de Flask: lo que guardes aquí vive solo
        # durante esa petición y es visible desde cualquier parte de ella.
        g._inicio = time.perf_counter()   # reloj monótono: no le afectan cambios de hora

        # request_id: identificador único de la petición. Si el cliente (o un
        # proxy) ya envía uno, lo respetamos; si no, generamos uno.
        # Sirve para CORRELACIONAR: todos los logs de una misma petición
        # comparten el mismo id, y así se sigue su rastro entre servicios.
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]

    @app.after_request
    def _registrar_peticion(response):
        duracion_ms = (time.perf_counter() - getattr(g, "_inicio", 0)) * 1000

        campos = {
            "request_id": getattr(g, "request_id", None),
            "method": request.method,                  # GET, POST...
            "path": request.path,                      # /users, /health...
            "status": response.status_code,            # numérico: permite status >= 500
            "duration_ms": round(duracion_ms, 2),
            "remote_addr": request.remote_addr,
            "user_agent": request.headers.get("User-Agent"),
        }

        # El nivel del log depende del resultado: así en Kibana basta filtrar por
        # level para encontrar los problemas, sin mirar códigos a mano.
        if response.status_code >= 500:
            nivel_log = logging.ERROR      # fallo del servidor
        elif response.status_code >= 400:
            nivel_log = logging.WARNING    # fallo del cliente (404, 401...)
        else:
            nivel_log = logging.INFO

        app.logger.log(
            nivel_log,
            "peticion",
            # extra={"extra_fields": ...} es el canal por el que nuestros campos
            # llegan al JsonFormatter de arriba.
            extra={"extra_fields": campos},
        )

        # Devolvemos el request_id al cliente: si alguien reporta un error, con
        # ese id encuentras su petición exacta en los logs.
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        return response

    # ---------- 3. Excepciones no controladas ----------
    @app.errorhandler(Exception)
    def _registrar_excepcion(error):
        # OJO: este handler recibe TODAS las excepciones, y Flask representa los
        # errores HTTP normales (404, 401, 405...) como HTTPException. Esos no son
        # fallos del servidor: hay que devolverlos tal cual o convertiríamos un
        # 404 en un 500. El log de la petición ya los registra como WARNING.
        if isinstance(error, HTTPException):
            return error

        # A partir de aquí sí son errores inesperados: traza completa al log.
        # logger.exception incluye el stack trace en el campo 'exception'.
        app.logger.exception(
            "excepcion no controlada",
            extra={"extra_fields": {
                "request_id": getattr(g, "request_id", None),
                "path": request.path,
                "method": request.method,
            }},
        )
        # Re-lanzamos para que Flask siga su curso normal (devolver un 500).
        raise error
