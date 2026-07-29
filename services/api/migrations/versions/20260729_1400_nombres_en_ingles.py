"""Nombres de tablas, columnas y valores de lista cerrada en inglés.

**Renombrado puro: ni un DROP ni un ADD.** `ALTER TABLE ... RENAME` conserva los
datos, las claves ajenas y los índices; un DROP seguido de un ADD vaciaría cada
columna. Por eso esta migración no está autogenerada: Alembic habría propuesto
justo lo segundo, porque no distingue un renombrado de un borrado más un alta.

Se renombran también índices, restricciones y secuencias. PostgreSQL NO los
renombra solo al renombrar la tabla, y si se quedan con el nombre viejo el
siguiente `alembic check` los ve como desviación y propone recrearlos.

Los valores de las listas cerradas también son código (van y vienen de la IA como
identificadores), así que se traducen con una migración de datos. Los NOMBRES y
las CATEGORÍAS de los alimentos NO: son datos, y siguen en español.

Revision ID: c4f1a9b7d2e8
Revises: 8cd6e0e4254b
Create Date: 2026-07-29 14:00:00.000000
"""
from alembic import op

revision = 'c4f1a9b7d2e8'
down_revision = '8cd6e0e4254b'
branch_labels = None
depends_on = None


TABLES = [
    ("alimentos", "foods"),
    ("analisis", "analyses"),
    ("recetas", "recipes"),
    ("ingredientes_receta", "recipe_ingredients"),
    ("planes", "plans"),
    ("comidas_planificadas", "planned_meals"),
]

# Indexadas por el nombre NUEVO de la tabla: las columnas se renombran después
# de las tablas. `users` no cambia de nombre, solo de columnas.
COLUMNS = {
    "foods": [
        ("nombre", "name"),
        ("nombre_normalizado", "normalized_name"),
        ("categoria", "category"),
        ("estado", "state"),
        ("energia_kcal", "energy_kcal"),
        ("grasas_g", "fat_g"),
        ("grasas_saturadas_g", "saturated_fat_g"),
        ("hidratos_g", "carbs_g"),
        ("azucares_g", "sugars_g"),
        ("fibra_g", "fiber_g"),
        ("proteinas_g", "protein_g"),
        ("sal_g", "salt_g"),
        ("nutrientes_extra", "extra_nutrients"),
        ("origen", "source"),
        ("id_externo", "external_id"),
        ("nombre_externo", "external_name"),
        ("creado_en", "created_at"),
        ("actualizado_en", "updated_at"),
    ],
    "users": [
        ("nombre", "name"),
        ("sexo", "sex"),
        ("fecha_nacimiento", "birth_date"),
        ("altura_cm", "height_cm"),
        ("peso_kg", "weight_kg"),
        ("nivel_actividad", "activity_level"),
        ("objetivo", "goal"),
        ("comidas_por_dia", "meals_per_day"),
        ("preferencia_alimentaria", "food_preference"),
        ("composicion_corporal", "body_composition"),
        ("perimetro_cintura_cm", "waist_cm"),
        ("perimetro_cadera_cm", "hip_cm"),
        ("perimetro_cuello_cm", "neck_cm"),
    ],
    "analyses": [
        ("estado", "state"),
        ("entrada", "input"),
        ("resultado", "result"),
        ("intentos", "attempts"),
        ("creado_en", "created_at"),
        ("actualizado_en", "updated_at"),
    ],
    "recipes": [
        ("nombre", "name"),
        ("pasos", "steps"),
        ("metodo_coccion", "cooking_method"),
        ("raciones", "servings"),
        ("origen", "source"),
        ("creado_en", "created_at"),
        ("actualizado_en", "updated_at"),
    ],
    "recipe_ingredients": [
        ("receta_id", "recipe_id"),
        ("alimento_id", "food_id"),
        ("gramos", "grams"),
    ],
    "plans": [
        ("nombre", "name"),
        ("activo", "active"),
        ("origen", "source"),
        ("creado_en", "created_at"),
        ("actualizado_en", "updated_at"),
    ],
    "planned_meals": [
        ("dia_semana", "day_of_week"),
        ("momento", "meal_slot"),
        ("receta_id", "recipe_id"),
        ("raciones", "servings"),
    ],
}

