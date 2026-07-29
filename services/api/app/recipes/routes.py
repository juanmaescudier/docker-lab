"""Endpoints del dominio Recetas.

Todos exigen sesión: una receta es dato de un usuario, no del catálogo público.
Se ven las propias y las del sistema (`user_id` nulo); solo se pueden modificar
o borrar las propias.

Sobre los códigos: una receta de OTRO usuario devuelve 404, porque un 403
confirmaría que existe. Una receta del SISTEMA devuelve 403, porque su
existencia ya es pública y lo único que falta es el permiso.
"""
from flask import Blueprint, jsonify, request
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from ..catalog.models import Food
from ..extensions import db
from ..session import current_user_id, login_required
from .models import COOKING_METHODS, SOURCE_MANUAL, Recipe, RecipeIngredient

recipes_bp = Blueprint("recipes", __name__, url_prefix="/recipes")

DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 100


def _int(value, default, minimum, maximum):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def _visible_to(user_id):
    """Filtro de visibilidad: las mías y las del sistema."""
    return or_(Recipe.user_id == user_id, Recipe.user_id.is_(None))


def _validate_recipe(data, require_name):
    """Valida los campos propios de la receta. Devuelve el error o None."""
    if require_name and not (data.get("name") or "").strip():
        return "'name' es obligatorio"
    if "name" in data and not (data["name"] or "").strip():
        return "'name' no puede quedar vacío"

    method = data.get("cooking_method")
    if method is not None and method not in COOKING_METHODS:
        return f"'cooking_method' debe ser uno de: {', '.join(COOKING_METHODS)}"

    if "servings" in data:
        servings = data["servings"]
        if isinstance(servings, bool) or not isinstance(servings, int):
            return "'servings' debe ser un número entero"
        if servings < 1:
            return "'servings' debe ser mayor que cero"

    return None


def _validate_ingredients(raw):
    """Valida la lista de ingredientes y comprueba que los alimentos existan.

    Devuelve `(lista_normalizada, error)`. La existencia se comprueba con una
    sola consulta en lugar de una por ingrediente.
    """
    if not isinstance(raw, list) or not raw:
        return None, "'ingredients' debe ser una lista no vacía"

    normalized = []
    seen = set()

    for position, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            return None, f"el ingrediente {position} debe ser un objeto"

        food_id = item.get("food_id")
        if isinstance(food_id, bool) or not isinstance(food_id, int):
            return None, f"el ingrediente {position} necesita un 'food_id' entero"

        grams = item.get("grams")
        if isinstance(grams, bool) or not isinstance(grams, (int, float)):
            return None, f"el ingrediente {position} necesita 'grams' numérico"
        if grams <= 0:
            return None, f"los gramos del ingrediente {position} deben ser mayores que cero"

        if food_id in seen:
            return None, (
                f"el alimento {food_id} aparece dos veces: júntalos en una "
                "sola línea o sus gramos se contarían dos veces"
            )
        seen.add(food_id)

        normalized.append({"food_id": food_id, "grams": float(grams)})

    existing = {
        row[0] for row in
        db.session.query(Food.id).filter(Food.id.in_(seen)).all()
    }
    missing = sorted(seen - existing)
    if missing:
        return None, (
            "estos alimentos no existen en el catálogo: "
            + ", ".join(str(i) for i in missing)
        )

    return normalized, None


def _replace_ingredients(recipe, normalized):
    """Deja la receta exactamente con los ingredientes recibidos.

    Se sustituye la lista entera en vez de intentar casar altas y bajas: una
    receta tiene un puñado de ingredientes y el borrado incremental solo añadiría
    formas de dejarla a medias.
    """
    if recipe.ingredients:
        recipe.ingredients.clear()
        # El flush es imprescindible: en un mismo flush SQLAlchemy emite los
        # INSERT antes que los DELETE, así que un alimento que esté en la lista
        # vieja y en la nueva chocaría con uq_ingredient_per_recipe. Forzando
        # aquí el borrado, las altas se insertan sobre la tabla ya limpia.
        db.session.flush()

    for item in normalized:
        recipe.ingredients.append(RecipeIngredient(**item))


