"""Endpoints CRUD del dominio Usuarios (contra PostgreSQL vía SQLAlchemy).

El registro exige contraseña y la guarda hasheada. El login/logout/me viven en
auth.py (usan sesión).

Editar y borrar solo valen sobre el propio usuario: si es otro, 403 —"sé quién
eres, pero no puedes hacer eso"—, no 404.
"""
from datetime import date, datetime, timezone

from flask import Blueprint, jsonify, request, session

from ..catalog.models import ALLERGENS, Food
from ..extensions import db
from ..session import current_user_id, login_required
from .models import (
    ACTIVITY_LEVELS,
    BODY_COMPOSITIONS,
    FOOD_PREFERENCES,
    GOAL_PACES,
    GOALS,
    INTOLERANCES,
    PREFERENCE_SPEC,
    PROFILE_FIELDS,
    SEXES,
    TOLERANCE_LEVELS,
    TRAINING_TYPES,
    User,
    UserAllergen,
    UserExcludedFood,
    UserIntolerance,
)

users_bp = Blueprint("users", __name__, url_prefix="/users")

# Campos de lista cerrada y sus valores admitidos.
CLOSED_LISTS = {
    "sex": SEXES,
    "activity_level": ACTIVITY_LEVELS,
    "goal": GOALS,
    "goal_pace": GOAL_PACES,
    "food_preference": FOOD_PREFERENCES,
    "body_composition": BODY_COMPOSITIONS,
    "training_type": TRAINING_TYPES,
}

# Rangos plausibles para un ser humano. No son reglas médicas: solo atajan
# valores absurdos o erratas de tecleo (un peso de 700 kg, una altura de 3 cm).
RANGES = {
    "height_cm": (50, 260),
    "weight_kg": (2, 500),
    "meals_per_day": (1, 10),
    "waist_cm": (20, 300),
    "hip_cm": (20, 300),
    "neck_cm": (10, 100),
    "training_days_per_week": (1, 7),
}

MAX_AGE = 120

# Cuántos alimentos puede vetar una persona. Es un tope de cordura, no una regla:
# quien veta doscientos alimentos no está usando el buscador, está pegando una
# lista, y el filtro acabaría dejando el catálogo sin nada con qué componer.
MAX_EXCLUDED_FOODS = 100


def _validate_profile(data):
    """Comprueba los campos del perfil. Devuelve el mensaje de error o None."""
    for field, allowed in CLOSED_LISTS.items():
        value = data.get(field)
        if value is not None and value not in allowed:
            return f"'{field}' debe ser uno de: {', '.join(allowed)}"

    for field, (minimum, maximum) in RANGES.items():
        value = data.get(field)
        if value is None:
            continue
        # `bool` es subclase de `int`: sin este filtro, `True` colaría como un 1.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"'{field}' debe ser un número"
        if not minimum <= value <= maximum:
            return f"'{field}' debe estar entre {minimum} y {maximum}"

    if data.get("birth_date") is not None:
        try:
            birth = date.fromisoformat(data["birth_date"])
        except (TypeError, ValueError):
            return "'birth_date' debe tener el formato AAAA-MM-DD"
        today = date.today()
        if birth > today:
            return "'birth_date' no puede estar en el futuro"
        if birth.year < today.year - MAX_AGE:
            return f"'birth_date' implica una edad mayor de {MAX_AGE} años"

    for check in (_validate_preferences, _validate_allergens,
                  _validate_intolerances, _validate_excluded_foods):
        error = check(data)
        if error:
            return error

    return None


def _validate_preferences(data):
    """Comprueba la columna JSON contra `PREFERENCE_SPEC`.

    **Las listas cerradas se validan en el servidor, no solo en la pantalla.** Que
    el valor acabe dentro de un JSON no lo convierte en texto libre: sigue siendo
    una respuesta de una lista, y un valor fuera de lista es un 400.

    Una clave desconocida también se rechaza en vez de guardarse. Guardar lo que
    llegue haría que un error de tecleo en el nombre de una pregunta se
    convirtiera en un dato que nadie lee y que nadie sabe que está mal.
    """
    if "preferences" not in data:
        return None

    preferences = data["preferences"]
    if not isinstance(preferences, dict):
        return "'preferences' debe ser un objeto"

    for key, value in preferences.items():
        spec = PREFERENCE_SPEC.get(key)
        if spec is None:
            return (
                f"'{key}' no es una preferencia conocida; las que hay son: "
                + ", ".join(sorted(PREFERENCE_SPEC))
            )

        # El nulo siempre vale: es como se borra una respuesta.
        if value is None:
            continue

        if spec["type"] == "choice":
            if value not in spec["options"]:
                return f"'{key}' debe ser uno de: {', '.join(spec['options'])}"

        elif spec["type"] == "multi":
            if not isinstance(value, list):
                return f"'{key}' debe ser una lista"
            unknown = [v for v in value if v not in spec["options"]]
            if unknown:
                return (
                    f"'{key}' solo admite estos valores: "
                    + ", ".join(spec["options"])
                )

        elif spec["type"] == "bool":
            if not isinstance(value, bool):
                return f"'{key}' debe ser verdadero o falso"

        elif spec["type"] == "text":
            # LA ÚNICA entrada libre de todo el cuestionario (3.19), y va tratada
            # como hostil por defecto. Aquí se le pone el límite de longitud; el
            # resto de las precauciones están donde toca: delimitada en el prompt
            # como dato del usuario, escapada al pintarla y parametrizada en la
            # base de datos por el ORM, como todo lo demás.
            if not isinstance(value, str):
                return f"'{key}' debe ser un texto"
            if len(value) > spec["max_length"]:
                return (
                    f"'{key}' no puede pasar de {spec['max_length']} caracteres "
                    f"(llegan {len(value)})"
                )

    return None


