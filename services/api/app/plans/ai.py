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
from ..catalog.models import Food
from . import nutrition

# Techo del catálogo que viaja en el prompt. La semilla son unas decenas de
# alimentos, pero importar de USDA puede engordar la tabla sin límite y un
# prompt con miles de líneas cuesta dinero y empeora la elección del modelo.
MAX_CATALOG_FOODS = 300


def available_foods():
    """Los alimentos entre los que puede elegir el modelo, ordenados por categoría.

    Ordenados por categoría y no por identificador para que el modelo vea juntas
    las opciones comparables (todas las carnes seguidas) en lugar de saltando.
    """
    foods = (
        Food.query
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
    """`input` de un trabajo `plan_generation`."""
    return {
        "profile": user.ai_profile(),
        "foods": available_foods(),
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
