"""Endpoints CRUD del dominio Usuarios (contra PostgreSQL vía SQLAlchemy).

El registro exige contraseña y la guarda hasheada. El login/logout/me viven en
auth.py (usan sesión).

Editar y borrar solo valen sobre el propio usuario: si es otro, 403 —"sé quién
eres, pero no puedes hacer eso"—, no 404.
"""
from datetime import date

from flask import Blueprint, jsonify, request, session

from ..extensions import db
from ..session import current_user_id, login_required
from .models import (
    ACTIVITY_LEVELS,
    BODY_COMPOSITIONS,
    FOOD_PREFERENCES,
    GOALS,
    PROFILE_FIELDS,
    SEXES,
    User,
)

users_bp = Blueprint("users", __name__, url_prefix="/users")

# Campos de lista cerrada y sus valores admitidos.
CLOSED_LISTS = {
    "sex": SEXES,
    "activity_level": ACTIVITY_LEVELS,
    "goal": GOALS,
    "food_preference": FOOD_PREFERENCES,
    "body_composition": BODY_COMPOSITIONS,
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
}

MAX_AGE = 120


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

    return None


def _apply_profile(user, data):
    """Vuelca al usuario solo los campos del perfil presentes en el cuerpo."""
    for field in PROFILE_FIELDS:
        if field not in data:
            continue
        value = data[field]
        # La fecha llega como texto ISO y la columna es de tipo Date.
        if field == "birth_date" and value is not None:
            value = date.fromisoformat(value)
        setattr(user, field, value)


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
