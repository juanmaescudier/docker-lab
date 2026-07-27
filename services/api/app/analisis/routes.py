"""Endpoints del dominio Análisis.

La API no ejecuta el trabajo: crea el registro, lo encola y responde 202.
"""
from flask import Blueprint, jsonify, request, session

from ..cola import encolar
from ..extensions import db
from .models import Analisis, PENDIENTE

analisis_bp = Blueprint("analisis", __name__, url_prefix="/analisis")


def _usuario_actual():
    return session.get("user_id")


@analisis_bp.post("")
def crear_analisis():
    """Encola un análisis y devuelve 202 con el identificador del trabajo."""
    user_id = _usuario_actual()
    if user_id is None:
        return jsonify(error="no autenticado"), 401

    data = request.get_json(silent=True) or {}
    alimentos = data.get("alimentos")

    if not isinstance(alimentos, list) or not alimentos:
        return jsonify(error="'alimentos' debe ser una lista no vacía"), 400

    analisis = Analisis(
        user_id=user_id,
        estado=PENDIENTE,
        entrada={"alimentos": alimentos},
    )
    db.session.add(analisis)
    db.session.commit()

    # El commit va antes de encolar: si no, el worker podría buscar una fila
    # que todavía no existe.
    encolar("analisis_nutricional", {"analisis_id": analisis.id})

    respuesta = jsonify(analisis.to_dict())
    respuesta.headers["Location"] = f"/analisis/{analisis.id}"
    return respuesta, 202


@analisis_bp.get("/<int:analisis_id>")
def obtener_analisis(analisis_id):
    """Devuelve el estado y, si está listo, el resultado del análisis."""
    user_id = _usuario_actual()
    if user_id is None:
        return jsonify(error="no autenticado"), 401

    analisis = db.session.get(Analisis, analisis_id)
    if analisis is None:
        return jsonify(error="análisis no encontrado"), 404

    # 404 en lugar de 403: un 403 confirmaría que el recurso existe.
    if analisis.user_id != user_id:
        return jsonify(error="análisis no encontrado"), 404

    return jsonify(analisis.to_dict()), 200


@analisis_bp.get("")
def listar_analisis():
    """Lista los análisis del usuario de la sesión, del más reciente al más antiguo."""
    user_id = _usuario_actual()
    if user_id is None:
        return jsonify(error="no autenticado"), 401

    analisis = (
        Analisis.query
        .filter_by(user_id=user_id)
        .order_by(Analisis.creado_en.desc())
        .all()
    )
    return jsonify([a.to_dict() for a in analisis]), 200
