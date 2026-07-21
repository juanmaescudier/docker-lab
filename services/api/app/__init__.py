"""Application factory: crea y configura la app Flask (ahora con Postgres)."""
import os

from flask import Flask, jsonify
from sqlalchemy import URL

from .extensions import db


def create_app():
    app = Flask(__name__)

    # --- Configuración de la conexión a Postgres ---
    # Leemos los datos de conexión de variables de entorno (las pone el compose).
    # Si falta alguna obligatoria, la app falla al arrancar (fail fast), que es lo que queremos.
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]
    host = os.environ["DB_HOST"]
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ["DB_NAME"]

    # Construimos la URL con URL.create() en vez de un f-string: así SQLAlchemy
    # ESCAPA automáticamente los caracteres especiales de la contraseña (@, /, :, ...).
    # Montarla a mano con un f-string rompe si la contraseña lleva una '@'.
    app.config["SQLALCHEMY_DATABASE_URI"] = URL.create(
        drivername="postgresql+psycopg",
        username=user,
        password=password,
        host=host,
        port=int(port),
        database=name,
    )

    # Conectamos el objeto db (definido en extensions.py) con ESTA app.
    db.init_app(app)

    @app.get("/health")
    def health():
        return jsonify(status="ok"), 200

    from .users.routes import users_bp
    app.register_blueprint(users_bp)

    # Crea las tablas si aún no existen. Es idempotente (no borra nada).
    # Para el M0 nos vale; en el futuro esto se hace con "migraciones" (Alembic).
    with app.app_context():
        db.create_all()

    return app
