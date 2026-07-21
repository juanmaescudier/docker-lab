"""Modelo de datos del dominio Usuarios.

Una clase = una tabla. Un objeto = una fila. Un atributo = una columna.
"""
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    # Guardamos el HASH de la contraseña, nunca la contraseña en claro.
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120))
    age = db.Column(db.Integer)
    height_cm = db.Column(db.Integer)
    weight_kg = db.Column(db.Float)
    goal = db.Column(db.String(120))

    def set_password(self, password):
        """Genera y guarda el hash (con sal) de la contraseña."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Comprueba si la contraseña coincide con el hash guardado."""
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        """Diccionario para el JSON. OJO: nunca incluimos el password_hash."""
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "age": self.age,
            "height_cm": self.height_cm,
            "weight_kg": self.weight_kg,
            "goal": self.goal,
        }
