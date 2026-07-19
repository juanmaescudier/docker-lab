# Docker Lab — Diseño y roadmap

> Mi laboratorio de contenedores de nivel portfolio para un rol **Cloud / DevOps Junior**.
> Última actualización: 7 de julio de 2026.
> **Estado:** diseño cerrado. Empezando por el módulo M0.

---

## 1. Objetivo

Construir **un único proyecto que evoluciona** desde un contenedor simple hasta un sistema multiservicio orquestado, observado y desplegado con CI/CD. Mi prioridad es **entender**, no ir rápido. Quiero que el resultado sea la pieza central de mi portfolio y algo que pueda defender bien en una entrevista.

Lo que **no** quiero: re-dockerizar mi laboratorio previo de Linux/AWS. Reaprovecho lo que me aporta (Prometheus/Grafana, GitHub Actions), pero el foco aquí es el ecosistema de contenedores.

---

## 2. Punto de partida y decisiones

| Dimensión | Decisión |
|-----------|----------|
| Mi nivel con contenedores | Intermedio-bajo (Dockerfile, volúmenes, redes, Compose básico). Sin experiencia en clúster. |
| Mi base previa | Linux, AWS, Prometheus/Grafana, GitHub Actions, backups 3-2-1. |
| Competencias objetivo | Docker sólido · Seguridad de imágenes · CI/CD de imágenes · Observabilidad · Orquestación (K8s). |
| Recursos | PC potente + free tier cloud. |
| Tiempo | 9–15 h/semana. |
| Horizonte | Aprender sin deadline, máxima profundidad. |
| Formato | Un proyecto que evoluciona (narrativa fuerte para el CV). |
| App núcleo | API + BD + cache → evoluciona a multiservicio (para no saturarme al principio). |
| Stack app | Python / Flask (continuidad con el curso; el lab es de contenedores, no de la app). |
| Kubernetes | Local primero (k3d/kind), cloud como extra final. |
| Contexto | Estoy haciendo un curso de Docker en paralelo (a mitad). |

---

## 3. Principios de diseño

1. **Un concepto nuevo por módulo.** No mezclo aprendizajes; cierro un módulo antes de abrir el siguiente.
2. **Todo reproducible.** Cualquiera clona el repo y levanta el sistema con un comando documentado. Nada de "funciona solo en mi máquina".
3. **Explicar el porqué, no solo el cómo.** Justifico cada decisión técnica en el repo (README por módulo o ADR corto).
4. **Seguridad desde el principio**, no como parche final (imágenes mínimas, no-root, secretos fuera del código).
5. **Camino con el curso.** Los primeros módulos avanzan al ritmo del curso de Docker; dejo Kubernetes para cuando tenga soltura.
6. **Criterios de "hecho" explícitos.** Cada módulo tiene una *Definition of Done* verificable.

---

## 4. Arquitectura objetivo (cómo evoluciona el sistema)

El sistema crece en tres estados. No salto de golpe al final: cada estado es funcional y presentable.

**Estado A — Servicio único contenerizado (M0–M1)**
```
[ API Flask ] ──> [ Cache (Redis) ]
       │
       └────────> [ BD (Postgres) ]
   (todo orquestado con Docker Compose, redes y volúmenes)
```

**Estado B — Multiservicio + CI/CD + observabilidad (M2–M3)**
```
        ┌──────────────┐      ┌──────────────┐
        │  API Flask   │─────>│    Cola      │
        └──────┬───────┘      └──────┬───────┘
               │                     │
        ┌──────▼───────┐      ┌──────▼───────┐
        │  Postgres    │      │   Worker     │
        └──────────────┘      └──────────────┘
   + Prometheus + Grafana + cAdvisor/node-exporter (observabilidad)
   + Pipeline GitHub Actions: build → escaneo → push a registry
```

**Estado C — Orquestado en Kubernetes local (M4–M5)**
```
   Clúster local (k3d/kind)
   ├─ Deployment API (N réplicas)  ─ Service
   ├─ Deployment Worker            ─ Service
   ├─ StatefulSet/Deployment BD    ─ Service
   ├─ Cache                        ─ Service
   └─ Stack de observabilidad
```

