# Docker Lab — Laboratorio de contenedores

[![CI](https://github.com/juanmaescudier/docker-lab/actions/workflows/publish-nutriapp-image.yml/badge.svg)](https://github.com/juanmaescudier/docker-lab/actions/workflows/publish-nutriapp-image.yml)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker_Compose-2496ED?logo=docker&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.1-000000?logo=flask&logoColor=white)
![Gunicorn](https://img.shields.io/badge/Gunicorn-499848?logo=gunicorn&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-336791?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?logo=redis&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-3fb950)
![Estado](https://img.shields.io/badge/estado-M3_observabilidad-3fb950)

Laboratorio de contenedores construido de forma progresiva como proyecto de portfolio para perfiles **Cloud / DevOps Junior**. Empieza siendo un único servicio y evoluciona hasta un sistema multiservicio orquestado, observado y desplegado con CI/CD e IaC. El objetivo no es académico: es **demostrar competencias prácticas** y poder **defender cada decisión técnica** en una entrevista.

![Arquitectura del laboratorio (M0)](docs/img/architecture.svg)

> **Estado:** en construcción. **M0–M3 completados** — API en contenedores con PostgreSQL y sesiones en Redis (M0), imagen endurecida y escaneada con Trivy (M1), CI/CD de imágenes con GitHub Actions y GHCR (M2), y observabilidad completa con sus dos pilares: **métricas** (Prometheus + Grafana, en tres capas) y **logs** (Elasticsearch + Kibana + Fluent Bit) (M3). Lo siguiente, según el [ROADMAP](ROADMAP.md): multiservicio, Kubernetes e IaC en AWS.

---

## Por qué este proyecto

Ya tengo un laboratorio previo de Linux + AWS con máquinas virtuales (bastión, web, base de datos, monitorización con Prometheus/Grafana, backups 3-2-1 a S3 y CI/CD con GitHub Actions). Con este lab quiero dar el siguiente paso: pasar del paradigma de VMs al de **contenedores y orquestación**, que es justo el recorrido que hace un DevOps en la vida real.

No es una re-implementación de aquel laboratorio en Docker. Es un proyecto nuevo, diseñado desde cero, para aprender el ecosistema de contenedores con criterio y no a base de copiar tutoriales.

---

## Qué quiero demostrar

- **Docker sólido:** Dockerfiles limpios (multi-stage, imágenes ligeras, usuario no-root), Compose bien estructurado, redes y volúmenes con criterio.
- **Seguridad de contenedores:** escaneo de vulnerabilidades, imágenes mínimas y gestión de secretos fuera del código.
- **CI/CD de imágenes:** pipelines que construyen, escanean y publican imágenes automáticamente.
- **Observabilidad:** métricas y dashboards de los contenedores con Prometheus y Grafana.
- **Orquestación:** migración de Docker Compose a Kubernetes en un clúster local.

---

## La aplicación

El núcleo es una **API en Python (Flask)** con una **base de datos (PostgreSQL)** y una **cache (Redis)**. Arranca como un servicio único y, más adelante, la parto en varios servicios (API + worker + cola) para que la orquestación tenga sentido real.

Elegí Flask a propósito: el foco de este laboratorio son los **contenedores**, no la aplicación. Mantengo la app simple para poder concentrarme en la infraestructura.

---

## Cómo evoluciona el sistema

El proyecto crece en tres estados, y cada uno es funcional por sí mismo:

1. **Servicio único contenerizado** — API + BD + cache con Docker Compose.
2. **Multiservicio + CI/CD + observabilidad** — la app se parte en varios servicios, con pipeline de imágenes y monitorización.
3. **Orquestado en Kubernetes** — todo el sistema corriendo en un clúster local, con escalado.

El detalle completo, con las decisiones técnicas justificadas y los criterios de "hecho" de cada módulo, está en el [ROADMAP](ROADMAP.md).

---

## Stack

| Área | Tecnología |
|------|------------|
| Aplicación | Python / Flask |
| Base de datos | PostgreSQL |
| Cache / cola | Redis |
| Orquestación local | Docker Compose → Kubernetes (k3d/kind) |
| Registry | GitHub Container Registry (GHCR) |
| CI/CD | GitHub Actions |
| Seguridad | Trivy / docker scout |
| Observabilidad (métricas) | Prometheus + Grafana + cAdvisor + node-exporter |
| Observabilidad (logs) | Elasticsearch + Kibana + Fluent Bit |

---

## Estructura del repositorio

```
docker-lab/
├── README.md                     # Este archivo
├── ROADMAP.md                    # Diseño y plan por módulos
├── LICENSE
├── compose.yaml                  # Stack base: API + Postgres + Redis
├── compose.observability.yaml    # Métricas: Prometheus, Grafana, cAdvisor, node-exporter
├── compose.logging.yaml          # Logs: Elasticsearch, Kibana, Fluent Bit
├── .env.example                  # Plantilla de variables de entorno
├── .github/workflows/            # CI: build → escaneo con Trivy → push a GHCR
├── docs/
│   ├── adr/                      # Decisiones de arquitectura (ADR)
│   └── img/                      # Diagramas y capturas
├── services/
│   └── api/                      # Servicio Flask: Dockerfile + código de la app
└── infra/
    ├── prometheus/               # Configuración de scrape
    ├── grafana/                  # Datasource y dashboards como código
    └── fluent-bit/               # Pipeline de logs
```

> La estructura crece módulo a módulo. Las decisiones importantes quedan registradas como ADR en `docs/`.

---

## Cómo levantarlo

Requisitos: Docker y Docker Compose.

```bash
git clone https://github.com/juanmaescudier/docker-lab.git
cd docker-lab

# Copiar la plantilla de variables y ajustar los valores
cp .env.example .env

# Construir y levantar el stack (API + PostgreSQL + Redis)
docker compose up --build
```

La API queda disponible en `http://localhost:8000`. Flujo de usuarios y sesión:

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

Los datos persisten en un volumen de Docker: `docker compose down` y un nuevo `up` los conservan; `docker compose down -v` los elimina. Las sesiones viven en Redis y son efímeras.

### Levantar la observabilidad

> **Antes de empezar: usa Docker sobre Linux nativo.**
> Dos partes del stack de observabilidad **no funcionan en Docker Desktop** (Windows/WSL2 y, por el mismo motivo, macOS): las **métricas por contenedor** (cAdvisor) y la **recolección de logs** (Fluent Bit). La causa es la misma en ambos casos: Docker Desktop ejecuta el daemon dentro de una VM propia, y ni el socket de containerd ni los ficheros de log de `/var/lib/docker/containers` son accesibles desde un contenedor. Los servicios arrancan sin errores visibles, pero no recogen datos, que es lo traicionero del asunto.
>
> El resto sí funciona en cualquier sitio: Prometheus, Grafana, las métricas de la app y las del host, Elasticsearch y Kibana.
>
> Yo desarrollo en Windows y **valido la observabilidad en una VM Ubuntu** con Docker Engine nativo, que es lo que se parece a producción. El diagnóstico completo de ambos casos está en los ADR [0006](docs/adr/0006-observabilidad-prometheus-grafana.md) y [0007](docs/adr/0007-logs-elastic-stack.md).

El stack está partido en tres ficheros Compose que se combinan con `-f`, de forma que la observabilidad es **opcional**: la app funciona sin ella y la añades cuando quieres mirar dentro.

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

| Servicio | URL | Notas |
|---|---|---|
| API | http://localhost:8000 | métricas en `/metrics` |
| Prometheus | http://localhost:9090 | pestaña *Status → Targets* para ver los objetivos |
| Grafana | http://localhost:3000 | `admin`/`admin`; datasource y dashboards ya provisionados |
| cAdvisor | http://localhost:8080 | métricas por contenedor |
| Elasticsearch | http://localhost:9200 | `/_cat/indices?v` lista los índices de logs |
| Kibana | http://localhost:5601 | crear una *data view* con el patrón `docker-lab-*` |

> Importante: hay que **bajar el stack con el mismo conjunto de `-f`** con el que se subió. Si no, Compose intenta borrar redes que otros servicios siguen usando y falla con *"network is still in use"*.

> Estado actual: **M0–M3 completados** — API contenerizada con PostgreSQL, sesiones en Redis y autenticación (M0), imagen endurecida y escaneada con Trivy (M1), CI/CD de imágenes con GitHub Actions y GHCR (M2) y observabilidad completa: métricas con Prometheus + Grafana y logs con Elasticsearch + Kibana + Fluent Bit, con dashboards como código (M3). El resto (multiservicio, Kubernetes, IaC en AWS) llega después, según el [ROADMAP](ROADMAP.md).

---

## Observabilidad

El stack se monitoriza en tres capas —host, contenedor y aplicación— con **Prometheus** (métricas) y **Grafana** (dashboards), todo provisionado como código (ver [ADR-0006](docs/adr/0006-observabilidad-prometheus-grafana.md)).

**Métricas de la aplicación** (Flask), siguiendo el método **RED** —Rate, Errors, Duration—. Construí los paneles a mano con PromQL:

![Dashboard de la aplicación (método RED)](docs/img/grafana-nutriapp.png)

**Métricas por contenedor** con cAdvisor (CPU, memoria y red de cada servicio), también con paneles propios:

![Dashboard de contenedores (cAdvisor)](docs/img/grafana-cadvisor.png)

Para la capa de host uso el dashboard *Node Exporter Full* (importado de la comunidad, ID 1860) sobre las métricas de `node-exporter`.

### Logs centralizados

El segundo pilar. Los logs de todos los contenedores van a **Elasticsearch** y se consultan desde **Kibana**, recolectados por **Fluent Bit** (ver [ADR-0007](docs/adr/0007-logs-elastic-stack.md)):

```
Contenedores (stdout) → Fluent Bit (tail) → Elasticsearch (un índice/día) → Kibana
```

La API emite **logs estructurados en JSON**: cada petición genera un registro con `service`, `level`, `method`, `path`, `status`, `duration_ms` y un `request_id` que permite rastrear una petición concreta. Eso convierte los logs en datos consultables:

```
service: nutriapp and status >= 400
duration_ms > 100
level: ERROR
```

![Logs de la API en Kibana, filtrados por método](docs/img/kibana-logs-get.png)

> Nota de entorno: la recolección con `tail` requiere Docker sobre **Linux nativo**. En Docker Desktop/WSL2 los ficheros de log viven en la VM interna de Docker y no son accesibles por bind mount, así que valido esta parte en una VM Ubuntu.

## Roadmap

Consulta el plan completo y el estado de cada módulo en **[ROADMAP.md](ROADMAP.md)**.

---

## Autor

Juanma — [github.com/juanmaescudier](https://github.com/juanmaescudier)