def _validate_allergens(data):
    if "allergens" not in data:
        return None
    allergens = data["allergens"]
    if not isinstance(allergens, list):
        return "'allergens' debe ser una lista"
    unknown = [a for a in allergens if a not in ALLERGENS]
    if unknown:
        return (
            "'allergens' solo admite los 14 de declaración obligatoria: "
            + ", ".join(ALLERGENS)
        )
    return None


def _validate_intolerances(data):
    """Cada intolerancia con su nivel: no es una exclusión, es una dosis (3.17)."""
    if "intolerances" not in data:
        return None
    rows = data["intolerances"]
    if not isinstance(rows, list):
        return "'intolerances' debe ser una lista"

    seen = set()
    for position, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            return (
                f"la intolerancia {position} debe ser un objeto con "
                "'intolerance' y 'tolerance'"
            )
        if row.get("intolerance") not in INTOLERANCES:
            return (
                f"la intolerancia {position}: 'intolerance' debe ser una de: "
                + ", ".join(INTOLERANCES)
            )
        if row.get("tolerance") not in TOLERANCE_LEVELS:
            return (
                f"la intolerancia {position}: 'tolerance' debe ser uno de: "
                + ", ".join(TOLERANCE_LEVELS)
            )
        if row["intolerance"] in seen:
            return f"'{row['intolerance']}' aparece dos veces con distinto nivel"
        seen.add(row["intolerance"])

    return None


def _validate_excluded_foods(data):
    """Los alimentos vetados van por identificador y tienen que existir.

    Que existan se comprueba aquí y no se deja a la clave ajena porque un veto a
    un alimento que no está es casi siempre un error del cliente, y un 400 que
    dice cuál falla se arregla; un error de integridad de PostgreSQL, no.
    """
    if "excluded_food_ids" not in data:
        return None
    ids = data["excluded_food_ids"]
    if not isinstance(ids, list):
        return "'excluded_food_ids' debe ser una lista de identificadores"
    if any(isinstance(i, bool) or not isinstance(i, int) for i in ids):
        return "'excluded_food_ids' solo admite identificadores enteros"
    if len(set(ids)) > MAX_EXCLUDED_FOODS:
        return f"no se pueden vetar más de {MAX_EXCLUDED_FOODS} alimentos"

    if ids:
        found = {
            row[0] for row in
            db.session.query(Food.id).filter(Food.id.in_(set(ids))).all()
        }
        missing = sorted(set(ids) - found)
        if missing:
            return (
                "estos alimentos no existen en el catálogo: "
                + ", ".join(str(i) for i in missing)
            )

    return None


def _apply_profile(user, data):
    """Vuelca al usuario solo los campos del perfil presentes en el cuerpo.

    Todo es parcial a propósito (3.15): el asistente inicial manda un `PATCH` por
    pantalla y la de ajustes manda otro con lo que se cambie. Por eso no hace
    falta ningún endpoint nuevo para el cuestionario: no es un dominio, es una
    forma de editar las preferencias del usuario.
    """
    for field in PROFILE_FIELDS:
        if field not in data:
            continue
        value = data[field]
        # La fecha llega como texto ISO y la columna es de tipo Date.
        if field == "birth_date" and value is not None:
            value = date.fromisoformat(value)
        setattr(user, field, value)

    _apply_preferences(user, data)
    _apply_lists(user, data)
    _apply_milestones(user, data)


def _apply_preferences(user, data):
    """Mezcla las preferencias que lleguen con las que ya había.

    Mezcla y no sustituye porque el asistente contesta un bloque por pantalla: un
    `PATCH` con la pantalla de la cocina no puede borrar lo que se contestó en la
    del objetivo. Para quitar una respuesta se manda esa clave a `null`.
    """
    if "preferences" not in data:
        return

    merged = dict(user.preferences or {})
    for key, value in data["preferences"].items():
        if value is None:
            merged.pop(key, None)
            continue
        spec = PREFERENCE_SPEC[key]
        if spec["type"] == "text":
            # Recortado además de validado: el límite ya lo comprueba
            # `_validate_preferences`, pero lo que se guarda no depende de que
            # esa comprobación siga estando mañana.
            value = value.strip()[:spec["max_length"]]
            if not value:
                merged.pop(key, None)
                continue
        elif spec["type"] == "multi":
            # Sin duplicados y en el orden de la lista oficial, para que dos
            # respuestas iguales se guarden iguales.
            value = [option for option in spec["options"] if option in value]
        merged[key] = value

    # Reasignación completa: el JSON de SQLAlchemy no detecta mutaciones sobre el
    # diccionario que ya tiene, así que tocarlo en sitio no llegaría a guardarse.
    user.preferences = merged


