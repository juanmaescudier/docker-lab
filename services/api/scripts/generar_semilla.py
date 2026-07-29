#!/usr/bin/env python3
"""Genera `app/catalogo/semilla.json` a partir de la API de USDA.

Se ejecuta A MANO, no forma parte del arranque de la aplicación. El JSON que
produce se versiona en git a propósito (decisión 3.14): así un `docker compose
up` desde cero deja el catálogo poblado sin depender de USDA ni de internet, y
las demostraciones salen siempre iguales.

    export USDA_API_KEY=...          # la clave real está en el .env, sin versionar
    python services/api/scripts/generar_semilla.py

Si un alimento falla, el script sigue con el resto y lo lista al final para
poder ajustar el término de búsqueda a mano.
"""
import json
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ_API = AQUI.parent
DESTINO = RAIZ_API / "app" / "catalogo" / "semilla.json"

# `usda.py` solo usa la biblioteca estándar y no importa nada de la aplicación,
# así que lo cargamos como módulo suelto en lugar de a través del paquete `app`:
# ese camino arrastraría Flask y la conexión a la base de datos, y este script se
# ejecuta desde el host, fuera del contenedor.
sys.path.insert(0, str(RAIZ_API / "app" / "catalogo"))
import usda  # noqa: E402

# nombre en español · categoría · estado (None si no aplica) · término en inglés.
#
# Los términos de búsqueda son la parte frágil: si USDA cambia su catálogo o su
# relevancia, se ajustan aquí y se vuelve a generar el JSON. Su buscador es muy
# laxo y premia coincidencias parciales, así que varios términos tuvieron que
# afinarse con la nomenclatura literal de USDA (ver las notas de más abajo):
# "milk whole" devolvía queso mozzarella, "oats" devolvía aceite de avena y
# "orange raw" devolvía piel de naranja. Regla práctica: cuanto más se parece el
# término a la descripción completa de USDA, menos margen hay para el error.
ALIMENTOS = [
    ("pechuga de pollo", "pollo", "crudo", "chicken breast raw"),
    # "chicken thigh raw" devolvía la PIEL del muslo (440 kcal).
    ("muslo de pollo", "pollo", "crudo", "chicken thigh meat only raw"),
    ("huevo de gallina", "huevo", "crudo", "egg whole raw"),
    ("clara de huevo", "huevo", "crudo", "egg white raw"),
    ("ternera, filete magro", "ternera", "crudo", "beef top round raw"),
    ("lomo de cerdo", "cerdo", "crudo", "pork loin raw"),
    ("salmón", "pescado", "crudo", "salmon atlantic raw"),
    ("bacalao", "pescado", "crudo", "cod atlantic raw"),
    ("atún en conserva al natural", "pescado", "conserva", "tuna light canned water"),
    ("gambas", "marisco", "crudo", "shrimp raw"),
    # "milk whole" devolvía mozzarella y "milk skim" yogur desnatado.
    ("leche entera", "lacteo", "líquido", "milk whole 3.25% milkfat"),
    ("leche desnatada", "lacteo", "líquido", "milk nonfat fluid"),
    ("yogur natural", "lacteo", None, "yogurt plain whole milk"),
    ("queso fresco batido", "lacteo", None, "cottage cheese lowfat"),
    ("queso curado", "lacteo", None, "cheese cheddar"),
    ("arroz blanco", "cereal", "crudo", "rice white long-grain raw"),
    ("arroz integral", "cereal", "crudo", "rice brown long-grain raw"),
    ("pasta", "cereal", "crudo", "pasta dry enriched"),
    # "oats" a secas devolvía "Oil, oat": aceite de avena, 884 kcal.
    ("avena en copos", "cereal", "crudo", "oats whole grain rolled"),
    ("quinoa", "cereal", "crudo", "quinoa uncooked"),
    # "bread white commercially prepared" devolvía la versión TOSTADA (290 kcal
    # frente a 266). La ficha Foundation "Bread, white, commercial" está vacía de
    # macronutrientes, así que hay que nombrar la de SR Legacy entera.
    ("pan blanco", "pan", None, "bread white commercially prepared includes soft bread crumbs"),
    # "bread whole wheat" devolvía pan de pita integral.
    ("pan integral", "pan", None, "bread whole-wheat commercially prepared"),
    ("patata", "tuberculo", "crudo", "potato flesh and skin raw"),
    # "sweet potato raw" devolvía las HOJAS del boniato.
    ("boniato", "tuberculo", "crudo", "sweet potato raw unprepared food distribution program"),
    ("lentejas", "legumbre", "crudo", "lentils raw"),
    ("garbanzos", "legumbre", "crudo", "chickpeas raw"),
    ("alubias blancas", "legumbre", "crudo", "beans white raw"),
    # "olive oil" devolvía una mezcla de maíz, cacahuete y oliva. La ficha
    # Foundation de "Oil, olive, extra virgin" existe pero solo publica ácidos
    # grasos, sin calorías: la única completa es la de SR Legacy.
    ("aceite de oliva virgen extra", "aceite", None, "oil olive salad or cooking"),
    ("aguacate", "fruta", "crudo", "avocado raw"),
    ("almendras", "fruto_seco", "crudo", "almonds raw"),
    ("nueces", "fruto_seco", "crudo", "walnuts english"),
    ("cacahuetes", "fruto_seco", "crudo", "peanuts raw"),
    ("plátano", "fruta", "crudo", "banana raw"),
    ("manzana", "fruta", "crudo", "apple raw with skin"),
    # "orange raw" devolvía la PIEL de la naranja.
    ("naranja", "fruta", "crudo", "oranges raw all commercial varieties"),
    ("fresas", "fruta", "crudo", "strawberries raw"),
    ("tomate", "verdura", "crudo", "tomato red raw"),
    ("cebolla", "verdura", "crudo", "onion raw"),
    ("pimiento rojo", "verdura", "crudo", "peppers sweet red raw"),
    ("brócoli", "verdura", "crudo", "broccoli raw"),
    ("espinacas", "verdura", "crudo", "spinach raw"),
    # "squash zucchini raw" devolvía el calabacín baby, no el corriente.
    ("calabacín", "verdura", "crudo", "squash summer zucchini includes skin raw"),
    ("lechuga", "verdura", "crudo", "lettuce romaine raw"),
    ("zanahoria", "verdura", "crudo", "carrots raw"),
    ("champiñones", "verdura", "crudo", "mushrooms white raw"),
]

