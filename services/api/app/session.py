"""Utilidades de sesión compartidas por todos los dominios.

Viven fuera de `users/` porque las usan catálogo, recetas y planes: si estuvieran
dentro del paquete de un dominio, el resto tendría que importar de él para algo
que en realidad es transversal.
"""
from functools import wraps

from flask import jsonify, session


def current_user_id():
    """Id del usuario de la sesión, o None si no hay sesión iniciada."""
    return session.get("user_id")


def login_required(view):
    """Corta con 401 si no hay sesión. 401 = "identifícate", no 403."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user_id() is None:
            return jsonify(error="no autenticado"), 401
        return view(*args, **kwargs)
    return wrapper
