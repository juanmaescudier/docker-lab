"""Modelo de datos del dominio Catálogo.

Cada fila es un alimento específico y medible ("pechuga de pollo, cruda"), no un
concepto ("pollo"): decisión 3.3 del diseño. Los valores son siempre por 100 g,
que es el dato fijo y universal; los gramos de una receta concreta viven en la
relación, no aquí (3.4).
"""
import unicodedata
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import ARRAY
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

# Los **14 alérgenos de declaración obligatoria** del anexo II del reglamento
# europeo de información alimentaria. Se usa esa lista y no una inventada por tres
# motivos: es la que la gente ya conoce de las etiquetas, es exhaustiva para lo
# que la ley considera relevante, y evita discutir qué entra y qué no.
#
# La misma lista vale para marcar un alimento y para que el usuario declare sus
# alergias: por eso vive aquí y la importa el dominio de usuarios, en vez de estar
# escrita dos veces.
ALLERGENS = (
    "gluten",        # cereales con gluten (trigo, centeno, cebada, avena...)
    "crustaceans",   # crustáceos
    "eggs",          # huevos
    "fish",          # pescado
    "peanuts",       # cacahuetes: alérgeno propio, NO son frutos de cáscara
    "soy",           # soja
    "milk",          # leche y derivados, lactosa incluida
    "nuts",          # frutos de cáscara (almendra, nuez, avellana, anacardo...)
    "celery",        # apio
    "mustard",       # mostaza
    "sesame",        # granos de sésamo
    "sulphites",     # dióxido de azufre y sulfitos por encima de 10 mg/kg
    "lupin",         # altramuces
    "molluscs",      # moluscos
)


# Qué categorías del catálogo quedan fuera según la preferencia alimentaria. La
# preferencia **filtra el catálogo** (3.16), y filtrarlo hace falta que se pueda
# decidir mirando la fila: la categoría es lo único que hay.
#
# Es una correspondencia frágil y conviene saberlo: las categorías las escribe a
# mano quien genera la semilla, así que una categoría nueva —"cordero"— no
# estaría en ninguna de estas listas y un vegano la vería. Aguanta mientras el
# catálogo lo escriba yo; en cuanto entre la importación de USDA hará falta que
# el alimento diga si es de origen animal, igual que dice sus alérgenos.
MEAT_AND_FISH_CATEGORIES = ("pollo", "ternera", "cerdo", "pescado", "marisco")
ANIMAL_PRODUCT_CATEGORIES = ("lacteo", "huevo")

EXCLUDED_CATEGORIES_BY_PREFERENCE = {
    "vegetarian": MEAT_AND_FISH_CATEGORIES,
    "vegan": MEAT_AND_FISH_CATEGORIES + ANIMAL_PRODUCT_CATEGORIES,
}


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

    # Qué alérgenos de los 14 obligatorios lleva este alimento (3.17). Es una
    # lista y no una tabla aparte porque no tiene atributos propios ni se consulta
    # nunca "dame los alimentos con sésamo": solo se cruza con las alergias del
    # usuario para QUITAR filas, y para eso un `&&` sobre el array basta.
    #
    # **El nulo no significa "no tiene alérgenos", significa "no lo sé"**, y por eso
    # la columna admite nulo en vez de tener `[]` por defecto. Un alimento sin
    # revisar no entra en la lista que ve el modelo si el usuario ha declarado
    # alguna alergia: prefiero un plan con menos opciones que uno con cacahuetes
    # para un alérgico. Es el mismo criterio de "el defecto es el seguro" que la
    # marca de revisado (3.21), con la que acabará juntándose.
    allergens = db.Column(ARRAY(db.String(20)))

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
            # Va también en los listados: es dato de seguridad, y una interfaz que
            # tenga que pedir el alimento entero para saber si lleva cacahuete
            # acabará por no preguntarlo.
            "allergens": self.allergens,
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
