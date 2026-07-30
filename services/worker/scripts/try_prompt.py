#!/usr/bin/env python3
"""Prueba un prompt contra uno o varios modelos, sin cola y sin base de datos.

Es la herramienta para **afinar el prompt y comparar modelos**: imprime la
respuesta cruda, si valida o no, y los tokens consumidos. Nada de esto toca
Redis ni PostgreSQL, así que se puede repetir todas las veces que haga falta sin
ensuciar datos.

Se ejecuta a mano dentro del contenedor del worker, que es quien tiene la clave
y la salida a internet:

    docker compose run --rm worker python scripts/try_prompt.py \\
        --provider openrouter --model openai/gpt-4o-mini

Comparar dos modelos en la misma ejecución es repetir `--model`:

    docker compose run --rm worker python scripts/try_prompt.py \\
        --provider openrouter \\
        -m openai/gpt-4o-mini -m google/gemini-2.0-flash-001

Otras opciones útiles:

    --job plan_review          prueba la revisión en lugar de la generación
    --profile perfil.json      usa tu propio perfil
    --foods catalogo.json      usa tu propio catálogo
    --response-format json_object   para modelos sin salida estructurada
    --show-prompt              imprime el prompt que se manda
"""
import argparse
import json
import sys
import time
from pathlib import Path

# El script vive en scripts/ y los módulos del worker en el directorio de
# arriba. Sin esto, `import prompts` solo funcionaría ejecutándolo desde /worker.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import prompts  # noqa: E402
import validation  # noqa: E402
from llm import PROVIDERS, LLMError, get_provider  # noqa: E402

# Perfil de ejemplo. Los valores son los de las listas cerradas del dominio, los
# mismos que mandaría la API.
SAMPLE_PROFILE = {
    "sex": "male",
    "age": 36,
    "height_cm": 178,
    "weight_kg": 78.0,
    "bmi": 24.6,
    "activity_level": "moderate",
    "goal": "lose_fat",
    "meals_per_day": 4,
    "food_preference": "omnivore",
    "body_composition": "average",
}

# Catálogo de ejemplo, con la misma forma que el que manda la API: identificador,
# nombre y categoría, y **sin valores nutricionales** (3.10). Va incrustado para
# que el script funcione sin base de datos.
SAMPLE_FOODS = [
    {"id": 1, "name": "pechuga de pollo", "category": "aves", "state": "raw"},
    {"id": 2, "name": "muslo de pollo sin piel", "category": "aves", "state": "raw"},
    {"id": 3, "name": "ternera magra", "category": "carnes", "state": "raw"},
    {"id": 4, "name": "lomo de cerdo", "category": "cerdo", "state": "raw"},
    {"id": 5, "name": "salmón", "category": "pescados", "state": "raw"},
    {"id": 6, "name": "merluza", "category": "pescados", "state": "raw"},
    {"id": 7, "name": "atún al natural", "category": "pescados", "state": "canned"},
    {"id": 8, "name": "huevo de gallina", "category": "huevos", "state": "raw"},
    {"id": 9, "name": "lentejas", "category": "legumbres", "state": "raw"},
    {"id": 10, "name": "garbanzos", "category": "legumbres", "state": "raw"},
    {"id": 11, "name": "arroz blanco de grano largo", "category": "cereales", "state": "raw"},
    {"id": 12, "name": "avena en copos", "category": "cereales", "state": "raw"},
    {"id": 13, "name": "pasta de trigo", "category": "cereales", "state": "raw"},
    {"id": 14, "name": "pan integral", "category": "cereales", "state": None},
    {"id": 15, "name": "patata", "category": "tubérculos", "state": "raw"},
    {"id": 16, "name": "brócoli", "category": "verduras", "state": "raw"},
    {"id": 17, "name": "espinacas", "category": "verduras", "state": "raw"},
    {"id": 18, "name": "tomate", "category": "verduras", "state": "raw"},
    {"id": 19, "name": "cebolla", "category": "verduras", "state": "raw"},
    {"id": 20, "name": "pimiento rojo", "category": "verduras", "state": "raw"},
    {"id": 21, "name": "manzana", "category": "frutas", "state": "raw"},
    {"id": 22, "name": "plátano", "category": "frutas", "state": "raw"},
    {"id": 23, "name": "yogur natural", "category": "lácteos", "state": None},
    {"id": 24, "name": "leche semidesnatada", "category": "lácteos", "state": "liquid"},
    {"id": 25, "name": "queso fresco batido", "category": "lácteos", "state": None},
    {"id": 26, "name": "almendras", "category": "frutos secos", "state": "raw"},
    {"id": 27, "name": "aceite de oliva virgen extra", "category": "aceite", "state": None},
    {"id": 28, "name": "tofu firme", "category": "legumbres", "state": "raw"},
]

