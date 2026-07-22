# ADR-0004: Endurecimiento y elección de imagen base del servicio API

- **Estado:** Aceptado
- **Fecha:** 2026-07-22

## Contexto

Quiero reducir la superficie de ataque y las vulnerabilidades de la imagen del servicio `api`, y hacerlo con criterio (no a ciegas). Escaneo con **Trivy**.

Línea base (`python:3.13-slim`, Debian 13): **168 CVEs**, **todas en paquetes del sistema operativo** de la imagen base; **0 CVEs en mis dependencias de Python**. La mayoría **sin versión que las corrija** (Debian aún no ha publicado parche).

## Decisión

Mantener la base **`python:3.13-slim`** (Debian 13, la más fresca disponible en la imagen oficial de Python) y endurecerla:

- **`apt upgrade`** en el build para aplicar los parches del SO disponibles.
- **Usuario no-root** (`appuser`).
- **Versiones fijadas** en todo (nada de `latest`).
- **Secretos fuera** de la imagen y del repo (`.dockerignore`, `.gitignore`, `.env`).
- **Escaneo con Trivy** integrado; informes guardados en `docs/security/`.

Evalué **distroless** y lo descarté (ver alternativas).

## Alternativas consideradas

- **Distroless** (`gcr.io/distroless/python3-debian12`): reduce mucho la **superficie de ataque** (sin shell, sin gestor de paquetes, sin perl/bash/coreutils → de hecho los 4 CVEs `CRITICAL` de perl **desaparecieron**). PERO va sobre **Debian 12 (más vieja)** y el recuento **total subió a 211**. Además es experimental y va por detrás en versiones de Python (3.11.2), lo que provocó un problema de dependencia condicional (`redis`/`async-timeout`). Conclusión: **gana en superficie, pierde en recuento**; para este caso no compensa la fricción.
- **Chainguard / Wolfi**: recuento casi cero gracias a reconstrucciones continuas, pero cambiar de ecosistema me alejaba del objetivo del laboratorio (Docker/Kubernetes). Anotado como **mejora futura**.

## Consecuencias

- La imagen final tiene **168 CVEs**, casi todas en paquetes del SO base **sin parche disponible**: riesgo residual **aceptado y documentado**.
- **0 CVEs en las dependencias de Python.**
- El `apt upgrade` no bajó el número hoy (no hay fixes publicados), pero mantiene el hábito y aplicará parches en cuanto existan.
- **Lección clave:** una imagen mínima reduce la **superficie de ataque**, no necesariamente el **recuento de CVEs**; el recuento depende sobre todo de lo **fresca** que sea la base. Son dos propiedades de seguridad distintas.
- **Mejora futura:** migrar a una base de recuento casi cero (Chainguard/Wolfi) si el proyecto lo justifica.

## Evidencia (escaneos Trivy en `docs/security/`)

| Fichero | Imagen | Total CVEs |
|---------|--------|------------|
| `scan-baseline.txt` | `python:3.13-slim` (Debian 13) — base | 168 |
| `scan-distroless.txt` | distroless (Debian 12) — experimento | 211 |
| `scan-final.txt` | `python:3.13-slim` + `apt upgrade` — final | 168 |
