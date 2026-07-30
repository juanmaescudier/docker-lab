"""Application factory: crea y configura la app Flask (Postgres + sesiones Redis)."""
import os
from datetime import timedelta

import redis
from flask import Flask, jsonify
from prometheus_flask_exporter import PrometheusMetrics

from .config import database_url
from .extensions import db, sess
from .logging_config import configure_logging


def create_app():
    app = Flask(__name__)

    # Lo primero, para que cualquier log posterior salga ya en JSON.
    configure_logging(app)

    # ---------- Base de datos (PostgreSQL) ----------
    # La misma función que usa Alembic: una sola definición de la conexión, para
    # que migraciones y aplicación no puedan apuntar a bases de datos distintas.
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url()
    db.init_app(app)

    # ---------- Sesiones (Flask-Session sobre Redis) ----------
    app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
    app.config["SESSION_TYPE"] = "redis"
    app.config["SESSION_REDIS"] = redis.Redis(
        host=os.environ["REDIS_HOST"],
        port=int(os.environ.get("REDIS_PORT", "6379")),
    )
    app.config["SESSION_USE_SIGNER"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Solo por HTTPS: False en desarrollo, True detrás de un proxy con TLS.
    app.config["SESSION_COOKIE_SECURE"] = (
        os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
    )
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
    sess.init_app(app)

    # ---------- Métricas para Prometheus ----------
    # Expone /metrics y mide cada petición. Con varios workers de gunicorn haría
    # falta el modo multiproceso (PROMETHEUS_MULTIPROC_DIR).
    metrics = PrometheusMetrics(app)
    metrics.info("nutriapp_info", "Información de la app nutriapp", version="0.1.0")

    # ---------- Salud ----------
    @app.get("/health")
    def health():
        return jsonify(status="ok"), 200

    # ---------- Panel de trabajo ----------
    # La página la sirve la propia API, en el MISMO ORIGEN que los endpoints.
    # La sesión va en una cookie HttpOnly firmada: desde otro puerto seguiría
    # siendo el mismo sitio (el puerto no cuenta para SameSite) pero sería otro
    # origen, y entonces cada llamada necesitaría cabeceras CORS con
    # `Access-Control-Allow-Credentials` y un origen explícito en vez de `*`.
    # Para una herramienta interna de depuración eso no se paga.
    #
    # Es temporal a propósito: cuando exista el frontend de verdad, este fichero
    # sale de aquí y se pone detrás de NGINX, que ya está en el ROADMAP.
    @app.get("/")
    def panel():
        return app.send_static_file("index.html")

    # ---------- Blueprints (un módulo por dominio) ----------
    from .users.routes import users_bp
    from .users.auth import auth_bp
    from .catalog.routes import catalog_bp
    from .recipes.routes import recipes_bp
    from .plans.routes import plans_bp
    # `jobs` no es un dominio de negocio: es infraestructura de la aplicación,
    # el único sitio donde se consulta el estado de cualquier trabajo.
    from .jobs.routes import jobs_bp
    app.register_blueprint(users_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(recipes_bp)
    app.register_blueprint(plans_bp)

    # El esquema lo crea Alembic (`alembic upgrade head`), no la aplicación:
    # `db.create_all()` solo añadía tablas nuevas y nunca modificaba las
    # existentes, así que no servía para hacer evolucionar el modelo.
    #
    # La semilla del catálogo sí se carga aquí: son DATOS, no esquema, y deben
    # poder recargarse sin inventar una migración (3.14).
    from .catalog.seed import load_seed
    load_seed(app)

    return app
