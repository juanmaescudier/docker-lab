"""Endpoints del dominio Análisis.

La API no ejecuta el trabajo: crea el registro, lo encola y responde 202.

El análisis es la revisión que hace la IA de un plan, y **solo se ofrece para los
planes creados a mano** (decisión 3.9): pedirle que revise un plan que ha
generado ella misma sería preguntarle si hizo bien su trabajo —por construcción
diría que sí— y no aportaría nada.
"""
from flask import Blueprint, jsonify, request

from ..extensions import db
from ..plans.models import SOURCE_MANUAL, Plan
from ..queue import enqueue
from ..session import current_user_id, login_required
from .models import Analysis, PENDING


analysis_bp = Blueprint("analysis", __name__, url_prefix="/analysis")


def _foods_from_plan(plan):
    """Aplana el plan a la lista de alimentos y gramos que consume en la semana.

    El worker sigue recibiendo `foods` en la entrada, así que no hay que
    tocarlo: lo que cambia es que ahora esa lista sale del catálogo en vez de
    escribirla el cliente a mano.
    """
    grams_per_food = {}

    for meal in plan.meals:
        recipe = meal.recipe
        if recipe is None:
            continue
        factor = meal.servings / (recipe.servings or 1)
        for ingredient in recipe.ingredients:
            if ingredient.food is None:
                continue
            name = ingredient.food.name
            grams_per_food[name] = (
                grams_per_food.get(name, 0.0) + ingredient.grams * factor
            )

    return [
        {"name": name, "grams": round(grams, 2)}
        for name, grams in sorted(grams_per_food.items())
    ]


@analysis_bp.post("")
@login_required
def create_analysis():
    """Encola el análisis de un plan y devuelve 202 con el identificador."""
    user_id = current_user_id()
    data = request.get_json(silent=True) or {}

    plan_id = data.get("plan_id")
    if isinstance(plan_id, bool) or not isinstance(plan_id, int):
        return jsonify(error="'plan_id' es obligatorio y debe ser un entero"), 400

    plan = Plan.query.filter(Plan.id == plan_id, Plan.user_id == user_id).first()
    if plan is None:
        return jsonify(error="plan no encontrado"), 404

    # 409 y no 400: la petición está bien formada y el plan existe. Lo que choca
    # es el estado del plan, y eso el cliente no lo arregla cambiando el cuerpo.
    if plan.source != SOURCE_MANUAL:
        return jsonify(error=(
            "solo se analizan los planes creados a mano: pedirle a la IA que "
            "revise su propio plan no aporta nada"
        )), 409

    analysis = Analysis(
        user_id=user_id,
        plan_id=plan.id,
        state=PENDING,
        input={"plan_id": plan.id, "foods": _foods_from_plan(plan)},
    )
    db.session.add(analysis)
    db.session.commit()

    # El commit va antes de encolar: si no, el worker podría buscar una fila
    # que todavía no existe.
    enqueue("nutritional_analysis", {"analysis_id": analysis.id})

    response = jsonify(analysis.to_dict())
    response.headers["Location"] = f"/analysis/{analysis.id}"
    return response, 202


@analysis_bp.get("/<int:analysis_id>")
@login_required
def get_analysis(analysis_id):
    """Devuelve el estado y, si está listo, el resultado del análisis."""
    user_id = current_user_id()

    analysis = db.session.get(Analysis, analysis_id)
    if analysis is None:
        return jsonify(error="análisis no encontrado"), 404

    # 404 en lugar de 403: un 403 confirmaría que el recurso existe.
    if analysis.user_id != user_id:
        return jsonify(error="análisis no encontrado"), 404

    return jsonify(analysis.to_dict()), 200


@analysis_bp.get("")
@login_required
def list_analyses():
    """Lista los análisis del usuario de la sesión, del más reciente al más antiguo."""
    analyses = (
        Analysis.query
        .filter_by(user_id=current_user_id())
        .order_by(Analysis.created_at.desc())
        .all()
    )
    return jsonify([a.to_dict() for a in analyses]), 200
