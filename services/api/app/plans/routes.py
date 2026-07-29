"""Endpoints del dominio Planes.

Un plan es privado de su usuario: no hay planes "del sistema" como en recetas.
Por eso todo lo que no es tuyo devuelve 404 y no 403 —un 403 confirmaría que
existe—, sin la excepción que sí tenían las recetas compartidas.
"""
from flask import Blueprint, jsonify, request
from sqlalchemy import or_

from ..extensions import db
from ..recipes.models import Recipe
from ..session import current_user_id, login_required
from . import shopping_list
from .models import (
    DAYS_OF_WEEK,
    MEAL_SLOTS,
    SOURCE_MANUAL,
    Plan,
    PlannedMeal,
)

plans_bp = Blueprint("plans", __name__, url_prefix="/plans")


def _my_plan(plan_id):
    """El plan si es del usuario de la sesión; None en cualquier otro caso."""
    return Plan.query.filter(
        Plan.id == plan_id, Plan.user_id == current_user_id()
    ).first()


def _validate_meals(raw):
    """Valida la parrilla. Devuelve `(lista_normalizada, error)`.

    Deliberadamente **no** se comprueba que todos los días tengan el mismo número
    de comidas: el lunes puede tener cinco y el domingo tres.
    `User.meals_per_day` es una preferencia, no una restricción del plan.
    """
    if raw is None:
        return [], None
    if not isinstance(raw, list):
        return None, "'meals' debe ser una lista"

    normalized = []
    used_recipes = set()

    for position, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            return None, f"la comida {position} debe ser un objeto"

        day = item.get("day_of_week")
        if day not in DAYS_OF_WEEK:
            return None, (
                f"la comida {position}: 'day_of_week' debe ser uno de: "
                + ", ".join(DAYS_OF_WEEK)
            )

        slot = item.get("meal_slot")
        if slot not in MEAL_SLOTS:
            return None, (
                f"la comida {position}: 'meal_slot' debe ser uno de: "
                + ", ".join(MEAL_SLOTS)
            )

        recipe_id = item.get("recipe_id")
        if isinstance(recipe_id, bool) or not isinstance(recipe_id, int):
            return None, f"la comida {position} necesita un 'recipe_id' entero"

        servings = item.get("servings", 1)
        if isinstance(servings, bool) or not isinstance(servings, (int, float)):
            return None, f"la comida {position} necesita 'servings' numérico"
        if servings <= 0:
            return None, f"las raciones de la comida {position} deben ser mayores que cero"

        used_recipes.add(recipe_id)
        normalized.append({
            "day_of_week": day,
            "meal_slot": slot,
            "recipe_id": recipe_id,
            "servings": float(servings),
        })

    if used_recipes:
        # Solo valen recetas que el usuario pueda ver: las suyas y las del
        # sistema. Referenciar la de otro colaría datos ajenos en su plan.
        visible = {
            row[0] for row in
            db.session.query(Recipe.id).filter(
                Recipe.id.in_(used_recipes),
                or_(Recipe.user_id == current_user_id(), Recipe.user_id.is_(None)),
            ).all()
        }
        missing = sorted(used_recipes - visible)
        if missing:
            return None, (
                "estas recetas no existen o no son tuyas: "
                + ", ".join(str(i) for i in missing)
            )

    return normalized, None


def _deactivate_others(user_id, except_id=None):
    """Deja sin activo cualquier otro plan del usuario.

    Se ejecuta ANTES de marcar el nuevo y con un flush inmediato: el índice único
    parcial de la base de datos rechazaría tener dos activos a la vez, aunque
    fuera durante una sola sentencia.
    """
    query = Plan.query.filter(Plan.user_id == user_id, Plan.active.is_(True))
    if except_id is not None:
        query = query.filter(Plan.id != except_id)
    query.update({"active": False}, synchronize_session=False)
    db.session.flush()


def _replace_meals(plan, normalized):
    """Deja el plan exactamente con las comidas recibidas."""
    if plan.meals:
        plan.meals.clear()
        db.session.flush()
    for item in normalized:
        plan.meals.append(PlannedMeal(**item))


