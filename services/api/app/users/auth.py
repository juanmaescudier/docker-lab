"""Autenticación por sesión: login, logout y "quién soy" (/me).

Usamos el objeto `session` de Flask. Gracias a Flask-Session, los datos que
metemos en `session` (aquí, el id de usuario) se guardan en REDIS, y al
navegador solo le viaja el ID de sesión en una cookie httpOnly.
"""
from flask import Blueprint, request, jsonify, session

from ..extensions import db
from .models import User

auth_bp = Blueprint("auth", __name__)   # sin prefijo: /login, /logout, /me


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    user = User.query.filter_by(email=data.get("email")).first()

    # Mismo mensaje si no existe el usuario o si la contraseña falla:
    # no revelamos cuál de las dos cosas ha fallado (evita "enumerar" usuarios).
    if user is None or not user.check_password(data.get("password", "")):
        return jsonify(error="credenciales inválidas"), 401  # 401 = Unauthorized

    session.clear()                 # empezamos sesión limpia -> evita session fixation
    session["user_id"] = user.id    # esto se guarda en Redis, no en la cookie
    session.permanent = True        # que aplique la caducidad configurada
    return jsonify(user.to_dict()), 200


@auth_bp.post("/logout")
def logout():
    session.clear()                 # borra la sesión de Redis y la cookie
    return jsonify(message="sesión cerrada"), 200


@auth_bp.get("/me")
def me():
    user_id = session.get("user_id")
    if user_id is None:
        return jsonify(error="no autenticado"), 401
    user = db.session.get(User, user_id)
    if user is None:                # por si el usuario fue borrado con sesión viva
        session.clear()
        return jsonify(error="no autenticado"), 401
    return jsonify(user.to_dict()), 200
