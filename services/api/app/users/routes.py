"""Endpoints CRUD del dominio Usuarios (contra PostgreSQL vía SQLAlchemy).

El registro (POST /users) ahora exige contraseña y la guarda hasheada.
El login/logout/me viven en auth.py (usan sesión).
"""
from flask import Blueprint, request, jsonify

from ..extensions import db
from .models import User

users_bp = Blueprint("users", __name__, url_prefix="/users")


@users_bp.post("")            # POST /users -> registro (CREATE)
def create_user():
    data = request.get_json(silent=True) or {}

    # Ahora email y password son obligatorios.
    if not data.get("email") or not data.get("password"):
        return jsonify(error="'email' y 'password' son obligatorios"), 400

    # Evitamos duplicados de email antes de intentar insertar.
    if User.query.filter_by(email=data["email"]).first():
        return jsonify(error="ese email ya está registrado"), 409  # 409 = Conflict

    user = User(
        email=data["email"],
        name=data.get("name"),
        age=data.get("age"),
        height_cm=data.get("height_cm"),
        weight_kg=data.get("weight_kg"),
        goal=data.get("goal"),
    )
    user.set_password(data["password"])   # se guarda el HASH, no la contraseña
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


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
