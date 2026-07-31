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

COOKING_METHODS = (
    "raw", "boiled", "steamed", "microwaved", "griddled", "sauteed", "baked",
    "air_fried", "fried", "stewed",
)

SOURCE_AI = "ai"

# **Una comida se identifica por su posición dentro del día, no por un nombre**
# (3.16). Había una lista cerrada de cinco momentos y se rompía con un caso real:
# quien come ocho veces al día no cabe en cinco casillas, y ampliarla a ocho solo
# mueve el problema al noveno.
#
# Lo estable son tres ANCLAS —desayuno, comida y cena— y el resto de comidas
# repartidas entre ellas. Eso es lo que se le explica al modelo, en vez de darle
# una lista de nombres.
MIN_POSITION = 1
MAX_POSITION = 10
MEAL_ANCHORS = ("desayuno", "comida", "cena")

DEFAULT_MEALS_PER_DAY = 3


def meals_per_day_for(profile_value):
    """Cuántas comidas al día se le piden al modelo para un perfil.

    Un perfil sin la respuesta cae al valor por defecto; uno fuera de rango se
    recorta en vez de rechazarse, porque la API ya lo valida al guardarlo y aquí
    no hay a quién devolverle un 400.
    """
    if isinstance(profile_value, bool) or not isinstance(profile_value, int):
        return DEFAULT_MEALS_PER_DAY
    return max(MIN_POSITION, min(profile_value, MAX_POSITION))
