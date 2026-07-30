"""La tabla de análisis pasa a ser la tabla genérica de trabajos.

`analyses` nunca modeló un análisis nutricional: modelaba `state`, `input`,
`result`, `error` e `attempts`, que es exactamente **un trabajo asíncrono**. Al
añadir la generación de planes habría hecho falta una segunda tabla idéntica, y
una tercera para las importaciones de USDA.

**Renombrado, nunca DROP + ADD.** `ALTER TABLE ... RENAME` conserva los datos, las
claves ajenas y los índices; borrar y recrear vaciaría el histórico de análisis
de todos los usuarios. Alembic no distingue un renombrado de un borrado más un
alta, así que esta migración está escrita a mano.

Se renombran también el índice, las restricciones y la secuencia: PostgreSQL NO
los renombra solo al renombrar la tabla, y si se quedan con el nombre viejo el
siguiente `alembic check` los ve como desviación.

La columna `type` se añade en tres pasos —nullable, relleno, NOT NULL— porque una
columna NOT NULL sin valor por defecto no se puede añadir a una tabla con filas.
Las filas que ya existían son todas revisiones de plan: era lo único que se podía
encolar.

El `input` de esas filas antiguas se queda como estaba (con su clave `foods`) en
lugar de convertirlo al formato nuevo. Son trabajos ya terminados que nadie va a
reprocesar, y una migración de datos que reinventa un `input` que jamás se usó
tiene más riesgo que valor.

**Lo que sí se pierde al bajar:** el `downgrade` borra la columna `type`, así que
un trabajo que era `plan_generation` vuelve como `plan_review` si se sube otra
vez. No hay forma de evitarlo —la información no cabe en el esquema antiguo— y no
es grave: las filas, los planes y las recetas siguen todos ahí.

Revision ID: a1e7c3d9b504
Revises: c4f1a9b7d2e8
Create Date: 2026-07-30 10:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'a1e7c3d9b504'
down_revision = 'c4f1a9b7d2e8'
branch_labels = None
depends_on = None


INDEXES = [
    ("ix_analyses_state", "ix_jobs_state"),
    ("ix_analyses_plan_id", "ix_jobs_plan_id"),
]

CONSTRAINTS = [
    ("analyses_pkey", "jobs_pkey"),
    ("analyses_user_id_fkey", "jobs_user_id_fkey"),
    ("analyses_plan_id_fkey", "jobs_plan_id_fkey"),
]

SEQUENCES = [
    ("analyses_id_seq", "jobs_id_seq"),
]


def upgrade():
    op.rename_table("analyses", "jobs")

    for old, new in INDEXES:
        op.execute(f'ALTER INDEX {old} RENAME TO {new}')

    for old, new in CONSTRAINTS:
        op.execute(f'ALTER TABLE jobs RENAME CONSTRAINT {old} TO {new}')

    for old, new in SEQUENCES:
        op.execute(f'ALTER SEQUENCE {old} RENAME TO {new}')

    op.add_column("jobs", sa.Column("type", sa.String(length=30), nullable=True))
    op.execute("UPDATE jobs SET type = 'plan_review' WHERE type IS NULL")
    op.alter_column("jobs", "type", nullable=False)
    op.create_index(op.f("ix_jobs_type"), "jobs", ["type"], unique=False)

    # `user_id` no tenía índice y ahora sí: `GET /jobs` filtra siempre por él, y
    # sin índice cada consulta recorrería la tabla entera de todos los usuarios.
    op.create_index(op.f("ix_jobs_user_id"), "jobs", ["user_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_jobs_user_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_type"), table_name="jobs")
    op.drop_column("jobs", "type")

    for old, new in SEQUENCES:
        op.execute(f'ALTER SEQUENCE {new} RENAME TO {old}')

    for old, new in CONSTRAINTS:
        op.execute(f'ALTER TABLE jobs RENAME CONSTRAINT {new} TO {old}')

    for old, new in INDEXES:
        op.execute(f'ALTER INDEX {new} RENAME TO {old}')

    op.rename_table("jobs", "analyses")
