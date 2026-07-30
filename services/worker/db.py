"""Acceso a PostgreSQL con SQL directo.

El worker **no usa el ORM** (ADR-0008): sus dependencias son tres líneas en vez
de las siete de la API, porque no arrastra Flask ni SQLAlchemy. Lo que se acepta
a cambio es que los nombres de las tablas y las columnas están escritos en dos
sitios; si cambia el esquema, hay que tocar los dos.

La conexión va en **autocommit**, para que los cambios de estado sean visibles de
inmediato para la API. Donde hace falta atomicidad —crear un plan entero— se abre
una transacción explícita con `conn.transaction()`.
"""
import os

import psycopg
from psycopg.types.json import Json

# Estados en los que un trabajo se puede coger. Un trabajo `processing` no se
# vuelve a coger: si el mensaje llegara duplicado a la cola, el segundo se
# encontraría el UPDATE sin filas y no haría nada.
CLAIMABLE_STATES = ("pending", "failed")


def connect():
    return psycopg.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        autocommit=True,
    )


# ----------------------------------------------------------- ciclo del trabajo

def claim_job(conn, job_id):
    """Marca el trabajo como en curso y devuelve sus datos, o None si no procede.

    El filtro por estado en el propio UPDATE es lo que hace que dos worker (o dos
    mensajes duplicados) no procesen el mismo trabajo: es una sola sentencia
    atómica, no un SELECT seguido de un UPDATE que otro podría colarse en medio.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE jobs
               SET state = 'processing',
                   attempts = attempts + 1,
                   updated_at = NOW()
             WHERE id = %s AND state = ANY(%s)
         RETURNING id, user_id, plan_id, type, input, attempts
            """,
            (job_id, list(CLAIMABLE_STATES)),
        )
        row = cur.fetchone()

    if row is None:
        return None

    return {
        "id": row[0],
        "user_id": row[1],
        "plan_id": row[2],
        "type": row[3],
        "input": row[4],
        "attempts": row[5],
    }


def record_attempt(conn, job_id, error):
    """Anota un intento fallido que todavía se va a reintentar.

    Se guarda el error aunque el trabajo siga vivo: si al final agota los
    intentos, el último mensaje ya está puesto, y mientras tanto se ve en
    `GET /jobs/<id>` por qué está tardando.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE jobs
               SET attempts = attempts + 1, error = %s, updated_at = NOW()
             WHERE id = %s
            """,
            (error[:2000], job_id),
        )


def complete_job(conn, job_id, result):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE jobs
               SET state = 'completed', result = %s, error = NULL, updated_at = NOW()
             WHERE id = %s
            """,
            (Json(result), job_id),
        )


def fail_job(conn, job_id, error):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE jobs
               SET state = 'failed', error = %s, updated_at = NOW()
             WHERE id = %s
            """,
            (error[:2000], job_id),
        )


# ------------------------------------------------------------- escritura real

class AlreadyDone(Exception):
    """El trabajo ya había creado su plan. Un reintento no debe crear otro."""


def write_generated_plan(conn, job_id, user_id, plan):
    """Crea las recetas, el plan y sus comidas, y cierra el trabajo. Atómico.

    **Idempotencia.** Todo va dentro de una única transacción que termina
    marcando `jobs.plan_id`. Tres cosas la garantizan:

    1. El `SELECT ... FOR UPDATE` del principio bloquea la fila del trabajo, así
       que dos worker no pueden entrar aquí a la vez con el mismo trabajo.
    2. Si `plan_id` ya tiene valor, el plan está creado: se aborta sin escribir.
       `jobs.plan_id` es el **marcador de idempotencia**, y vive en la misma fila
       y la misma transacción que el resto, así que no puede desincronizarse.
    3. Si el proceso muere a mitad, la transacción no llega a confirmarse y no
       queda ni un plan huérfano ni una receta suelta: o todo o nada.

    Sin esto, reintentar un trabajo que ya había escrito su plan crearía un
    segundo plan, desactivaría el primero y dejaría recetas duplicadas.
    """
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                "SELECT plan_id FROM jobs WHERE id = %s FOR UPDATE", (job_id,)
            )
            row = cur.fetchone()
            if row is None:
                raise AlreadyDone(f"el trabajo {job_id} ya no existe")
            if row[0] is not None:
                raise AlreadyDone(
                    f"el trabajo {job_id} ya había creado el plan {row[0]}"
                )

            recipe_ids = _insert_recipes(cur, user_id, plan["recipes"])

            # Desactivar ANTES de insertar el nuevo activo: el índice único
            # parcial `uq_active_plan_per_user` rechazaría dos activos a la vez,
            # aunque fuera dentro de la misma transacción (3.1).
            cur.execute(
                "UPDATE plans SET active = false, updated_at = NOW() "
                "WHERE user_id = %s AND active",
                (user_id,),
            )

            cur.execute(
                """
                INSERT INTO plans (user_id, name, active, source, created_at, updated_at)
                VALUES (%s, %s, true, 'ai', NOW(), NOW())
                RETURNING id
                """,
                (user_id, plan["plan_name"]),
            )
            plan_id = cur.fetchone()[0]

            cur.executemany(
                """
                INSERT INTO planned_meals
                       (plan_id, day_of_week, meal_slot, recipe_id, servings)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (
                        plan_id,
                        meal["day_of_week"],
                        meal["meal_slot"],
                        recipe_ids[meal["recipe_index"]],
                        meal["servings"],
                    )
                    for meal in plan["meals"]
                ],
            )

            # Dentro de la MISMA transacción: es lo que ata el trabajo a su plan.
            # Si esto se confirmara aparte, una caída en medio dejaría un plan
            # creado y un trabajo sin marcar, y el reintento crearía el segundo.
            cur.execute(
                "UPDATE jobs SET plan_id = %s, updated_at = NOW() WHERE id = %s",
                (plan_id, job_id),
            )

            return plan_id, recipe_ids


def _insert_recipes(cur, user_id, recipes):
    """Inserta las recetas con sus ingredientes y devuelve sus identificadores.

    Las cantidades van **en crudo** (3.2): es lo que dice el prompt, es como está
    medido el catálogo y es lo que hace directa la lista de la compra.
    """
    recipe_ids = []

    for recipe in recipes:
        cur.execute(
            """
            INSERT INTO recipes
                   (user_id, name, steps, cooking_method, servings, source,
                    created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, 'ai', NOW(), NOW())
            RETURNING id
            """,
            (
                user_id,
                recipe["name"],
                recipe["steps"] or None,
                recipe["cooking_method"],
                recipe["servings"],
            ),
        )
        recipe_id = cur.fetchone()[0]
        recipe_ids.append(recipe_id)

        cur.executemany(
            "INSERT INTO recipe_ingredients (recipe_id, food_id, grams) "
            "VALUES (%s, %s, %s)",
            [
                (recipe_id, item["food_id"], item["grams"])
                for item in recipe["ingredients"]
            ],
        )

    return recipe_ids
