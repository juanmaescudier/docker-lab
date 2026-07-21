"""Modelo de datos del dominio Usuarios.

Una clase = una tabla. Un objeto = una fila. Un atributo = una columna.
Esto es el ORM: trabajamos con objetos Python y SQLAlchemy genera el SQL.
"""
from ..extensions import db


class User(db.Model):
    __tablename__ = "users"                                   # nombre de la tabla en Postgres

    id = db.Column(db.Integer, primary_key=True)              # clave primaria, autoincremental
    email = db.Column(db.String(255), unique=True, nullable=False)  # obligatorio y único
    name = db.Column(db.String(120))
    age = db.Column(db.Integer)
    height_cm = db.Column(db.Integer)
    weight_kg = db.Column(db.Float)
    goal = db.Column(db.String(120))

    def to_dict(self):
        """Convierte la fila (objeto) en un diccionario para devolverlo como JSON."""
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "age": self.age,
            "height_cm": self.height_cm,
            "weight_kg": self.weight_kg,
            "goal": self.goal,
        }
