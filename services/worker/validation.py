"""Validación de lo que devuelve el modelo.

**Nunca se confía en la forma de la respuesta**, ni siquiera con la salida
estructurada activada: OpenRouter documenta que el cumplimiento estricto del
esquema depende del proveedor que acabe atendiendo la petición, y ningún
mecanismo impide que el modelo elija un `food_id` que no existe.

Lo que se comprueba aquí es de dos clases:

- **Forma**: tipos, campos obligatorios, valores de lista cerrada.
- **Coherencia con el catálogo**: que cada `food_id` esté entre los que se le
  ofrecieron, que cada `recipe_ref` resuelva, que no haya el mismo alimento dos
  veces en una receta ni dos comidas en el mismo día y momento.

Lo segundo es lo que hace real la regla 3.10: si propone un alimento que no está,
se rechaza. Y sin lo tercero, la escritura reventaría contra las restricciones
`uq_ingredient_per_recipe` y las claves ajenas, con un error de PostgreSQL en
lugar de uno legible.

Todo fallo se traduce a `LLMSchemaError`, que es reintentable: el modelo es no
determinista y a la segunda suele acertar.
"""
from domain import COOKING_METHODS, DAYS_OF_WEEK, MEAL_SLOTS
from llm.errors import LLMSchemaError
# El rango de recetas es una decisión de producto y vive en `prompts.py`, que es
# donde se le pide al modelo. Aquí se importa en vez de repetirlo para que
# cambiarlo allí surta efecto también en la validación.
from prompts import MAX_RECIPES, MIN_RECIPES

# Topes de cordura. No son reglas de nutrición: son el filtro que evita escribir
# en la base de datos un plan absurdo (una receta de 90 kg de arroz) cuando el
# modelo se despista con las unidades.
MAX_GRAMS_PER_INGREDIENT = 2000
MAX_INGREDIENTS_PER_RECIPE = 20
MAX_MEALS = 70
MAX_SERVINGS = 12

# **No confundir con `prompts.MAX_RECIPES`, que vale 14.** Aquel dice cuántos
# platos distintos tiene sentido que cocine una persona en una semana: es
# producto, y se ajusta. Este es el punto en el que la respuesta deja de ser un
# plan y pasa a ser una avería; existe solo para no recorrer y escribir una
# respuesta absurda. Por eso está muy por encima y no se toca al afinar el prompt.
HARD_MAX_RECIPES = 40


def _fail(message):
    raise LLMSchemaError(message)


def _text(data, key, where, max_length, required=True, default=""):
    value = data.get(key)
    if value is None and not required:
        return default
    if not isinstance(value, str) or not value.strip():
        _fail(f"{where}: '{key}' debe ser un texto no vacío")
    return value.strip()[:max_length]


def _number(data, key, where, minimum, maximum):
    value = data.get(key)
    # `bool` es subclase de `int` en Python: sin este filtro, `true` pasaría por
    # un 1 perfectamente válido.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{where}: '{key}' debe ser un número")
    if not minimum <= value <= maximum:
        _fail(f"{where}: '{key}' fuera de rango ({minimum}–{maximum}): {value}")
    return float(value)


