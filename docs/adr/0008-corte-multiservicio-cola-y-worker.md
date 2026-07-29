# ADR-0008: Corte a multiservicio con cola y worker

- **Estado:** Aceptado
- **Fecha:** 2026-07-29

## Contexto

El M2 dejó hecho el CI/CD pero pendiente el corte a multiservicio. Toda la
aplicación era un único proceso que respondía peticiones HTTP, así que la
orquestación que viene en M4 no tendría nada que orquestar más allá de la base de
datos y la caché.

Además, la aplicación necesita hacer cosas **lentas**: generar un plan semanal con
un modelo de lenguaje tarda decenas de segundos. Resolverlo dentro de la petición
HTTP significaría bloquear un *worker* de gunicorn todo ese tiempo, y con cuatro
peticiones lentas simultáneas la API dejaría de responder a todo el mundo.

## Decisión

Parto la aplicación **por modo de ejecución**, no por dominio de negocio:

```
Cliente → API (responde en milisegundos) → cola (Redis) → worker (trabajo lento)
                    ↓                                          ↓
                PostgreSQL  ←────────────────────────────────────
```

- La **API** atiende HTTP. Cuando llega una petición lenta, crea el registro del
  trabajo, lo encola y responde **202 Accepted** con un identificador.
- El **worker** es un proceso sin HTTP: consume la cola, procesa y actualiza el
  estado en PostgreSQL.
- El cliente consulta el resultado más tarde con un `GET`.

Los dominios de negocio (usuarios, catálogo, recetas, planes) **siguen viviendo
dentro de la API** como módulos con su propio *blueprint*. Es un **monolito
modular con procesamiento en segundo plano**.

## Alternativas consideradas

**Corte por dominio** (un servicio para usuarios, otro para el catálogo, otro para
la lista de la compra...). Descartado por ahora:

- Multiplica el coste operativo —una imagen, un pipeline y un despliegue por
  servicio— sin enseñarme infraestructura nueva: el Dockerfile sería el mismo
  patrón repetido cuatro veces.
- Obliga a resolver comunicación entre servicios y propiedad de datos, problemas
  reales pero que no necesito todavía.
- La recomendación mayoritaria hoy para equipos pequeños es empezar con un
  monolito modular y extraer servicios cuando duela algo concreto.

Como los dominios ya están separados en módulos, extraer uno más adelante es
viable. De hecho está previsto: **la lista de la compra se promoverá a su propio
servicio** como ejercicio deliberado de separar y comunicar servicios.

**Procesar de forma síncrona con un tiempo de espera largo.** Descartado: un
proceso bloqueado no atiende a nadie más, y los intermediarios (proxies,
balanceadores, navegadores) cortan las peticiones largas.

## Decisiones concretas

### La cola: Redis directamente, no una librería

Uso `LPUSH` desde la API y `BRPOP` desde el worker, sin Celery ni RQ.

**Por qué:** para entender el mecanismo. Con una librería, el bloqueo, la
atomicidad y la pérdida de mensajes quedan tapados por la abstracción. Está
previsto **migrar a Celery** cuando el problema que resuelve se haya visto de
primera mano.

**Lo que ya sé que no cubre:** `BRPOP` **elimina** el mensaje al entregarlo. Si el
worker muere a mitad del trabajo, ese mensaje se pierde y el registro se queda en
`procesando` para siempre. Se puede resolver con `LMOVE`, que mueve el mensaje a
una lista de "en proceso" en lugar de borrarlo, o con Redis Streams. Es
precisamente el problema que justificará la migración.

### Dos instancias de Redis separadas

Una para las sesiones y otra para la cola.

**Por qué:** una caché de sesiones se configura para **expulsar claves cuando se
llena la memoria**, y eso borraría trabajos pendientes. Además limita el radio de
impacto: si la cola se satura, no se lleva por delante las sesiones de todos los
usuarios.

### La cola transporta, PostgreSQL recuerda

El mensaje de la cola solo lleva el identificador del trabajo. Todo el estado
—pendiente, procesando, completado, fallido, el resultado y los errores— vive en
una tabla.

**Por qué:** la cola es efímera por naturaleza; el historial de análisis de un
usuario es dato de negocio y debe sobrevivir a los reinicios. Además, un mensaje
mínimo nunca queda desincronizado con la fila real.

El orden importa: **primero se guarda la fila y se confirma, después se encola**.
Al revés, el worker podría coger el mensaje y buscar una fila que aún no existe.

### El worker no usa el ORM

Habla con PostgreSQL con SQL directo, así que sus dependencias son dos líneas
frente a las siete de la API: no arrastra Flask ni SQLAlchemy.

**Lo que acepto a cambio:** el nombre de la tabla y sus columnas están escritos en
dos sitios. Si cambia el esquema, hay que tocar los dos. La alternativa —compartir
los modelos, que es lo que hace Celery— acopla los dos servicios.

### El apagado limpio es responsabilidad del worker

Docker envía `SIGTERM` y espera unos segundos antes de matar el proceso. El worker
captura esa señal, **termina el trabajo en curso** y sale. Por eso `BRPOP` usa un
tiempo de espera de cinco segundos en lugar de esperar indefinidamente: con espera
infinita nunca comprobaría si le han pedido parar.

## Migraciones de esquema

`db.create_all()` solo crea tablas nuevas; **nunca modifica una existente**. En
cuanto el modelo evoluciona deja de servir, así que el esquema pasa a gestionarse
con **Alembic**.

**Cómo se ejecutan:** con un **servicio efímero** en Compose que lanza
`alembic upgrade head` y termina. La API y el worker esperan a que ese servicio
haya salido con código 0 (`service_completed_successfully`) antes de arrancar.

**Por qué así y no en el arranque de la API:**

- Se ejecuta **una sola vez**, tenga la API una réplica o veinte. Con la migración
  en el arranque, todas las réplicas competirían por migrar a la vez.
- Si la migración falla, **la aplicación no arranca**. Es lo correcto: una
  aplicación contra un esquema equivocado no da un error claro, da fallos raros y
  esporádicos.
- Es el **mismo modelo mental que un `Job` de Kubernetes**, así que en M4 la
  traducción será directa.

**La lección de las migraciones autogeneradas:** al renombrar columnas, Alembic
propuso `DROP` + `ADD`, que habría vaciado los datos. No puede saber que la
intención era renombrar: solo ve dos esquemas y calcula la diferencia. Una
migración autogenerada es un **borrador que hay que revisar**, no un resultado.

## Consecuencias

- La API responde en milisegundos a operaciones que tardan decenas de segundos.
- El worker **escala por separado**: `--scale worker=3` reparte los trabajos entre
  las réplicas, porque `BRPOP` entrega cada mensaje a una sola. En Kubernetes será
  un número de réplicas distinto por *deployment*.
- La observabilidad del M3 cubre el servicio nuevo **sin tocar nada**: el worker
  emite los mismos logs en JSON y aparece en los dashboards de contenedores.
- Un trabajo que falla no tumba el worker: se marca como fallido y sigue
  consumiendo.
- **Deuda asumida:** la pérdida de mensajes de `BRPOP`, la duplicación del esquema
  en el worker, y que el CI/CD todavía construye una sola imagen —falta el
  pipeline del worker.
