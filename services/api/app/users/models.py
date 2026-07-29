"""Modelo de datos del dominio Usuarios.

Una clase = una tabla. Un objeto = una fila. Un atributo = una columna.

Los campos que describen el perfil son los que la IA necesita para estimar
necesidades calóricas (3.9). Ni la edad ni el IMC se guardan: se derivan (3.5).
"""
from datetime import date

from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db

# Listas cerradas (3.7): la interfaz muestra un desplegable, la base de datos no
# se llena de variantes del mismo concepto y —sobre todo— la IA recibe y devuelve
# valores predecibles en lugar de texto libre que habría que interpretar.
SEXES = ("male", "female", "other")
ACTIVITY_LEVELS = ("sedentary", "light", "moderate", "high")
GOALS = ("lose_fat", "maintain", "gain_muscle")
FOOD_PREFERENCES = ("omnivore", "vegetarian", "vegan")
BODY_COMPOSITIONS = ("lean", "average", "athletic", "overweight")

# Campos del perfil que el usuario puede fijar al registrarse o editar. Se listan
# aquí porque los recorren tanto el alta como el PATCH.
PROFILE_FIELDS = (
    "name", "sex", "birth_date", "height_cm", "weight_kg",
    "activity_level", "goal", "meals_per_day", "food_preference",
    "body_composition", "waist_cm", "hip_cm", "neck_cm",
)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    # Guardamos el HASH de la contraseña, nunca la contraseña en claro.
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120))

    sex = db.Column(db.String(10))
    # La fecha de nacimiento en vez de la edad (3.5): "edad = 34" sería falso
    # dentro de un año y nadie iría a actualizarlo. Se persiste el hecho que no
    # cambia y se deriva el resto.
    birth_date = db.Column(db.Date)
    height_cm = db.Column(db.Integer)
    weight_kg = db.Column(db.Float)

    activity_level = db.Column(db.String(20))
    goal = db.Column(db.String(20))
    # Preferencia del usuario, no una restricción del plan: un plan puede tener
    # cinco comidas el lunes y tres el domingo.
    meals_per_day = db.Column(db.Integer)
    food_preference = db.Column(db.String(20))

    # El IMC no distingue músculo de grasa. Estos campos aportan el contexto que
    # por sí solo no da: la percepción del usuario y los perímetros, opcionales.
    body_composition = db.Column(db.String(20))
    waist_cm = db.Column(db.Float)
    hip_cm = db.Column(db.Float)
    neck_cm = db.Column(db.Float)

    def set_password(self, password):
        """Genera y guarda el hash (con sal) de la contraseña."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Comprueba si la contraseña coincide con el hash guardado."""
        return check_password_hash(self.password_hash, password)

    @property
    def age(self):
        """Años cumplidos hoy. Derivada, nunca guardada (3.5)."""
        if self.birth_date is None:
            return None
        today = date.today()
        # Restar solo los años daría un año de más a quien aún no ha cumplido:
        # el booleano corrige justamente ese caso.
        birthday_pending = (today.month, today.day) < (
            self.birth_date.month, self.birth_date.day
        )
        return today.year - self.birth_date.year - birthday_pending

    @property
    def bmi(self):
        """Índice de masa corporal. Derivado del peso y la altura actuales (3.5).

        Orientativo: no distingue músculo de grasa. La interfaz debe presentarlo
        como tal y acompañarlo de `body_composition` y los perímetros.
        """
        if not self.weight_kg or not self.height_cm:
            return None
        height_m = self.height_cm / 100
        return round(self.weight_kg / (height_m ** 2), 1)

    def to_dict(self):
        """Diccionario para el JSON. OJO: nunca incluimos el password_hash."""
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "sex": self.sex,
            "birth_date": self.birth_date.isoformat() if self.birth_date else None,
            "height_cm": self.height_cm,
            "weight_kg": self.weight_kg,
            "activity_level": self.activity_level,
            "goal": self.goal,
            "meals_per_day": self.meals_per_day,
            "food_preference": self.food_preference,
            "body_composition": self.body_composition,
            "waist_cm": self.waist_cm,
            "hip_cm": self.hip_cm,
            "neck_cm": self.neck_cm,
            # Derivados al vuelo: si mañana cambia el peso, el IMC cambia solo.
            "age": self.age,
            "bmi": self.bmi,
        }
