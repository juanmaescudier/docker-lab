"""Modelo de un trabajo asíncrono.

Vive en `app/` y no dentro de un dominio por el mismo motivo que `queue.py` y
`session.py`: es **infraestructura de la aplicación**, no negocio. Un trabajo no
sabe de nutrición; sabe de estados, intentos y errores.

Esta tabla nació como `analyses`, pero nunca modeló un análisis nutricional:
modelaba `state`, `input`, `result`, `error` e `attempts`, que es exactamente un
trabajo en segundo plano. Al añadir la generación de planes habría hecho falta
una segunda tabla idéntica, y una tercera para las importaciones de USDA. La
columna `type` evita esa duplicación.

La cola de Redis es el transporte del mensaje; esta tabla es la fuente de la
verdad y sobrevive a los reinicios (ADR-0008).
"""
from datetime import datetime, timezone

from ..extensions import db

# Ciclo de vida. Lista cerrada (3.7).
PENDING = "pending"
PROCESSING = "processing"
COMPLETED = "completed"
FAILED = "failed"

STATES = (PENDING, PROCESSING, COMPLETED, FAILED)

# Qué clase de trabajo es. El worker despacha por este valor.
TYPE_PLAN_GENERATION = "plan_generation"
TYPE_PLAN_REVIEW = "plan_review"
# Declarado pero sin implementar todavía: la importación de alimentos desde USDA
# vive aquí en cuanto se escriba su manejador (3.11).
TYPE_FOOD_IMPORT = "food_import"

JOB_TYPES = (TYPE_PLAN_GENERATION, TYPE_PLAN_REVIEW, TYPE_FOOD_IMPORT)


def _now():
    return datetime.now(timezone.utc)


class Job(db.Model):
    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True)

    # ON DELETE CASCADE para que borrar una cuenta funcione: sin él, la clave
    # ajena bloquearía el DELETE de cualquier usuario que ya hubiera pedido un
    # trabajo. Un trabajo no tiene sentido sin su usuario.
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Qué plan toca el trabajo. Nulo mientras no lo sepa: en `plan_review` lo
    # rellena la API con el plan a revisar, y en `plan_generation` lo rellena el
    # WORKER cuando crea el plan. Ese segundo caso es lo que hace idempotente el
    # trabajo: si esta columna ya tiene valor, el plan está creado y un reintento
    # no debe crear otro.
    plan_id = db.Column(
        db.Integer, db.ForeignKey("plans.id", ondelete="CASCADE"), index=True
    )

    type = db.Column(db.String(30), nullable=False, index=True)
    state = db.Column(db.String(20), nullable=False, default=PENDING, index=True)

    # Lo que la API deja preparado para el worker. El worker NO vuelve a
    # calcular nada que ya esté aquí (3.10): sumar nutrientes es de la API.
    input = db.Column(db.JSON, nullable=False)
    result = db.Column(db.JSON)

    error = db.Column(db.Text)
    attempts = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime(timezone=True), default=_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now)

    def to_dict(self, include_input=True):
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "plan_id": self.plan_id,
            "type": self.type,
            "state": self.state,
            "result": self.result,
            "error": self.error,
            "attempts": self.attempts,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_input:
            # En el listado se omite: el `input` de una generación lleva el
            # catálogo entero y multiplicarlo por todos los trabajos del usuario
            # daría respuestas de megabytes para un dato que ahí no se mira.
            data["input"] = self.input
        return data