# Resumen nutricional de ejemplo para probar `plan_review`. Tiene la forma que
# produce `app/plans/nutrition.py`, recortado a dos días para que se lea.
SAMPLE_NUTRITION = {
    "weekly_totals": {
        "energy_kcal": 14200.0, "fat_g": 480.5, "saturated_fat_g": 120.2,
        "carbs_g": 1450.0, "sugars_g": 310.4, "fiber_g": 190.0,
        "protein_g": 890.6, "salt_g": 42.1,
    },
    "daily_average": {
        "energy_kcal": 2028.6, "fat_g": 68.6, "saturated_fat_g": 17.2,
        "carbs_g": 207.1, "sugars_g": 44.3, "fiber_g": 27.1,
        "protein_g": 127.2, "salt_g": 6.0,
    },
    "days_planned": 7,
    "by_day": [
        {
            "day_of_week": "monday",
            "totals": {"energy_kcal": 2600.0, "protein_g": 150.0},
            "meals": [
                {"meal_slot": "breakfast", "recipe": "Avena con plátano", "servings": 1},
                {"meal_slot": "lunch", "recipe": "Arroz con pollo", "servings": 1.5},
                {"meal_slot": "dinner", "recipe": "Merluza al horno", "servings": 1},
            ],
        },
        {
            "day_of_week": "sunday",
            "totals": {"energy_kcal": 1250.0, "protein_g": 70.0},
            "meals": [
                {"meal_slot": "lunch", "recipe": "Ensalada de garbanzos", "servings": 1},
            ],
        },
    ],
    "incomplete_nutrients": ["sugars_g"],
    "note": "Cantidades en crudo.",
}

JOBS = ("plan_generation", "plan_review")


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _build_input(args):
    profile = _load_json(args.profile) if args.profile else dict(SAMPLE_PROFILE)

    if args.job == "plan_review":
        return {
            "plan_id": 0,
            "plan_name": "Plan de prueba",
            "profile": profile,
            "nutrition": (
                _load_json(args.nutrition) if args.nutrition else SAMPLE_NUTRITION
            ),
        }

    foods = _load_json(args.foods) if args.foods else SAMPLE_FOODS
    return {"profile": profile, "foods": foods}


def _validate(job, data, job_input):
    """Pasa la respuesta por el MISMO validador que usa el worker.

    Es el sentido del script: si aquí valida, en producción también, porque no
    hay dos validaciones distintas.
    """
    if job == "plan_review":
        return validation.validate_review(data)
    allowed = {food["id"] for food in job_input["foods"]}
    return validation.validate_plan(data, allowed)


def _describe(job, validated):
    if job == "plan_review":
        return (
            f"veredicto={validated['verdict']} · "
            f"{len(validated['adjustments'])} ajustes"
        )
    return (
        f"«{validated['plan_name']}» · {len(validated['recipes'])} recetas · "
        f"{len(validated['meals'])} comidas"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Prueba un prompt contra uno o varios modelos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-m", "--model", action="append", dest="models", metavar="MODELO",
        help="modelo a probar; repetible para comparar varios",
    )
    parser.add_argument(
        "-p", "--provider", choices=sorted(PROVIDERS),
        help="proveedor (por defecto, el de LLM_PROVIDER)",
    )
    parser.add_argument("-j", "--job", choices=JOBS, default="plan_generation")
    parser.add_argument("--profile", help="fichero JSON con el perfil del usuario")
    parser.add_argument("--foods", help="fichero JSON con el catálogo de alimentos")
    parser.add_argument("--nutrition", help="fichero JSON con el resumen nutricional")
    parser.add_argument(
        "--response-format", choices=("json_schema", "json_object", "none"),
        help="mecanismo de salida estructurada (solo openrouter)",
    )
    parser.add_argument(
        "--show-prompt", action="store_true", help="imprime el prompt que se manda"
    )
    args = parser.parse_args()

    job_input = _build_input(args)
    prompt = (
        prompts.plan_review(job_input) if args.job == "plan_review"
        else prompts.plan_generation(job_input)
    )

    if args.show_prompt:
        print("=" * 72)
        print("SYSTEM\n" + prompt.system)
        print("-" * 72)
        print("USER\n" + prompt.user)
        print("=" * 72)

    failures = 0

    for model in args.models or [None]:
        provider = get_provider(args.provider, model)
        if args.response_format and hasattr(provider, "response_format"):
            provider.response_format = args.response_format

        print("\n" + "=" * 72)
        print(f"proveedor={provider.name}  modelo={provider.model}  trabajo={args.job}")
        print("=" * 72)

        started = time.perf_counter()
        try:
            response = provider.complete(prompt)
        except LLMError as exc:
            elapsed = time.perf_counter() - started
            # Se imprime el tipo además del mensaje: es lo que decide si el
            # worker reintentaría o daría el trabajo por fallido.
            print(f"FALLO ({type(exc).__name__}, reintentable={exc.retryable}) "
                  f"tras {elapsed:.1f} s")
            print(f"  {exc}")
            failures += 1
            continue

        elapsed = time.perf_counter() - started

        print("\n--- respuesta cruda ---")
        print(response.raw)

        print("\n--- consumo ---")
        print(f"  modelo real:  {response.model}")
        print(f"  entrada:      {response.prompt_tokens} tokens")
        print(f"  salida:       {response.completion_tokens} tokens")
        print(f"  total:        {response.total_tokens} tokens")
        if response.cost is not None:
            print(f"  coste:        {response.cost}")
        # El del proveedor es el que acaba en el log JSON; el de fuera incluye
        # además construir el prompt. Se enseñan los dos para poder compararlos.
        print(f"  tiempo:       {response.duration_ms / 1000:.1f} s "
              f"(medido por el proveedor) · {elapsed:.1f} s de reloj")

        print("\n--- validación ---")
        try:
            validated = _validate(args.job, response.data, job_input)
        except LLMError as exc:
            print(f"  NO VALIDA ({type(exc).__name__}): {exc}")
            failures += 1
        else:
            print(f"  VALIDA · {_describe(args.job, validated)}")

    # Código de salida distinto de cero si algo falló: así el script sirve
    # también dentro de un script de comparación sin leer la salida a ojo.
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
