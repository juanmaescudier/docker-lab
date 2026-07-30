"""Resumen nutricional de un plan completo.

Calculado, nunca guardado, por el mismo motivo que la lista de la compra (3.6):
si se persistiera, cambiar una comida dejaría dos versiones de la verdad.

Este módulo es **de la API a propósito**. Sumar los nutrientes de un plan son
microsegundos y los números salen del catálogo, así que no tiene nada que hacer
en una cola: el worker recibe este resumen ya calculado dentro del `input` del
trabajo y no lo recalcula (3.10).
"""
from ..catalog.models import NUTRITION_FIELDS
from .models import DAYS_OF_WEEK, MEAL_SLOTS


def _empty_totals():
    # None y no 0.0: un nutriente sin ningún dato es "no lo sabemos", que no es
    # lo mismo que cero.
    return {field: None for field in NUTRITION_FIELDS}


def _add(totals, food, grams, incomplete):
    """Suma un ingrediente a un acumulador: valor_por_100g × gramos ÷ 100."""
    factor = grams / 100
    for field in NUTRITION_FIELDS:
        value = getattr(food, field)
        if value is None:
            # Un nulo del catálogo no se suma como 0: daría un total
            # falsamente preciso. Se anota y se avisa en la salida.
            incomplete.add(field)
            continue
        totals[field] = (totals[field] or 0.0) + value * factor


def _rounded(totals, divisor=1):
    return {
        field: (round(value / divisor, 2) if value is not None else None)
        for field, value in totals.items()
    }


def summarize(plan):
    """Devuelve los totales de la semana, la media diaria y el desglose por día.

    El desglose por día es lo que hace útil la revisión: un plan puede cuadrar de
    calorías en la semana y tener un lunes de 3.500 kcal y un domingo de 900.
    """
    weekly = _empty_totals()
    incomplete = set()
    per_day = {day: _empty_totals() for day in DAYS_OF_WEEK}
    meals_per_day = {day: [] for day in DAYS_OF_WEEK}

    for meal in plan.meals:
        recipe = meal.recipe
        if recipe is None:
            continue

        # Los ingredientes son para `recipe.servings` raciones y de esta comida
        # se comen `meal.servings`. Sin el factor, una receta que rinde 4 y de la
        # que se come 1 contaría cuatro veces de más.
        factor = meal.servings / (recipe.servings or 1)
        day = meal.day_of_week if meal.day_of_week in per_day else None

        for ingredient in recipe.ingredients:
            if ingredient.food is None:
                continue
            grams = ingredient.grams * factor
            _add(weekly, ingredient.food, grams, incomplete)
            if day is not None:
                _add(per_day[day], ingredient.food, grams, incomplete)

        if day is not None:
            meals_per_day[day].append({
                "meal_slot": meal.meal_slot,
                "recipe": recipe.name,
                "servings": meal.servings,
            })

    days_with_meals = [day for day in DAYS_OF_WEEK if meals_per_day[day]]

    return {
        "weekly_totals": _rounded(weekly),
        # Se divide entre los días que tienen comidas, no siempre entre siete: un
        # plan de cinco días daría una media diaria un 30 % baja.
        "daily_average": _rounded(weekly, len(days_with_meals) or 1),
        "days_planned": len(days_with_meals),
        "by_day": [
            {
                "day_of_week": day,
                "totals": _rounded(per_day[day]),
                "meals": sorted(
                    meals_per_day[day],
                    key=lambda m: MEAL_SLOTS.index(m["meal_slot"])
                    if m["meal_slot"] in MEAL_SLOTS else 99,
                ),
            }
            for day in days_with_meals
        ],
        # Sin esto, "0 g de fibra" y "no sabemos la fibra" se verían igual.
        "incomplete_nutrients": sorted(incomplete),
        # Las cantidades son EN CRUDO y hay que decirlo en cada sitio donde
        # aparezcan: no puede quedar implícito (3.2).
        "note": "Cantidades en crudo.",
    }
