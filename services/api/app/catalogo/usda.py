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
TIPOS_DATO_GENERICOS = ("Foundation", "SR Legacy")

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
NUTRIENTES = {
    # 1008 = Energy (kcal), lo habitual en SR Legacy. Muchos alimentos Foundation
    # no la publican y solo dan la energía calculada por factores de Atwater:
    # 2048 (específicos del alimento, más precisos) antes que 2047 (generales).
    "energia_kcal": (1008, 2048, 2047),
    "grasas_g": (1004,),                # Total lipid (fat)
    "grasas_saturadas_g": (1258,),      # Fatty acids, total saturated
    # 1005 es "por diferencia", el estándar. 1050 ("por sumatorio") es el
    # respaldo de los Foundation modernos que ya no traen el anterior.
    "hidratos_g": (1005, 1050),
    # 2000 es la medida vigente ("Total Sugars"); 1063 la antigua, que sigue
    # apareciendo en filas más viejas.
    "azucares_g": (2000, 1063),
    # 1079 es la fibra dietética clásica; 2033 el método AOAC 2011.25.
    "fibra_g": (1079, 2033),
    "proteinas_g": (1003,),             # Protein
}

# La UE etiqueta SAL, no sodio, y USDA da sodio en miligramos. La conversión del
# reglamento de etiquetado es sal = sodio × 2,5 (peso molecular del NaCl).
SODIO_ID = 1093
FACTOR_SODIO_A_SAL = 2.5

# Sin estos cuatro el alimento no sirve para planificar una dieta: si faltan,
# el emparejamiento se descarta en vez de guardar una fila a medias.
IMPRESCINDIBLES = ("energia_kcal", "proteinas_g", "grasas_g", "hidratos_g")


class ErrorUSDA(Exception):
    """Fallo al consultar USDA.

    El mensaje nunca incluye la clave de la API: por eso se construye a mano a
    partir del código de error y no se propaga el texto de la excepción de
    urllib, que podría arrastrar la URL de la petición.
    """


class TiempoAgotado(ErrorUSDA):
    """USDA no respondió a tiempo."""


class LimitePeticiones(ErrorUSDA):
    """USDA devolvió 429: se ha superado el límite de peticiones por hora."""


class ClaveRechazada(ErrorUSDA):
    """USDA rechazó la clave (403). No se muestra su valor, solo el código."""


class NoEncontrado(ErrorUSDA):
    """La búsqueda no devolvió ningún alimento genérico utilizable."""


class RespuestaIncompleta(ErrorUSDA):
    """El alimento existe pero no trae los nutrientes que necesitamos."""


def _clave():
    clave = os.environ.get("USDA_API_KEY", "").strip()
    if not clave:
        raise ErrorUSDA("falta la variable de entorno USDA_API_KEY")
    return clave


def buscar_alimentos(termino, limite=10, tiempo_espera=20):
    """Busca alimentos genéricos en USDA y devuelve los resultados en bruto.

    La clave viaja en la cabecera `X-Api-Key` y no como parámetro de la URL: así
    no puede acabar en un log de acceso, en un proxy ni en una traza de error.
    """
    parametros = urllib.parse.urlencode({
        "query": termino,
        "dataType": ",".join(TIPOS_DATO_GENERICOS),
        "pageSize": limite,
    })
    peticion = urllib.request.Request(
        f"{API_BASE}/foods/search?{parametros}",
        headers={"X-Api-Key": _clave(), "Accept": "application/json"},
    )

    try:
        with urllib.request.urlopen(peticion, timeout=tiempo_espera) as respuesta:
            cuerpo = json.load(respuesta)
    except urllib.error.HTTPError as error:
        # Solo el código: el cuerpo o la URL del error podrían llevar la clave.
        if error.code == 429:
            raise LimitePeticiones("límite de peticiones de USDA superado (429)") from None
        if error.code in (401, 403):
            raise ClaveRechazada(f"USDA rechazó la petición ({error.code})") from None
        raise ErrorUSDA(f"USDA respondió con un error HTTP {error.code}") from None
    except TimeoutError:
        raise TiempoAgotado(f"USDA no respondió en {tiempo_espera} s") from None
    except urllib.error.URLError as error:
        # Un timeout de socket llega envuelto aquí en lugar de como TimeoutError.
        if isinstance(error.reason, TimeoutError):
            raise TiempoAgotado(f"USDA no respondió en {tiempo_espera} s") from None
        raise ErrorUSDA("no se pudo contactar con USDA") from None
    except json.JSONDecodeError:
        raise ErrorUSDA("USDA devolvió una respuesta que no es JSON") from None

    resultados = cuerpo.get("foods") or []
    # El filtro `dataType` lo aplica el servidor, pero lo repetimos por si alguna
    # vez lo ignora: no queremos productos de marca en el catálogo.
    return [r for r in resultados if r.get("dataType") in TIPOS_DATO_GENERICOS]


