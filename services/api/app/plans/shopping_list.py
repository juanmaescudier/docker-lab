"""Cálculo de la lista de la compra a partir de un plan.

**No es una entidad: se calcula** (decisión 3.6). No hay tabla que mantener y la
lista nunca queda desfasada respecto al plan. Si se guardara y luego cambiara una
comida, habría dos versiones de la verdad y tocaría decidir cuál manda.

Vive en su propio módulo, aislada del resto del dominio, porque está pensada para
**extraerse a su propio microservicio** más adelante (nota de futuro de 3.6).
"""
MIN_WEEKS = 1
MAX_WEEKS = 4

# Cuando un alimento no tiene categoría, va a un cajón propio en vez de
# desaparecer o mezclarse con otro.
UNCATEGORIZED = "sin categoría"


def calculate(plan, weeks):
    """Devuelve los gramos a comprar, agrupados por categoría de alimento.

    Agrupada por categoría porque es como se recorre un supermercado: la carne
    junta, la verdura junta. Una lista ordenada por nombre obligaría a dar
    vueltas por el pasillo.

    Como el plan es una plantilla semanal fija, comprar para tres semanas es
    exactamente tres veces lo mismo: el multiplicador es trivial (3.6).
    """
    accumulated = {}

    for meal in plan.meals:
        recipe = meal.recipe
        if recipe is None:
            continue

        # Los ingredientes de la receta son para `recipe.servings` raciones, y
        # de esa comida se comen `meal.servings`. Sin este factor, una receta
        # que rinde 4 y de la que se come 1 haría comprar cuatro veces de más.
        factor = (meal.servings / (recipe.servings or 1)) * weeks

        for ingredient in recipe.ingredients:
            food = ingredient.food
            if food is None:
                continue

            entry = accumulated.setdefault(food.id, {
                "food_id": food.id,
                "name": food.name,
                "category": food.category or UNCATEGORIZED,
                "grams": 0.0,
            })
            entry["grams"] += ingredient.grams * factor

    # Agrupar al final y no sobre la marcha: primero se suma cada alimento una
    # sola vez y después se reparte por categorías, en vez de buscar el alimento
    # dentro de su categoría en cada iteración.
    by_category = {}
    for entry in accumulated.values():
        entry["grams"] = round(entry["grams"], 2)
        by_category.setdefault(entry["category"], []).append(entry)

    categories = [
        {
            "category": category,
            "foods": sorted(foods, key=lambda f: f["name"]),
        }
        for category, foods in sorted(by_category.items())
    ]

    return {
        "plan_id": plan.id,
        "plan": plan.name,
        "weeks": weeks,
        "categories": categories,
        "total_foods": len(accumulated),
        # Las cantidades son EN CRUDO y hay que decirlo explícitamente en cada
        # sitio donde aparezcan: no puede quedar implícito (3.2).
        "note": "Cantidades en crudo.",
    }