@plans_bp.get("")
@login_required
def list_plans():
    """Lista los planes del usuario, el activo primero."""
    plans = (
        Plan.query
        .filter(Plan.user_id == current_user_id())
        .order_by(Plan.active.desc(), Plan.created_at.desc())
        .all()
    )
    return jsonify([p.to_dict(include_meals=False) for p in plans]), 200


@plans_bp.get("/<int:plan_id>")
@login_required
def get_plan(plan_id):
    """Devuelve el plan con su parrilla completa."""
    plan = _my_plan(plan_id)
    if plan is None:
        return jsonify(error="plan no encontrado"), 404
    return jsonify(plan.to_dict()), 200


@plans_bp.post("")
@login_required
def create_plan():
    """Crea un plan a mano, con sus comidas en la misma petición."""
    data = request.get_json(silent=True) or {}
    user_id = current_user_id()

    if not (data.get("name") or "").strip():
        return jsonify(error="'name' es obligatorio"), 400

    normalized, error = _validate_meals(data.get("meals"))
    if error:
        return jsonify(error=error), 400

    active = bool(data.get("active", False))
    if active:
        _deactivate_others(user_id)

    plan = Plan(
        user_id=user_id,
        name=data["name"].strip(),
        active=active,
        # Creado a mano por definición: los de la IA los escribe el worker.
        source=SOURCE_MANUAL,
    )
    _replace_meals(plan, normalized)

    db.session.add(plan)
    db.session.commit()

    response = jsonify(plan.to_dict())
    response.headers["Location"] = f"/plans/{plan.id}"
    return response, 201


@plans_bp.patch("/<int:plan_id>")
@login_required
def update_plan(plan_id):
    """Edita un plan propio. Si llegan 'meals', sustituyen a la parrilla actual."""
    plan = _my_plan(plan_id)
    if plan is None:
        return jsonify(error="plan no encontrado"), 404

    data = request.get_json(silent=True) or {}

    if "name" in data and not (data["name"] or "").strip():
        return jsonify(error="'name' no puede quedar vacío"), 400

    normalized, error = (None, None)
    if "meals" in data:
        normalized, error = _validate_meals(data["meals"])
        if error:
            return jsonify(error=error), 400

    if "name" in data:
        plan.name = data["name"].strip()

    if "active" in data:
        active = bool(data["active"])
        if active:
            # Activar uno desactiva el anterior: solo puede haber uno (3.1).
            _deactivate_others(plan.user_id, except_id=plan.id)
        plan.active = active

    if normalized is not None:
        _replace_meals(plan, normalized)

    db.session.commit()
    return jsonify(plan.to_dict()), 200


@plans_bp.delete("/<int:plan_id>")
@login_required
def delete_plan(plan_id):
    """Borra un plan propio. Su parrilla se va con él."""
    plan = _my_plan(plan_id)
    if plan is None:
        return jsonify(error="plan no encontrado"), 404

    db.session.delete(plan)
    db.session.commit()
    return "", 204


@plans_bp.get("/<int:plan_id>/shopping-list")
@login_required
def get_shopping_list(plan_id):
    """Calcula la lista de la compra del plan para N semanas."""
    plan = _my_plan(plan_id)
    if plan is None:
        return jsonify(error="plan no encontrado"), 404

    raw = request.args.get("weeks", "1")
    try:
        weeks = int(raw)
    except (TypeError, ValueError):
        return jsonify(error="'weeks' debe ser un número entero"), 400

    # Se rechaza en lugar de recortar al rango: si alguien pide 99 semanas se ha
    # equivocado, y devolverle la lista de 4 sin avisar sería peor que un error.
    if not shopping_list.MIN_WEEKS <= weeks <= shopping_list.MAX_WEEKS:
        return jsonify(error=(
            f"'weeks' debe estar entre {shopping_list.MIN_WEEKS} y "
            f"{shopping_list.MAX_WEEKS}"
        )), 400

    return jsonify(shopping_list.calculate(plan, weeks)), 200
