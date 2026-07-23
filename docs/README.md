# docs/ — Documentación y decisiones

Aquí guardo las **decisiones de arquitectura** del proyecto en forma de **ADR** (*Architecture Decision Record*): un registro corto de cada decisión importante, explicando el contexto, qué decidí y qué consecuencias tiene.

Uso ADRs porque en un proyecto real el "por qué se hizo así" se pierde con el tiempo. Dejarlo escrito demuestra criterio y facilita que cualquiera (o yo mismo dentro de meses) entienda las decisiones sin tener que preguntar.

## Estructura

- [`adr/0000-template.md`](adr/0000-template.md) — plantilla para nuevos ADRs.
- [`adr/0001-arquitectura-y-alcance-inicial.md`](adr/0001-arquitectura-y-alcance-inicial.md) — decisiones de arranque del proyecto.
- [`adr/0002-punto-de-montaje-postgres.md`](adr/0002-punto-de-montaje-postgres.md) — punto de montaje del volumen de PostgreSQL 18+.
- [`adr/0003-autenticacion-por-sesion.md`](adr/0003-autenticacion-por-sesion.md) — autenticación por sesión con Flask-Session sobre Redis.
- [`adr/0004-seguridad-de-la-imagen.md`](adr/0004-seguridad-de-la-imagen.md) — endurecimiento y elección de imagen base (distroless vs slim).
- [`adr/0005-cicd-imagenes-github-actions.md`](adr/0005-cicd-imagenes-github-actions.md) — CI/CD de la imagen con GitHub Actions y GHCR.

Los ADRs se numeran de forma incremental y **no se editan** una vez aceptados: si una decisión cambia, se crea un ADR nuevo que reemplaza al anterior (y se marca el viejo como *Superseded*).
