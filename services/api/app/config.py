"""Configuración compartida entre la aplicación y las migraciones.

La URL de la base de datos vive aquí y no en el *factory* porque Alembic también
la necesita. Duplicarla en `alembic.ini` significaría tener las credenciales en
dos sitios y que un día dejaran de coincidir: las migraciones se aplicarían
contra una base de datos distinta de la que usa la API.
"""
import os

from sqlalchemy import URL


def database_url():
    """Construye la URL de PostgreSQL a partir del entorno.

    `URL.create()` en vez de interpolar una cadena: escapa por sí solo los
    caracteres especiales de la contraseña.
    """
    return URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "5432")),
        database=os.environ["DB_NAME"],
    )
