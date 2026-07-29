"""Traductor de USDA FoodData Central.

Todo el conocimiento sobre el formato de USDA vive aquí y en ningún otro sitio
(decisión 3.12 del diseño): si mañana cambian su respuesta, se arregla en este
fichero y el resto de la aplicación ni se entera. Y añadir una segunda fuente
sería escribir otro traductor, no tocar el modelo.

Deliberadamente **no importa nada de la aplicación** ni ninguna dependencia
externa: solo biblioteca estándar. Así el script de la semilla puede cargarlo
desde el host sin levantar Flask ni la base de datos.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.nal.usda.gov/fdc/v1"

# Solo alimentos genéricos: para escribir recetas hace falta "pechuga de pollo
# cruda", no un producto de marca con código de barras (3.11).
GENERIC_DATA_TYPES = ("Foundation", "SR Legacy")

# ---------------------------------------------------------------------------
# Correspondencia entre los nutrientes de USDA y nuestras ocho columnas.
#
# La clave es el `nutrientId` de FoodData Central, NO el nombre: hay nutrientes
# distintos que comparten nombre —1008 es "Energy" en kcal y 1062 es "Energy" en
# kilojulios—, así que emparejar por texto metería kilojulios en la columna de
# calorías. Verificado contra respuestas reales de la API, de los dos tipos de
# dato: los identificadores no están deducidos.
#
# Cada campo lleva una tupla de candidatos en orden de preferencia; se coge el
# primero que el alimento traiga, porque la cobertura de nutrientes no es igual
# en Foundation que en SR Legacy.
# ---------------------------------------------------------------------------
NUTRIENTS = {
    # 1008 = Energy (kcal), lo habitual en SR Legacy. Muchos alimentos Foundation
    # no la publican y solo dan la energía calculada por factores de Atwater:
    # 2048 (específicos del alimento, más precisos) antes que 2047 (generales).
    "energy_kcal": (1008, 2048, 2047),
    "fat_g": (1004,),                   # Total lipid (fat)
    "saturated_fat_g": (1258,),         # Fatty acids, total saturated
    # 1005 es "por diferencia", el estándar. 1050 ("por sumatorio") es el
    # respaldo de los Foundation modernos que ya no traen el anterior.
    "carbs_g": (1005, 1050),
    # 2000 es la medida vigente ("Total Sugars"); 1063 la antigua, que sigue
    # apareciendo en filas más viejas.
    "sugars_g": (2000, 1063),
    # 1079 es la fibra dietética clásica; 2033 el método AOAC 2011.25.
    "fiber_g": (1079, 2033),
    "protein_g": (1003,),               # Protein
}

# La UE etiqueta SAL, no sodio, y USDA da sodio en miligramos. La conversión del
# reglamento de etiquetado es sal = sodio × 2,5 (peso molecular del NaCl).
SODIUM_ID = 1093
SODIUM_TO_SALT_FACTOR = 2.5

# Sin estos cuatro el alimento no sirve para planificar una dieta: si faltan,
# el emparejamiento se descarta en vez de guardar una fila a medias.
REQUIRED_FIELDS = ("energy_kcal", "protein_g", "fat_g", "carbs_g")


class USDAError(Exception):
    """Fallo al consultar USDA.

    El mensaje nunca incluye la clave de la API: por eso se construye a mano a
    partir del código de error y no se propaga el texto de la excepción de
    urllib, que podría arrastrar la URL de la petición.
    """


class TimedOut(USDAError):
    """USDA no respondió a tiempo."""


class RateLimited(USDAError):
    """USDA devolvió 429: se ha superado el límite de peticiones por hora."""


class KeyRejected(USDAError):
    """USDA rechazó la clave (403). No se muestra su valor, solo el código."""


class NotFound(USDAError):
    """La búsqueda no devolvió ningún alimento genérico utilizable."""


class IncompleteResponse(USDAError):
    """El alimento existe pero no trae los nutrientes que necesitamos."""


def _api_key():
    key = os.environ.get("USDA_API_KEY", "").strip()
    if not key:
        raise USDAError("falta la variable de entorno USDA_API_KEY")
    return key


def search_foods(term, limit=10, timeout=20):
    """Busca alimentos genéricos en USDA y devuelve los resultados en bruto.

    La clave viaja en la cabecera `X-Api-Key` y no como parámetro de la URL: así
    no puede acabar en un log de acceso, en un proxy ni en una traza de error.
    """
    params = urllib.parse.urlencode({
        "query": term,
        "dataType": ",".join(GENERIC_DATA_TYPES),
        "pageSize": limit,
    })
    request = urllib.request.Request(
        f"{API_BASE}/foods/search?{params}",
        headers={"X-Api-Key": _api_key(), "Accept": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.load(response)
    except urllib.error.HTTPError as error:
        # Solo el código: el cuerpo o la URL del error podrían llevar la clave.
        if error.code == 429:
            raise RateLimited("límite de peticiones de USDA superado (429)") from None
        if error.code in (401, 403):
            raise KeyRejected(f"USDA rechazó la petición ({error.code})") from None
        raise USDAError(f"USDA respondió con un error HTTP {error.code}") from None
    except TimeoutError:
        raise TimedOut(f"USDA no respondió en {timeout} s") from None
    except urllib.error.URLError as error:
        # Un timeout de socket llega envuelto aquí en lugar de como TimeoutError.
        if isinstance(error.reason, TimeoutError):
            raise TimedOut(f"USDA no respondió en {timeout} s") from None
        raise USDAError("no se pudo contactar con USDA") from None
    except json.JSONDecodeError:
        raise USDAError("USDA devolvió una respuesta que no es JSON") from None

    results = body.get("foods") or []
    # El filtro `dataType` lo aplica el servidor, pero lo repetimos por si alguna
    # vez lo ignora: no queremos productos de marca en el catálogo.
    return [r for r in results if r.get("dataType") in GENERIC_DATA_TYPES]


def _values_by_id(result):
    """Aplana los nutrientes del resultado a {nutrientId: (valor, unidad, nombre)}.

    Los alimentos Foundation y SR Legacy publican sus valores por 100 g, que es
    justo la unidad del catálogo, así que no hay que escalar nada.
    """
    values = {}
    for nutrient in result.get("foodNutrients") or []:
        identifier = nutrient.get("nutrientId")
        value = nutrient.get("value")
        if identifier is None or value is None:
            continue
        values[identifier] = (
            value,
            nutrient.get("unitName") or "",
            nutrient.get("nutrientName") or "",
        )
    return values


def _first_available(values, candidates):
    for identifier in candidates:
        if identifier in values:
            # Algunos alimentos traen valores ligeramente negativos porque los
            # hidratos "por diferencia" salen de restar: como cantidad no tienen
            # sentido, se recortan a cero.
            return max(0.0, float(values[identifier][0]))
    return None


def translate_food(result):
    """Traduce un resultado de USDA a los campos de `Food`.

    Devuelve un diccionario listo para construir la fila. Lanza
    `IncompleteResponse` si faltan los nutrientes imprescindibles, para que el
    llamante pruebe con otro resultado en vez de guardar un alimento sin datos.
    """
    values = _values_by_id(result)

    translated = {
        field: _first_available(values, candidates)
        for field, candidates in NUTRIENTS.items()
    }

    sodium = values.get(SODIUM_ID)
    # El sodio viene en miligramos y la sal se etiqueta en gramos.
    translated["salt_g"] = (
        round(max(0.0, float(sodium[0])) * SODIUM_TO_SALT_FACTOR / 1000, 4)
        if sodium else None
    )

    missing = [f for f in REQUIRED_FIELDS if translated[f] is None]
    if missing:
        raise IncompleteResponse(
            f"al alimento {result.get('fdcId')} le faltan: {', '.join(missing)}"
        )

    # Todo lo que no ha entrado en las ocho columnas va al JSON. Se indexa por
    # nutrientId (como texto, porque las claves JSON lo son) en vez de por
    # nombre: el nombre se repite entre nutrientes distintos y se perderían.
    used = {SODIUM_ID}
    for candidates in NUTRIENTS.values():
        used.update(candidates)
    extra = {
        str(identifier): {"name": name, "unit": unit, "value": value}
        for identifier, (value, unit, name) in sorted(values.items())
        if identifier not in used
    }

    translated["extra_nutrients"] = extra
    translated["external_id"] = str(result.get("fdcId"))
    translated["external_name"] = result.get("description")
    return translated


def search_and_translate(term, limit=10):
    """Busca un término y traduce el primer resultado que traiga datos suficientes.

    Se recorren los resultados en el orden de relevancia de USDA en lugar de
    quedarse con el primero a secas: hay fichas —sobre todo de Foundation— que
    publican decenas de ácidos grasos pero ni calorías ni proteínas, y esas no
    sirven para el catálogo.
    """
    results = search_foods(term, limit=limit)
    if not results:
        raise NotFound(f"USDA no devolvió alimentos genéricos para «{term}»")

    for result in results:
        try:
            return translate_food(result)
        except IncompleteResponse:
            continue

    raise IncompleteResponse(
        f"ninguno de los {len(results)} resultados de «{term}» trae los "
        "nutrientes imprescindibles"
    )
