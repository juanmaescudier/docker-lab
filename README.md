# Docker Lab — Laboratorio de contenedores

Laboratorio personal donde construyo, paso a paso, un sistema en contenedores que empieza siendo un único servicio y termina orquestado, observado y desplegado con CI/CD. Lo hago para consolidar mi perfil **Cloud / DevOps Junior** y, sobre todo, para entender de verdad cada decisión que tomo.

> **Estado:** en construcción. Ahora mismo estoy en el módulo **M0 (fundamentos)**. Voy avanzando en paralelo a un curso de Docker.

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
| Observabilidad | Prometheus + Grafana + cAdvisor + node-exporter |

---

## Estructura del repositorio

```
docker-lab/
├── README.md          # Este archivo
├── ROADMAP.md         # Diseño y plan por módulos
├── .gitignore
└── ...                # (se irá completando módulo a módulo)
```

> La estructura definitiva (carpetas por servicio, `infra/`, `docs/`) la voy fijando conforme avanzo. La documento en el ROADMAP.

---

## Cómo levantarlo

Todavía en construcción. Cuando cierre el módulo M0, aquí documentaré el comando para levantar el sistema completo con un solo `docker compose up`. De momento, para clonar el repo:

```bash
git clone https://github.com/juanmaescudier/docker-lab.git
```

---

## Roadmap

Consulta el plan completo y el estado de cada módulo en **[ROADMAP.md](ROADMAP.md)**.

---

## Autor

Juanma — [github.com/juanmaescudier](https://github.com/juanmaescudier)
