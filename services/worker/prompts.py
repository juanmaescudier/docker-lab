"""Redacción de los prompts y del esquema de la respuesta.

Un sitio y solo uno donde está escrito **qué se le pide al modelo**, **qué forma
tiene que tener la respuesta** y **cómo es una respuesta válida de ejemplo**
(`stub_response`). Los tres juntos porque los tres cambian a la vez: tocar el
esquema sin tocar el ejemplo dejaría el stub devolviendo algo que ya no vale.

La regla que gobierna todo esto es la 3.10 del diseño: **la IA compone, el
catálogo aporta los números**. Por eso los alimentos viajan con su identificador
y su nombre pero **sin valores nutricionales**: el modelo no tiene que estimar
calorías, tiene que elegir de una lista. Los números se leen después de la tabla.
"""
import json

from domain import COOKING_METHODS, DAYS_OF_WEEK, MEAL_SLOTS, slots_for
from llm.base import Prompt

# Techo de recetas distintas que se le piden. Una semana entera con receta nueva
# en cada comida serían 35, y eso es una respuesta enorme, cara y poco realista:
# nadie cocina 35 platos distintos a la semana. Se reutilizan.
MAX_RECIPES = 14
MIN_RECIPES = 5


# ---------------------------------------------------------------- generación

PLAN_SYSTEM = """\
Eres un nutricionista que compone planes semanales de comidas.

Reglas que no puedes saltarte:

1. SOLO puedes usar alimentos de la lista que te doy, referenciados por su `id`.
   Si un alimento no está en la lista, NO existe: no lo inventes ni lo cites por
   su nombre. Un `food_id` que no esté en la lista invalida el plan entero.
2. NO des valores nutricionales (calorías, proteínas, grasas). No es tu trabajo:
   esos números salen de la base de datos. Tú decides QUÉ y CUÁNTO.
3. Las cantidades van en GRAMOS y SIEMPRE EN CRUDO, que es como se compra y como
   está medido el catálogo. 100 g de arroz crudo no son 100 g de arroz cocido.
4. Respeta la preferencia alimentaria del perfil. Si es `vegetarian` no uses
   carne ni pescado; si es `vegan`, tampoco huevos, lácteos ni miel.
5. Ajusta las cantidades al objetivo del perfil (`lose_fat`, `maintain`,
   `gain_muscle`), a su peso, su altura, su edad y su nivel de actividad.
6. Repite recetas a lo largo de la semana: nadie cocina un plato distinto en cada
   comida. Define entre {min_recipes} y {max_recipes} recetas y reutilízalas.
7. Responde ÚNICAMENTE con el objeto JSON del esquema. Sin texto alrededor, sin
   explicaciones y sin bloques de código.

Escribe los nombres de las recetas, los pasos y las notas en español.\
"""

PLAN_USER = """\
Perfil del usuario:
{profile}

Alimentos disponibles (elige solo de aquí, por `id`):
{foods}

Compón un plan semanal completo: los siete días, y en cada día estos momentos:
{slots}.

Cada comida referencia una receta por su `recipe_ref`, que tiene que coincidir
con el `ref` de una de las recetas que definas.\
"""

# Cada campo del esquema es obligatorio y `additionalProperties` va a false: es
# lo que exige el modo estricto de la salida estructurada, y además deja fuera
# los campos de más que un modelo suele añadir por su cuenta.
INGREDIENT_SCHEMA = {
    "type": "object",
    "properties": {
        "food_id": {
            "type": "integer",
            "description": "id de un alimento de la lista dada. Nada más vale.",
        },
        "grams": {
            "type": "number",
            "description": "Gramos EN CRUDO para el total de raciones de la receta.",
        },
    },
    "required": ["food_id", "grams"],
    "additionalProperties": False,
}

RECIPE_SCHEMA = {
    "type": "object",
    "properties": {
        "ref": {
            "type": "string",
            "description": "Identificador corto y único dentro de esta respuesta.",
        },
        "name": {"type": "string"},
        "cooking_method": {"type": "string", "enum": list(COOKING_METHODS)},
        "servings": {
            "type": "integer",
            "description": "Raciones que rinde la receta con esas cantidades.",
        },
        "steps": {"type": "string", "description": "Elaboración, en español."},
        "ingredients": {
            "type": "array",
            "items": INGREDIENT_SCHEMA,
            "minItems": 1,
        },
    },
    "required": ["ref", "name", "cooking_method", "servings", "steps", "ingredients"],
    "additionalProperties": False,
}

MEAL_SCHEMA = {
    "type": "object",
    "properties": {
        "day_of_week": {"type": "string", "enum": list(DAYS_OF_WEEK)},
        "meal_slot": {"type": "string", "enum": list(MEAL_SLOTS)},
        "recipe_ref": {"type": "string"},
        "servings": {
            "type": "number",
            "description": "Raciones que se come en esa comida.",
        },
    },
    "required": ["day_of_week", "meal_slot", "recipe_ref", "servings"],
    "additionalProperties": False,
}

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "plan_name": {"type": "string"},
        "daily_kcal_target": {
            "type": "number",
            "description": (
                "Necesidad diaria estimada, en kcal. Es una ORIENTACIÓN del "
                "modelo: los totales reales se calculan desde el catálogo."
            ),
        },
        "notes": {"type": "string"},
        "recipes": {"type": "array", "items": RECIPE_SCHEMA, "minItems": 1},
        "meals": {"type": "array", "items": MEAL_SCHEMA, "minItems": 1},
    },
    "required": ["plan_name", "daily_kcal_target", "notes", "recipes", "meals"],
    "additionalProperties": False,
}


