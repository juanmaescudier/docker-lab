"""Application factory: crea y configura la app Flask (Postgres + sesiones Redis)."""
import os
from datetime import timedelta

import redis
from flask import Flask, jsonify
from sqlalchemy import URL

from .extensions import db, sess


def create_app():
    app = Flask(__name__)

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
    # SECRET_KEY: clave con la que Flask FIRMA la cookie de sesión (es un secreto).
    app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
    app.config["SESSION_TYPE"] = "redis"                 # dónde se guardan las sesiones
    app.config["SESSION_REDIS"] = redis.Redis(           # cliente hacia el contenedor redis
        host=os.environ["REDIS_HOST"],
        port=int(os.environ.get("REDIS_PORT", "6379")),
    )
    app.config["SESSION_USE_SIGNER"] = True              # firma también el ID de la cookie
    app.config["SESSION_COOKIE_HTTPONLY"] = True         # el JS del navegador NO puede leerla
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"        # mitiga CSRF
    # Secure = solo enviar la cookie por HTTPS. En dev (http) debe ser False;
    # en producción (detrás de nginx con TLS) tiene que ser True.
    app.config["SESSION_COOKIE_SECURE"] = (
        os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
    )
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)  # caducidad de la sesión
    sess.init_app(app)

    # ---------- Salud ----------
    @app.get("/health")
    def health():
        return jsonify(status="ok"), 200

    # ---------- Blueprints (dominio Usuarios) ----------
    from .users.routes import users_bp
    from .users.auth import auth_bp
    app.register_blueprint(users_bp)
    app.register_blueprint(auth_bp)

    # Crea las tablas si no existen (M0). En el futuro: migraciones (Alembic).
    with app.app_context():
        db.create_all()

    return app