> La app arranca como **servicio único** y solo la parto en **worker + cola** en M2, cuando ya domino Compose. Así subo la dificultad de forma gradual.

---

## 5. Stack tecnológico y por qué lo elijo

| Pieza | Elección | Por qué (trade-off) |
|-------|----------|---------------------|
| Lenguaje app | **Python / Flask** | Continuidad con mi curso; mínima fricción. El foco es contenedores, no la app. |
| Base de datos | **PostgreSQL** | Estándar de industria, más "de portfolio" que SQLite; me obliga a entender persistencia con volúmenes. |
| Cache / cola | **Redis** | Ya lo toco en el curso; me sirve como cache y luego como cola simple para el worker. |
| Orquestación local | **Docker Compose** | Punto de partida natural desde el curso; base conceptual antes de K8s. |
| Registry | **GHCR** (GitHub Container Registry) primero | Gratis, integrado con Actions que ya conozco; registry propio (`registry:2`) como módulo opcional. |
| CI/CD | **GitHub Actions** | Reutilizo lo que aprendí en el lab de Linux, ahora aplicado a imágenes. |
| Escaneo seguridad | **Trivy** y/o **docker scout** | Estándar actual; `docker scan` (Snyk) está obsoleto. |
| Observabilidad (métricas) | **Prometheus + Grafana + cAdvisor + node-exporter** | Reaprovecho Prometheus/Grafana que ya domino, ahora a nivel contenedor. |
| Observabilidad (logs) | **Elastic Stack: Elasticsearch + Kibana** + Fluent Bit | Pilar de logs. El keyword clásico y más reconocible del sector (ELK). Desde 2024 vuelve a ser open source (AGPLv3), sin pegas de licencia para un lab auto-hospedado. En mi lab de Linux monto el equivalente ligero (Grafana Loki) para tocar ambos enfoques. |
| Kubernetes | **k3d** o **kind** (local) | Coste cero, iteración rápida; los comparo en M4. Cloud gestionado como extra final. |

> Ninguna decisión es dogma: la justifico y la puedo cambiar módulo a módulo si tengo un motivo.

---

## 6. Roadmap por módulos

Cada módulo indica: **objetivo**, **qué construyo**, **conceptos que quiero entender**, **Definition of Done (DoD)** y **valor para el CV/entrevista**.

### M0 — Fundamentos y base del proyecto
- **Objetivo:** una API Flask contenerizada con BD y cache, orquestada con Compose y hecha con criterio.
- **Qué construyo:** estructura del repo, Dockerfile de la API (multi-stage, usuario no-root, imagen ligera), Compose con API + Postgres + Redis, redes y volúmenes con nombres con sentido, healthchecks, `.env`/variables.
- **Conceptos que quiero entender:** capas y caché de build; diferencia imagen/contenedor/volumen; por qué multi-stage reduce tamaño y superficie; por qué no correr como root; healthcheck vs depends_on.
- **DoD:** `docker compose up` levanta los 3 servicios sanos; la API responde y persiste datos tras `down`/`up`; la imagen de la API pesa lo razonable y no corre como root; el README explica cada decisión.
- **Valor CV:** demuestra que sé hacer un Dockerfile *de verdad*, no copiado. Es lo primero que mira un revisor técnico.
- *Camina con el curso de Docker.*

### M1 — Calidad y seguridad de imágenes
- **Objetivo:** endurecer las imágenes y la gestión de secretos.
- **Qué construyo:** escaneo de vulnerabilidades en local (Trivy/scout), `.dockerignore` con criterio, imágenes base mínimas (slim/alpine con sus trade-offs), gestión de secretos fuera del código, pin de versiones.
- **Conceptos que quiero entender:** superficie de ataque; por qué `latest` es un anti-patrón en prod; musl vs glibc (alpine); diferencia entre secreto en `ENV`, en `.env` y en un gestor de secretos.
- **DoD:** el escaneo pasa sin vulnerabilidades críticas evitables; ningún secreto en el repo ni en la imagen; versiones fijadas; documentado qué acepté y por qué.
- **Valor CV:** "seguridad de contenedores" es un diferenciador claro en juniors.

