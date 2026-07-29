"""Modelo del dominio Análisis: el estado de un trabajo asíncrono.

La cola de Redis es el transporte del mensaje; esta tabla es la fuente de la
verdad y sobrevive a los reinicios.
"""
from datetime import datetime, timezone

from ..extensions import db

PENDING = "pending"
PROCESSING = "processing"
COMPLETED = "completed"
FAILED = "failed"

STATES = (PENDING, PROCESSING, COMPLETED, FAILED)


def _now():
    return datetime.now(timezone.utc)


class Analysis(db.Model):
    __tablename__ = "analyses"

    id = db.Column(db.Integer, primary_key=True)
    # ON DELETE CASCADE para que borrar una cuenta funcione: sin él, la clave
    # ajena bloquearía el DELETE de cualquier usuario que ya hubiera pedido un
    # análisis. Los análisis no tienen sentido sin su usuario.
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Qué plan se está analizando. Admite nulo por los análisis anteriores a que
    # existieran los planes; los nuevos siempre lo llevan.
    plan_id = db.Column(
        db.Integer, db.ForeignKey("plans.id", ondelete="CASCADE"), index=True
    )
    state = db.Column(db.String(20), nullable=False, default=PENDING, index=True)

    input = db.Column(db.JSON, nullable=False)
    result = db.Column(db.JSON)

    error = db.Column(db.Text)
    attempts = db.Column(db.Integer, nullable=False, default=0)

    created_at = db.Column(db.DateTime(timezone=True), default=_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "plan_id": self.plan_id,
            "state": self.state,
            "input": self.input,
            "result": self.result,
            "error": self.error,
            "attempts": self.attempts,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
