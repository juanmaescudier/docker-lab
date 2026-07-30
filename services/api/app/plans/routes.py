"""Endpoints del dominio Planes.

Un plan es privado de su usuario: no hay planes "del sistema" como en recetas.
Por eso todo lo que no es tuyo devuelve 404 y no 403 —un 403 confirmaría que
existe—, sin la excepción que sí tenían las recetas compartidas.
"""
from flask import Blueprint, jsonify, request
from sqlalchemy import or_

from ..extensions import db
from ..jobs.models import (
    PENDING,
    PROCESSING,
    TYPE_PLAN_GENERATION,
    TYPE_PLAN_REVIEW,
    Job,
)
from ..queue import enqueue
from ..recipes.models import Recipe
from ..session import current_user_id, login_required
from ..users.models import User
from . import ai, shopping_list
from .models import (
    DAYS_OF_WEEK,
    MEAL_SLOTS,
    SOURCE_MANUAL,
    Plan,
    PlannedMeal,
)

plans_bp = Blueprint("plans", __name__, url_prefix="/plans")

# Sin estos campos el modelo no puede estimar necesidades calóricas (3.9): le
# faltaría lo básico y devolvería un plan inventado con cara de plausible.
REQUIRED_PROFILE_FIELDS = (
    "sex", "birth_date", "height_cm", "weight_kg", "activity_level", "goal",
)


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


def _pending_job(user_id, job_type):
    """El trabajo de ese tipo que ya está en marcha, si lo hay."""
    return Job.query.filter(
        Job.user_id == user_id,
        Job.type == job_type,
        Job.state.in_((PENDING, PROCESSING)),
    ).first()


def _accepted(job):
    """Respuesta común de los endpoints que encolan: 202 y dónde consultarlo.

    202 y no 201: no se ha creado el plan todavía, se ha **aceptado el encargo**
    de crearlo. El cliente pregunta después por `Location`.
    """
    response = jsonify(job.to_dict(include_input=False))
    response.headers["Location"] = f"/jobs/{job.id}"
    return response, 202


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


@plans_bp.post("/generate")
@login_required
def generate_plan():
    """Encola la generación de un plan por IA y devuelve 202 con el `job_id`.

    Aquí no se llama al modelo: hacerlo dentro de la petición bloquearía un
    worker de gunicorn decenas de segundos y con cuatro peticiones a la vez la
    API dejaría de responder a todo el mundo (ADR-0008).

    La API deja el `input` preparado —perfil y catálogo— para que el worker no
    tenga que conocer el esquema.
    """
    user_id = current_user_id()
    user = db.session.get(User, user_id)

    missing = [f for f in REQUIRED_PROFILE_FIELDS if getattr(user, f) is None]
    if missing:
        # 409 y no 400: la petición está perfecta, lo que choca es el estado del
        # perfil. El cliente no lo arregla cambiando el cuerpo, sino su usuario.
        return jsonify(error=(
            "completa tu perfil antes de generar un plan; faltan: "
            + ", ".join(missing)
        )), 409

    in_flight = _pending_job(user_id, TYPE_PLAN_GENERATION)
    if in_flight is not None:
        # Sin esto, pulsar dos veces generaría dos planes y el segundo
        # desactivaría al primero: dinero gastado en un plan que nadie ve.
        return jsonify(
            error="ya tienes una generación en marcha",
            job_id=in_flight.id,
        ), 409

    job_input = ai.build_generation_input(user)
    if not job_input["foods"]:
        return jsonify(error="el catálogo está vacío: no hay con qué componer"), 409

    job = Job(
        user_id=user_id,
        type=TYPE_PLAN_GENERATION,
        state=PENDING,
        input=job_input,
    )
    db.session.add(job)
    db.session.commit()

    # El commit va antes de encolar: si no, el worker podría coger el mensaje y
    # buscar una fila que todavía no existe.
    enqueue(TYPE_PLAN_GENERATION, job.id)

    return _accepted(job)


@plans_bp.post("/<int:plan_id>/review")
@login_required
def review_plan(plan_id):
    """Encola la revisión de un plan por IA y devuelve 202 con el `job_id`.

    Es lo que antes era `POST /analysis`. Vive en el dominio de planes porque lo
    que se pide es «revísame **este plan**»; el trabajo resultante se consulta,
    como todos, en `/jobs/<id>`.

    Solo para planes creados a mano (3.9): pedirle a la IA que revise un plan que
    ha generado ella misma sería preguntarle si hizo bien su trabajo —por
    construcción diría que sí— y no aportaría nada.
    """
    plan = _my_plan(plan_id)
    if plan is None:
        return jsonify(error="plan no encontrado"), 404

    if plan.source != SOURCE_MANUAL:
        return jsonify(error=(
            "solo se revisan los planes creados a mano: pedirle a la IA que "
            "revise su propio plan no aporta nada"
        )), 409

    if not plan.meals:
        return jsonify(error="el plan no tiene comidas: no hay nada que revisar"), 409

    user = db.session.get(User, plan.user_id)

    job = Job(
        user_id=plan.user_id,
        plan_id=plan.id,
        type=TYPE_PLAN_REVIEW,
        state=PENDING,
        # El resumen nutricional lo calcula la API, no el worker: sumar los
        # nutrientes del catálogo son microsegundos y los números tienen que
        # salir de la tabla, nunca del modelo (3.10).
        input=ai.build_review_input(user, plan),
    )
    db.session.add(job)
    db.session.commit()

    enqueue(TYPE_PLAN_REVIEW, job.id)

    return _accepted(job)


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
