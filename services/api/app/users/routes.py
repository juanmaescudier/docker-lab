"""Endpoints del dominio Usuarios (ahora contra PostgreSQL vía SQLAlchemy).

Ya no hay diccionario en memoria: cada usuario se guarda como una fila en la
tabla "users" de Postgres, así que sobrevive a reinicios y lo comparten todos
los workers.
"""
from flask import Blueprint, request, jsonify

from ..extensions import db
from .models import User

users_bp = Blueprint("users", __name__, url_prefix="/users")


@users_bp.post("")            # POST /users -> crear (CREATE)
def create_user():
    data = request.get_json(silent=True) or {}

    if not data.get("email"):
        return jsonify(error="el campo 'email' es obligatorio"), 400

    # Creamos el objeto User (una fila en potencia).
    user = User(
        email=data["email"],
        name=data.get("name"),
        age=data.get("age"),
        height_cm=data.get("height_cm"),
        weight_kg=data.get("weight_kg"),
        goal=data.get("goal"),
    )
    db.session.add(user)      # lo añadimos a la "sesión" (cambios pendientes)
    db.session.commit()       # commit = confirma y escribe de verdad en Postgres
    return jsonify(user.to_dict()), 201


@users_bp.get("")             # GET /users -> listar (READ)
def list_users():
    users = User.query.all()  # SELECT * FROM users
    return jsonify([u.to_dict() for u in users]), 200


@users_bp.get("/<int:user_id>")   # GET /users/5 -> ver uno (READ)
def get_user(user_id):
    user = db.session.get(User, user_id)   # busca por clave primaria
    if user is None:
        return jsonify(error="usuario no encontrado"), 404
    return jsonify(user.to_dict()), 200