def validate_plan(data, allowed_food_ids):
    """Comprueba un plan generado y lo devuelve normalizado.

    `allowed_food_ids` son los identificadores que la API le ofreció al modelo,
    no el catálogo entero: si entre que se encoló el trabajo y se procesó alguien
    borró un alimento, escribirlo daría un fallo de clave ajena.
    """
    if not isinstance(data, dict):
        _fail(f"se esperaba un objeto y ha llegado {type(data).__name__}")

    raw_recipes = data.get("recipes")
    if not isinstance(raw_recipes, list) or not raw_recipes:
        _fail("'recipes' debe ser una lista no vacía")
    if len(raw_recipes) > HARD_MAX_RECIPES:
        _fail(f"demasiadas recetas: {len(raw_recipes)} (tope duro {HARD_MAX_RECIPES})")

    recipes = []
    refs = {}

    for position, raw in enumerate(raw_recipes, start=1):
        where = f"receta {position}"
        if not isinstance(raw, dict):
            _fail(f"{where}: debe ser un objeto")

        ref = _text(raw, "ref", where, max_length=40)
        if ref in refs:
            _fail(f"{where}: la referencia '{ref}' está repetida")

        method = raw.get("cooking_method")
        if method is not None and method not in COOKING_METHODS:
            _fail(
                f"{where}: 'cooking_method' debe ser uno de: "
                + ", ".join(COOKING_METHODS)
            )

        raw_ingredients = raw.get("ingredients")
        if not isinstance(raw_ingredients, list) or not raw_ingredients:
            _fail(f"{where}: 'ingredients' debe ser una lista no vacía")
        if len(raw_ingredients) > MAX_INGREDIENTS_PER_RECIPE:
            _fail(f"{where}: demasiados ingredientes ({len(raw_ingredients)})")

        ingredients = []
        seen_foods = set()

        for number, item in enumerate(raw_ingredients, start=1):
            item_where = f"{where}, ingrediente {number}"
            if not isinstance(item, dict):
                _fail(f"{item_where}: debe ser un objeto")

            food_id = item.get("food_id")
            if isinstance(food_id, bool) or not isinstance(food_id, int):
                _fail(f"{item_where}: 'food_id' debe ser un entero")

            # El corazón de la regla 3.10: el modelo compone, pero solo con lo
            # que hay en el catálogo. Un alimento inventado tira el plan entero.
            if food_id not in allowed_food_ids:
                _fail(
                    f"{item_where}: el alimento {food_id} no está en el catálogo "
                    "que se le ofreció al modelo"
                )

            if food_id in seen_foods:
                # Lo prohíbe `uq_ingredient_per_recipe`: el mismo alimento dos
                # veces duplicaría su aporte en los totales sin que se notara.
                _fail(f"{item_where}: el alimento {food_id} está repetido en la receta")
            seen_foods.add(food_id)

            grams = _number(item, "grams", item_where, 0.1, MAX_GRAMS_PER_INGREDIENT)
            ingredients.append({"food_id": food_id, "grams": round(grams, 2)})

        servings = raw.get("servings", 1)
        if isinstance(servings, bool) or not isinstance(servings, int) or servings < 1:
            _fail(f"{where}: 'servings' debe ser un entero mayor que cero")
        if servings > MAX_SERVINGS:
            _fail(f"{where}: 'servings' fuera de rango: {servings}")

        recipe = {
            "name": _text(raw, "name", where, max_length=160),
            "steps": _text(raw, "steps", where, max_length=4000, required=False),
            "cooking_method": method,
            "servings": servings,
            "ingredients": ingredients,
        }
        refs[ref] = len(recipes)
        recipes.append(recipe)

    raw_meals = data.get("meals")
    if not isinstance(raw_meals, list) or not raw_meals:
        _fail("'meals' debe ser una lista no vacía")
    if len(raw_meals) > MAX_MEALS:
        _fail(f"demasiadas comidas: {len(raw_meals)} (máximo {MAX_MEALS})")

    meals = []
    occupied = set()

    for position, raw in enumerate(raw_meals, start=1):
        where = f"comida {position}"
        if not isinstance(raw, dict):
            _fail(f"{where}: debe ser un objeto")

        day = raw.get("day_of_week")
        if day not in DAYS_OF_WEEK:
            _fail(f"{where}: 'day_of_week' debe ser uno de: " + ", ".join(DAYS_OF_WEEK))

        slot = raw.get("meal_slot")
        if slot not in MEAL_SLOTS:
            _fail(f"{where}: 'meal_slot' debe ser uno de: " + ", ".join(MEAL_SLOTS))

        if (day, slot) in occupied:
            # Dos cenas el martes no es un plan, es un descuido del modelo.
            _fail(f"{where}: ya hay una comida en {day}/{slot}")
        occupied.add((day, slot))

        ref = raw.get("recipe_ref")
        if ref not in refs:
            _fail(f"{where}: 'recipe_ref' no coincide con ninguna receta: {ref!r}")

        meals.append({
            "day_of_week": day,
            "meal_slot": slot,
            "recipe_index": refs[ref],
            "servings": round(_number(raw, "servings", where, 0.1, MAX_SERVINGS), 2),
        })

    # Una receta que no se come en ningún momento de la semana no se escribe: es
    # una fila huérfana que solo ocupa sitio.
    used = {meal["recipe_index"] for meal in meals}
    if len(used) < len(recipes):
        keep = sorted(used)
        remap = {old: new for new, old in enumerate(keep)}
        recipes = [recipes[old] for old in keep]
        for meal in meals:
            meal["recipe_index"] = remap[meal["recipe_index"]]

    # El rango se comprueba DESPUÉS de descartar las huérfanas: lo que importa es
    # cuántas recetas distintas se come de verdad, no cuántas venían en el JSON.
    #
    # Y se comprueba aunque el esquema ya lo diga, por lo mismo que todo lo demás
    # de este módulo: con `LLM_RESPONSE_FORMAT` en `json_object` o en `none` no
    # hay esquema que lo imponga, y ahí el mínimo tiene que sostenerse solo. Es
    # justo el caso en el que hoy un modelo podía colar una sola receta para las
    # 28 comidas de la semana y el plan se guardaba sin una queja.
    if len(recipes) < MIN_RECIPES:
        _fail(
            f"el plan solo trae {len(recipes)} recetas distintas y se piden al "
            f"menos {MIN_RECIPES}: una semana con tan pocos platos no es un plan"
        )
    if len(recipes) > MAX_RECIPES:
        _fail(
            f"el plan trae {len(recipes)} recetas distintas y el máximo es "
            f"{MAX_RECIPES}: nadie cocina tantos platos distintos en una semana"
        )

    return {
        "plan_name": _text(data, "plan_name", "el plan", max_length=160,
                           required=False, default="Plan generado"),
        "notes": _text(data, "notes", "el plan", max_length=2000,
                       required=False, default=""),
        "daily_kcal_target": data.get("daily_kcal_target"),
        "recipes": recipes,
        "meals": meals,
    }


VERDICTS = ("fits", "needs_adjustment", "does_not_fit")


def validate_review(data):
    """Comprueba una revisión de plan y la devuelve normalizada."""
    if not isinstance(data, dict):
        _fail(f"se esperaba un objeto y ha llegado {type(data).__name__}")

    verdict = data.get("verdict")
    if verdict not in VERDICTS:
        _fail("'verdict' debe ser uno de: " + ", ".join(VERDICTS))

    raw_adjustments = data.get("adjustments", [])
    if not isinstance(raw_adjustments, list):
        _fail("'adjustments' debe ser una lista")

    adjustments = []
    for position, item in enumerate(raw_adjustments[:20], start=1):
        if not isinstance(item, str) or not item.strip():
            _fail(f"ajuste {position}: debe ser un texto no vacío")
        adjustments.append(item.strip()[:500])

    kcal = data.get("estimated_daily_kcal")
    if kcal is not None:
        kcal = _number(data, "estimated_daily_kcal", "la revisión", 500, 8000)

    return {
        "verdict": verdict,
        "summary": _text(data, "summary", "la revisión", max_length=4000),
        "adjustments": adjustments,
        "estimated_daily_kcal": kcal,
    }
