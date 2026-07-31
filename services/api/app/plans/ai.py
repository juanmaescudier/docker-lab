"""Preparación del `input` de los trabajos que hablan con el modelo.

**La API deja el trabajo preparado; el worker solo compone y escribe.** Todo lo
que sale de la base de datos —el perfil, el catálogo, el resumen nutricional— se
resuelve aquí, en milisegundos y con el ORM a mano. Al worker le llega un JSON
cerrado y no necesita conocer el esquema para armar el prompt.

Esto es lo que hace realista la regla 3.10: **la IA compone, el catálogo aporta
los números**. Los alimentos viajan con su identificador y su nombre, sin valores
nutricionales, porque el modelo no tiene que dar cifras: tiene que elegir de una
lista. Los valores se leen después de la tabla.
"""
from ..catalog.models import EXCLUDED_CATEGORIES_BY_PREFERENCE, Food
from . import nutrition

# Techo del catálogo que viaja en el prompt. La semilla son unas decenas de
# alimentos, pero importar de USDA puede engordar la tabla sin límite y un
# prompt con miles de líneas cuesta dinero y empeora la elección del modelo.
MAX_CATALOG_FOODS = 300


def available_foods(allergens=(), excluded_ids=(), food_preference=None):
    """Los alimentos entre los que puede elegir el modelo, ordenados por categoría.

    Ordenados por categoría y no por identificador para que el modelo vea juntas
    las opciones comparables (todas las carnes seguidas) en lugar de saltando.

    **Lo que no puede comer se quita de la lista, no se le pide que lo evite.** Es
    el mismo principio que con los `food_id` inventados (3.10): no se confía en
    que se porte bien, se le quita la posibilidad. Un vegano no recibe 400 carnes
    para que el modelo tenga el detalle de no usarlas.

    Con las alergias eso además es una decisión de seguridad (3.17): poner "soy
    alérgico a los frutos secos" en un JSON que le llega como prosa es fiar la
    salud de una persona a que no se despiste, y "casi siempre acierta" con una
    alergia no vale.

    **Y el filtro de alergias falla hacia el lado seguro.** Un alimento con
    `allergens` a nulo no es un alimento sin alérgenos: es uno que nadie ha
    revisado. Con alergias declaradas, esos también se quedan fuera. Prefiero un
    plan con menos opciones que uno con cacahuetes para un alérgico.
    """
    query = Food.query

    if allergens:
        query = query.filter(
            Food.allergens.isnot(None),
            ~Food.allergens.overlap(list(allergens)),
        )

    if excluded_ids:
        query = query.filter(Food.id.notin_(list(excluded_ids)))

    forbidden = EXCLUDED_CATEGORIES_BY_PREFERENCE.get(food_preference)
    if forbidden:
        # Los de categoría nula no se tocan: no se sabe qué son, y quitarlos
        # castigaría al vegano por un dato que falta en el catálogo, no en su
        # perfil. Con una alergia la duda se resuelve al revés porque lo que hay
        # en juego es distinto.
        query = query.filter(
            Food.category.is_(None) | Food.category.notin_(forbidden)
        )

    # El recorte va DESPUÉS de filtrar, no antes: al revés se cogerían 300
    # alimentos y se dejarían en 200 al quitar los que llevan leche, que es
    # perder opciones sin motivo.
    foods = (
        query
        .order_by(Food.category.asc().nulls_last(), Food.name.asc())
        .limit(MAX_CATALOG_FOODS)
        .all()
    )
    return [
        {
            "id": food.id,
            "name": food.name,
            "category": food.category,
            "state": food.state,
        }
        for food in foods
    ]


def build_generation_input(user):
    """`input` de un trabajo `plan_generation`.

    El catálogo se filtra **antes** de armar la lista, no después: lo que el
    usuario no puede o no quiere comer no llega a estar entre las opciones.
    """
    return {
        "profile": user.ai_profile(),
        "foods": available_foods(
            allergens=user.allergen_values(),
            excluded_ids=user.excluded_food_ids(),
            food_preference=user.food_preference,
        ),
    }


def build_review_input(user, plan):
    """`input` de un trabajo `plan_review`.

    Lleva el resumen nutricional **ya calculado**: el worker no vuelve a sumar
    nada. Su trabajo es pedirle al modelo una segunda opinión sobre unos números
    que ya son correctos, no producirlos.
    """
    return {
        "plan_id": plan.id,
        "plan_name": plan.name,
        "profile": user.ai_profile(),
        "nutrition": nutrition.summarize(plan),
    }
