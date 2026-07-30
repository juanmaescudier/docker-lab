"""Proveedor de mentira: devuelve una respuesta fija y válida, sin tocar la red.

Es lo que se usa en los tests y para probar la tubería completa —encolar,
procesar, escribir el plan, consultar `/jobs/<id>`— **sin gastar dinero ni
depender de internet**. Con `LLM_PROVIDER=stub` un `docker compose up` desde cero
hace el recorrido entero.

La respuesta la trae el propio `Prompt` (`stub_response`), porque quien redacta el
prompt es quien sabe qué forma tiene una respuesta correcta. Así el stub no
duplica el esquema y no se queda desfasado cuando el esquema cambie.

**No se salta la validación.** Lo que devuelve pasa por el mismo validador que la
respuesta de un modelo real: si el stub se rompiera, el fallo tiene que salir en
los tests, no colarse.
"""
import json
import os
import time

from .base import LLMProvider, LLMResponse

# Latencia simulada. Por defecto **cero**: el objetivo del stub es que los tests
# sean rápidos. Se sube a mano cuando lo que se quiere ver es el trabajo pasando
# por el estado `processing`, que con 0 s dura un suspiro.
DEFAULT_LATENCY_SECONDS = 0.0


class StubProvider(LLMProvider):
    name = "stub"

    def __init__(self, model=None, latency=None):
        # El modelo configurado se ignora a propósito. Si el stub informara del
        # valor de LLM_MODEL, el log de consumo diría que la respuesta la dio un
        # modelo real cuando no ha salido ni una petición a la red.
        super().__init__(model=None)
        if latency is None:
            try:
                latency = float(os.environ.get("LLM_STUB_LATENCY_SECONDS", ""))
            except ValueError:
                latency = DEFAULT_LATENCY_SECONDS
        self.latency = latency

    def default_model(self):
        return "stub"

    def complete(self, prompt):
        if self.latency:
            time.sleep(self.latency)

        raw = json.dumps(prompt.stub_response, ensure_ascii=False)

        # Los tokens se cuentan a cero y no se inventan: un número falso en el
        # log de consumo estropearía justo la medida que ese log existe para dar.
        return LLMResponse(
            data=prompt.stub_response,
            raw=raw,
            model=self.model,
            extra={"stub": True},
        )
