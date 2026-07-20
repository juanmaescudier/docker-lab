"""Application factory: crea y configura la app Flask.

El patrón "factory" (fábrica) es una función que CREA la app y la devuelve,
en vez de crearla como una variable global. Ventajas: es más fácil de testear
y de configurar distinto según el entorno (dev, test, producción).
"""
from flask import Flask, jsonify


def create_app():
    app = Flask(__name__)

    # Endpoint de salud. Devuelve "ok" si el servicio está vivo.
    # Más adelante Docker lo usará como healthcheck para saber si el
    # contenedor está sano (esto conecta con el M0).
    @app.get("/health")
    def health():
        return jsonify(status="ok"), 200

    # Importamos y registramos el "blueprint" del dominio Usuarios.
    # Un blueprint = un grupo de endpoints relacionados (nuestro "dominio").
    from .users.routes import users_bp
    app.register_blueprint(users_bp)

    return app
