"""Proveedor que llama a OpenRouter.

La URL, las cabeceras y el formato de la petición salen de su documentación, no
de deducirlos: https://openrouter.ai/docs — la API es compatible con la de
OpenAI, el endpoint es `/api/v1/chat/completions` y la clave viaja en
`Authorization: Bearer`.

**La clave nunca aparece en el código, ni en un log, ni en un mensaje de error.**
Se lee del entorno en cada llamada y los mensajes de error se construyen a mano
en vez de arrastrar la excepción original, que puede llevar la petición entera
—cabeceras incluidas— dentro de su representación.
"""
import json
import os
import time

import requests

from .base import LLMProvider, LLMResponse
from .errors import (
    LLMAuthError,
    LLMBadRequest,
    LLMInvalidJSON,
    LLMRateLimited,
    LLMServiceError,
    LLMTimeout,
    LLMTruncated,
)

API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Se puede apuntar a otro sitio con LLM_API_URL. Sirve para dos cosas: meter un
# proxy o pasarela por delante, y —sobre todo— poder ensayar los fallos (una
# respuesta que no es JSON, un alimento inventado) contra un servidor de mentira,
# sin gastar peticiones reales ni depender de que el modelo se equivoque.

# Modelo por defecto solo para que el proceso arranque si nadie ha puesto
# LLM_MODEL. La idea es fijarlo siempre por entorno y poder cambiarlo sin
# reconstruir la imagen.
DEFAULT_MODEL = "openai/gpt-4o-mini"

# Tope de duración TOTAL de la llamada, en segundos. Sube de 120 a 300 porque con
# 120 el modelo que se está usando fallaría dos de cada tres veces: cinco
# generaciones medidas de `deepseek/deepseek-v4-pro` tardaron 118, 146, 150 y
# 174 s. No es un tope de silencio, es de reloj (ver `_read_within_deadline`).
DEFAULT_TIMEOUT_SECONDS = 300

# Establecer la conexión es cuestión de milisegundos; si tarda más de esto, el
# extremo no está. Va aparte del tope total: mezclarlos haría esperar cinco
# minutos a un servidor que ni siquiera acepta la conexión.
CONNECT_TIMEOUT_SECONDS = 10

CHUNK_SIZE_BYTES = 8192

# Tope de tamaño del cuerpo. Un servidor que emite sin parar llenaría la memoria
# del worker antes de vencer ningún plazo. 8 MiB son de sobra: la respuesta más
# grande medida hasta ahora no llega a 40 KiB.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
# Un plan semanal completo son unas 3.000 fichas de salida con un modelo normal,
# pero los de razonamiento gastan bastante más antes de escribir la respuesta: uno
# de ellos consumió 9.500 en una prueba real y con el tope en 16.000 se cortó. El
# tope está para que un modelo que se desboque no salga caro, no para recortar
# una respuesta legítima.
DEFAULT_MAX_TOKENS = 32000
DEFAULT_TEMPERATURE = 0.6

# Cómo se le pide el JSON al modelo:
#   json_schema  → salida estructurada: el proveedor impone el esquema.
#   json_object  → solo «devuelve JSON», sin esquema.
#   none         → nada; el JSON se pide únicamente en el prompt.
# No todos los modelos de OpenRouter admiten salida estructurada, y con los que
# no la admiten la petición falla con 400. Por eso es una variable de entorno:
# probar un modelo nuevo no puede exigir tocar el código.
RESPONSE_FORMATS = ("json_schema", "json_object", "none")
DEFAULT_RESPONSE_FORMAT = "json_schema"


def _int_env(name, default):
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


def _float_env(name, default):
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