REINTENTOS_POR_LIMITE = 3


def importar(termino):
    """Consulta USDA reintentando solo si el fallo es el límite de peticiones.

    El resto de errores no mejoran esperando: si la clave está mal o el término
    no devuelve nada, reintentar solo gasta cuota.
    """
    for intento in range(1, REINTENTOS_POR_LIMITE + 1):
        try:
            return usda.buscar_y_traducir(termino)
        except usda.LimitePeticiones:
            if intento == REINTENTOS_POR_LIMITE:
                raise
            espera = 30 * intento
            print(f"    límite de peticiones: espero {espera} s", flush=True)
            time.sleep(espera)


def main():
    semilla = []
    fallidos = []

    for numero, (nombre, categoria, estado, termino) in enumerate(ALIMENTOS, start=1):
        print(f"[{numero:2}/{len(ALIMENTOS)}] {nombre} ← «{termino}»", flush=True)
        try:
            datos = importar(termino)
        except usda.ClaveRechazada as error:
            # La clave es el único fallo que no tiene sentido arrastrar: si está
            # mal, fallarán los 45. Se corta, informando del código, nunca del valor.
            print(f"\n  Abortado: {error}. Revisa USDA_API_KEY.", file=sys.stderr)
            return 1
        except usda.ErrorUSDA as error:
            print(f"    fallo: {error}", flush=True)
            fallidos.append((nombre, termino, str(error)))
            continue

        datos.update(nombre=nombre, categoria=categoria, estado=estado)
        semilla.append(datos)
        print(
            f"    → {datos['nombre_externo']} "
            f"({datos['energia_kcal']} kcal, {datos['proteinas_g']} g proteína)",
            flush=True,
        )

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(
        json.dumps(semilla, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"\n{len(semilla)} alimentos escritos en {DESTINO.relative_to(RAIZ_API.parent.parent)}")
    if fallidos:
        print(f"\n{len(fallidos)} sin importar — ajusta el término de búsqueda:")
        for nombre, termino, motivo in fallidos:
            print(f"  · {nombre:32} «{termino}» → {motivo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
