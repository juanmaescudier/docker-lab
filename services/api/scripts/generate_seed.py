#!/usr/bin/env python3
"""Genera `app/catalog/seed.json` a partir de la API de USDA.

Se ejecuta A MANO, no forma parte del arranque de la aplicación. El JSON que
produce se versiona en git a propósito (decisión 3.14): así un `docker compose
up` desde cero deja el catálogo poblado sin depender de USDA ni de internet, y
las demostraciones salen siempre iguales.

    export USDA_API_KEY=...          # la clave real está en el .env, sin versionar
    python services/api/scripts/generate_seed.py

Si un alimento falla, el script sigue con el resto y lo lista al final para
poder ajustar el término de búsqueda a mano.
"""
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
API_ROOT = HERE.parent
DESTINATION = API_ROOT / "app" / "catalog" / "seed.json"

# `usda.py` solo usa la biblioteca estándar y no importa nada de la aplicación,
# así que lo cargamos como módulo suelto en lugar de a través del paquete `app`:
# ese camino arrastraría Flask y la conexión a la base de datos, y este script se
# ejecuta desde el host, fuera del contenedor.
sys.path.insert(0, str(API_ROOT / "app" / "catalog"))
import usda  # noqa: E402

# nombre en español · categoría · estado (None si no aplica) · alérgenos ·
# término en inglés.
#
# **Los alérgenos se marcan aquí y no en el JSON** aunque el JSON sea lo que se
# carga: si vivieran solo allí, la siguiente regeneración se los llevaría por
# delante. Son los 14 de declaración obligatoria (`catalog/models.ALLERGENS`), y
# una lista vacía significa "revisado, no lleva ninguno". USDA no publica esta
# información, así que van a mano uno a uno; los cuatro casos que dieron duda
# están comentados en su línea.
#
# Los términos de búsqueda son la parte frágil: si USDA cambia su catálogo o su
# relevancia, se ajustan aquí y se vuelve a generar el JSON. Su buscador es muy
# laxo y premia coincidencias parciales, así que varios términos tuvieron que
# afinarse con la nomenclatura literal de USDA (ver las notas de más abajo):
# "milk whole" devolvía queso mozzarella, "oats" devolvía aceite de avena y
# "orange raw" devolvía piel de naranja. Regla práctica: cuanto más se parece el
# término a la descripción completa de USDA, menos margen hay para el error.
FOODS = [
    ("pechuga de pollo", "pollo", "raw", [], "chicken breast raw"),
    # "chicken thigh raw" devolvía la PIEL del muslo (440 kcal).
    ("muslo de pollo", "pollo", "raw", [], "chicken thigh meat only raw"),
    ("huevo de gallina", "huevo", "raw", ["eggs"], "egg whole raw"),
    ("clara de huevo", "huevo", "raw", ["eggs"], "egg white raw"),
    ("ternera, filete magro", "ternera", "raw", [], "beef top round raw"),
    ("lomo de cerdo", "cerdo", "raw", [], "pork loin raw"),
    ("salmón", "pescado", "raw", ["fish"], "salmon atlantic raw"),
    ("bacalao", "pescado", "raw", ["fish"], "cod atlantic raw"),
    # DUDA: la ficha de USDA es genérica. Muchas conservas llevan además soja
    # o sulfitos según la marca, y eso no se puede saber desde aquí.
    ("atún en conserva al natural", "pescado", "canned", ["fish"], "tuna light canned water"),
    ("gambas", "marisco", "raw", ["crustaceans"], "shrimp raw"),
    # "milk whole" devolvía mozzarella y "milk skim" yogur desnatado.
    ("leche entera", "lacteo", "liquid", ["milk"], "milk whole 3.25% milkfat"),
    ("leche desnatada", "lacteo", "liquid", ["milk"], "milk nonfat fluid"),
    ("yogur natural", "lacteo", None, ["milk"], "yogurt plain whole milk"),
    ("queso fresco batido", "lacteo", None, ["milk"], "cottage cheese lowfat"),
    ("queso curado", "lacteo", None, ["milk"], "cheese cheddar"),
    ("arroz blanco", "cereal", "raw", [], "rice white long-grain raw"),
    ("arroz integral", "cereal", "raw", [], "rice brown long-grain raw"),
    ("pasta", "cereal", "raw", ["gluten"], "pasta dry enriched"),
    # "oats" a secas devolvía "Oil, oat": aceite de avena, 884 kcal.
    # La avena está en el anexo II entre los cereales con gluten, aunque exista
    # avena certificada sin gluten. Se marca por la lista, no por el caso.
    ("avena en copos", "cereal", "raw", ["gluten"], "oats whole grain rolled"),
    ("quinoa", "cereal", "raw", [], "quinoa uncooked"),
    # "bread white commercially prepared" devolvía la versión TOSTADA (290 kcal
    # frente a 266). La ficha Foundation "Bread, white, commercial" está vacía de
    # macronutrientes, así que hay que nombrar la de SR Legacy entera.
    # DUDA: el pan comercial suele llevar soja, sésamo o leche según la receta.
    # La ficha de USDA no lo dice, así que solo se marca el gluten.
    ("pan blanco", "pan", None, ["gluten"], "bread white commercially prepared includes soft bread crumbs"),
    # "bread whole wheat" devolvía pan de pita integral.
    ("pan integral", "pan", None, ["gluten"], "bread whole-wheat commercially prepared"),
    ("patata", "tuberculo", "raw", [], "potato flesh and skin raw"),
    # "sweet potato raw" devolvía las HOJAS del boniato.
    ("boniato", "tuberculo", "raw", [], "sweet potato raw unprepared food distribution program"),
    ("lentejas", "legumbre", "raw", [], "lentils raw"),
    ("garbanzos", "legumbre", "raw", [], "chickpeas raw"),
    ("alubias blancas", "legumbre", "raw", [], "beans white raw"),
    # "olive oil" devolvía una mezcla de maíz, cacahuete y oliva. La ficha
    # Foundation de "Oil, olive, extra virgin" existe pero solo publica ácidos
    # grasos, sin calorías: la única completa es la de SR Legacy.
    ("aceite de oliva virgen extra", "aceite", None, [], "oil olive salad or cooking"),
    ("aguacate", "fruta", "raw", [], "avocado raw"),
    ("almendras", "fruto_seco", "raw", ["nuts"], "almonds raw"),
    ("nueces", "fruto_seco", "raw", ["nuts"], "walnuts english"),
    # El cacahuete es un alérgeno PROPIO en el anexo II: no es fruto de cáscara
    # aunque coloquialmente se le llame fruto seco. Quien marca "frutos de
    # cáscara" sigue viendo cacahuetes, y es lo correcto.
    ("cacahuetes", "fruto_seco", "raw", ["peanuts"], "peanuts raw"),
    ("plátano", "fruta", "raw", [], "banana raw"),
    ("manzana", "fruta", "raw", [], "apple raw with skin"),
    # "orange raw" devolvía la PIEL de la naranja.
    ("naranja", "fruta", "raw", [], "oranges raw all commercial varieties"),
    ("fresas", "fruta", "raw", [], "strawberries raw"),
    ("tomate", "verdura", "raw", [], "tomato red raw"),
    ("cebolla", "verdura", "raw", [], "onion raw"),
    ("pimiento rojo", "verdura", "raw", [], "peppers sweet red raw"),
    ("brócoli", "verdura", "raw", [], "broccoli raw"),
    ("espinacas", "verdura", "raw", [], "spinach raw"),
    # "squash zucchini raw" devolvía el calabacín baby, no el corriente.
    ("calabacín", "verdura", "raw", [], "squash summer zucchini includes skin raw"),
    ("lechuga", "verdura", "raw", [], "lettuce romaine raw"),
    ("zanahoria", "verdura", "raw", [], "carrots raw"),
    ("champiñones", "verdura", "raw", [], "mushrooms white raw"),
]

