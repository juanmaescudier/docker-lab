"""Endpoints del dominio Catálogo.

La lectura es pública —el catálogo son datos de dominio público de USDA— y la
escritura exige sesión iniciada. Al editar un alimento su `source` pasa a
`manual`, que es lo que lo blinda frente a la importación automática (3.13).
"""
from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..session import login_required
from .models import (
    NUTRITION_FIELDS,
    SOURCE_MANUAL,
    STATES,
    Food,
    normalize,
)

catalog_bp = Blueprint("catalog", __name__, url_prefix="/foods")

DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 100


def _int(value, default, minimum, maximum):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def _search_pattern(term):
    """Convierte el término en un patrón LIKE seguro.

    Hay que escapar `%`, `_` y `\\` antes de interpolarlos: si no, buscar "100%"
    devolvería el catálogo entero porque el `%` es un comodín de SQL.
    """
    escaped = (
        normalize(term)
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escaped}%"


def _validate(data, require_name):
    """Comprueba el cuerpo de un POST/PATCH. Devuelve el mensaje de error o None."""
    if require_name and not (data.get("name") or "").strip():
        return "'name' es obligatorio"

    if "name" in data and not (data["name"] or "").strip():
        return "'name' no puede quedar vacío"

    state = data.get("state")
    if state is not None and state not in STATES:
        return f"'state' debe ser uno de: {', '.join(STATES)}"

    for field in NUTRITION_FIELDS:
        value = data.get(field)
        if value is None:
            continue
        # `bool` es subclase de `int` en Python: sin este filtro, `True` colaría
        # como si fuera un 1.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"'{field}' debe ser un número"
        if value < 0:
            return f"'{field}' no puede ser negativo"

    return None


def _apply(food, data):
    """Vuelca al alimento solo los campos presentes en el cuerpo."""
    for field in ("name", "category", "state", "extra_nutrients", *NUTRITION_FIELDS):
        if field in data:
            setattr(food, field, data[field])


@catalog_bp.get("")
def list_foods():
    """Busca en el catálogo. Público, paginado y sin distinguir mayúsculas ni acentos."""
    query = Food.query

    search = (request.args.get("search") or "").strip()
    if search:
        # Se busca contra `normalized_name`, que ya está en minúsculas y sin
        # acentos, así que "platano" y "Plátano" encuentran lo mismo.
        query = query.filter(
            Food.normalized_name.like(_search_pattern(search), escape="\\")
        )

    category = (request.args.get("category") or "").strip()
    if category:
        query = query.filter(Food.category == category)

    page = _int(request.args.get("page"), 1, 1, 10_000)
    per_page = _int(request.args.get("per_page"), DEFAULT_PER_PAGE, 1, MAX_PER_PAGE)

    result = (
        query.order_by(Food.normalized_name)
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return jsonify(
        # Sin `extra_nutrients`: son ~100 nutrientes por alimento y aquí no se miran.
        foods=[f.to_dict(include_extra=False) for f in result.items],
        page=result.page,
        per_page=result.per_page,
        total=result.total,
        pages=result.pages,
    ), 200


@catalog_bp.get("/<int:food_id>")
def get_food(food_id):
    """Devuelve un alimento con todos sus nutrientes."""
    food = db.session.get(Food, food_id)
    if food is None:
        return jsonify(error="alimento no encontrado"), 404
    return jsonify(food.to_dict()), 200


@catalog_bp.post("")
@login_required
def create_food():
    """Crea un alimento a mano. Nace como `manual` y queda protegido desde el minuto uno."""
    data = request.get_json(silent=True) or {}

    error = _validate(data, require_name=True)
    if error:
        return jsonify(error=error), 400

    food = Food(source=SOURCE_MANUAL)
    _apply(food, data)
    db.session.add(food)
    db.session.commit()

    response = jsonify(food.to_dict())
    response.headers["Location"] = f"/foods/{food.id}"
    return response, 201


@catalog_bp.patch("/<int:food_id>")
@login_required
def update_food(food_id):
    """Edita un alimento y lo marca como `manual` (decisión 3.13).

    El cambio de origen no es opcional ni configurable: tocarlo ES lo que lo
    blinda. Así no hace falta revisar el catálogo entero, solo lo que chirría.
    """
    food = db.session.get(Food, food_id)
    if food is None:
        return jsonify(error="alimento no encontrado"), 404

    data = request.get_json(silent=True) or {}

    error = _validate(data, require_name=False)
    if error:
        return jsonify(error=error), 400

    _apply(food, data)
    food.source = SOURCE_MANUAL
    db.session.commit()

    return jsonify(food.to_dict()), 200


@catalog_bp.delete("/<int:food_id>")
@login_required
def delete_food(food_id):
    """Borra un alimento. 204 porque no hay nada que devolver."""
    food = db.session.get(Food, food_id)
    if food is None:
        return jsonify(error="alimento no encontrado"), 404

    db.session.delete(food)
    try:
        db.session.commit()
    except IntegrityError:
        # La clave ajena de `recipe_ingredients` es RESTRICT: borrar el alimento
        # dejaría recetas apuntando al vacío. 409 porque choca con el estado
        # actual, no porque la petición estuviera mal.
        db.session.rollback()
        return jsonify(
            error="ese alimento se usa en alguna receta: quítalo de ellas antes de borrarlo"
        ), 409

    return "", 204