INDEXES = [
    ("ix_alimentos_categoria", "ix_foods_category"),
    ("ix_alimentos_id_externo_unico", "ix_foods_external_id_unique"),
    ("ix_alimentos_nombre", "ix_foods_name"),
    ("ix_alimentos_nombre_normalizado", "ix_foods_normalized_name"),
    ("ix_alimentos_origen", "ix_foods_source"),
    ("ix_analisis_estado", "ix_analyses_state"),
    ("ix_analisis_plan_id", "ix_analyses_plan_id"),
    ("ix_recetas_nombre", "ix_recipes_name"),
    ("ix_recetas_user_id", "ix_recipes_user_id"),
    ("ix_ingredientes_receta_receta_id", "ix_recipe_ingredients_recipe_id"),
    ("ix_planes_user_id", "ix_plans_user_id"),
    ("uq_plan_activo_por_usuario", "uq_active_plan_per_user"),
    ("ix_comidas_planificadas_plan_id", "ix_planned_meals_plan_id"),
]

# (tabla ya renombrada, nombre viejo, nombre nuevo)
CONSTRAINTS = [
    ("foods", "alimentos_pkey", "foods_pkey"),
    ("analyses", "analisis_pkey", "analyses_pkey"),
    ("analyses", "analisis_user_id_fkey", "analyses_user_id_fkey"),
    ("analyses", "analisis_plan_id_fkey", "analyses_plan_id_fkey"),
    ("recipes", "recetas_pkey", "recipes_pkey"),
    ("recipes", "recetas_user_id_fkey", "recipes_user_id_fkey"),
    ("recipes", "ck_recetas_raciones_positivas", "ck_recipes_servings_positive"),
    ("recipe_ingredients", "ingredientes_receta_pkey", "recipe_ingredients_pkey"),
    ("recipe_ingredients", "ingredientes_receta_receta_id_fkey",
     "recipe_ingredients_recipe_id_fkey"),
    ("recipe_ingredients", "ingredientes_receta_alimento_id_fkey",
     "recipe_ingredients_food_id_fkey"),
    ("recipe_ingredients", "ck_ingredientes_gramos_positivos",
     "ck_recipe_ingredients_grams_positive"),
    ("recipe_ingredients", "uq_ingrediente_por_receta", "uq_ingredient_per_recipe"),
    ("plans", "planes_pkey", "plans_pkey"),
    ("plans", "planes_user_id_fkey", "plans_user_id_fkey"),
    ("planned_meals", "comidas_planificadas_pkey", "planned_meals_pkey"),
    ("planned_meals", "comidas_planificadas_plan_id_fkey", "planned_meals_plan_id_fkey"),
    ("planned_meals", "comidas_planificadas_receta_id_fkey",
     "planned_meals_recipe_id_fkey"),
    ("planned_meals", "ck_comidas_raciones_positivas",
     "ck_planned_meals_servings_positive"),
]

SEQUENCES = [
    ("alimentos_id_seq", "foods_id_seq"),
    ("analisis_id_seq", "analyses_id_seq"),
    ("recetas_id_seq", "recipes_id_seq"),
    ("ingredientes_receta_id_seq", "recipe_ingredients_id_seq"),
    ("planes_id_seq", "plans_id_seq"),
    ("comidas_planificadas_id_seq", "planned_meals_id_seq"),
]

# Valores de lista cerrada, por (tabla ya renombrada, columna ya renombrada).
# `origen` en foods ('seed'/'api'/'manual') ya estaba en inglés y no aparece.
VALUES = {
    ("foods", "state"): {
        "crudo": "raw", "cocinado": "cooked",
        "conserva": "canned", "líquido": "liquid",
    },
    ("users", "sex"): {"hombre": "male", "mujer": "female", "otro": "other"},
    ("users", "goal"): {
        "perder_grasa": "lose_fat", "mantener": "maintain",
        "ganar_musculo": "gain_muscle",
    },
    ("users", "activity_level"): {
        "sedentario": "sedentary", "ligero": "light",
        "moderado": "moderate", "alto": "high",
    },
    ("users", "food_preference"): {
        "omnivoro": "omnivore", "vegetariano": "vegetarian", "vegano": "vegan",
    },
    ("users", "body_composition"): {
        "delgado": "lean", "normal": "average",
        "atletico": "athletic", "sobrepeso": "overweight",
    },
    ("recipes", "cooking_method"): {
        "crudo": "raw", "hervido": "boiled", "vapor": "steamed",
        "microondas": "microwaved", "plancha": "griddled", "salteado": "sauteed",
        "horno": "baked", "freidora_aire": "air_fried", "frito": "fried",
        "guisado": "stewed",
    },
    ("recipes", "source"): {"ia": "ai"},
    ("plans", "source"): {"ia": "ai"},
    ("planned_meals", "day_of_week"): {
        "lunes": "monday", "martes": "tuesday", "miercoles": "wednesday",
        "jueves": "thursday", "viernes": "friday", "sabado": "saturday",
        "domingo": "sunday",
    },
    ("planned_meals", "meal_slot"): {
        "desayuno": "breakfast", "media_manana": "mid_morning", "comida": "lunch",
        "merienda": "afternoon_snack", "cena": "dinner",
    },
    ("analyses", "state"): {
        "pendiente": "pending", "procesando": "processing",
        "completado": "completed", "fallido": "failed",
    },
}


