# Diseño del dominio — nutriapp

Documento de diseño de la aplicación del laboratorio. Recoge qué hace, cómo está
modelada y por qué tomé cada decisión. El código viene después de esto, no antes.

![Modelo de entidades](img/modelo-entidades.svg)

---

## 1. Qué hace la aplicación

Un asistente de nutrición que planifica comidas y genera la lista de la compra.
El recorrido completo:

1. Me registro y doy mis datos físicos y mi **objetivo** (de una lista cerrada).
2. Pido un **plan semanal**. La IA lo compone: crea recetas y las reparte por los
   días y momentos de la semana.
3. Puedo **editarlo todo a mano**: crear mis propias recetas y planes sin IA.
4. Genero la **lista de la compra** de ese plan: suma los ingredientes de todas
   las recetas planificadas.
5. Pido un **análisis** del plan contra mi objetivo.

Los pasos 2 y 5 son lentos (hablan con un modelo de lenguaje), así que van por
cola y los procesa un worker. El resto son operaciones inmediatas de la API.

**Alcance deliberado:** esto es el laboratorio, no el producto. Cada pieza existe
y hace algo real —para que las métricas, los logs, el escalado y el CI/CD tengan
sentido— pero con la lógica de negocio mínima. Si una funcionalidad no aporta
aprendizaje de infraestructura, se queda fuera o es un *stub*.

---

## 2. Las entidades

| Entidad | Qué representa |
|---|---|
| `User` | Quién soy: datos físicos y objetivo |
| `Alimento` | Un alimento concreto con sus macros por 100 g |
| `Receta` | Un plato, con sus pasos y método de cocción |
| `IngredienteReceta` | Cuántos gramos de un alimento lleva una receta |
| `Plan` | Una semana planificada de un usuario |
| `ComidaPlanificada` | Una receta en un día y momento concretos |
| `Analisis` | Un trabajo asíncrono y su resultado |

La lista de la compra **no es una entidad**: se calcula.

---

## 3. Decisiones de diseño

### 3.1 Las cantidades siempre en crudo

Un alimento cambia mucho al cocinarse: 100 g de arroz crudo no son 100 g de arroz
cocido, porque absorbe agua. Mezclar ambos estados daría cálculos erróneos.

**Decisión:** las recetas expresan sus cantidades **en crudo**, y el método de
cocción se guarda aparte como información para quien cocina.

**Por qué:** es como se escriben las recetas y como se compra en el supermercado,
lo que hace que la lista de la compra sea directa (200 g de arroz en el plan =
200 g que compro). La alternativa —expresarlo en cocinado, que es como pesa la
comida quien hace seguimiento de dieta— obligaría a factores de conversión por
alimento y por método.

**Consecuencia:** la interfaz debe decir **explícitamente** que las cantidades son
en crudo, en cada pantalla donde aparezcan. No puede quedar implícito.

### 3.2 El catálogo guarda alimentos específicos, no conceptos

"Pollo" no es un alimento con macros: la pechuga cruda, el muslo con piel y el
pollo asado tienen valores distintos. Si el catálogo tuviera una única fila
`pollo`, mentiría en casi todas las recetas.

**Decisión:** cada fila de `Alimento` es un alimento **específico y medible**
("pechuga de pollo, cruda"), y una columna `categoria` agrupa las variantes.

**Consecuencia:** "pollo" pasa a ser un **criterio de búsqueda**, no un registro.
Tanto el usuario como la IA ven las variantes disponibles con sus macros y eligen
la que corresponde a esa receta.

### 3.3 La cantidad vive en la relación, no en el alimento

`Alimento` guarda los macros **por 100 g**, que son fijos y universales. Los 200 g
de pollo de una receta concreta pertenecen a esa receta.

Como una receta lleva varios alimentos y un alimento aparece en varias recetas,
es una relación **muchos a muchos**; y como además lleva un dato propio (los
gramos), no basta con una tabla de unión: es una entidad, `IngredienteReceta`.

