"""Modelo de datos del dominio Usuarios.

Una clase = una tabla. Un objeto = una fila. Un atributo = una columna.

Los campos que describen el perfil son los que la IA necesita para estimar
necesidades calóricas (3.9). Ni la edad ni el IMC se guardan: se derivan (3.5).
"""
from datetime import date

from werkzeug.security import check_password_hash, generate_password_hash

from ..catalog.models import ALLERGENS
from ..extensions import db
from ..recipes.models import COOKING_METHODS

# Listas cerradas (3.7): la interfaz muestra un desplegable, la base de datos no
# se llena de variantes del mismo concepto y —sobre todo— la IA recibe y devuelve
# valores predecibles en lugar de texto libre que habría que interpretar.
SEXES = ("male", "female", "other")
ACTIVITY_LEVELS = ("sedentary", "light", "moderate", "high")
GOALS = ("lose_fat", "maintain", "gain_muscle")
FOOD_PREFERENCES = ("omnivore", "vegetarian", "vegan")
BODY_COMPOSITIONS = ("lean", "average", "athletic", "overweight")

# A qué ritmo quiere llegar al objetivo. De los que más cambian el resultado: el
# ritmo decide el déficit, y hasta ahora solo estaba el objetivo.
GOAL_PACES = ("gentle", "moderate", "fast")

# Bloque 8 del cuestionario. `no` es un valor y no un nulo: "no entreno" es una
# respuesta, y no saberlo es otra cosa.
TRAINING_TYPES = ("no", "strength", "cardio", "mixed", "sport")

# Intolerancias, que NO son alergias (3.17): la alergia es absoluta y quita el
# alimento del catálogo; la intolerancia tiene dosis y es una restricción con
# cantidad. Por eso van en listas distintas y la intolerancia lleva su nivel.
#
# La celiaquía no está aquí: es una enfermedad autoinmune con exclusión absoluta
# y va con las alergias, dentro de los cereales con gluten.
INTOLERANCES = ("lactose", "gluten_non_celiac", "fructose", "sorbitol", "histamine")
TOLERANCE_LEVELS = ("none", "small", "moderate")

# Campos del perfil que el usuario puede fijar al registrarse o editar. Se listan
# aquí porque los recorren tanto el alta como el PATCH.
PROFILE_FIELDS = (
    "name", "sex", "birth_date", "height_cm", "weight_kg",
    "activity_level", "goal", "goal_pace", "meals_per_day", "food_preference",
    "body_composition", "waist_cm", "hip_cm", "neck_cm",
    "training_type", "training_days_per_week",
)

# ------------------------------------------------------------------ preferencias
#
# **El criterio para decidir dónde vive cada respuesta es uno solo** (3.16): ¿hay
# código Python que decida algo mirando ese valor? Si sí, es una columna, porque
# necesita tipo, restricción y poder aparecer en un `WHERE`. Si solo acaba
# convertido en palabras dentro del prompt, va aquí.
#
# Y va aquí porque **esto es lo que evoluciona**: voy a añadir y quitar preguntas
# cada semana mientras afino el prompt, y si cada una cuesta una migración
# acabaré por no añadirlas. Es el mismo criterio de `extra_nutrients` (3.8).
#
# Cada entrada dice qué forma tiene el valor, y con eso se valida en el servidor:
#   choice → uno de la lista        multi → varios de la lista
#   bool   → sí o no                text  → LA ÚNICA entrada libre (3.19)
PREFERENCE_SPEC = {
    # Bloque 4 · cómo comes
    "dessert": {"type": "choice", "options": ("none", "lunch", "dinner", "both")},
    "weekend": {"type": "choice", "options": ("same", "looser", "very_different")},
    # Bloque 5 · cómo cocinas
    #
    # Los métodos de cocción **filtran de verdad**: si no marca horno, no aparecen
    # recetas al horno. Podrían ir en columna por eso, pero el filtro no es una
    # consulta a la base de datos —no hay `WHERE cooking_method IN (...)` en
    # ningún sitio—, sino el `enum` del esquema JSON que se le manda al modelo.
    # Desde aquí sale igual de bien y sin migración, así que se quedan.
    "cooking_methods": {"type": "multi", "options": COOKING_METHODS},
    "cooking_time": {"type": "choice", "options": ("quick", "normal", "relaxed")},
    "freezer": {"type": "bool"},
    # Bloque 6 · la compra
    "shopping_frequency": {
        "type": "choice", "options": ("daily", "twice_week", "weekly", "biweekly"),
    },
    "budget": {"type": "choice", "options": ("tight", "normal", "generous")},
    # Bloque 7 · gustos
    "spicy": {"type": "choice", "options": ("none", "mild", "love_it")},
    "variety": {"type": "choice", "options": ("low", "balanced", "high")},
    "breakfast_variety": {"type": "choice", "options": ("same_every_day", "varied")},
    "daily_drinks": {
        "type": "multi", "options": ("coffee", "milk", "soft_drinks", "alcohol"),
    },
    "weighs_food": {"type": "choice", "options": ("weighs", "estimates")},
    # Bloque 8 · detalles del entrenamiento (el tipo y los días son columna)
    "training_days": {
        "type": "multi",
        "options": ("monday", "tuesday", "wednesday", "thursday", "friday",
                    "saturday", "sunday"),
    },
    "training_time": {
        "type": "choice", "options": ("morning", "midday", "evening", "night"),
    },
    "different_on_training_days": {"type": "bool"},
    # Bloque 9 · LA ÚNICA PREGUNTA ABIERTA de todo el cuestionario (3.19).
    # Tratada como hostil por defecto: límite de longitud aquí, delimitada en el
    # prompt como dato del usuario, escapada al pintarla y parametrizada en la
    # base de datos como todo lo demás.
    "previous_attempts": {"type": "text", "max_length": 1000},
}

