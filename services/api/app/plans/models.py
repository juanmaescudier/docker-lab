"""Modelo de datos del dominio Planes.

Un plan es una **plantilla semanal, no un rango de fechas** (decisión 3.1): así
es como funciona una pauta de nutricionista en la vida real, te dan una semana
tipo y la repites hasta que te la cambian. Por eso `PlannedMeal` guarda
`day_of_week` y no una fecha del calendario, y por eso el plan no tiene fecha de
fin: tiene `active`.
"""
from datetime import datetime, timezone

from ..extensions import db

# Listas cerradas (3.7).
DAYS_OF_WEEK = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
)
MEAL_SLOTS = ("breakfast", "mid_morning", "lunch", "afternoon_snack", "dinner")

SOURCE_AI = "ai"
SOURCE_MANUAL = "manual"
SOURCES = (SOURCE_AI, SOURCE_MANUAL)


def _now():
    return datetime.now(timezone.utc)


class Plan(db.Model):
    __tablename__ = "plans"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name = db.Column(db.String(160), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=False)
    source = db.Column(db.String(10), nullable=False, default=SOURCE_MANUAL)

    created_at = db.Column(db.DateTime(timezone=True), default=_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now)

    meals = db.relationship(
        "PlannedMeal",
        back_populates="plan",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        # Un solo plan activo por usuario, garantizado por la BASE DE DATOS y no
        # solo por el código: si dos peticiones activaran dos planes a la vez, la
        # comprobación en Python las dejaría pasar a las dos. El índice es
        # parcial porque los planes archivados (active=false) son muchos y ahí
        # no hay unicidad que imponer.
        db.Index(
            "uq_active_plan_per_user",
            "user_id",
            unique=True,
            postgresql_where=db.text("active"),
        ),
    )

    def to_dict(self, include_meals=True):
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "active": self.active,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_meals:
            # Ordenadas por día y momento de la semana, no alfabéticamente:
            # "domingo" antes que "lunes" no es una parrilla, es una lista.
            data["meals"] = [
                m.to_dict() for m in sorted(
                    self.meals,
                    key=lambda m: (
                        DAYS_OF_WEEK.index(m.day_of_week) if m.day_of_week in DAYS_OF_WEEK else 99,
                        MEAL_SLOTS.index(m.meal_slot) if m.meal_slot in MEAL_SLOTS else 99,
                    ),
                )
            ]
        else:
            data["meal_count"] = len(self.meals)
        return data


class PlannedMeal(db.Model):
    __tablename__ = "planned_meals"

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(
        db.Integer, db.ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    day_of_week = db.Column(db.String(10), nullable=False)
    meal_slot = db.Column(db.String(15), nullable=False)
    # RESTRICT por el mismo motivo que en los ingredientes: borrar una receta no
    # debe dejar agujeros silenciosos en los planes que la usan.
    recipe_id = db.Column(
        db.Integer, db.ForeignKey("recipes.id", ondelete="RESTRICT"), nullable=False
    )
    # Cuántas raciones se come, que no tiene por qué ser lo que rinde la receta.
    # Admite decimales: media ración es una cantidad razonable.
    servings = db.Column(db.Float, nullable=False, default=1)

    plan = db.relationship("Plan", back_populates="meals")
    recipe = db.relationship("Recipe", lazy="joined")

    __table_args__ = (
        db.CheckConstraint("servings > 0", name="ck_planned_meals_servings_positive"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "day_of_week": self.day_of_week,
            "meal_slot": self.meal_slot,
            "recipe_id": self.recipe_id,
            "recipe": self.recipe.name if self.recipe else None,
            "servings": self.servings,
        }
