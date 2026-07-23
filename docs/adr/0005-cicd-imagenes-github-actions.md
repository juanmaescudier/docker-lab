# ADR-0005: CI/CD de la imagen con GitHub Actions y GHCR

- **Estado:** Aceptado
- **Fecha:** 2026-07-24

## Contexto

Quiero automatizar el ciclo de vida de la imagen del servicio `api`: construirla, escanearla y publicarla sin hacerlo a mano, y garantizar que **solo se publican imágenes ya escaneadas**. También quiero un artefacto versionado y trazable al commit que lo generó.

## Decisión

Un workflow de **GitHub Actions** (`.github/workflows/`) que:

- **En push a `main`:** construye → escanea con Trivy → **publica** en GHCR.
- **En Pull Request a `main`:** construye y escanea, pero **NO publica** (validación previa antes de fusionar).
- Expone también `workflow_dispatch` (ejecución manual).

Decisiones concretas:

- **Registry: GHCR** (`ghcr.io`). Integrado con el repo y autenticación con el **`GITHUB_TOKEN` automático** (sin credenciales que gestionar). Se descartó Docker Hub por ser menos integrado y requerir guardar un token como secreto.
- **Orden build → scan → push:** una imagen vulnerable nunca llega al registry. Se construye con `load: true` (local), se escanea, y solo entonces se publica.
- **Política de Trivy:** misma que el M1 — `severity: CRITICAL,HIGH`, `ignore-unfixed: true`, `exit-code: 1`. Rompe el build solo por vulnerabilidades **con fix disponible**.
- **Estrategia de tags** (con `docker/metadata-action`): `sha-<commit>` (trazable al código exacto) y `latest` (solo en `main`).
- **Actions de terceros fijadas por SHA de commit**, no por tag.

## Alternativas consideradas

- **Docker Hub** en vez de GHCR: descartado por menos integración y por tener que gestionar un token como secreto.
- **Publicar sin escanear**: descartado, es justo lo que queremos evitar.
- **Fijar las actions por tag** (`@v0.36.0`): descartado por seguridad — ver consecuencias.

## Consecuencias

- Cada push a `main` publica una imagen **escaneada y trazable** al commit; cero pasos manuales.
- El pipeline usa el `GITHUB_TOKEN` automático → nada de credenciales que rotar.
- **Lección de supply-chain:** `aquasecurity/trivy-action` sufrió un secuestro de tags en marzo de 2026. Por eso las actions de terceros se fijan por **SHA de commit** (inmutable), no por tag (mutable). Es el mismo principio que fijar imágenes por digest (M1).
- **Mejoras futuras:** automatizar la actualización de los SHAs con **Renovate/Dependabot**, y **firmar la imagen** publicada con Cosign (autenticidad, complementa al escaneo).