def _apply_lists(user, data):
    """Sustituye las tres relaciones. Lo que llega es la lista entera, no un añadido.

    Sustituir y no acumular es lo que hace que desmarcar una casilla funcione:
    con un cuestionario de casillas, "ya no soy alérgico al huevo" se expresa
    mandando la lista sin el huevo.
    """
    if "allergens" in data:
        user.allergens = [
            UserAllergen(allergen=value)
            for value in ALLERGENS if value in data["allergens"]
        ]

    if "intolerances" in data:
        user.intolerances = [
            UserIntolerance(
                intolerance=row["intolerance"], tolerance=row["tolerance"]
            )
            for row in data["intolerances"]
        ]

    if "excluded_food_ids" in data:
        user.excluded_foods = [
            UserExcludedFood(food_id=food_id)
            for food_id in sorted(set(data["excluded_food_ids"]))
        ]


def _apply_milestones(user, data):
    """El cribado y el fin del asistente, que son fechas y no banderas.

    **Del cribado no se guarda qué condición declaró, solo que pasó y cuándo**
    (3.18). Este endpoint ni siquiera acepta ese dato: no hay una clave que lo
    recoja, así que no hay forma de que acabe en la base de datos por descuido.
    Es un dato de salud de categoría especial que no hace falta para nada.
    """
    if data.get("screening_passed") is True and user.screening_passed_at is None:
        # Solo la primera vez: la fecha dice cuándo pasó el cribado, y volver a
        # contestar lo mismo no lo vuelve a pasar.
        user.screening_passed_at = datetime.now(timezone.utc)

    if data.get("onboarded") is True and user.onboarded_at is None:
        user.onboarded_at = datetime.now(timezone.utc)


@users_bp.post("")            # POST /users -> registro (CREATE)
def create_user():
    data = request.get_json(silent=True) or {}

    if not data.get("email") or not data.get("password"):
        return jsonify(error="'email' y 'password' son obligatorios"), 400

    error = _validate_profile(data)
    if error:
        return jsonify(error=error), 400

    # Evitamos duplicados de email antes de intentar insertar.
    if User.query.filter_by(email=data["email"]).first():
        return jsonify(error="ese email ya está registrado"), 409  # 409 = Conflict

    user = User(email=data["email"])
    _apply_profile(user, data)
    user.set_password(data["password"])   # se guarda el HASH, no la contraseña
    db.session.add(user)
    db.session.commit()

    response = jsonify(user.to_dict())
    response.headers["Location"] = f"/users/{user.id}"
    return response, 201


@users_bp.get("")             # GET /users -> listar (READ)
def list_users():
    users = User.query.all()
    return jsonify([u.to_dict() for u in users]), 200


@users_bp.get("/<int:user_id>")   # GET /users/5 -> ver uno (READ)
def get_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify(error="usuario no encontrado"), 404
    return jsonify(user.to_dict()), 200


@users_bp.patch("/<int:user_id>")
@login_required
def update_user(user_id):
    """Edita el perfil. Solo el propio usuario."""
    # El 403 se decide ANTES de mirar si la fila existe: comprobarlo al revés
    # convertiría el endpoint en un detector de qué identificadores están dados
    # de alta.
    if user_id != current_user_id():
        return jsonify(error="solo puedes editar tu propio usuario"), 403

    user = db.session.get(User, user_id)
    if user is None:
        return jsonify(error="usuario no encontrado"), 404

    data = request.get_json(silent=True) or {}

    error = _validate_profile(data)
    if error:
        return jsonify(error=error), 400

    # El email y la contraseña se cambian por su propio camino: colarlos aquí
    # dejaría cambiar credenciales sin volver a pedir la actual.
    _apply_profile(user, data)
    db.session.commit()

    return jsonify(user.to_dict()), 200


@users_bp.delete("/<int:user_id>")
@login_required
def delete_user(user_id):
    """Borra el propio usuario y cierra su sesión. 204 porque no hay nada que devolver."""
    if user_id != current_user_id():
        return jsonify(error="solo puedes borrar tu propio usuario"), 403

    user = db.session.get(User, user_id)
    if user is None:
        return jsonify(error="usuario no encontrado"), 404

    db.session.delete(user)
    db.session.commit()

    # Sin esto quedaría una sesión viva apuntando a un usuario que ya no existe.
    session.clear()
    return "", 204
