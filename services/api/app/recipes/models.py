"""Modelo de datos del dominio Recetas.

Una receta lleva varios alimentos y un alimento aparece en varias recetas: es una
relación muchos a muchos. Y como además lleva un dato propio —los gramos—, no
basta con una tabla de unión: es una entidad, `RecipeIngredient` (decisión 3.4).

Las cantidades se expresan **en crudo** (3.2). 100 g de arroz crudo no son 100 g
de arroz cocido, y mezclar ambos estados daría cálculos erróneos.
"""
from datetime import datetime, timezone

from ..catalog.models import NUTRITION_FIELDS
from ..extensions import db

# El método de cocción no cambia los valores nutricionales (que son del alimento
# crudo): es información para quien cocina (3.2).
COOKING_METHODS = (
    "raw", "boiled", "steamed", "microwaved", "griddled", "sauteed", "baked",
    "air_fried", "fried", "stewed",
)

SOURCE_AI = "ai"
SOURCE_MANUAL = "manual"
SOURCES = (SOURCE_AI, SOURCE_MANUAL)


def _now():
    return datetime.now(timezone.utc)


class Recipe(db.Model):
    __tablename__ = "recipes"

    id = db.Column(db.Integer, primary_key=True)

    # Nulo = receta del sistema, visible para todos. Por eso la columna admite
    # nulo en lugar de apuntar a un usuario "sistema" ficticio.
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    name = db.Column(db.String(160), nullable=False, index=True)
    steps = db.Column(db.Text)
    cooking_method = db.Column(db.String(20))
    servings = db.Column(db.Integer, nullable=False, default=1)
    source = db.Column(db.String(10), nullable=False, default=SOURCE_MANUAL)

    created_at = db.Column(db.DateTime(timezone=True), default=_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now)

    # `delete-orphan` para que quitar un ingrediente de la lista lo borre de la
    # tabla; el ON DELETE CASCADE de la clave ajena cubre el borrado de la receta
    # entera aunque no pase por el ORM.
    ingredients = db.relationship(
        "RecipeIngredient",
        back_populates="recipe",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        db.CheckConstraint("servings > 0", name="ck_recipes_servings_positive"),
    )

    def nutrition_summary(self):
        """Suma los valores de los ingredientes: valor_por_100g × gramos ÷ 100.

        **Calculado, nunca guardado.** Si mañana se corrigen los valores de un
        alimento, los totales de todas sus recetas quedan corregidos solos; si se
        hubieran copiado en la receta, habría que actualizar miles de filas y
        acabarían divergiendo (3.4).
        """
        totals = {field: None for field in NUTRITION_FIELDS}
        incomplete = set()

        for ingredient in self.ingredients:
            factor = ingredient.grams / 100
            for field in NUTRITION_FIELDS:
                value = getattr(ingredient.food, field)
                if value is None:
                    # Un nulo del catálogo es "no lo sabemos", no un cero: hay
                    # alimentos de USDA sin fibra o sin azúcares publicados.
                    # Sumarlo como 0 daría un total falsamente preciso.
                    incomplete.add(field)
                    continue
                totals[field] = (totals[field] or 0.0) + value * factor

        def rounded(values, divisor=1):
            return {
                field: (round(v / divisor, 2) if v is not None else None)
                for field, v in values.items()
            }

        return {
            "totals": rounded(totals),
            "per_serving": rounded(totals, self.servings or 1),
            # Qué nutrientes tienen algún ingrediente sin dato. Sin esto, "0 g de
            # fibra" y "no sabemos la fibra" se verían igual.
            "incomplete_nutrients": sorted(incomplete),
        }

    def to_dict(self, include_ingredients=True):
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "steps": self.steps,
            "cooking_method": self.cooking_method,
            "servings": self.servings,
            "source": self.source,
            "is_system": self.user_id is None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_ingredients:
            data["ingredients"] = [i.to_dict() for i in self.ingredients]
            data["nutrition"] = self.nutrition_summary()
        else:
            data["ingredient_count"] = len(self.ingredients)
        return data


class RecipeIngredient(db.Model):
    __tablename__ = "recipe_ingredients"

    id = db.Column(db.Integer, primary_key=True)
    recipe_id = db.Column(
        db.Integer, db.ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # RESTRICT, no CASCADE: borrar un alimento del catálogo no debe vaciar en
    # silencio las recetas que lo usan. El catálogo devuelve 409 y obliga a
    # decidir qué hacer con ellas.
    food_id = db.Column(
        db.Integer, db.ForeignKey("foods.id", ondelete="RESTRICT"), nullable=False
    )
    grams = db.Column(db.Float, nullable=False)

    recipe = db.relationship("Recipe", back_populates="ingredients")
    food = db.relationship("Food", lazy="joined")

    __table_args__ = (
        db.CheckConstraint("grams > 0", name="ck_recipe_ingredients_grams_positive"),
        # El mismo alimento dos veces en una receta duplicaría su aporte en los
        # totales sin que se notara.
        db.UniqueConstraint("recipe_id", "food_id", name="uq_ingredient_per_recipe"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "food_id": self.food_id,
            # El nombre evita que quien consume la API tenga que pedir el
            # alimento aparte solo para poder mostrar la lista.
            "food": self.food.name if self.food else None,
            "category": self.food.category if self.food else None,
            "grams": self.grams,
        }