**Por qué importa:** los macros del pollo se guardan una sola vez. Si mañana los
corrijo, toco una fila y todas las recetas quedan corregidas. Si los hubiera
copiado dentro de cada receta, tendría que actualizar miles de filas y acabarían
divergiendo entre sí.

**Sobre el tamaño:** `IngredienteReceta` crece con las recetas, pero cada fila son
dos enteros y un decimal. Mil recetas de seis ingredientes son seis mil filas.
`Alimento`, en cambio, se mantiene acotado: los alimentos del mundo son finitos.

### 3.4 La lista de la compra se calcula, no se guarda

**Decisión:** `GET /planes/<id>/lista-compra` recorre las comidas del plan, suma
los gramos por alimento y devuelve el resultado en el momento.

**Por qué:** no hay tabla que mantener y la lista **nunca queda desfasada**
respecto al plan. Si guardara la lista y luego cambiara una comida del plan,
tendría dos versiones de la verdad y habría que decidir cuál manda.

**Lo que acepto a cambio:** no se pueden marcar artículos como comprados ni editar
la lista. Para el laboratorio sobra; en un producto real haría falta persistirla.

**Nota de futuro:** esta lógica está pensada para **extraerse a su propio
microservicio** más adelante, como ejercicio deliberado de separar un servicio y
comunicar servicios entre sí. Por eso vive aislada.

### 3.5 Listas cerradas en vez de texto libre

`objetivo`, `momento` y `estado` toman valores de un conjunto fijo.

**Por qué:** la interfaz muestra un desplegable, la base de datos no se llena de
variantes del mismo concepto ("adelgazar", "bajar peso", "perder grasa"), y sobre
todo la IA recibe y devuelve **valores predecibles** en lugar de texto libre que
habría que interpretar.

### 3.6 La IA compone; el catálogo aporta los números

Un modelo de lenguaje es bueno decidiendo qué pega con qué y cómo repartir las
comidas de la semana. Es malo dando cifras exactas: si le pregunto las calorías
del pollo, dará un número plausible que puede variar entre respuestas.

**Decisión:** la IA recibe el catálogo y **solo puede elegir de él**. Los macros
salen siempre de la tabla, nunca del modelo.

Esto se llama **anclar** (*grounding*) el modelo en datos verificados. Tiene dos
ventajas: los números son correctos y trazables, y la tarea del modelo se vuelve
mucho más fácil —elegir identificadores de una lista en lugar de recordar datos
nutricionales—, lo que permite usar modelos más pequeños.

**No hace falta entrenar nada.** Entrenar (o hacer *fine-tuning*) es ajustar los
pesos del modelo con datos propios: caro, con GPU y conjuntos de datos grandes, y
sirve para cambiar su comportamiento, no para darle información. Aquí basta con
instrucciones en el *prompt* y el catálogo como contexto.

### 3.7 Origen de los datos nutricionales: USDA + semilla propia

**Decisión:** una tabla `Alimento` propia que es la fuente de la verdad, sembrada
con 30-50 alimentos básicos versionados en el repo, y ampliable bajo demanda
consultando la API de **USDA FoodData Central**.

**Por qué USDA y no Open Food Facts:**

| | USDA FoodData Central | Open Food Facts |
|---|---|---|
| Tipo de dato | Alimentos **genéricos** | Productos de supermercado con código de barras |
| Licencia | CC0, dominio público | ODbL: atribución y *share-alike* |
| Clave | Requiere clave gratuita | Sin clave |

Para recetas hacen falta alimentos genéricos, no marcas concretas. Y la licencia
ODbL de Open Food Facts obliga a publicar como datos abiertos cualquier base
derivada, lo que es una atadura real si esto llegara a ser un producto.

Que USDA pida una clave **no es un inconveniente en este laboratorio**: es un
secreto que gestionar, y eso conecta con la gestión de secretos del M1, con los
`Secret` de Kubernetes y con Terraform.

**El pero:** los nombres de USDA están en inglés y con nomenclatura de laboratorio
("Chicken, broilers or fryers, breast, meat only, raw"). Se resuelve guardando en
`Alimento` tanto el `nombre` en español —que es lo que ven el usuario y la IA—
como el `nombre_externo` y el `id_externo`. Todo el sistema habla español; el
inglés solo aparece al importar un alimento nuevo, y esa importación ocurre **una
vez por alimento**, no una vez por receta.

