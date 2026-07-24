# ADR-0006: Observabilidad con Prometheus + Grafana (host, contenedor y app)

- **Estado:** Aceptado
- **Fecha:** 2026-07-24

## Contexto

Hasta ahora tenía el stack corriendo pero **a ciegas**: no podía ver cuánta CPU o memoria consumía cada contenedor, ni qué latencia o errores servía la API. Quiero demostrar competencia en **observabilidad** y poder responder en una entrevista a "¿cómo sabes si tu servicio está sano?". Necesito métricas del **host**, de los **contenedores** y de la **aplicación**, con dashboards, y que todo sea **reproducible**: que un `up` desde cero lo levante sin clicar nada.

## Decisión

Monto un stack de métricas con **Prometheus** (recolección) y **Grafana** (visualización), organizado en **tres capas**, cada una con su exporter:

- **Host** → `node-exporter` (CPU, RAM, disco y red de la máquina).
- **Contenedor** → `cAdvisor` (métricas por contenedor).
- **Aplicación** → `prometheus-flask-exporter` en la API, siguiendo el **método RED** (Rate, Errors, Duration).

Decisiones concretas:

- **Modelo pull:** Prometheus **raspa** el endpoint `/metrics` de cada objetivo cada 15s. No son los servicios los que empujan métricas.
- **Red dedicada `monitoring`:** todo el stack de observabilidad vive en su propia red, separada de `frontend`/`backend`. La API se conecta también a `monitoring` para exponerse a Prometheus, sin mezclar el tráfico de monitorización con el de negocio.
- **Dos ficheros compose** (`compose.yaml` + `compose.observability.yaml`) que se combinan con `-f`. La observabilidad es opcional: se activa añadiendo el segundo fichero.
- **Todo como código:** el datasource de Prometheus y los tres dashboards se **provisionan** desde ficheros (`infra/grafana/`). El datasource lleva un **`uid` fijo** (`prometheus`) para que los JSON de los dashboards apunten a él de forma estable en cualquier instancia.
- **cAdvisor 0.60.5** (desde `ghcr.io`), no una versión anterior — ver alternativas y consecuencias.

## Alternativas consideradas

- **Modelo push (Pushgateway/StatsD):** descartado. El pull encaja mejor con servicios de larga vida y es el estándar de Prometheus; el push se reserva para jobs efímeros.
- **Dashboards a mano (sin provisioning):** descartado. Se pierden si se borra el volumen de Grafana y no son reproducibles. Provisionarlos es justo la mentalidad IaC que quiero demostrar.
- **Dashboards de la comunidad para contenedores:** los probé (importé varios), pero venían rotos con cAdvisor moderno + cgroup v2. Preferí **construir los paneles a mano con PromQL** para entenderlos y no depender de terceros.
- **cAdvisor 0.49.1 (versión previa):** no soporta el image store de containerd (snapshotters) — ver consecuencias.

## Consecuencias

- Tengo visibilidad de las tres capas y dashboards reproducibles: quien clone el repo y haga `up` obtiene datasource + dashboards cargados solos.
- **Lección cAdvisor + containerd:** Docker migró su almacén de imágenes a los **snapshotters de containerd** (driver `overlayfs`). cAdvisor 0.49 no sabía leer las capas de ahí y fallaba con *"failed to identify the read-write layer ID"*, dejando los contenedores sin métricas. Lo diagnostiqué por los **logs de cAdvisor** y lo resolví actualizando a **0.60.5**, que sí lo soporta. De paso aprendí que el registry migró de `gcr.io/cadvisor/cadvisor` a `ghcr.io/google/cadvisor` a partir de la 0.53.
- **Limitación de entorno (dev vs prod):** en **Docker Desktop/WSL2**, cAdvisor no alcanza el socket de containerd (corre aislado en la VM interna de Docker Desktop), así que las métricas de contenedor **no funcionan ahí**. Sí funcionan en **Linux nativo** (una VM Ubuntu, y por extensión AWS). Decisión: valido la observabilidad en un entorno tipo servidor, que replica producción.
- **El monitoreo no es gratis:** cAdvisor es el mayor consumidor de CPU del stack (escanea cgroups constantemente). Es un coste consciente de la observabilidad.
- **Mejoras futuras:** añadir **alertas** (Alertmanager) sobre estos mismos datos, y la capa de **logs** (M3b, Elastic Stack) para completar métricas + logs.
