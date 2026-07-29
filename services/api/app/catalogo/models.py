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
ORIGEN_SEED = "seed"
ORIGEN_API = "api"
ORIGEN_MANUAL = "manual"
ORIGENES = (ORIGEN_SEED, ORIGEN_API, ORIGEN_MANUAL)

# Estado en que se mide el alimento. Como las recetas se expresan en crudo (3.2)
# y 100 g de arroz crudo no son 100 g de arroz cocido, el estado forma parte de
# la identidad del alimento. Puede ser nulo cuando no aplica (aceite, pan).
ESTADOS = ("crudo", "cocinado", "conserva", "líquido")

# Los ocho valores del etiquetado obligatorio de la UE (3.8). Se listan aquí
# porque los recorren tanto la validación de la API como la carga de la semilla.
CAMPOS_NUTRICIONALES = (
    "energia_kcal",
    "grasas_g",
    "grasas_saturadas_g",
    "hidratos_g",
    "azucares_g",
    "fibra_g",
    "proteinas_g",
    "sal_g",
)


def _ahora():
    return datetime.now(timezone.utc)


def normalizar(texto):
    """Pasa a minúsculas y quita los acentos, para poder buscar sin distinguirlos.

    Se hace en Python y se guarda en una columna en vez de resolverlo en SQL con
    la extensión `unaccent`, que obligaría a instalarla en el servidor de base de
    datos y ataría la aplicación a PostgreSQL.
    """
    if texto is None:
        return None
    descompuesto = unicodedata.normalize("NFKD", texto.strip().lower())
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


class Alimento(db.Model):
    __tablename__ = "alimentos"

    id = db.Column(db.Integer, primary_key=True)

    # El nombre en español es lo que ven el usuario y la IA. El de USDA se guarda
    # aparte (`nombre_externo`) y solo se usa al importar (3.11).
    nombre = db.Column(db.String(160), nullable=False, index=True)
    # Copia sin acentos y en minúsculas del nombre, mantenida por el validador de
    # abajo. Es la columna contra la que se busca, y por eso lleva índice.
    nombre_normalizado = db.Column(db.String(160), nullable=False, index=True)
    categoria = db.Column(db.String(60), index=True)
    estado = db.Column(db.String(20))

    # Los ocho del etiquetado de la UE, por 100 g. Admiten nulo: USDA no siempre
    # publica azúcares o fibra, y un 0 inventado sería un dato falso.
    energia_kcal = db.Column(db.Float)
    grasas_g = db.Column(db.Float)
    grasas_saturadas_g = db.Column(db.Float)
    hidratos_g = db.Column(db.Float)
    azucares_g = db.Column(db.Float)
    fibra_g = db.Column(db.Float)
    proteinas_g = db.Column(db.Float)
    sal_g = db.Column(db.Float)

    # La cola larga (vitaminas, minerales, colesterol…): se muestra, pero no se
    # filtra ni se suma, así que no merece una columna propia (3.8).
    nutrientes_extra = db.Column(db.JSON)

    origen = db.Column(db.String(10), nullable=False, default=ORIGEN_MANUAL, index=True)
    # Identificador de USDA (fdcId). Nulo en los alimentos creados a mano.
    id_externo = db.Column(db.String(40))
    nombre_externo = db.Column(db.String(255))

    creado_en = db.Column(db.DateTime(timezone=True), default=_ahora)
    actualizado_en = db.Column(db.DateTime(timezone=True), default=_ahora, onupdate=_ahora)

    __table_args__ = (
        # Índice único parcial: impide importar dos veces el mismo alimento de
        # USDA, pero deja convivir todos los alimentos manuales, que no tienen
        # identificador externo.
        db.Index(
            "ix_alimentos_id_externo_unico",
            "id_externo",
            unique=True,
            postgresql_where=db.text("id_externo IS NOT NULL"),
        ),
    )

    @validates("nombre")
    def _sincronizar_nombre_normalizado(self, clave, valor):
        """Mantiene `nombre_normalizado` al día sin que nadie tenga que acordarse."""
        self.nombre_normalizado = normalizar(valor)
        return valor

    def to_dict(self, incluir_extra=True):
        """Diccionario para el JSON.

        `incluir_extra=False` en los listados: `nutrientes_extra` son unos cien
        nutrientes por alimento y multiplicarlos por una página entera daría
        respuestas de megabytes para un dato que ahí no se mira.
        """
        datos = {
            "id": self.id,
            "nombre": self.nombre,
            "categoria": self.categoria,
            "estado": self.estado,
            "energia_kcal": self.energia_kcal,
            "grasas_g": self.grasas_g,
            "grasas_saturadas_g": self.grasas_saturadas_g,
            "hidratos_g": self.hidratos_g,
            "azucares_g": self.azucares_g,
            "fibra_g": self.fibra_g,
            "proteinas_g": self.proteinas_g,
            "sal_g": self.sal_g,
            "origen": self.origen,
            "id_externo": self.id_externo,
            "nombre_externo": self.nombre_externo,
            "creado_en": self.creado_en.isoformat() if self.creado_en else None,
            "actualizado_en": self.actualizado_en.isoformat() if self.actualizado_en else None,
        }
        if incluir_extra:
            datos["nutrientes_extra"] = self.nutrientes_extra
        return datos
