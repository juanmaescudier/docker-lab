"""Modelo del dominio Análisis: el estado de un trabajo asíncrono.

La cola de Redis es el transporte del mensaje; esta tabla es la fuente de la
verdad y sobrevive a los reinicios.
"""
from datetime import datetime, timezone

from ..extensions import db

PENDIENTE = "pendiente"
PROCESANDO = "procesando"
COMPLETADO = "completado"
FALLIDO = "fallido"


def _ahora():
    return datetime.now(timezone.utc)


class Analisis(db.Model):
    __tablename__ = "analisis"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default=PENDIENTE, index=True)

    entrada = db.Column(db.JSON, nullable=False)
    resultado = db.Column(db.JSON)

    error = db.Column(db.Text)
    intentos = db.Column(db.Integer, nullable=False, default=0)

    creado_en = db.Column(db.DateTime(timezone=True), default=_ahora)
    actualizado_en = db.Column(db.DateTime(timezone=True), default=_ahora, onupdate=_ahora)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "estado": self.estado,
            "entrada": self.entrada,
            "resultado": self.resultado,
            "error": self.error,
            "intentos": self.intentos,
            "creado_en": self.creado_en.isoformat() if self.creado_en else None,
            "actualizado_en": self.actualizado_en.isoformat() if self.actualizado_en else None,
        }
