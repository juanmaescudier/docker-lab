"""Las respuestas del cuestionario inicial.

**El cuestionario no es un dominio** (3.15): si se borra, las respuestas siguen
significando algo; si se borran las respuestas, el cuestionario no tiene nada que
hacer. El concepto son las preferencias del usuario, y el asistente inicial y la
pantalla de ajustes son dos formas de editar lo mismo. Por eso aquí no hay tabla
de preguntas ni de respuestas: hay columnas de `users` y tres relaciones.

Dónde vive cada respuesta lo decide una sola pregunta (3.16): **¿hay código
Python que decida algo mirando ese valor?**

- **Columna** si necesita tipo, restricción y poder aparecer en un `WHERE`:
  `goal_pace`, `training_type`, `training_days_per_week` y las dos fechas.
- **Relación propia** si gobierna una consulta: alergias, intolerancias y
  alimentos vetados son los que quitan filas del catálogo antes de que el modelo
  lo vea.
- **JSON** si solo acaba convertido en palabras dentro del prompt: todo lo demás.
  Y va en JSON precisamente porque es lo que evoluciona: voy a añadir y quitar
  preguntas cada semana mientras afino el prompt, y si cada una cuesta una
  migración acabaré por no añadirlas.

Dos cosas que conviene mirar dos veces:

**`screening_passed_at` guarda que pasó el cribado y cuándo, jamás qué declaró**
(3.18). "Este usuario tiene diabetes" es un dato de salud de categoría especial
que no hace falta para nada: la única decisión que depende de él —seguir o no
seguir— ya está tomada cuando se escribe esta fecha. No hay columna donde
guardarlo, y es a propósito.

**Fechas anulables en vez de booleanos**, aquí y en `onboarded_at`: dicen si pasó
y además cuándo, gratis.

Las alergias y las intolerancias llevan su lista cerrada en un `CHECK` de la base
de datos y no solo en la validación de Python. Son datos de seguridad: no pueden
depender de que todos los caminos de escritura se acuerden de comprobarlo.

`preferences` se crea con `'{}'` por defecto y NOT NULL para que nadie tenga que
distinguir entre "sin preferencias" y "nulo", que serían lo mismo con dos formas.

Revision ID: c9a4e18b5f72
Revises: b8f3c2d17e40
Create Date: 2026-07-31 11:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'c9a4e18b5f72'
down_revision = 'b8f3c2d17e40'
branch_labels = None
depends_on = None


# Las listas cerradas, copiadas y no importadas: una migración tiene que seguir
# corriendo igual dentro de un año, cuando la aplicación ya use otras.
ALLERGENS = (
    "gluten", "crustaceans", "eggs", "fish", "peanuts", "soy", "milk", "nuts",
    "celery", "mustard", "sesame", "sulphites", "lupin", "molluscs",
)
INTOLERANCES = ("lactose", "gluten_non_celiac", "fructose", "sorbitol", "histamine")
TOLERANCE_LEVELS = ("none", "small", "moderate")


def _in_list(column, values):
    return column + " IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade():
    op.add_column("users", sa.Column("goal_pace", sa.String(length=20), nullable=True))
    op.add_column(
        "users", sa.Column("training_type", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "users", sa.Column("training_days_per_week", sa.Integer(), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("screening_passed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users", sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True)
    )

    # En tres pasos, como toda columna NOT NULL sobre una tabla con filas: se
    # añade con valor por defecto, se rellenan las que había y se cierra.
    op.add_column(
        "users",
        sa.Column("preferences", sa.JSON(), nullable=True, server_default="{}"),
    )
    op.execute("UPDATE users SET preferences = '{}' WHERE preferences IS NULL")
    op.alter_column("users", "preferences", nullable=False)

    op.create_table(
        "user_allergens",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("allergen", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            _in_list("allergen", ALLERGENS), name="ck_user_allergens_closed_list"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "allergen"),
    )

    op.create_table(
        "user_intolerances",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("intolerance", sa.String(length=30), nullable=False),
        sa.Column("tolerance", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            _in_list("intolerance", INTOLERANCES),
            name="ck_user_intolerances_closed_list",
        ),
        sa.CheckConstraint(
            _in_list("tolerance", TOLERANCE_LEVELS),
            name="ck_user_intolerances_tolerance_level",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "intolerance"),
    )

    # CASCADE por los dos lados: si desaparece el alimento, el veto deja de tener
    # sentido; si desaparece la cuenta, se va con ella.
    op.create_table(
        "user_excluded_foods",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("food_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["food_id"], ["foods.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "food_id"),
    )


def downgrade():
    op.drop_table("user_excluded_foods")
    op.drop_table("user_intolerances")
    op.drop_table("user_allergens")
    op.drop_column("users", "preferences")
    op.drop_column("users", "onboarded_at")
    op.drop_column("users", "screening_passed_at")
    op.drop_column("users", "training_days_per_week")
    op.drop_column("users", "training_type")
    op.drop_column("users", "goal_pace")
