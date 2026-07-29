"""Endpoints del dominio Catálogo.

La lectura es pública —el catálogo son datos de dominio público de USDA— y la
escritura exige sesión iniciada. Al editar un alimento su `origen` pasa a
`manual`, que es lo que lo blinda frente a la importación automática (3.13).
"""
from functools import wraps

from flask import Blueprint, jsonify, request, session

from ..extensions import db
from .models import (
    CAMPOS_NUTRICIONALES,
    ESTADOS,
    ORIGEN_MANUAL,
    Alimento,
    normalizar,
)

catalogo_bp = Blueprint("catalogo", __name__, url_prefix="/alimentos")

POR_PAGINA_POR_DEFECTO = 25
POR_PAGINA_MAXIMO = 100


def requiere_sesion(vista):
    """Deja pasar solo con sesión iniciada. La lectura del catálogo no lo usa."""
    @wraps(vista)
    def envoltorio(*args, **kwargs):
        if session.get("user_id") is None:
            return jsonify(error="no autenticado"), 401
        return vista(*args, **kwargs)
    return envoltorio


def _entero(valor, por_defecto, minimo, maximo):
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return por_defecto
    return max(minimo, min(numero, maximo))


def _patron_busqueda(termino):
    """Convierte el término en un patrón LIKE seguro.

    Hay que escapar `%`, `_` y `\\` antes de interpolarlos: si no, buscar "100%"
    devolvería el catálogo entero porque el `%` es un comodín de SQL.
    """
    escapado = (
        normalizar(termino)
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return f"%{escapado}%"


def _validar(datos, exigir_nombre):
    """Comprueba el cuerpo de un POST/PATCH. Devuelve el mensaje de error o None."""
    if exigir_nombre and not (datos.get("nombre") or "").strip():
        return "'nombre' es obligatorio"

    if "nombre" in datos and not (datos["nombre"] or "").strip():
        return "'nombre' no puede quedar vacío"

    estado = datos.get("estado")
    if estado is not None and estado not in ESTADOS:
        return f"'estado' debe ser uno de: {', '.join(ESTADOS)}"

    for campo in CAMPOS_NUTRICIONALES:
        valor = datos.get(campo)
        if valor is None:
            continue
        # `bool` es subclase de `int` en Python: sin este filtro, `True` colaría
        # como si fuera un 1.
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            return f"'{campo}' debe ser un número"
        if valor < 0:
            return f"'{campo}' no puede ser negativo"

    return None


def _aplicar(alimento, datos):
    """Vuelca al alimento solo los campos presentes en el cuerpo."""
    for campo in ("nombre", "categoria", "estado", "nutrientes_extra", *CAMPOS_NUTRICIONALES):
        if campo in datos:
            setattr(alimento, campo, datos[campo])


@catalogo_bp.get("")
def listar_alimentos():
    """Busca en el catálogo. Público, paginado y sin distinguir mayúsculas ni acentos."""
    consulta = Alimento.query

    buscar = (request.args.get("buscar") or "").strip()
    if buscar:
        # Se busca contra `nombre_normalizado`, que ya está en minúsculas y sin
        # acentos, así que "platano" y "Plátano" encuentran lo mismo.
        consulta = consulta.filter(
            Alimento.nombre_normalizado.like(_patron_busqueda(buscar), escape="\\")
        )

    categoria = (request.args.get("categoria") or "").strip()
    if categoria:
        consulta = consulta.filter(Alimento.categoria == categoria)

    pagina = _entero(request.args.get("pagina"), 1, 1, 10_000)
    por_pagina = _entero(
        request.args.get("por_pagina"), POR_PAGINA_POR_DEFECTO, 1, POR_PAGINA_MAXIMO
    )

    resultado = (
        consulta.order_by(Alimento.nombre_normalizado)
        .paginate(page=pagina, per_page=por_pagina, error_out=False)
    )

    return jsonify(
        # Sin `nutrientes_extra`: son ~100 nutrientes por alimento y aquí no se miran.
        alimentos=[a.to_dict(incluir_extra=False) for a in resultado.items],
        pagina=resultado.page,
        por_pagina=resultado.per_page,
        total=resultado.total,
        paginas=resultado.pages,
    ), 200


@catalogo_bp.get("/<int:alimento_id>")
def obtener_alimento(alimento_id):
    """Devuelve un alimento con todos sus nutrientes."""
    alimento = db.session.get(Alimento, alimento_id)
    if alimento is None:
        return jsonify(error="alimento no encontrado"), 404
    return jsonify(alimento.to_dict()), 200


@catalogo_bp.post("")
@requiere_sesion
def crear_alimento():
    """Crea un alimento a mano. Nace como `manual` y queda protegido desde el minuto uno."""
    datos = request.get_json(silent=True) or {}

    error = _validar(datos, exigir_nombre=True)
    if error:
        return jsonify(error=error), 400

    alimento = Alimento(origen=ORIGEN_MANUAL)
    _aplicar(alimento, datos)
    db.session.add(alimento)
    db.session.commit()

    respuesta = jsonify(alimento.to_dict())
    respuesta.headers["Location"] = f"/alimentos/{alimento.id}"
    return respuesta, 201


@catalogo_bp.patch("/<int:alimento_id>")
@requiere_sesion
def editar_alimento(alimento_id):
    """Edita un alimento y lo marca como `manual` (decisión 3.13).

    El cambio de origen no es opcional ni configurable: tocarlo ES lo que lo
    blinda. Así no hace falta revisar el catálogo entero, solo lo que chirría.
    """
    alimento = db.session.get(Alimento, alimento_id)
    if alimento is None:
        return jsonify(error="alimento no encontrado"), 404

    datos = request.get_json(silent=True) or {}

    error = _validar(datos, exigir_nombre=False)
    if error:
        return jsonify(error=error), 400

    _aplicar(alimento, datos)
    alimento.origen = ORIGEN_MANUAL
    db.session.commit()

    return jsonify(alimento.to_dict()), 200


@catalogo_bp.delete("/<int:alimento_id>")
@requiere_sesion
def borrar_alimento(alimento_id):
    """Borra un alimento. 204 porque no hay nada que devolver."""
    alimento = db.session.get(Alimento, alimento_id)
    if alimento is None:
        return jsonify(error="alimento no encontrado"), 404

    db.session.delete(alimento)
    db.session.commit()
    return "", 204