class OpenRouterProvider(LLMProvider):
    name = "openrouter"

    def __init__(self, model=None, response_format=None, timeout=None):
        super().__init__(model=model)
        self.api_url = os.environ.get("LLM_API_URL") or API_URL
        self.timeout = timeout or _int_env("LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        self.max_tokens = _int_env("LLM_MAX_TOKENS", DEFAULT_MAX_TOKENS)
        self.temperature = _float_env("LLM_TEMPERATURE", DEFAULT_TEMPERATURE)

        chosen = (
            response_format
            or os.environ.get("LLM_RESPONSE_FORMAT")
            or DEFAULT_RESPONSE_FORMAT
        ).lower()
        if chosen not in RESPONSE_FORMATS:
            raise ValueError(
                f"LLM_RESPONSE_FORMAT='{chosen}' desconocido; opciones: "
                + ", ".join(RESPONSE_FORMATS)
            )
        self.response_format = chosen

    def default_model(self):
        return DEFAULT_MODEL

    # ---------- Petición ----------

    def _headers(self):
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key:
            # Se dice qué variable falta, nunca su valor.
            raise LLMAuthError("falta la variable de entorno OPENROUTER_API_KEY")

        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # Opcionales, solo para las clasificaciones de OpenRouter. Van con
            # el nombre exacto que documenta el proveedor.
            "HTTP-Referer": os.environ.get(
                "LLM_APP_URL", "https://github.com/nutriapp/docker-lab"
            ),
            "X-OpenRouter-Title": os.environ.get("LLM_APP_NAME", "nutriapp"),
        }

    def _body(self, prompt):
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        if self.response_format == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": prompt.name,
                    # `strict` hace que los proveedores con modo estricto nativo
                    # impongan el esquema exactamente. Aun así se valida después:
                    # la documentación dice que el cumplimiento varía según el
                    # proveedor que enrute la petición.
                    "strict": True,
                    "schema": prompt.schema,
                },
            }
        elif self.response_format == "json_object":
            body["response_format"] = {"type": "json_object"}

        return body

    def complete(self, prompt):
        # El plazo se cuenta con `monotonic` y no con la hora del sistema: un
        # ajuste de reloj a mitad de llamada no puede alargarlo ni acortarlo.
        started = time.monotonic()

        try:
            # `stream=True` devuelve en cuanto llegan las CABECERAS, sin
            # descargar el cuerpo. Es lo que permite ir mirando el reloj mientras
            # se consume la respuesta (ver `_read_within_deadline`).
            with requests.post(
                self.api_url,
                headers=self._headers(),
                json=self._body(prompt),
                # El primer valor acota la conexión; el segundo, el SILENCIO
                # entre bytes. Ninguno acota la duración total: eso lo pone el
                # reloj de `_read_within_deadline`.
                timeout=(CONNECT_TIMEOUT_SECONDS, self.timeout),
                stream=True,
            ) as response:
                self._raise_for_status(response)
                body = self._read_within_deadline(response, started)
        except requests.Timeout:
            raise LLMTimeout(
                f"el modelo no ha enviado nada en {self.timeout} s"
            ) from None
        except requests.RequestException as exc:
            # Solo el tipo de excepción, nunca su repr: puede llevar la petición
            # completa con la cabecera Authorization dentro.
            raise LLMServiceError(
                f"no se ha podido contactar con OpenRouter ({type(exc).__name__})"
            ) from None

        return self._parse(body, (time.monotonic() - started) * 1000)

    def _read_within_deadline(self, response, started):
        """Descarga el cuerpo vigilando el reloj. Devuelve el texto.

        **Por qué hace falta esto y no basta con el parámetro `timeout`.** La
        documentación de `requests` es explícita: el *read timeout* es «el número
        de segundos que el cliente espera ENTRE bytes enviados por el servidor»,
        y añade que «ni el timeout de conexión ni el de lectura son de reloj de
        pared». Cada byte que llega reinicia la cuenta, así que un servidor que
        gotea mantiene la llamada abierta indefinidamente: con 120 s
        configurados se midió una llamada de **8 minutos** que no cortó, y dejó
        al worker bloqueado todo ese rato.

        Se descarta la alarma del sistema operativo (`signal.alarm`), que era la
        otra vía: solo funciona en el hilo principal, es estado global del
        proceso —una sola alarma para todo el mundo— y aquí ya hay manejadores
        de `SIGTERM` y `SIGINT` que no conviene rozar. Este bucle no depende del
        hilo, no toca señales y cierra la conexión de forma determinista.

        Se descarta también lanzar la llamada en otro hilo con un `Future`: al
        vencer el plazo el hilo sigue vivo, porque a un hilo de Python no se le
        puede matar, y cada vencimiento dejaría una conexión abierta y un hilo
        colgado.

        **Qué garantiza exactamente:** entre trozo y trozo se comprueba el reloj,
        así que un goteo se corta al llegar al plazo. Un silencio total después
        de las cabeceras lo corta el *read timeout*, que en el peor caso puede
        sumarse al plazo; se acepta porque ese caso ya lo cubre `LLMTimeout`
        igual y evita meter una variable más solo para el peor caso.
        """
        chunks = []
        size = 0

        for chunk in response.iter_content(chunk_size=CHUNK_SIZE_BYTES):
            elapsed = time.monotonic() - started
            if elapsed > self.timeout:
                raise LLMTimeout(
                    f"la llamada ha superado el tope de {self.timeout} s "
                    f"(iba por {elapsed:.0f} s y seguía recibiendo datos)"
                )

            if not chunk:
                # `iter_content` puede entregar trozos vacíos de keep-alive.
                continue

            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                # Un cuerpo sin fin llenaría la memoria del worker antes de que
                # venciera ningún plazo. El tope va en bytes y no en tokens
                # porque aquí todavía no se ha parseado nada.
                raise LLMServiceError(
                    f"la respuesta supera los {MAX_RESPONSE_BYTES} bytes"
                )
            chunks.append(chunk)

        return b"".join(chunks).decode("utf-8", errors="replace")

    # ---------- Respuesta ----------

    @staticmethod
    def _error_message(response):
        """Extrae el mensaje de error del cuerpo, si viene en el formato documentado."""
        try:
            payload = response.json()
        except ValueError:
            return response.text[:200]

        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message", ""))[:300]
        return str(payload)[:300]

    def _raise_for_status(self, response):
        """Traduce el código HTTP al tipo de error que corresponde.

        Los códigos y su significado son los que documenta OpenRouter. Lo que
        decide el tipo es si reintentar sirve de algo.
        """
        status = response.status_code

        if status < 400:
            return

        message = self._error_message(response)

        if status in (401, 403):
            raise LLMAuthError(f"OpenRouter ha rechazado la credencial ({status})")
        if status == 402:
            raise LLMAuthError("la cuenta de OpenRouter no tiene saldo (402)")
        if status == 429:
            # `Retry-After` viene en segundos: hacerle caso es más educado —y más
            # eficaz— que aplicar la espera creciente propia.
            retry_after = response.headers.get("Retry-After")
            try:
                retry_after = float(retry_after) if retry_after else None
            except ValueError:
                retry_after = None
            raise LLMRateLimited(
                f"OpenRouter ha limitado el ritmo de peticiones (429): {message}",
                retry_after=retry_after,
            )
        if status == 408:
            raise LLMTimeout("OpenRouter ha dado la petición por caducada (408)")
        if status == 400:
            raise LLMBadRequest(
                f"petición inválida para el modelo '{self.model}' (400): {message}. "
                "Si el modelo no admite salida estructurada, prueba con "
                "LLM_RESPONSE_FORMAT=json_object"
            )
        if status == 404:
            # Un modelo que no existe (o ya retirado) no aparece por reintentar:
            # es un error de configuración, no una avería pasajera. Sale al
            # probar modelos por su nombre, que es justo lo que hace try_prompt.
            raise LLMBadRequest(
                f"OpenRouter no conoce el modelo '{self.model}' (404): {message}"
            )
        if status >= 500:
            raise LLMServiceError(f"OpenRouter ha fallado ({status}): {message}")

        raise LLMServiceError(f"OpenRouter ha respondido {status}: {message}")

    def _parse(self, body, duration_ms):
        try:
            payload = json.loads(body)
        except ValueError:
            raise LLMInvalidJSON(
                "OpenRouter ha respondido algo que no es JSON: " + body[:200]
            ) from None

        # Un fallo del proveedor puede llegar con HTTP 200 y el error dentro del
        # cuerpo, porque las cabeceras ya se habían enviado. Sin esta comprobación
        # se leería `choices` de una respuesta que no lo tiene.
        error = payload.get("error")
        if isinstance(error, dict):
            raise LLMServiceError(
                f"OpenRouter ha devuelto un error en el cuerpo: "
                f"{str(error.get('message', ''))[:300]}"
            )

        choices = payload.get("choices") or []
        if not choices:
            raise LLMInvalidJSON("la respuesta de OpenRouter no trae 'choices'")

        choice = choices[0]
        finish_reason = choice.get("finish_reason")
        content = (choice.get("message") or {}).get("content")

        if finish_reason == "length":
            # Tipo propio y no LLMInvalidJSON: el síntoma es el mismo (un JSON
            # roto) pero la causa es determinista, así que reintentar solo
            # gastaría dinero para volver a cortarse en el mismo sitio.
            raise LLMTruncated(
                f"la respuesta se ha cortado al llegar al límite de "
                f"{self.max_tokens} tokens de salida; sube LLM_MAX_TOKENS"
            )
        if finish_reason == "error":
            raise LLMServiceError("el proveedor ha cortado la generación con error")

        usage = payload.get("usage") or {}

        return LLMResponse(
            data=self.parse_json(content),
            raw=content or "",
            # El modelo que responde puede no ser exactamente el pedido:
            # OpenRouter enruta y puede aplicar variantes o alternativas.
            model=payload.get("model") or self.model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            cost=usage.get("cost"),
            duration_ms=round(duration_ms, 1),
            extra={"finish_reason": finish_reason, "id": payload.get("id")},
        )