def _format_foods(foods):
    """Una línea por alimento: `id · nombre (categoría, estado)`.

    En líneas y no en JSON porque ocupa la mitad de tokens para la misma
    información, y el modelo lo lee igual de bien.
    """
    lines = []
    for food in foods:
        detail = ", ".join(
            part for part in (food.get("category"), food.get("state")) if part
        )
        lines.append(
            f"{food['id']} · {food['name']}" + (f" ({detail})" if detail else "")
        )
    return "\n".join(lines)


def _stub_plan(job_input):
    """Un plan fijo y válido construido con los alimentos que haya de verdad.

    No puede ser una constante: los identificadores del catálogo cambian en cada
    despliegue, y un `food_id` inventado lo rechazaría el propio validador. Se
    toman los primeros alimentos de la lista que la API ha mandado.
    """
    foods = job_input.get("foods") or []
    slots = slots_for((job_input.get("profile") or {}).get("meals_per_day"))

    # Se reparten en grupos para que cada receta lleve ingredientes distintos:
    # el mismo alimento dos veces en una receta lo rechaza la base de datos.
    recipes = []
    for index, slot in enumerate(slots):
        chunk = foods[index * 2:index * 2 + 2] or foods[:2]
        recipes.append({
            "ref": f"r{index + 1}",
            "name": f"Plato de prueba {index + 1}",
            "cooking_method": "boiled",
            "servings": 1,
            "steps": "Receta de ejemplo generada por el proveedor de prueba.",
            "ingredients": [
                {"food_id": food["id"], "grams": 100.0} for food in chunk
            ],
        })

    meals = [
        {
            "day_of_week": day,
            "meal_slot": slot,
            "recipe_ref": recipes[index]["ref"],
            "servings": 1.0,
        }
        for day in DAYS_OF_WEEK
        for index, slot in enumerate(slots)
    ]

    return {
        "plan_name": "Plan de prueba (proveedor stub)",
        "daily_kcal_target": 2000,
        "notes": "Plan de ejemplo: no ha intervenido ningún modelo de lenguaje.",
        "recipes": recipes,
        "meals": meals,
    }


def plan_generation(job_input):
    """Prompt del trabajo `plan_generation`."""
    profile = job_input.get("profile") or {}
    foods = job_input.get("foods") or []
    slots = slots_for(profile.get("meals_per_day"))

    return Prompt(
        system=PLAN_SYSTEM.format(min_recipes=MIN_RECIPES, max_recipes=MAX_RECIPES),
        user=PLAN_USER.format(
            profile=json.dumps(profile, ensure_ascii=False, indent=2),
            foods=_format_foods(foods),
            slots=", ".join(slots),
        ),
        schema=PLAN_SCHEMA,
        name="weekly_plan",
        stub_response=_stub_plan(job_input),
    )


# ----------------------------------------------------------------- revisión

REVIEW_SYSTEM = """\
Eres un nutricionista que da una segunda opinión sobre un plan que ha montado el
propio usuario a mano.

Reglas que no puedes saltarte:

1. Los números nutricionales que te doy ya están calculados desde una base de
   datos de alimentos: son correctos. NO los recalcules ni los corrijas.
2. Valora si el plan encaja con el perfil y el objetivo del usuario, y di qué
   ajustarías. Concreto y accionable, no genérico.
3. Fíjate en el reparto por días, no solo en el total de la semana: un plan puede
   cuadrar en la semana y tener un lunes de 3.500 kcal y un domingo de 900.
4. Si te aviso de nutrientes incompletos, no los trates como ceros: son datos que
   faltan en el catálogo.
5. Responde ÚNICAMENTE con el objeto JSON del esquema, en español.\
"""

REVIEW_USER = """\
Perfil del usuario:
{profile}

Plan «{plan_name}» y su resumen nutricional (cantidades en crudo):
{nutrition}\
"""

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["fits", "needs_adjustment", "does_not_fit"],
            "description": "Encaje del plan con el perfil y el objetivo.",
        },
        "summary": {
            "type": "string",
            "description": "Valoración en dos o tres frases, en español.",
        },
        "adjustments": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Cambios concretos que harías, uno por elemento.",
        },
        "estimated_daily_kcal": {
            "type": "number",
            "description": "Necesidad diaria estimada del usuario, en kcal.",
        },
    },
    "required": ["verdict", "summary", "adjustments", "estimated_daily_kcal"],
    "additionalProperties": False,
}

STUB_REVIEW = {
    "verdict": "needs_adjustment",
    "summary": (
        "Revisión de ejemplo generada por el proveedor de prueba: no ha "
        "intervenido ningún modelo de lenguaje."
    ),
    "adjustments": ["Configura LLM_PROVIDER=openrouter para una revisión real."],
    "estimated_daily_kcal": 2000,
}


def plan_review(job_input):
    """Prompt del trabajo `plan_review`.

    El resumen nutricional llega **ya calculado** dentro del `input`: lo hizo la
    API desde el catálogo. El worker no vuelve a sumar nada (3.10).
    """
    return Prompt(
        system=REVIEW_SYSTEM,
        user=REVIEW_USER.format(
            profile=json.dumps(
                job_input.get("profile") or {}, ensure_ascii=False, indent=2
            ),
            plan_name=job_input.get("plan_name") or "sin nombre",
            nutrition=json.dumps(
                job_input.get("nutrition") or {}, ensure_ascii=False, indent=2
            ),
        ),
        schema=REVIEW_SCHEMA,
        name="plan_review",
        stub_response=STUB_REVIEW,
    )
