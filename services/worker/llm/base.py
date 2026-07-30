"""La interfaz del proveedor de modelo.

Todo lo que el worker sabe hacer con un modelo está aquí: mandarle un `Prompt` y
recibir **JSON**. No hay streaming ni conversación: un trabajo de la cola es una
pregunta y una respuesta.

Que la interfaz devuelva JSON y no texto no es un capricho: lo que el worker hace
con la respuesta es escribir filas en PostgreSQL, y para eso necesita campos, no
prosa.
"""
import json
from dataclasses import dataclass, field

from .errors import LLMInvalidJSON


@dataclass
class Prompt:
    """Todo lo que define una petición al modelo.

    Va junto en un objeto en vez de suelto en cuatro argumentos porque quien
    construye el prompt es también quien sabe qué forma tiene una respuesta
    correcta: `stub_response` la acompaña.

    `stub_response` es la respuesta fija y **válida** que devuelve `StubProvider`.
    Que la escriba el mismo módulo que redacta el prompt es lo que la mantiene
    coherente con el esquema: si mañana cambia un campo, se ven los dos a la vez.
    """

    system: str
    user: str
    schema: dict
    name: str
    stub_response: dict = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Respuesta de una llamada, con lo necesario para medir el coste.

    `raw` se conserva además de `data` porque cuando una respuesta no valida, lo
    único que sirve para entender por qué es el texto tal y como llegó.
    """

    data: dict
    raw: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    # Coste en créditos, cuando el proveedor lo informa. El stub no lo tiene.
    cost: float | None = None
    # Duración de reloj de la llamada, en milisegundos.
    duration_ms: float = 0.0
    extra: dict = field(default_factory=dict)

    def usage_fields(self):
        """Los campos de consumo, listos para el log en JSON.

        Primer paso para poder medir el coste: con esto en Kibana se puede
        agregar por modelo y ver qué cuesta cada tipo de trabajo.

        La duración va aquí y no solo en `scripts/try_prompt.py` porque ese
        script es de usar y tirar: la latencia hay que verla en el código que
        corre de verdad, que es donde se decide si un tope está bien puesto.
        """
        fields = {
            "llm_model": self.model,
            "llm_prompt_tokens": self.prompt_tokens,
            "llm_completion_tokens": self.completion_tokens,
            "llm_total_tokens": self.total_tokens,
            "llm_duration_ms": self.duration_ms,
        }
        if self.cost is not None:
            fields["llm_cost"] = self.cost
        return fields


class LLMProvider:
    """Contrato que cumplen el stub, OpenRouter y —más adelante— Ollama."""

    #: Nombre corto para los logs.
    name = "base"

    def __init__(self, model=None):
        self.model = model or self.default_model()

    def default_model(self):
        return "unset"

    def complete(self, prompt):
        """Pide una respuesta en JSON y la devuelve ya parseada.

        Los proveedores que sepan imponer el esquema lo usan; los que no, se
        limitan a pedir JSON en el prompt. En **ningún caso** eso exime de
        validar: quien llama comprueba la respuesta por su cuenta.
        """
        raise NotImplementedError

    @staticmethod
    def parse_json(raw):
        """Convierte el texto del modelo en un diccionario.

        Tolera que venga envuelto en un bloque ```json, que es lo que hacen los
        modelos que no soportan salida estructurada por mucho que se les pida
        «solo JSON».
        """
        text = (raw or "").strip()

        if text.startswith("```"):
            # Quita la primera línea (```json) y la valla de cierre.
            text = text.split("\n", 1)[-1]
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3]
            text = text.strip()

        if not text:
            raise LLMInvalidJSON("el modelo ha devuelto una respuesta vacía")

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            # Se recorta: una respuesta de 8.000 caracteres en el campo `error`
            # de la fila no ayuda a nadie y llena la tabla.
            raise LLMInvalidJSON(
                f"la respuesta no es JSON válido ({exc.msg} en la posición "
                f"{exc.pos}): {text[:200]}"
            ) from None

        if not isinstance(data, dict):
            raise LLMInvalidJSON(
                f"se esperaba un objeto JSON y ha llegado {type(data).__name__}"
            )

        return data
