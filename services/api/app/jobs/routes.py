"""Endpoints de consulta de trabajos.

**Único sitio donde se consulta el estado de cualquier trabajo**, sea una
generación de plan, una revisión o una importación. Quien encola devuelve un
`job_id`; quien quiere saber cómo va pregunta aquí.

Aquí no se encola nada: crear un trabajo es siempre una acción de un dominio
(«genérame un plan», «revísame este plan»), y su endpoint vive en ese dominio.
Este módulo solo lee.
"""
from flask import Blueprint, jsonify, request

from ..extensions import db
from ..session import current_user_id, login_required
from .models import JOB_TYPES, STATES, Job

jobs_bp = Blueprint("jobs", __name__, url_prefix="/jobs")


@jobs_bp.get("/<int:job_id>")
@login_required
def get_job(job_id):
    """Estado y, si está listo, resultado del trabajo."""
    job = db.session.get(Job, job_id)

    # 404 en lugar de 403 cuando es de otro: un 403 confirmaría que existe.
    if job is None or job.user_id != current_user_id():
        return jsonify(error="trabajo no encontrado"), 404

    return jsonify(job.to_dict()), 200


@jobs_bp.get("")
@login_required
def list_jobs():
    """Lista los trabajos del usuario de la sesión, del más reciente al más antiguo.

    Admite filtrar por `type` y por `state`. Un filtro con un valor que no
    pertenece a la lista cerrada es un error del cliente, no una lista vacía:
    devolver 200 con `[]` ante un `?state=completado` mal escrito haría creer
    que no hay trabajos cuando lo que hay es una errata.
    """
    query = Job.query.filter(Job.user_id == current_user_id())

    job_type = request.args.get("type")
    if job_type is not None:
        if job_type not in JOB_TYPES:
            return jsonify(error=f"'type' debe ser uno de: {', '.join(JOB_TYPES)}"), 400
        query = query.filter(Job.type == job_type)

    state = request.args.get("state")
    if state is not None:
        if state not in STATES:
            return jsonify(error=f"'state' debe ser uno de: {', '.join(STATES)}"), 400
        query = query.filter(Job.state == state)

    jobs = query.order_by(Job.created_at.desc(), Job.id.desc()).all()
    return jsonify([j.to_dict(include_input=False) for j in jobs]), 200