### M2 — De monolito a multiservicio + CI/CD
- **Objetivo:** partir la app en **API + worker + cola** y automatizar el ciclo de imágenes.
- **Qué construyo:** un worker que consume trabajos de Redis (cola simple); pipeline GitHub Actions: build → escaneo → push a GHCR con tags versionados.
- **Conceptos que quiero entender:** por qué separar responsabilidades en servicios; comunicación asíncrona (cola) vs síncrona (HTTP); versionado de imágenes (semver, sha, `latest`); qué se ejecuta en CI y por qué.
- **DoD:** un push a `main` construye, escanea y publica la imagen automáticamente; el sistema multiservicio funciona vía Compose; los tags de imagen son trazables al commit.
- **Valor CV:** demuestra CI/CD real y diseño multiservicio, dos cosas muy buscadas.

### M3 — Observabilidad de contenedores (los dos pilares)
La observabilidad tiene dos pilares que **no se pisan**: métricas (números en el tiempo) y logs (texto). Los abordo en ese orden.

**M3a — Métricas**
- **Objetivo:** ver qué pasa dentro del sistema con métricas y dashboards.
- **Qué construyo:** Prometheus + Grafana contenerizados; cAdvisor y node-exporter para métricas de contenedor/host; exposición de métricas de la propia app; 1-2 dashboards útiles.
- **Conceptos que quiero entender:** modelo pull de Prometheus; qué es un exporter; diferencia entre métricas de host, de contenedor y de aplicación; qué alertar y qué no.
- **DoD:** Grafana muestra métricas reales de CPU/memoria por contenedor y al menos una métrica de negocio de la app; documentado qué mide cada dashboard.

**M3b — Logs (centralización con el Elastic Stack / ELK)**
- **Objetivo:** centralizar los logs de todos los servicios en un solo sitio y poder buscarlos/analizarlos.
- **Qué construyo:** Elasticsearch + Kibana; un recolector de logs (Fluent Bit; alternativa: Beats/Elastic Agent) que envía los logs de los contenedores a Elasticsearch; al menos una vista/búsqueda útil en Kibana.
- **Conceptos que quiero entender:** diferencia métricas vs logs; qué es un shipper/recolector (Fluent Bit) y por qué ya no se usa tanto Logstash; índice invertido y por qué Elasticsearch come RAM; qué es Elasticsearch vs OpenSearch (el fork de AWS) por cultura general.
- **DoD:** los logs de la API y el worker aparecen centralizados en Kibana y puedo buscarlos/filtrarlos por servicio; documentado el flujo contenedor → Fluent Bit → Elasticsearch → Kibana.
- **Nota de recursos:** Elasticsearch es lo más pesado del lab (JVM). Configuro el heap de forma explícita (p.ej. 512 MB–1 GB) y arranco en modo single-node. Con 64 GB de RAM no hay problema en levantarlo junto al resto.

- **Valor CV:** demuestro los dos pilares de observabilidad. **Elasticsearch/Kibana (ELK)** es el keyword de logs más reconocible; además, en mi lab de Linux monto el equivalente ligero (**Grafana Loki**) para dominar los dos enfoques.

### M4 — Orquestación con Kubernetes (local)
- **Objetivo:** migrar el sistema de Compose a un clúster local y entender el modelo de K8s.
- **Qué construyo:** clúster local (comparo k3d vs kind vs minikube y elijo); manifiestos para desplegar API, worker, BD, cache y observabilidad; escalado de réplicas.
- **Conceptos que quiero entender:** Pod, Deployment, Service, ConfigMap, Secret; por qué K8s y no Compose en producción; declarativo vs imperativo; cómo se resuelve la red y el DNS interno.
- **DoD:** el sistema corre en el clúster local; puedo escalar la API a N réplicas y sigue funcionando; documentada la equivalencia Compose → K8s.
- **Valor CV:** **el módulo estrella.** Kubernetes es el skill más demandado y el que más me diferencia.

