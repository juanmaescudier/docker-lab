# Guía de uso

Cómo levantar el laboratorio completo, probar la API y acceder a la observabilidad.
Para el resumen rápido, ver el [README](../README.md).

## Requisitos

- Docker y Docker Compose (v2).
- **Docker sobre Linux nativo** si quieres las métricas por contenedor y la recolección de logs (ver [limitaciones por entorno](#limitaciones-por-entorno)).
- Para Elasticsearch: el host puede necesitar `vm.max_map_count` alto. Si no arranca:
  ```bash
  sudo sysctl -w vm.max_map_count=262144
  ```

## Arrancar el stack base

```bash
git clone https://github.com/juanmaescudier/docker-lab.git
cd docker-lab

# Copiar la plantilla de variables y ajustar los valores
cp .env.example .env

# Construir y levantar API + PostgreSQL + Redis
docker compose up --build
```

La API queda en `http://localhost:8000`, y ahí mismo está el **panel de trabajo**:
una página estática servida por la propia API desde la que relleno el
cuestionario, genero planes y veo el modelo, los tokens, el coste, la duración y
los errores de cada generación. Para lo del día a día es más cómodo que `curl`.

Los datos persisten en un volumen: `docker compose down` y un nuevo `up` los conservan; `docker compose down -v` los elimina. Las sesiones viven en Redis y son efímeras.

## Generar un plan con un modelo de lenguaje

El worker arranca en modo `stub` por defecto: devuelve una respuesta fija y válida
**sin salir a internet y sin gastar dinero**, que es lo que quiero para que
cualquiera pueda levantar el stack y verlo funcionar.

Para usar un modelo de verdad hacen falta dos variables en el `.env`
(ver `.env.example`, que explica cada una):

```bash
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=tu_clave
```

La clave **solo la recibe el worker**, que es el único servicio con salida a
internet a través de la red `egress`. La API no la ve.

Un plan semanal tarda **minutos**, no segundos, así que `POST /plans/generate`
devuelve **202** con un identificador y el trabajo se sigue en `GET /jobs/<id>`.
El porqué del modelo elegido y lo que aprendí midiendo está en
[ADR-0009](adr/0009-proveedor-y-modelo-de-lenguaje.md).

## Probar la API

```bash
# Registro (email y password obligatorios)
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"1234","name":"Demo"}'

# Login: guarda la cookie de sesión (httpOnly) en cookies.txt
curl -c cookies.txt -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"1234"}'

# Quién soy: envía la cookie de sesión
curl -b cookies.txt http://localhost:8000/me

# Cerrar sesión
curl -b cookies.txt -X POST http://localhost:8000/logout
```

## Arrancar la observabilidad

El stack está partido en tres ficheros Compose que se combinan con `-f`, de forma que la observabilidad es **opcional**: la app funciona sin ella y se añade cuando hace falta mirar dentro.

```bash
# App + métricas (Prometheus, Grafana, cAdvisor, node-exporter)
docker compose -f compose.yaml -f compose.observability.yaml up -d --build

# App + logs (Elasticsearch, Kibana, Fluent Bit)
docker compose -f compose.yaml -f compose.logging.yaml up -d --build

# Todo junto
docker compose -f compose.yaml -f compose.observability.yaml -f compose.logging.yaml up -d --build
```

Para no repetir la lista de ficheros en cada comando:

```bash
export COMPOSE_FILE=compose.yaml:compose.observability.yaml:compose.logging.yaml
docker compose up -d --build     # ya coge los tres
```

> **Hay que bajar el stack con el mismo conjunto de `-f` con el que se subió.** Si no, Compose intenta borrar redes que otros servicios siguen usando y falla con *"network is still in use"*.

## Puertos y accesos

| Servicio | URL | Notas |
|---|---|---|
| API | http://localhost:8000 | métricas en `/metrics` |
| Prometheus | http://localhost:9090 | pestaña *Status → Targets* para ver los objetivos |
| Grafana | http://localhost:3000 | `admin`/`admin`; datasource y dashboards ya provisionados |
| cAdvisor | http://localhost:8080 | métricas por contenedor |
| Elasticsearch | http://localhost:9200 | `/_cat/indices?v` lista los índices de logs |
| Kibana | http://localhost:5601 | crear una *data view* con el patrón `docker-lab-*` |

## Consultar los logs en Kibana

1. **Stack Management → Data Views → Create data view.**
2. Patrón de índice: `docker-lab-*`. Campo de tiempo: `@timestamp`.
3. Ir a **Discover** y filtrar con KQL:

```
service: nutriapp                      # solo la API
service: nutriapp and status >= 400    # peticiones con error
level: ERROR                           # errores del servidor
duration_ms > 100                      # peticiones lentas
request_id: "abc123def456"             # seguir una petición concreta
```

## Limitaciones por entorno

Dos partes de la observabilidad **no funcionan en Docker Desktop** (Windows/WSL2 y macOS):

| Componente | Docker Desktop | Linux nativo |
|---|---|---|
| Métricas por contenedor (cAdvisor) | ❌ no recoge datos | ✅ |
| Recolección de logs (Fluent Bit, plugin `tail`) | ❌ no recoge datos | ✅ |
| Prometheus, Grafana, métricas de app y host | ✅ | ✅ |
| Elasticsearch, Kibana | ✅ | ✅ |

La causa es la misma en ambos casos: Docker Desktop ejecuta el daemon dentro de una VM propia, y ni el socket de containerd ni los ficheros de log de `/var/lib/docker/containers` son accesibles desde un contenedor. Lo traicionero es que **los servicios arrancan sin errores visibles**: simplemente no recogen nada.

Yo desarrollo en Windows y valido la observabilidad en una VM Ubuntu con Docker Engine nativo, que es lo que se parece a producción. El diagnóstico completo está en los ADR [0006](adr/0006-observabilidad-prometheus-grafana.md) y [0007](adr/0007-logs-elastic-stack.md).

## Notas de recursos

Elasticsearch es lo más pesado del stack (corre sobre la JVM). El heap está fijado a 512 MB en `compose.logging.yaml` y arranca en modo `single-node`. Contando Kibana, conviene tener al menos 8 GB de RAM en la máquina si se levanta todo a la vez.

El índice de logs aparece en estado `yellow` y es lo normal: pide una réplica y con un solo nodo no hay dónde colocarla. No hay pérdida de datos.