**Para lo que no existe todavía:** cuando la IA propone un alimento que no está en
el catálogo, el worker lo busca en USDA y, si hace falta, usa el propio modelo
para desambiguar entre los resultados. Desambiguar entre opciones parecidas es
justo lo que un LLM hace bien. Como ocurre dentro del worker, que ya es asíncrono,
no añade latencia visible.

### 3.8 Cómo se protege el catálogo

`Alimento.origen` toma tres valores:

| Origen | Significado | ¿Lo sobrescribe la API? |
|---|---|---|
| `seed` | Vino del fichero de semilla del repo | No |
| `api` | Importado de USDA | Sí |
| `manual` | Lo he creado o editado yo | No |

Al editar un alimento pasa a ser `manual`, así que **queda protegido por el mero
hecho de haberlo tocado**. No hace falta revisar el catálogo alimento por alimento:
solo se corrige lo que chirría, y corregirlo ya lo blinda.

### 3.9 Por qué existe la semilla

Los datos de semilla se cargan al desplegar si la tabla está vacía. Con ellos, un
`docker compose up` desde cero deja la aplicación **funcionando sin depender de
USDA ni de internet**, y las demostraciones salen siempre iguales.

---

## 4. Endpoints

| Método | Ruta | Qué hace | Códigos |
|---|---|---|---|
| POST | `/users` | Registro | 201 · 400 · 409 |
| POST | `/login` · `/logout` | Sesión | 200 · 401 |
| GET | `/me` | Quién soy | 200 · 401 |
| PATCH · DELETE | `/users/<id>` | Editar o borrar mi usuario | 200 · 204 · 401 · 403 |
| GET | `/alimentos?buscar=pollo` | Buscar en el catálogo | 200 |
| POST · PATCH · DELETE | `/alimentos` | Mantener el catálogo | 201 · 400 · 401 |
| GET · POST | `/recetas` | Listar y crear recetas | 200 · 201 · 400 |
| GET · PATCH · DELETE | `/recetas/<id>` | Ver, editar, borrar | 200 · 204 · 404 |
| GET · POST | `/planes` | Listar y crear planes a mano | 200 · 201 |
| POST | `/planes/generar` | **Encola** la generación por IA | **202** |
| GET | `/planes/<id>` | Ver el plan y su estado | 200 · 404 |
| GET | `/planes/<id>/lista-compra` | Lista calculada al vuelo | 200 · 404 |
| POST | `/analisis` | **Encola** el análisis de un plan | **202** |
| GET | `/analisis/<id>` | Estado y resultado | 200 · 404 |
| GET | `/health` · `/metrics` | Salud y métricas | 200 |

Los dos endpoints que devuelven **202 Accepted** son los que encolan trabajo: la
API responde en milisegundos con un identificador y el worker procesa después.

---

## 5. Qué se queda fuera (y por qué)

- **Persistir la lista de la compra** y poder marcar artículos: no aporta
  aprendizaje de infraestructura.
- **Recetas con pasos estructurados**, tiempos, dificultad, fotos: relleno.
- **Cálculo de necesidades calóricas** con fórmulas: es lógica de negocio pura y
  requeriría rigor nutricional que no es el objetivo del laboratorio.
- **Datos de salud sensibles** (alergias, patologías): en un producto real serían
  datos especialmente protegidos por el RGPD. Fuera del alcance.

---

## 6. Lo que queda por decidir

- **Qué modelo de lenguaje**: la progresión prevista es *stub* → API gestionada →
  Ollama autoalojado. La llamada al modelo vive detrás de una interfaz, así que
  cambiar entre los tres no toca la arquitectura.
- **Cómo se despliega el modelo en la nube**: en local, Ollama con GPU; en AWS, las
  instancias con GPU son caras, así que probablemente un servicio gestionado. Esa
  diferencia entre entorno local y nube se decide en el módulo de IaC.