RATE_LIMIT_RETRIES = 3


def import_food(term):
    """Consulta USDA reintentando solo si el fallo es el límite de peticiones.

    El resto de errores no mejoran esperando: si la clave está mal o el término
    no devuelve nada, reintentar solo gasta cuota.
    """
    for attempt in range(1, RATE_LIMIT_RETRIES + 1):
        try:
            return usda.search_and_translate(term)
        except usda.RateLimited:
            if attempt == RATE_LIMIT_RETRIES:
                raise
            wait = 30 * attempt
            print(f"    límite de peticiones: espero {wait} s", flush=True)
            time.sleep(wait)


def main():
    seed = []
    failed = []

    for number, (name, category, state, allergens, term) in enumerate(FOODS, start=1):
        print(f"[{number:2}/{len(FOODS)}] {name} ← «{term}»", flush=True)
        try:
            data = import_food(term)
        except usda.KeyRejected as error:
            # La clave es el único fallo que no tiene sentido arrastrar: si está
            # mal, fallarán los 45. Se corta, informando del código, nunca del valor.
            print(f"\n  Abortado: {error}. Revisa USDA_API_KEY.", file=sys.stderr)
            return 1
        except usda.USDAError as error:
            print(f"    fallo: {error}", flush=True)
            failed.append((name, term, str(error)))
            continue

        data.update(
            name=name, category=category, state=state, allergens=list(allergens)
        )
        seed.append(data)
        print(
            f"    → {data['external_name']} "
            f"({data['energy_kcal']} kcal, {data['protein_g']} g proteína)",
            flush=True,
        )

    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    DESTINATION.write_text(
        json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"\n{len(seed)} alimentos escritos en {DESTINATION.relative_to(API_ROOT.parent.parent)}")
    if failed:
        print(f"\n{len(failed)} sin importar — ajusta el término de búsqueda:")
        for name, term, reason in failed:
            print(f"  · {name:32} «{term}» → {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