# Qué preferencias viajan hacia el modelo. Se listan en vez de mandar el JSON
# entero para que añadir una pregunta interna —una que solo lea la interfaz— no
# acabe automáticamente dentro de un prompt que va a un tercero.
PREFERENCES_FOR_AI = tuple(PREFERENCE_SPEC)


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
    goal_pace = db.Column(db.String(20))
    # Preferencia del usuario, no una restricción del plan: un plan puede tener
    # cinco comidas el lunes y tres el domingo.
    meals_per_day = db.Column(db.Integer)
    food_preference = db.Column(db.String(20))

    # Entrenamiento (bloque 8). Va en el asistente inicial y no en ajustes: la
    # actividad física cambia las necesidades, y preguntarla al final o no
    # preguntarla es renunciar a la ventaja que da conocer el terreno.
    training_type = db.Column(db.String(20))
    training_days_per_week = db.Column(db.Integer)

    # **Del cribado se guarda que pasó y cuándo, nunca qué declaró** (3.18).
    # "Este usuario tiene diabetes" es un dato de salud de categoría especial que
    # no hace falta para nada: la única decisión que depende de él es seguir o no
    # seguir, y esa decisión ya está tomada cuando se escribe esta fecha.
    #
    # Fecha anulable en vez de booleano, aquí y en `onboarded_at`: dice si pasó y
    # además cuándo, gratis.
    screening_passed_at = db.Column(db.DateTime(timezone=True))
    onboarded_at = db.Column(db.DateTime(timezone=True))

    # Todo lo que solo acaba siendo palabras dentro del prompt (3.16). La forma de
    # cada clave la fija `PREFERENCE_SPEC`, que es lo que se valida en el servidor.
    preferences = db.Column(db.JSON, nullable=False, default=dict)

    # El IMC no distingue músculo de grasa. Estos campos aportan el contexto que
    # por sí solo no da: la percepción del usuario y los perímetros, opcionales.
    body_composition = db.Column(db.String(20))
    waist_cm = db.Column(db.Float)
    hip_cm = db.Column(db.Float)
    neck_cm = db.Column(db.Float)

    # Las tres relaciones que NO caben en una columna JSON porque gobiernan una
    # consulta: son las que quitan filas del catálogo antes de que el modelo lo
    # vea (3.16, 3.17).
    allergens = db.relationship(
        "UserAllergen", cascade="all, delete-orphan", lazy="selectin"
    )
    intolerances = db.relationship(
        "UserIntolerance", cascade="all, delete-orphan", lazy="selectin"
    )
    excluded_foods = db.relationship(
        "UserExcludedFood", cascade="all, delete-orphan", lazy="selectin"
    )

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

    def allergen_values(self):
        """Los alérgenos declarados, en una lista plana para filtrar el catálogo."""
        return [row.allergen for row in self.allergens]

    def excluded_food_ids(self):
        """Los alimentos que el usuario no quiere ver, por identificador.

        Se guarda el `food_id` y nunca lo que tecleó (3.16): el usuario busca por
        nombre, pero lo que queda es una clave ajena. Así el filtro es una
        consulta y no hay una entrada libre más llegando al prompt.
        """
        return [row.food_id for row in self.excluded_foods]

    def ai_profile(self):
        """El perfil tal y como viaja en el `input` de un trabajo del modelo.

        Solo lo que el modelo necesita para planificar (3.9): ni el email ni el
        identificador, que no aportan nada a la decisión y son dato personal que
        no tiene por qué salir hacia un servicio de terceros.

        Va la **edad**, no la fecha de nacimiento: es lo que se usa para estimar
        necesidades, y es un dato menos identificativo.

        **No van las alergias, y es a propósito.** Una alergia no se le pide al
        modelo, se le quita del catálogo (3.17): los alimentos que la contienen no
        están en la lista que recibe, así que no puede usarlos ni queriendo.
        Mandársela además como prosa daría la falsa impresión de que la seguridad
        depende de que él se acuerde, y no depende ni debe depender.

        **Las intolerancias sí van**, por lo contrario: no son una exclusión sino
        una restricción con cantidad —mucha gente tolera un yogur y no un vaso de
        leche—, y eso solo lo puede resolver quien decide las cantidades.

        **Tampoco va el cribado.** No hay nada que contar: si esta persona no lo
        hubiera pasado, no habría plan que generar (3.18).
        """
        return {
            "sex": self.sex,
            "age": self.age,
            "height_cm": self.height_cm,
            "weight_kg": self.weight_kg,
            "bmi": self.bmi,
            "activity_level": self.activity_level,
            "goal": self.goal,
            "goal_pace": self.goal_pace,
            "meals_per_day": self.meals_per_day,
            "food_preference": self.food_preference,
            "body_composition": self.body_composition,
            "training_type": self.training_type,
            "training_days_per_week": self.training_days_per_week,
            "intolerances": [row.to_dict() for row in self.intolerances],
            "preferences": {
                key: value
                for key, value in (self.preferences or {}).items()
                if key in PREFERENCES_FOR_AI
            },
        }

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
            "goal_pace": self.goal_pace,
            "meals_per_day": self.meals_per_day,
            "food_preference": self.food_preference,
            "body_composition": self.body_composition,
            "waist_cm": self.waist_cm,
            "hip_cm": self.hip_cm,
            "neck_cm": self.neck_cm,
            "training_type": self.training_type,
            "training_days_per_week": self.training_days_per_week,
            # Del cribado solo sale la fecha. Qué condición marcó no está guardado
            # en ninguna parte, así que no hay nada que devolver aquí (3.18).
            "screening_passed_at": (
                self.screening_passed_at.isoformat()
                if self.screening_passed_at else None
            ),
            "onboarded_at": (
                self.onboarded_at.isoformat() if self.onboarded_at else None
            ),
            "preferences": self.preferences or {},
            "allergens": self.allergen_values(),
            "intolerances": [row.to_dict() for row in self.intolerances],
            "excluded_food_ids": self.excluded_food_ids(),
            # Derivados al vuelo: si mañana cambia el peso, el IMC cambia solo.
            "age": self.age,
            "bmi": self.bmi,
        }