### M5 — Infraestructura como código y despliegue real en AWS
- **Objetivo:** llevar el sistema a AWS de forma reproducible con IaC, para que sea un producto realmente desplegable (no solo un lab local).
- **Qué construyo:** la infraestructura definida en **Terraform**; despliegue en AWS (**EKS** para Kubernetes, o **ECS** como alternativa más simple); pipeline que despliega.
- **Conceptos que quiero entender:** IaC declarativa y el *state* de Terraform; qué recursos AWS hacen falta (VPC/red, clúster, registry ECR, IAM, secretos); coste y cómo apagarlo.
- **Nota de costes:** usar free tier donde se pueda y **destruir la infra (`terraform destroy`) cuando no se use**. Vigilar EKS (tiene coste por hora).
- **Valor CV:** el broche — "diseñé, contenericé, orqueté y desplegué un producto real de IA en AWS con IaC". Conecta directamente con mi lab previo de Linux/AWS.

---

## 7. Cómo conecta con mi lab de Linux/AWS previo

- **Reaprovecho:** Prometheus/Grafana (mismos conceptos, ahora contenerizados) y GitHub Actions (ahora para imágenes).
- **Complemento (no repito):** aquel lab demostraba infra con VMs; este demuestra el paradigma de contenedores y orquestación. Juntos cuentan la transición **VMs → contenedores → orquestación**, que es exactamente el arco de un DevOps.
- **Narrativa de entrevista:** "monté infra tradicional con VMs y luego construí su equivalente en contenedores para entender los trade-offs de cada paradigma".

---

## 8. Convenciones del proyecto (a fijar en M0)

- Estructura de repo clara (carpeta por servicio, `infra/` para observabilidad y orquestación, `docs/`).
- Un **README por módulo** explicando decisiones, o ADRs cortos (*Architecture Decision Records*).
- Nombres explícitos para redes, volúmenes y servicios.
- Versionado de imágenes trazable al commit.
- Ramas/PRs para practicar flujo real (opcional pero recomendable para el CV).

---

## 9. Anti-patrones que quiero evitar (mi checklist)

- Correr como root sin necesidad.
- Usar `latest` en producción / imágenes sin versionar.
- Secretos en el código, en el Dockerfile o commiteados.
- Imágenes enormes por no usar multi-stage o `.dockerignore`.
- `depends_on` sin healthcheck creyendo que espera a que el servicio esté "listo".
- Copiar todo el contexto (`COPY . .`) sin `.dockerignore`.
- Saltar a Kubernetes sin dominar Compose antes.

---

## 10. Glosario y etimologías (referencia rápida)

- **Docker:** de *docker* = estibador (quien carga/descarga contenedores en el puerto). La metáfora del contenedor de mercancías es literal.
- **Compose:** "componer" varios servicios en un sistema desde un único archivo.
- **Kubernetes:** griego *κυβερνήτης* (kybernḗtēs) = "timonel/piloto". De ahí también *cyber-* y *gobernador*. El abreviado **k8s** = k + 8 letras + s.
- **Pod:** "vaina" (como una vaina de guisantes): agrupa uno o más contenedores que comparten red y almacenamiento.
- **Prometheus:** el titán que dio el fuego (la observación/conocimiento) a los humanos.
- **Trivy:** de *trivial* — un escáner de seguridad que "debería ser trivial de usar".
- **containerd / runc:** *containerd* = daemon de contenedores; *runc* = *run container* (runtime de referencia de la OCI).

---

## 11. Método de trabajo

- Avanzo módulo a módulo, cerrando cada uno antes de empezar el siguiente.
- Escribo yo el código y las configuraciones en local (VS Code), y las reviso contra el checklist de anti-patrones antes de commitear.
- Guardo mis apuntes de estudio en la carpeta `notas/` (excluida del repo con `.gitignore`).

---

## 12. Próximo paso

Arrancar **M0**: fijar la estructura del repo y escribir el primer Dockerfile de la API, revisándolo con criterio (flags, orden de capas, seguridad) antes de pasar a Compose.
