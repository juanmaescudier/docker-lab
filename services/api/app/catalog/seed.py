"""Carga del catálogo de semilla al arrancar la aplicación.

Decisión 3.14 del diseño: con la semilla versionada en el repo, un `docker
compose up` desde cero deja la aplicación funcionando sin depender de USDA ni de
internet, y las demostraciones salen siempre iguales.

El fichero `seed.json` lo genera `scripts/generate_seed.py`, que se ejecuta a
mano. Aquí solo se lee.
"""
import json
from pathlib import Path

from sqlalchemy.exc import IntegrityError, ProgrammingError

from ..extensions import db
from .models import SOURCE_SEED, Food

SEED_FILE = Path(__file__).resolve().parent / "seed.json"

# Campos que la semilla puede rellenar. Se listan a propósito en vez de volcar el
# JSON entero al constructor: así un campo nuevo o inesperado en el fichero no
# acaba silenciosamente en la tabla.
FIELDS = (
    "name", "category", "state",
    "energy_kcal", "fat_g", "saturated_fat_g", "carbs_g",
    "sugars_g", "fiber_g", "protein_g", "salt_g",
    "extra_nutrients", "external_id", "external_name",
)


def load_seed(app):
    """Puebla `foods` si está vacía. Si ya tiene filas, no toca nada.

    Que la condición sea "está vacía" y no "falta este alimento" es deliberado:
    un alimento borrado a mano no debe reaparecer en el siguiente despliegue.
    """
    with app.app_context():
        try:
            has_rows = db.session.query(Food.id).first() is not None
        except ProgrammingError:
            # Desde que el esquema lo gestiona Alembic, la tabla puede no existir
            # todavía. Arrancar igualmente y avisar es mejor que reventar sin
            # explicar qué falta.
            db.session.rollback()
            app.logger.error(
                "la tabla 'foods' no existe: ejecuta 'alembic upgrade head' "
                "antes de arrancar la API"
            )
            return 0

        if has_rows:
            app.logger.info("catálogo ya poblado, no se carga la semilla")
            return 0

        if not SEED_FILE.exists():
            app.logger.warning("no hay seed.json: el catálogo arranca vacío")
            return 0

        records = json.loads(SEED_FILE.read_text(encoding="utf-8"))
        for record in records:
            db.session.add(Food(
                source=SOURCE_SEED,
                **{f: record.get(f) for f in FIELDS},
            ))

        try:
            db.session.commit()
        except IntegrityError:
            # Con varios workers de gunicorn arrancando a la vez, dos pueden ver
            # la tabla vacía y cargar los dos. El índice único de `external_id`
            # corta al segundo: no es un error, es la carrera resuelta.
            db.session.rollback()
            app.logger.info("la semilla ya la había cargado otro worker")
            return 0

        app.logger.info("semilla cargada: %d alimentos", len(records))
        return len(records)