def _valores_por_id(resultado):
    """Aplana los nutrientes del resultado a {nutrientId: (valor, unidad, nombre)}.

    Los alimentos Foundation y SR Legacy publican sus valores por 100 g, que es
    justo la unidad del catálogo, así que no hay que escalar nada.
    """
    valores = {}
    for nutriente in resultado.get("foodNutrients") or []:
        identificador = nutriente.get("nutrientId")
        valor = nutriente.get("value")
        if identificador is None or valor is None:
            continue
        valores[identificador] = (
            valor,
            nutriente.get("unitName") or "",
            nutriente.get("nutrientName") or "",
        )
    return valores


def _primero_disponible(valores, candidatos):
    for identificador in candidatos:
        if identificador in valores:
            # Algunos alimentos traen valores ligeramente negativos porque los
            # hidratos "por diferencia" salen de restar: como cantidad no tienen
            # sentido, se recortan a cero.
            return max(0.0, float(valores[identificador][0]))
    return None


def traducir_alimento(resultado):
    """Traduce un resultado de USDA a los campos de `Alimento`.

    Devuelve un diccionario listo para construir la fila. Lanza
    `RespuestaIncompleta` si faltan los nutrientes imprescindibles, para que el
    llamante pruebe con otro resultado en vez de guardar un alimento sin datos.
    """
    valores = _valores_por_id(resultado)

    traducido = {
        campo: _primero_disponible(valores, candidatos)
        for campo, candidatos in NUTRIENTES.items()
    }

    sodio = valores.get(SODIO_ID)
    # El sodio viene en miligramos y la sal se etiqueta en gramos.
    traducido["sal_g"] = (
        round(max(0.0, float(sodio[0])) * FACTOR_SODIO_A_SAL / 1000, 4)
        if sodio else None
    )

    faltan = [c for c in IMPRESCINDIBLES if traducido[c] is None]
    if faltan:
        raise RespuestaIncompleta(
            f"al alimento {resultado.get('fdcId')} le faltan: {', '.join(faltan)}"
        )

    # Todo lo que no ha entrado en las ocho columnas va al JSON. Se indexa por
    # nutrientId (como texto, porque las claves JSON lo son) en vez de por
    # nombre: el nombre se repite entre nutrientes distintos y se perderían.
    usados = {SODIO_ID}
    for candidatos in NUTRIENTES.values():
        usados.update(candidatos)
    extra = {
        str(identificador): {"nombre": nombre, "unidad": unidad, "valor": valor}
        for identificador, (valor, unidad, nombre) in sorted(valores.items())
        if identificador not in usados
    }

    traducido["nutrientes_extra"] = extra
    traducido["id_externo"] = str(resultado.get("fdcId"))
    traducido["nombre_externo"] = resultado.get("description")
    return traducido


def buscar_y_traducir(termino, limite=10):
    """Busca un término y traduce el primer resultado que traiga datos suficientes.

    Se recorren los resultados en el orden de relevancia de USDA en lugar de
    quedarse con el primero a secas: hay fichas —sobre todo de Foundation— que
    publican decenas de ácidos grasos pero ni calorías ni proteínas, y esas no
    sirven para el catálogo.
    """
    resultados = buscar_alimentos(termino, limite=limite)
    if not resultados:
        raise NoEncontrado(f"USDA no devolvió alimentos genéricos para «{termino}»")

    for resultado in resultados:
        try:
            return traducir_alimento(resultado)
        except RespuestaIncompleta:
            continue

    raise RespuestaIncompleta(
        f"ninguno de los {len(resultados)} resultados de «{termino}» trae los "
        "nutrientes imprescindibles"
    )
