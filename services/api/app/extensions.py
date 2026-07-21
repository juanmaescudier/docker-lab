"""Extensiones compartidas de la app (sin atarlas todavía a ninguna app).

Se conectan a la app en el factory con .init_app(app). Tenerlas aquí, sueltas,
evita importaciones circulares entre el factory y los módulos que las usan.
"""
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()      # ORM (Postgres)
sess = Session()       # gestión de sesiones (Flask-Session, respaldada por Redis)
