"""Acceso al modelo de lenguaje.

Una interfaz (`LLMProvider`) y dos implementaciones: `StubProvider`, que no toca
la red, y `OpenRouterProvider`, que llama al servicio gestionado. Ollama queda
como tercera implementación para más adelante; por eso la elección es una
variable de entorno y no un `import`.

Ni el proveedor ni el modelo están escritos en el código: se eligen con
`LLM_PROVIDER` y `LLM_MODEL`, para poder probar modelos distintos sin reconstruir
la imagen.
"""
import os

from .base import LLMProvider, LLMResponse
from .errors import (
    LLMAuthError,
    LLMError,
    LLMInvalidJSON,
    LLMRateLimited,
    LLMSchemaError,
    LLMServiceError,
    LLMTimeout,
)
from .openrouter import OpenRouterProvider
from .stub import StubProvider

PROVIDERS = {
    "stub": StubProvider,
    "openrouter": OpenRouterProvider,
}

DEFAULT_PROVIDER = "stub"


def get_provider(name=None, model=None):
    """Construye el proveedor indicado por el entorno (o por argumento).

    El argumento existe para `scripts/try_prompt.py`, que necesita cambiar de
    modelo en cada ejecución sin tocar el entorno del contenedor.

    Por defecto, `stub`: si alguien despliega sin configurar nada, la tubería
    funciona sin gastar dinero en vez de fallar a mitad del primer trabajo.
    """
    name = (name or os.environ.get("LLM_PROVIDER") or DEFAULT_PROVIDER).lower()

    provider_class = PROVIDERS.get(name)
    if provider_class is None:
        raise ValueError(
            f"LLM_PROVIDER='{name}' desconocido; opciones: "
            + ", ".join(sorted(PROVIDERS))
        )

    return provider_class(model=model or os.environ.get("LLM_MODEL"))


__all__ = [
    "DEFAULT_PROVIDER",
    "PROVIDERS",
    "LLMAuthError",
    "LLMError",
    "LLMInvalidJSON",
    "LLMProvider",
    "LLMRateLimited",
    "LLMResponse",
    "LLMSchemaError",
    "LLMServiceError",
    "LLMTimeout",
    "OpenRouterProvider",
    "StubProvider",
    "get_provider",
]