def _translate_values(mapping, reverse=False):
    """Traduce los valores de lista cerrada con un CASE.

    El `ELSE` deja intacto lo que no reconozca: una migración de datos no debe
    borrar valores que no esperaba, solo traducir los que sí.
    """
    for (table, column), pairs in mapping.items():
        if reverse:
            pairs = {v: k for k, v in pairs.items()}
        whens = " ".join(
            f"WHEN '{old}' THEN '{new}'" for old, new in pairs.items()
        )
        op.execute(
            f"UPDATE {table} SET {column} = CASE {column} {whens} ELSE {column} END "
            f"WHERE {column} IS NOT NULL"
        )


def _translate_input_json(old_key, new_key, old_name, new_name, old_grams, new_grams):
    """Renombra las claves del JSON de entrada de los análisis.

    El worker lee `input->'foods'` para reprocesar un trabajo fallido, así que si
    la clave se quedara en español el reintento no encontraría nada. El CASE por
    `jsonb_typeof` respeta los elementos que sean cadenas sueltas, que el worker
    también admite.

    `result` NO se traduce: es la salida de una ejecución pasada, no la lee nadie
    y el worker la sobrescribe entera si el análisis se vuelve a ejecutar.
    """
    op.execute(f"""
        UPDATE analyses
           SET input = (
                 (input::jsonb - '{old_key}')
                 || jsonb_build_object('{new_key}', COALESCE((
                      SELECT jsonb_agg(
                          CASE WHEN jsonb_typeof(elem) = 'object'
                               THEN (elem - '{old_name}' - '{old_grams}')
                                    || jsonb_strip_nulls(jsonb_build_object(
                                           '{new_name}', elem -> '{old_name}',
                                           '{new_grams}', elem -> '{old_grams}'))
                               ELSE elem END)
                        FROM jsonb_array_elements(input::jsonb -> '{old_key}') AS elem
                 ), '[]'::jsonb))
               )::text::json
         WHERE input IS NOT NULL AND input::jsonb ? '{old_key}'
    """)


def upgrade():
    for old, new in TABLES:
        op.rename_table(old, new)

    for table, columns in COLUMNS.items():
        for old, new in columns:
            op.alter_column(table, old, new_column_name=new)

    for old, new in INDEXES:
        op.execute(f'ALTER INDEX {old} RENAME TO {new}')

    for table, old, new in CONSTRAINTS:
        op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT {old} TO {new}')

    for old, new in SEQUENCES:
        op.execute(f'ALTER SEQUENCE {old} RENAME TO {new}')

    _translate_values(VALUES)
    _translate_input_json("alimentos", "foods", "nombre", "name", "gramos", "grams")


def downgrade():
    _translate_input_json("foods", "alimentos", "name", "nombre", "grams", "gramos")
    _translate_values(VALUES, reverse=True)

    for old, new in SEQUENCES:
        op.execute(f'ALTER SEQUENCE {new} RENAME TO {old}')

    for table, old, new in CONSTRAINTS:
        op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT {new} TO {old}')

    for old, new in INDEXES:
        op.execute(f'ALTER INDEX {new} RENAME TO {old}')

    for table, columns in COLUMNS.items():
        for old, new in columns:
            op.alter_column(table, new, new_column_name=old)

    for old, new in TABLES:
        op.rename_table(new, old)
