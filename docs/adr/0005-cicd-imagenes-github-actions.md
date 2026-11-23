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
- **Todas las actions fijadas por SHA de commit**, con la versión en un comentario al lado para saber qué estoy usando sin tener que resolver el hash:

  | Action | Versión |
  |---|---|
  | `actions/checkout` | v6.1.0 |
  | `docker/setup-buildx-action` | v4.4.1 |
  | `docker/metadata-action` | v6.2.0 |
  | `docker/login-action` | v4.8.0 |
  | `docker/build-push-action` | v7.4.0 |
  | `aquasecurity/trivy-action` | v0.36.0 |

  Antes solo iba fijada `trivy-action`, que fue la que me dio el susto; el resto usaba tags mayores. **La regla ahora es fijarlas todas, sin excepciones**, y eso incluye `actions/checkout` aunque sea de GitHub. Una excepción por confianza en el publicador es exactamente el hueco por el que entra el siguiente incidente, y mantener dos criterios distintos en el mismo fichero obliga a decidir caso por caso cada vez que añado una action.

- **Dependabot** (`.github/dependabot.yml`) con `package-ecosystem: "github-actions"` y revisión **semanal**. Cuando sale una versión nueva me abre un PR con el SHA actualizado; lo reviso y lo fusiono si el CI pasa.

## Alternativas consideradas

- **Docker Hub** en vez de GHCR: descartado por menos integración y por tener que gestionar un token como secreto.
- **Publicar sin escanear**: descartado, es justo lo que queremos evitar.
- **Fijar las actions por tag** (`@v0.36.0`): descartado por seguridad — ver consecuencias.

## Consecuencias

- Cada push a `main` publica una imagen **escaneada y trazable** al commit; cero pasos manuales.
- El pipeline usa el `GITHUB_TOKEN` automático → nada de credenciales que rotar.
- **Lección de supply-chain:** `aquasecurity/trivy-action` sufrió un secuestro de tags en marzo de 2026. Por eso las actions se fijan por **SHA de commit** (inmutable), no por tag (mutable). Es el mismo principio que fijar imágenes por digest (M1).
- **El compromiso que esto trae, y cómo lo compenso:** fijar por SHA significa que **las actions dejan de actualizarse solas**. Un tag mayor como `@v4` recibe parches y correcciones de seguridad sin que yo haga nada; un SHA se queda congelado donde lo dejé. O sea que cambio el riesgo de que me cuelen código por el riesgo de quedarme con una versión vieja y vulnerable.

  **Dependabot es lo que paga ese precio.** Revisa semanalmente, y cuando hay versión nueva me abre un PR con el SHA actualizado en vez de cambiármelo por la espalda. Yo decido si entra, y el propio CI valida el cambio antes de fusionarlo. Así me quedo con lo mejor de los dos: inmutabilidad en lo que se ejecuta y actualizaciones que no se me olvidan, pero pasando siempre por mi revisión.

  Sin Dependabot, fijar por SHA sería cambiar un problema por otro.
- **Mejoras futuras:** **firmar la imagen** publicada con Cosign (autenticidad, complementa al escaneo).

---

## Historial

- **2026-11-23** — Reviso el ADR: todas las actions pasan a estar fijadas por SHA (antes solo `trivy-action`) y añado Dependabot para compensar el congelado de versiones. Dependabot sale de "Mejoras futuras" y entra en la decisión.
