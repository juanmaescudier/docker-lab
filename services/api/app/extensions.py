"""Extensiones compartidas de la app.

Creamos aquí el objeto `db` (SQLAlchemy) SIN atarlo todavía a ninguna app.
Se conecta a la app luego, en el factory, con db.init_app(app).
Ponerlo en su propio fichero evita importaciones circulares: tanto el factory
como los modelos pueden importar `db` desde aquí sin depender uno del otro.
"""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
