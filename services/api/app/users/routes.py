"""Endpoints del dominio Usuarios.

De momento guardamos los usuarios EN MEMORIA (un diccionario de Python).
OJO: eso significa que se BORRAN al reiniciar el contenedor. En el siguiente
paso lo cambiaremos por PostgreSQL para que persista de verdad.

Tampoco hay login ni contraseñas todavía: eso llega con el paso de auth + Redis.
Aquí solo practicamos la mecánica de crear y leer usuarios (CRUD básico).
"""
from flask import Blueprint, request, jsonify

# Un Blueprint agrupa endpoints bajo un prefijo común. Todo lo de aquí
# colgará de /users  (porque url_prefix="/users").
users_bp = Blueprint("users", __name__, url_prefix="/users")

# "Base de datos" temporal en memoria: un diccionario {id: usuario}.
_users = {}
_next_id = 1


@users_bp.post("")            # POST /users  -> crear un usuario (CREATE)
def create_user():
    # request.get_json() lee el cuerpo (body) que llega en formato JSON.
    # silent=True evita que reviente si no viene JSON; devolvemos {} en ese caso.
    data = request.get_json(silent=True) or {}

    # Validación mínima: el email es obligatorio.
    # Si falta, devolvemos 400 = "Bad Request" (petición mal formada).
    if not data.get("email"):
        return jsonify(error="el campo 'email' es obligatorio"), 400

    global _next_id
    user = {
        "id": _next_id,
        "email": data["email"],
        "name": data.get("name"),
        "age": data.get("age"),
        "height_cm": data.get("height_cm"),
        "weight_kg": data.get("weight_kg"),
        "goal": data.get("goal"),          # objetivo: "perder grasa", etc.
    }
    _users[_next_id] = user
    _next_id += 1

    # 201 = "Created". Devolvemos el usuario recién creado en JSON.
    return jsonify(user), 201


@users_bp.get("")             # GET /users  -> listar todos (READ)
def list_users():
    return jsonify(list(_users.values())), 200


@users_bp.get("/<int:user_id>")   # GET /users/5 -> ver uno concreto (READ)
def get_user(user_id):
    # <int:user_id> captura el número de la URL y lo pasa como argumento.
    user = _users.get(user_id)
    if user is None:
        # 404 = "Not Found": no existe ese usuario.
        return jsonify(error="usuario no encontrado"), 404
    return jsonify(user), 200
