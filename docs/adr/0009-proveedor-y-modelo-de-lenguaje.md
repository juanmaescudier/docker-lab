# ADR-0009: Proveedor y modelo de lenguaje

- **Estado:** Aceptado
- **Fecha:** 2026-07-31

## Contexto

El ADR-0008 dejó montado el corte a multiservicio con la cola y el worker, pero el
worker no hablaba con ningún modelo: calculaba unas calorías con una constante en
el código, que era un *stub* para tener algo que encolar.

Al mirarlo con calma vi que ese trabajo **no debería existir**: sumar los
nutrientes de seis ingredientes son microsegundos y sale del catálogo, así que
pertenece a la API y no a una cola. Lo que sí justifica una cola es llamar a un
modelo de lenguaje, que tarda **minutos** y falla de formas variadas.

O sea que había que meter el modelo de verdad para que el worker tuviera sentido.

## Decisión

**Un servicio gestionado a través de OpenRouter, con `deepseek/deepseek-v4-pro`**,
detrás de una interfaz que permite cambiar de proveedor sin tocar la arquitectura.

El proveedor y el modelo van por **variable de entorno**, así que probar otro no
exige reconstruir la imagen.

## Alternativas consideradas

**Ollama autoalojado en un contenedor.** Era mi idea inicial: tengo una 3090 y 64
GB de RAM, así que en local funcionaría. Lo descarté porque **no se parece a
producción**: en AWS una instancia con GPU cuesta mucho más que las llamadas a una
API a este volumen, y una GPU parada cuesta igual que una trabajando. Nadie pone
un contenedor de Ollama para servir cientos de generaciones al día.

Sigue teniendo sentido como proveedor de desarrollo, y por eso la interfaz existe.

**Un proveedor concreto (OpenAI, Anthropic) directamente.** OpenRouter es una
pasarela: un solo contrato y una sola clave para hablar con modelos de varias
casas. Eso es exactamente lo que necesitaba para **comparar modelos con el mismo
código**, y es además un patrón real de producción.

**Seguir con el stub.** Habría dejado el worker sin razón de ser y, sobre todo,
todo lo que aprendí midiendo habría quedado invisible (ver más abajo).

## Por qué este modelo

Medido el 30/07/2026 con el mismo perfil y el mismo catálogo de 45 alimentos:

| Modelo | Tiempo | Coste por plan | Recetas para 28 comidas |
|---|---|---|---|
| `openai/gpt-4o-mini` | 13–17 s | $0,0009–0,0011 | 5–7 |
| `openai/gpt-5-nano` | 72–126 s | $0,0042–0,0046 | 7–8 |
| `deepseek/deepseek-v4-pro` | 85–174 s | $0,009–0,034 | **12–13** |

Lo que decidió no fue la tabla, fue verlo en la parrilla: **`gpt-4o-mini` repite el
mismo desayuno los siete días y deepseek alterna tres.** Un plan que repite
desayuno toda la semana no lo sigue nadie.

Es también el único de los tres con capacidad de razonamiento y el único que llega
a 12–13 recetas. Evidencia flaca —tres modelos, pocas pasadas— pero apunta a que
componer un plan es un problema de restricciones encadenadas, y ahí el
razonamiento paga.

**Es una decisión revisable y barata de revisar**, que es justo el punto de que el
modelo vaya por entorno.

## Decisiones concretas

**La clave solo llega al worker.** Es el único servicio que habla con OpenRouter.
La API no la recibe, así que no puede filtrarla aunque quisiera.

**Una red `egress` aparte.** El worker está en `backend` y en `egress`; el resto de
servicios no tienen salida a internet. Aprendí que basta con que un servicio esté
en **una** red no interna para que tenga salida: `internal: true` en las otras no
lo impide.

**Los errores se clasifican por si merece la pena reintentar**, no por su código
HTTP. Un 429 se reintenta respetando el `Retry-After`; un 401 no, porque es
configuración; y una respuesta truncada por `max_tokens` tampoco, porque **la misma
petición se corta igual y cada reintento cuesta dinero**.

**El consumo se registra en el log JSON de cada llamada**: modelo, tokens de
entrada y salida, coste y duración. Es lo que permite calcular el coste por
usuario, que es el suelo de cualquier precio que ponga algún día.

**El modelo nunca ve un número nutricional.** Recibe id, nombre, categoría y estado
de cada alimento, y nada más. No puede inventarse una caloría porque no ve
ninguna: los totales los calcula la API desde el catálogo. Y todo lo que devuelve
se valida aunque haya prometido cumplir el esquema.

## Lo que aprendí midiendo

**El `timeout` de `requests` no acota la duración total.** Acota el silencio entre
bytes: cada byte que llega reinicia la cuenta. Con 120 s configurados tuve una
llamada abierta **8 minutos** sin que saltara nada, y el worker bloqueado todo ese
rato. El tope real hay que ponerlo mirando el reloj mientras se consume la
respuesta. Lo di por bueno sin comprobarlo y me equivoqué; la documentación lo dice
con todas las letras.

**Los tokens de salida no miden contenido.** `gpt-5-nano` gastó 11.059 tokens para
7 recetas y deepseek 9.794 para 13. El primero es verboso, no sustancioso.

**El coste de un modelo de razonamiento varía mucho**: deepseek se movió casi cuatro
veces entre generaciones ($0,009 a $0,034), mientras nano varió un 8%. Para
presupuestar, uno es predecible y el otro no.

**Los límites tienen que abrazar el rango natural del modelo, no rozarlo.** Con el
mínimo de recetas en 12, `gpt-4o-mini` cumplió 1 de cada 4 pasadas —una de las
fallidas devolvió 11— y **cada rechazo se paga**. Con tres intentos por trabajo,
eso son cuatro de cada diez generaciones fallando del todo.

**Un campo mal nombrado hace que el modelo adivine mal.** Un `label` en la comida
se rellenó con el día de la semana en las 56 comidas de un plan. Renombrarlo a
`meal_label` y explicarlo en el prompt lo arregló. El *naming* es contrato, también
con un modelo.

**Y dos fallos que solo aparecieron con el proveedor real**: un 404 de modelo
inexistente estaba clasificado como reintentable cuando es configuración, y el
truncado por `max_tokens` necesitaba su propio tipo. Con el stub eran invisibles, y
es el argumento de por qué empecé por el servicio gestionado.

## Consecuencias

**A favor:** el worker tiene una razón de ser real; la cola, los reintentos y la
idempotencia dejan de ser un ejercicio y protegen algo que cuesta dinero; y el
coste por trabajo es medible desde el primer día.

**En contra:** dependo de un tercero y de que su latencia sea razonable, que ya vi
que no siempre lo es. Una generación de plan semanal completo se acerca al techo de
tokens según crecen las comidas al día, así que **generar la semana entera en una
sola llamada no escala**: la salida natural será partirlo, y queda anotado.

**Pendiente:** un trabajo que se queda en `processing` porque el worker murió no lo
recupera nadie, y no hay forma de cancelarlo desde la aplicación. Me pasó de
verdad y lo tuve que resolver a mano en la base de datos. Es el *visibility
timeout* que implementan las colas serias, y es el argumento concreto para migrar
a Celery.
