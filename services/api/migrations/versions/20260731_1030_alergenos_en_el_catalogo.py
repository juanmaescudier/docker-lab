"""Los alimentos declaran qué alérgenos llevan.

`foods` tenía nombre, categoría, estado y nutrientes, y **nada sobre alérgenos**,
así que no había forma de filtrar el catálogo por alergia. Ese filtro es el que
sostiene la decisión 3.17: una alergia no se le pide al modelo, se le quita del
catálogo.

Es un array y no una tabla aparte porque no tiene atributos propios ni se
consulta nunca "dame los alimentos con sésamo": solo se cruza con las alergias
del usuario para quitar filas, y para eso el operador `&&` de PostgreSQL basta.

**Admite nulo a propósito, y el nulo NO significa "no lleva ninguno".** Significa
"nadie lo ha revisado". Un alimento sin revisar no entra en la lista que ve el
modelo si el usuario ha declarado alguna alergia: prefiero un plan con menos
opciones que uno con cacahuetes para un alérgico. El defecto es el seguro, igual
que con la marca de revisado (3.21), con la que acabará juntándose.

**Y por eso esta migración sí rellena los 45 de la semilla.** Podría dejarlos a
nulo y ser coherente con la regla, pero el resultado sería que el catálogo entero
desaparece para cualquier usuario con una alergia y la aplicación respondería
"el catálogo está vacío". Las filas de la semilla están revisadas una a una —la
marca vive en `scripts/generate_seed.py`, que es de donde sale el JSON—, así que
lo honesto es escribirlas.

La correspondencia va copiada aquí y no importada de la aplicación: una migración
tiene que seguir corriendo igual dentro de un año, cuando la semilla ya sea otra.
Solo toca filas con `source = 'seed'` y el nombre exacto; lo que alguien haya
editado a mano o importado de USDA se queda sin revisar, que es lo correcto.

Revision ID: b8f3c2d17e40
Revises: e5b2f7c1a3d9
Create Date: 2026-07-31 10:30:00.000000
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'b8f3c2d17e40'
down_revision = 'e5b2f7c1a3d9'
branch_labels = None
depends_on = None


# Los 45 de la semilla, tal y como estaban marcados el día de esta migración.
# Una tupla vacía es "revisado, no lleva ninguno", que NO es lo mismo que nulo.
SEED_ALLERGENS = {
    "pechuga de pollo": (),
    "muslo de pollo": (),
    "huevo de gallina": ("eggs",),
    "clara de huevo": ("eggs",),
    "ternera, filete magro": (),
    "lomo de cerdo": (),
    "salmón": ("fish",),
    "bacalao": ("fish",),
    "atún en conserva al natural": ("fish",),
    "gambas": ("crustaceans",),
    "leche entera": ("milk",),
    "leche desnatada": ("milk",),
    "yogur natural": ("milk",),
    "queso fresco batido": ("milk",),
    "queso curado": ("milk",),
    "arroz blanco": (),
    "arroz integral": (),
    "pasta": ("gluten",),
    "avena en copos": ("gluten",),
    "quinoa": (),
    "pan blanco": ("gluten",),
    "pan integral": ("gluten",),
    "patata": (),
    "boniato": (),
    "lentejas": (),
    "garbanzos": (),
    "alubias blancas": (),
    "aceite de oliva virgen extra": (),
    "aguacate": (),
    "almendras": ("nuts",),
    "nueces": ("nuts",),
    "cacahuetes": ("peanuts",),
    "plátano": (),
    "manzana": (),
    "naranja": (),
    "fresas": (),
    "tomate": (),
    "cebolla": (),
    "pimiento rojo": (),
    "brócoli": (),
    "espinacas": (),
    "calabacín": (),
    "lechuga": (),
    "zanahoria": (),
    "champiñones": (),
}


def upgrade():
    op.add_column(
        "foods",
        sa.Column("allergens", postgresql.ARRAY(sa.String(length=20)), nullable=True),
    )

    # Parametrizado y fila a fila: los nombres llevan acentos y comas, y montar
    # un `UPDATE ... CASE` interpolando texto a mano en SQL es exactamente lo que
    # no se hace nunca (3.19), aunque aquí el texto sea mío.
    connection = op.get_bind()
    statement = sa.text(
        "UPDATE foods SET allergens = :allergens, updated_at = NOW() "
        " WHERE name = :name AND source = 'seed'"
    ).bindparams(sa.bindparam("allergens", type_=postgresql.ARRAY(sa.String)))

    for name, allergens in SEED_ALLERGENS.items():
        connection.execute(statement, {"name": name, "allergens": list(allergens)})


def downgrade():
    op.drop_column("foods", "allergens")
