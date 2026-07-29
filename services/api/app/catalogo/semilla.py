"""Carga del catálogo de semilla al arrancar la aplicación.

Decisión 3.14 del diseño: con la semilla versionada en el repo, un `docker
compose up` desde cero deja la aplicación funcionando sin depender de USDA ni de
internet, y las demostraciones salen siempre iguales.

El fichero `semilla.json` lo genera `scripts/generar_semilla.py`, que se ejecuta
a mano. Aquí solo se lee.
"""
import json
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from ..extensions import db
from .models import ORIGEN_SEED, Alimento

FICHERO_SEMILLA = Path(__file__).resolve().parent / "semilla.json"

# Campos que la semilla puede rellenar. Se listan a propósito en vez de volcar el
# JSON entero al constructor: así un campo nuevo o inesperado en el fichero no
# acaba silenciosamente en la tabla.
CAMPOS = (
    "nombre", "categoria", "estado",
    "energia_kcal", "grasas_g", "grasas_saturadas_g", "hidratos_g",
    "azucares_g", "fibra_g", "proteinas_g", "sal_g",
    "nutrientes_extra", "id_externo", "nombre_externo",
)


def cargar_semilla(app):
    """Puebla `alimentos` si está vacía. Si ya tiene filas, no toca nada.

    Que la condición sea "está vacía" y no "falta este alimento" es deliberado:
    un alimento borrado a mano no debe reaparecer en el siguiente despliegue.
    """
    with app.app_context():
        if db.session.query(Alimento.id).first() is not None:
            app.logger.info("catálogo ya poblado, no se carga la semilla")
            return 0

        if not FICHERO_SEMILLA.exists():
            app.logger.warning("no hay semilla.json: el catálogo arranca vacío")
            return 0

        registros = json.loads(FICHERO_SEMILLA.read_text(encoding="utf-8"))
        for registro in registros:
            db.session.add(Alimento(
                origen=ORIGEN_SEED,
                **{c: registro.get(c) for c in CAMPOS},
            ))

        try:
            db.session.commit()
        except IntegrityError:
            # Con varios workers de gunicorn arrancando a la vez, dos pueden ver
            # la tabla vacía y cargar los dos. El índice único de `id_externo`
            # corta al segundo: no es un error, es la carrera resuelta.
            db.session.rollback()
            app.logger.info("la semilla ya la había cargado otro worker")
            return 0

        app.logger.info("semilla cargada: %d alimentos", len(registros))
        return len(registros)
