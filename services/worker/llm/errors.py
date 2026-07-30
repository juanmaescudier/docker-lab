"""Tipos de error de una llamada al modelo.

Cada fallo se distingue por su tipo y no por el texto del mensaje, porque de lo
que decide el worker es de si **merece la pena reintentar**:

- Un tiempo de espera agotado o un 429 se arreglan solos esperando.
- Una clave rechazada no se arregla nunca reintentando: reintentar solo gasta
  tiempo y puede acabar bloqueando la cuenta.
- Una respuesta que no es JSON o que no cumple el esquema **sí** se reintenta: el
  modelo es no determinista y a la segunda suele salir bien.

`retryable` es un atributo de clase para que el worker no tenga que mantener una
lista de tipos: pregunta al error.

**Ningún mensaje de error incluye jamás la clave de la API.** Los mensajes se
construyen a mano en lugar de arrastrar la excepción original, que en algunas
librerías lleva la petición completa —cabeceras incluidas— dentro del `repr`.
"""


class LLMError(Exception):
    """Cualquier fallo hablando con el modelo."""

    retryable = False


class LLMTimeout(LLMError):
    """Se agotó el tiempo de espera."""

    retryable = True


class LLMRateLimited(LLMError):
    """El proveedor ha limitado el ritmo de peticiones (429)."""

    retryable = True

    def __init__(self, message, retry_after=None):
        super().__init__(message)
        # Segundos que pide esperar la cabecera `Retry-After`, si la manda.
        self.retry_after = retry_after


class LLMAuthError(LLMError):
    """Clave rechazada o sin saldo (401, 402, 403). No se reintenta."""

    retryable = False


class LLMServiceError(LLMError):
    """El proveedor o el modelo han fallado (5xx, modelo caído)."""

    retryable = True


class LLMBadRequest(LLMError):
    """La petición es inválida para ese modelo (400).

    No se reintenta: el modelo elegido no admite lo que se le pide —salida
    estructurada, por ejemplo— y volver a pedírselo dará el mismo 400.
    """

    retryable = False


class LLMInvalidJSON(LLMError):
    """El modelo ha devuelto algo que no es JSON válido."""

    retryable = True


class LLMTruncated(LLMError):
    """La respuesta se cortó al llegar al límite de tokens de salida.

    **No se reintenta**, aunque el síntoma sea un JSON roto. La causa no es el
    azar del modelo sino el propio límite: la misma petición con el mismo tope se
    va a cortar otra vez, y cada reintento cuesta dinero de verdad. Lo que hay
    que cambiar es `LLM_MAX_TOKENS`, no volver a intentarlo.

    Se ve enseguida con los modelos de razonamiento, que gastan buena parte del
    presupuesto de salida antes de escribir la primera llave.
    """

    retryable = False


class LLMSchemaError(LLMError):
    """El JSON es válido pero no cumple el esquema o contradice el catálogo.

    Campos de más, tipos equivocados, un identificador de alimento que no existe.
    **Nunca se confía en la forma de la respuesta**, aunque el modelo prometa
    cumplir el esquema.
    """

    retryable = True
