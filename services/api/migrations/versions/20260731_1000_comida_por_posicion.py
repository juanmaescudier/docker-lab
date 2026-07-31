"""Una comida se identifica por su posición dentro del día, no por un nombre.

`planned_meals.meal_slot` era un valor de una lista cerrada de cinco —desayuno,
media mañana, comida, merienda y cena— y esa lista no se sostiene (3.16): hay
quien come ocho veces al día y ahí no hay cinco casillas que marcar. Ampliarla a
ocho nombres solo mueve el problema al noveno.

Lo estable son **tres anclas —desayuno, comida y cena— y N comidas repartidas
entre ellas**, así que lo que identifica una comida dentro del día es su
POSICIÓN. La etiqueta se conserva, pero como texto descriptivo para la pantalla:
la escribe quien compone el plan y no es clave de nada.

**La conversión reordena, no traduce uno a uno.** Un plan de tres comidas tenía
`breakfast`, `lunch` y `dinner`, que en la lista vieja ocupaban las casillas 1, 3
y 5; como posiciones tienen que ser 1, 2 y 3. Por eso el relleno va con un
`ROW_NUMBER()` sobre el orden de la lista antigua y no con un `CASE` de cinco
ramas: lo que importa es el orden dentro del día, no en qué casilla estaba.

El índice único nuevo `(plan_id, day_of_week, position)` no existía antes en
ninguna forma: la tabla admitía dos cenas el mismo martes y solo lo impedía la
validación. Ahora lo impide la base de datos.

**Lo que se pierde al bajar:** las posiciones por encima de la quinta no caben en
la lista de cinco nombres y se recortan a `dinner`, así que un plan de ocho
comidas al día vuelve con cuatro cenas. No hay forma de evitarlo —la información
no cabe en el esquema antiguo— y es justamente el caso que motiva esta migración.
La etiqueta también se pierde: en el esquema viejo no hay dónde ponerla.

Revision ID: e5b2f7c1a3d9
Revises: a1e7c3d9b504
Create Date: 2026-07-31 10:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = 'e5b2f7c1a3d9'
down_revision = 'a1e7c3d9b504'
branch_labels = None
depends_on = None


# La lista cerrada que desaparece. Se escribe aquí y no se importa de la
# aplicación a propósito: una migración tiene que seguir corriendo igual dentro
# de un año, cuando en el código ya no quede ni rastro de estos cinco valores.
OLD_SLOTS = ("breakfast", "mid_morning", "lunch", "afternoon_snack", "dinner")

OLD_SLOT_LABELS = {
    "breakfast": "Desayuno",
    "mid_morning": "Media mañana",
    "lunch": "Comida",
    "afternoon_snack": "Merienda",
    "dinner": "Cena",
}


def upgrade():
    op.add_column("planned_meals", sa.Column("position", sa.Integer(), nullable=True))
    op.add_column("planned_meals", sa.Column("label", sa.String(length=40), nullable=True))

    # La posición sale del ORDEN dentro del día según la lista vieja, no de la
    # casilla que ocupaba: así un plan de tres comidas queda 1-2-3 y no 1-3-5.
    # El `id` desempata para que el resultado sea estable si dos filas tuvieran
    # el mismo momento, cosa que el esquema antiguo permitía.
    slots = ", ".join(f"'{slot}'" for slot in OLD_SLOTS)
    op.execute(f"""
        UPDATE planned_meals AS m
           SET "position" = ordered.rank
          FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY plan_id, day_of_week
                           ORDER BY array_position(ARRAY[{slots}], meal_slot), id
                       ) AS rank
                  FROM planned_meals
               ) AS ordered
         WHERE m.id = ordered.id
    """)

    # La etiqueta que ya tenían, en español y como texto: es lo que el usuario
    # leía en la parrilla, y perderla al migrar sería empeorar planes que ya
    # estaban bien.
    cases = "\n".join(
        f"WHEN '{slot}' THEN '{label}'" for slot, label in OLD_SLOT_LABELS.items()
    )
    op.execute(f"UPDATE planned_meals SET label = CASE meal_slot {cases} END")

    op.alter_column("planned_meals", "position", nullable=False)

    op.create_check_constraint(
        "ck_planned_meals_position_range", "planned_meals",
        '"position" BETWEEN 1 AND 10',
    )
    op.create_index(
        "uq_meal_position_per_day", "planned_meals",
        ["plan_id", "day_of_week", "position"], unique=True,
    )

    op.drop_column("planned_meals", "meal_slot")


def downgrade():
    op.add_column(
        "planned_meals", sa.Column("meal_slot", sa.String(length=15), nullable=True)
    )

    # Recortando a la quinta casilla: las posiciones de más no caben. Se pierde
    # información y no hay alternativa, está avisado arriba.
    cases = "\n".join(
        f"WHEN {position} THEN '{slot}'"
        for position, slot in enumerate(OLD_SLOTS, start=1)
    )
    op.execute(f"""
        UPDATE planned_meals
           SET meal_slot = CASE LEAST("position", {len(OLD_SLOTS)})
                           {cases}
                           END
    """)

    op.alter_column("planned_meals", "meal_slot", nullable=False)

    op.drop_index("uq_meal_position_per_day", table_name="planned_meals")
    op.drop_constraint(
        "ck_planned_meals_position_range", "planned_meals", type_="check"
    )
    op.drop_column("planned_meals", "label")
    op.drop_column("planned_meals", "position")
