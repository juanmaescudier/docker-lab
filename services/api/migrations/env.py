"""Entorno de ejecución de Alembic.

Toma la URL de la base de datos y los metadatos del MISMO sitio que la
aplicación: `app.config.database_url()` y `db.metadata`. Así el autogenerado
compara el esquema real contra los modelos de verdad, y no contra una copia que
podría quedarse atrás.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import database_url
from app.extensions import db

# Importar los modelos es lo que los registra en `db.metadata`. Sin esto,
# `--autogenerate` vería el esquema vacío y propondría BORRAR todas las tablas.
# Cada dominio nuevo tiene que añadir su línea aquí.
from app.catalog import models as _catalog  # noqa: F401
from app.jobs import models as _jobs  # noqa: F401
from app.plans import models as _plans  # noqa: F401
from app.recipes import models as _recipes  # noqa: F401
from app.users import models as _users  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# La URL no está en alembic.ini: se inyecta aquí desde el entorno.
# `render_as_string(hide_password=False)` es necesario porque el objeto URL
# oculta la contraseña con asteriscos al convertirlo a texto.
config.set_main_option(
    "sqlalchemy.url",
    database_url().render_as_string(hide_password=False).replace("%", "%%"),
)

target_metadata = db.metadata


def run_migrations_offline():
    """Genera el SQL sin conectarse, para revisarlo o aplicarlo a mano."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Aplica las migraciones contra la base de datos."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Sin esto, cambiar el tipo de una columna (por ejemplo Integer a
            # Date) pasaría desapercibido al autogenerar.
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