@recipes_bp.get("")
@login_required
def list_recipes():
    """Lista las recetas propias y las del sistema, paginadas."""
    page = _int(request.args.get("page"), 1, 1, 10_000)
    per_page = _int(request.args.get("per_page"), DEFAULT_PER_PAGE, 1, MAX_PER_PAGE)

    result = (
        Recipe.query
        .filter(_visible_to(current_user_id()))
        .order_by(Recipe.name)
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return jsonify(
        # Sin ingredientes ni totales: calcularlos para una página entera son
        # muchas sumas para un dato que en el listado no se mira.
        recipes=[r.to_dict(include_ingredients=False) for r in result.items],
        page=result.page,
        per_page=result.per_page,
        total=result.total,
        pages=result.pages,
    ), 200


@recipes_bp.get("/<int:recipe_id>")
@login_required
def get_recipe(recipe_id):
    """Devuelve la receta con sus ingredientes y sus totales nutricionales."""
    recipe = Recipe.query.filter(
        Recipe.id == recipe_id, _visible_to(current_user_id())
    ).first()
    if recipe is None:
        return jsonify(error="receta no encontrada"), 404
    return jsonify(recipe.to_dict()), 200


@recipes_bp.post("")
@login_required
def create_recipe():
    """Crea una receta con sus ingredientes en la misma petición."""
    data = request.get_json(silent=True) or {}

    error = _validate_recipe(data, require_name=True)
    if error:
        return jsonify(error=error), 400

    normalized, error = _validate_ingredients(data.get("ingredients"))
    if error:
        return jsonify(error=error), 400

    recipe = Recipe(
        user_id=current_user_id(),
        name=data["name"].strip(),
        steps=data.get("steps"),
        cooking_method=data.get("cooking_method"),
        servings=data.get("servings", 1),
        # Creada a mano por definición: las de la IA las escribe el worker.
        source=SOURCE_MANUAL,
    )
    _replace_ingredients(recipe, normalized)

    db.session.add(recipe)
    db.session.commit()

    response = jsonify(recipe.to_dict())
    response.headers["Location"] = f"/recipes/{recipe.id}"
    return response, 201


@recipes_bp.patch("/<int:recipe_id>")
@login_required
def update_recipe(recipe_id):
    """Edita una receta propia. Si llegan 'ingredients', sustituyen a los actuales."""
    user_id = current_user_id()

    recipe = Recipe.query.filter(
        Recipe.id == recipe_id, _visible_to(user_id)
    ).first()
    if recipe is None:
        return jsonify(error="receta no encontrada"), 404
    if recipe.user_id != user_id:
        return jsonify(error="las recetas del sistema no se pueden editar"), 403

    data = request.get_json(silent=True) or {}

    error = _validate_recipe(data, require_name=False)
    if error:
        return jsonify(error=error), 400

    for field in ("name", "steps", "cooking_method", "servings"):
        if field in data:
            setattr(recipe, field, data[field])

    if "ingredients" in data:
        normalized, error = _validate_ingredients(data["ingredients"])
        if error:
            return jsonify(error=error), 400
        _replace_ingredients(recipe, normalized)

    db.session.commit()
    return jsonify(recipe.to_dict()), 200


@recipes_bp.delete("/<int:recipe_id>")
@login_required
def delete_recipe(recipe_id):
    """Borra una receta propia. Sus ingredientes se van con ella."""
    user_id = current_user_id()

    recipe = Recipe.query.filter(
        Recipe.id == recipe_id, _visible_to(user_id)
    ).first()
    if recipe is None:
        return jsonify(error="receta no encontrada"), 404
    if recipe.user_id != user_id:
        return jsonify(error="las recetas del sistema no se pueden borrar"), 403

    db.session.delete(recipe)
    try:
        db.session.commit()
    except IntegrityError:
        # `planned_meals.recipe_id` es RESTRICT: borrarla dejaría huecos en los
        # planes que la usan. Igual que en el catálogo, 409.
        db.session.rollback()
        return jsonify(
            error="esa receta se usa en algún plan: quítala de él antes de borrarla"
        ), 409

    return "", 204
