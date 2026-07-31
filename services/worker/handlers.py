"""Qué hace el worker con cada tipo de trabajo.

Un manejador recibe la conexión, el trabajo y el proveedor de modelo, y devuelve
lo que hay que guardar en `jobs.result`. El bucle no sabe qué hace ninguno: solo
despacha por `type`.

Todos siguen la misma secuencia: **construir el prompt → llamar al modelo →
validar la respuesta → escribir**. La validación no es opcional en ninguno, y en
la generación es lo que impide que un alimento inventado llegue a la base de
datos (3.10).
"""
import db
import prompts
import validation
from llm.errors import LLMError

# Los nombres tienen que coincidir exactamente con los de `app/jobs/models.py`:
# la API escribe el valor en la columna `type` y aquí se lee.
TYPE_PLAN_GENERATION = "plan_generation"
TYPE_PLAN_REVIEW = "plan_review"
TYPE_FOOD_IMPORT = "food_import"


class UnsupportedJob(LLMError):
    """Un tipo de trabajo que existe en el modelo pero no tiene manejador.

    No se reintenta: no va a aparecer un manejador entre un intento y el
    siguiente.
    """

    retryable = False


def handle_plan_generation(conn, job, provider, log_response):
    """Genera un plan semanal con el modelo y lo escribe como filas reales.

    La IA **compone**; el catálogo **aporta los números** (3.10). Aquí no se
    guarda ni una caloría que venga del modelo: lo que se escribe son recetas con
    sus alimentos y sus gramos, y los valores nutricionales se calculan después
    desde `foods` cada vez que alguien mira el plan.
    """
    job_input = job["input"] or {}
    foods = job_input.get("foods") or []
    if not foods:
        raise UnsupportedJob("el trabajo no trae catálogo: no hay con qué componer")

    prompt = prompts.plan_generation(job_input)
    response = provider.complete(prompt)
    log_response(response)

    # Contra los identificadores que la API le ofreció al modelo, no contra el
    # catálogo de ahora: si alguien borró un alimento mientras el trabajo estaba
    # en la cola, escribirlo daría un fallo de clave ajena.
    allowed = {food["id"] for food in foods if isinstance(food.get("id"), int)}
    plan = validation.validate_plan(response.data, allowed, job_input.get("profile"))

    try:
        plan_id, recipe_ids = db.write_generated_plan(
            conn, job["id"], job["user_id"], plan
        )
    except db.AlreadyDone as exc:
        # Un reintento de un trabajo que ya escribió su plan. No es un error:
        # es exactamente lo que tiene que pasar. Se completa sin duplicar nada.
        return {
            "note": str(exc),
            "idempotent_replay": True,
            **response.usage_fields(),
        }

    return {
        "plan_id": plan_id,
        "plan_name": plan["plan_name"],
        "recipe_ids": recipe_ids,
        "meals": len(plan["meals"]),
        # Estimación del modelo, no una pauta médica (3.9). Se guarda como
        # orientación y separada de los totales reales, que salen del catálogo.
        "daily_kcal_target_estimated": plan["daily_kcal_target"],
        "notes": plan["notes"],
        **response.usage_fields(),
    }


def handle_plan_review(conn, job, provider, log_response):
    """Pide al modelo una segunda opinión sobre un plan hecho a mano.

    El resumen nutricional llega ya calculado por la API dentro del `input`: el
    worker no vuelve a sumar nada. Su salida es texto, así que se guarda en el
    propio `result` y no crea filas en ninguna parte.
    """
    job_input = job["input"] or {}
    if not job_input.get("nutrition"):
        # Pasa con los análisis anteriores a este encargo, cuyo `input` tenía
        # otra forma. Reintentarlo no lo va a arreglar.
        raise UnsupportedJob(
            "el trabajo no trae resumen nutricional: vuelve a pedir la revisión"
        )

    prompt = prompts.plan_review(job_input)
    response = provider.complete(prompt)
    log_response(response)

    review = validation.validate_review(response.data)

    return {**review, **response.usage_fields()}


def handle_food_import(conn, job, provider, log_response):
    """Importación de alimentos desde USDA. Declarada, todavía sin implementar."""
    raise UnsupportedJob(
        "el tipo de trabajo 'food_import' aún no está implementado"
    )


HANDLERS = {
    TYPE_PLAN_GENERATION: handle_plan_generation,
    TYPE_PLAN_REVIEW: handle_plan_review,
    TYPE_FOOD_IMPORT: handle_food_import,
}
