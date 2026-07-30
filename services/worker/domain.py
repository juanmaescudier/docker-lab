"""Las listas cerradas del dominio, tal y como las guarda la base de datos.

Están duplicadas respecto a `app/plans/models.py` y `app/recipes/models.py`. Es
la misma deuda que ya asume el ADR-0008 con los nombres de tablas y columnas: el
worker **no usa el ORM**, así que sus dependencias son dos líneas en vez de
siete, y a cambio hay valores escritos en dos sitios. Si cambia una lista, hay
que tocar los dos.

Se mantienen aquí y no repartidas por el código porque son a la vez lo que se le
permite al modelo y lo que se valida después: un solo sitio donde mirar.
"""

DAYS_OF_WEEK = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
)

MEAL_SLOTS = ("breakfast", "mid_morning", "lunch", "afternoon_snack", "dinner")

COOKING_METHODS = (
    "raw", "boiled", "steamed", "microwaved", "griddled", "sauteed", "baked",
    "air_fried", "fried", "stewed",
)

SOURCE_AI = "ai"

# Qué momentos del día se piden según las comidas que haga el usuario. Repartir
# cuatro comidas como desayuno, comida, merienda y cena es más razonable que
# quedarse con los cuatro primeros de la lista, que dejaría fuera la cena.
SLOTS_BY_MEALS_PER_DAY = {
    1: ("lunch",),
    2: ("lunch", "dinner"),
    3: ("breakfast", "lunch", "dinner"),
    4: ("breakfast", "lunch", "afternoon_snack", "dinner"),
    5: MEAL_SLOTS,
}

DEFAULT_MEALS_PER_DAY = 3


def slots_for(meals_per_day):
    """Momentos del día que se le piden al modelo para un perfil."""
    if not isinstance(meals_per_day, int) or meals_per_day not in SLOTS_BY_MEALS_PER_DAY:
        meals_per_day = DEFAULT_MEALS_PER_DAY
    return SLOTS_BY_MEALS_PER_DAY[meals_per_day]