class UserAllergen(db.Model):
    """Un alérgeno declarado por un usuario, de la lista cerrada de 14.

    **No es una clave ajena a `foods`**: es una lista fija de la que también se
    marcan los alimentos. Apuntar a una fila del catálogo sería decir "soy
    alérgico a esta pechuga concreta" en lugar de "al huevo".

    Tabla propia y no una columna JSON porque esto **gobierna una consulta**
    (3.16): es lo que quita filas del catálogo antes de que el modelo lo vea.
    """

    __tablename__ = "user_allergens"

    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    allergen = db.Column(db.String(20), primary_key=True)

    __table_args__ = (
        # La lista cerrada, impuesta por la base de datos y no solo por la
        # validación: es un dato de seguridad y no puede depender de que todos
        # los caminos de escritura se acuerden de comprobarlo.
        db.CheckConstraint(
            "allergen IN (" + ", ".join(f"'{a}'" for a in ALLERGENS) + ")",
            name="ck_user_allergens_closed_list",
        ),
    )


class UserIntolerance(db.Model):
    """Una intolerancia declarada, **con su nivel de tolerancia**.

    Lo que la separa de una alergia es que tiene dosis: mucha gente con
    intolerancia a la lactosa tolera un yogur y no un vaso de leche (3.17). Por
    eso no quita alimentos del catálogo, viaja hasta el modelo con su nivel y es
    él quien decide las cantidades.
    """

    __tablename__ = "user_intolerances"

    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    intolerance = db.Column(db.String(30), primary_key=True)
    tolerance = db.Column(db.String(20), nullable=False)

    __table_args__ = (
        db.CheckConstraint(
            "intolerance IN (" + ", ".join(f"'{i}'" for i in INTOLERANCES) + ")",
            name="ck_user_intolerances_closed_list",
        ),
        db.CheckConstraint(
            "tolerance IN (" + ", ".join(f"'{t}'" for t in TOLERANCE_LEVELS) + ")",
            name="ck_user_intolerances_tolerance_level",
        ),
    )

    def to_dict(self):
        return {"intolerance": self.intolerance, "tolerance": self.tolerance}


class UserExcludedFood(db.Model):
    """Un alimento que el usuario no quiere ver. Clave ajena de verdad.

    Aquí sí se apunta al catálogo, porque "no me pongas coliflor" habla de una
    fila concreta. El usuario la busca por nombre, pero **lo que se guarda es el
    identificador y nunca lo que tecleó** (3.16): así el filtro es una consulta y
    no hay texto libre llegando al prompt.

    CASCADE por los dos lados: si se borra el alimento del catálogo, el veto deja
    de tener sentido; si se borra la cuenta, se va con ella.
    """

    __tablename__ = "user_excluded_foods"

    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    food_id = db.Column(
        db.Integer, db.ForeignKey("foods.id", ondelete="CASCADE"), primary_key=True
    )
