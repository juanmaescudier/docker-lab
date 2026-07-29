"""Modelo de datos del dominio Catálogo.

Cada fila es un alimento específico y medible ("pechuga de pollo, cruda"), no un
concepto ("pollo"): decisión 3.3 del diseño. Los valores son siempre por 100 g,
que es el dato fijo y universal; los gramos de una receta concreta viven en la
relación, no aquí (3.4).
"""
import unicodedata
from datetime import datetime, timezone

from sqlalchemy.orm import validates

from ..extensions import db

# Origen del dato (decisión 3.13): decide quién puede sobrescribir la fila.
# 'seed' y 'manual' quedan protegidos frente a la importación automática.
SOURCE_SEED = "seed"
SOURCE_API = "api"
SOURCE_MANUAL = "manual"
SOURCES = (SOURCE_SEED, SOURCE_API, SOURCE_MANUAL)

# Estado en que se mide el alimento. Como las recetas se expresan en crudo (3.2)
# y 100 g de arroz crudo no son 100 g de arroz cocido, el estado forma parte de
# la identidad del alimento. Puede ser nulo cuando no aplica (aceite, pan).
STATES = ("raw", "cooked", "canned", "liquid")

# Los ocho valores del etiquetado obligatorio de la UE (3.8). Se listan aquí
# porque los recorren tanto la validación de la API como la carga de la semilla.
NUTRITION_FIELDS = (
    "energy_kcal",
    "fat_g",
    "saturated_fat_g",
    "carbs_g",
    "sugars_g",
    "fiber_g",
    "protein_g",
    "salt_g",
)


def _now():
    return datetime.now(timezone.utc)


def normalize(text):
    """Pasa a minúsculas y quita los acentos, para poder buscar sin distinguirlos.

    Se hace en Python y se guarda en una columna en vez de resolverlo en SQL con
    la extensión `unaccent`, que obligaría a instalarla en el servidor de base de
    datos y ataría la aplicación a PostgreSQL.
    """
    if text is None:
        return None
    decomposed = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


class Food(db.Model):
    __tablename__ = "foods"

    id = db.Column(db.Integer, primary_key=True)

    # El nombre en español es lo que ven el usuario y la IA. El de USDA se guarda
    # aparte (`external_name`) y solo se usa al importar (3.11).
    name = db.Column(db.String(160), nullable=False, index=True)
    # Copia sin acentos y en minúsculas del nombre, mantenida por el validador de
    # abajo. Es la columna contra la que se busca, y por eso lleva índice.
    normalized_name = db.Column(db.String(160), nullable=False, index=True)
    category = db.Column(db.String(60), index=True)
    state = db.Column(db.String(20))

    # Los ocho del etiquetado de la UE, por 100 g. Admiten nulo: USDA no siempre
    # publica azúcares o fibra, y un 0 inventado sería un dato falso.
    energy_kcal = db.Column(db.Float)
    fat_g = db.Column(db.Float)
    saturated_fat_g = db.Column(db.Float)
    carbs_g = db.Column(db.Float)
    sugars_g = db.Column(db.Float)
    fiber_g = db.Column(db.Float)
    protein_g = db.Column(db.Float)
    salt_g = db.Column(db.Float)

    # La cola larga (vitaminas, minerales, colesterol…): se muestra, pero no se
    # filtra ni se suma, así que no merece una columna propia (3.8).
    extra_nutrients = db.Column(db.JSON)

    source = db.Column(db.String(10), nullable=False, default=SOURCE_MANUAL, index=True)
    # Identificador de USDA (fdcId). Nulo en los alimentos creados a mano.
    external_id = db.Column(db.String(40))
    external_name = db.Column(db.String(255))

    created_at = db.Column(db.DateTime(timezone=True), default=_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (
        # Índice único parcial: impide importar dos veces el mismo alimento de
        # USDA, pero deja convivir todos los alimentos manuales, que no tienen
        # identificador externo.
        db.Index(
            "ix_foods_external_id_unique",
            "external_id",
            unique=True,
            postgresql_where=db.text("external_id IS NOT NULL"),
        ),
    )

    @validates("name")
    def _sync_normalized_name(self, key, value):
        """Mantiene `normalized_name` al día sin que nadie tenga que acordarse."""
        self.normalized_name = normalize(value)
        return value

    def to_dict(self, include_extra=True):
        """Diccionario para el JSON.

        `include_extra=False` en los listados: `extra_nutrients` son unos cien
        nutrientes por alimento y multiplicarlos por una página entera daría
        respuestas de megabytes para un dato que ahí no se mira.
        """
        data = {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "state": self.state,
            "energy_kcal": self.energy_kcal,
            "fat_g": self.fat_g,
            "saturated_fat_g": self.saturated_fat_g,
            "carbs_g": self.carbs_g,
            "sugars_g": self.sugars_g,
            "fiber_g": self.fiber_g,
            "protein_g": self.protein_g,
            "salt_g": self.salt_g,
            "source": self.source,
            "external_id": self.external_id,
            "external_name": self.external_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_extra:
            data["extra_nutrients"] = self.extra_nutrients
        return data
