"""Application factory: crea y configura la app Flask (Postgres + sesiones Redis)."""
import os
from datetime import timedelta

import redis
from flask import Flask, jsonify
from prometheus_flask_exporter import PrometheusMetrics
from sqlalchemy import URL

from .extensions import db, sess
from .logging_config import configurar_logging


def create_app():
    app = Flask(__name__)

    # Lo primero, para que cualquier log posterior salga ya en JSON.
    configurar_logging(app)

    # ---------- Base de datos (PostgreSQL) ----------
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]
    host = os.environ["DB_HOST"]
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ["DB_NAME"]

    # URL.create() escapa los caracteres especiales de la contraseña automáticamente.
    app.config["SQLALCHEMY_DATABASE_URI"] = URL.create(
        drivername="postgresql+psycopg",
        username=user,
        password=password,
        host=host,
        port=int(port),
        database=name,
    )
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

    # ---------- Blueprints (un módulo por dominio) ----------
    from .users.routes import users_bp
    from .users.auth import auth_bp
    from .analisis.routes import analisis_bp
    app.register_blueprint(users_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(analisis_bp)

    # Crea las tablas que falten. Pendiente: migraciones con Alembic.
    with app.app_context():
        db.create_all()

    return app
