# docs/ — Documentación y decisiones

Aquí guardo las **decisiones de arquitectura** del proyecto en forma de **ADR** (*Architecture Decision Record*): un registro corto de cada decisión importante, explicando el contexto, qué decidí y qué consecuencias tiene.

Uso ADRs porque en un proyecto real el "por qué se hizo así" se pierde con el tiempo. Dejarlo escrito demuestra criterio y facilita que cualquiera (o yo mismo dentro de meses) entienda las decisiones sin tener que preguntar.

## Decisiones de arquitectura (ADR)

- [`adr/0000-template.md`](adr/0000-template.md) — plantilla para nuevos ADRs.
- [`adr/0001-arquitectura-y-alcance-inicial.md`](adr/0001-arquitectura-y-alcance-inicial.md) — decisiones de arranque del proyecto.
- [`adr/0002-punto-de-montaje-postgres.md`](adr/0002-punto-de-montaje-postgres.md) — punto de montaje del volumen de PostgreSQL 18+.
- [`adr/0003-autenticacion-por-sesion.md`](adr/0003-autenticacion-por-sesion.md) — autenticación por sesión con Flask-Session sobre Redis.
- [`adr/0004-seguridad-de-la-imagen.md`](adr/0004-seguridad-de-la-imagen.md) — endurecimiento y elección de imagen base (distroless vs slim).
- [`adr/0005-cicd-imagenes-github-actions.md`](adr/0005-cicd-imagenes-github-actions.md) — CI/CD de la imagen con GitHub Actions y GHCR.
- [`adr/0006-observabilidad-prometheus-grafana.md`](adr/0006-observabilidad-prometheus-grafana.md) — métricas en tres capas y dashboards como código.
- [`adr/0007-logs-elastic-stack.md`](adr/0007-logs-elastic-stack.md) — centralización de logs con Fluent Bit, Elasticsearch y Kibana.
- [`adr/0008-corte-multiservicio-cola-y-worker.md`](adr/0008-corte-multiservicio-cola-y-worker.md) — corte a multiservicio con cola y worker, y migraciones con Alembic.
- [`adr/0009-proveedor-y-modelo-de-lenguaje.md`](adr/0009-proveedor-y-modelo-de-lenguaje.md) — servicio gestionado frente a modelo autoalojado, y qué modelo.

Los ADRs se numeran de forma incremental y **no se editan** una vez aceptados: si una decisión cambia, se crea un ADR nuevo que reemplaza al anterior (y se marca el viejo como *Superseded*).

## Diseño de la aplicación

Los ADRs recogen decisiones de **infraestructura**. Estos dos documentos recogen
las de **producto**, que evolucionan y sí se editan:

- [`diseno-dominio.md`](diseno-dominio.md) — qué hace la aplicación, el modelo de entidades y el porqué de cada decisión de diseño.
- [`cuestionario-inicial.md`](cuestionario-inicial.md) — las preguntas que se le hacen al usuario, con sus opciones y el reparto entre el asistente inicial y los ajustes.

## Uso

- [`uso.md`](uso.md) — cómo levantar el stack, el panel de trabajo y las llamadas de ejemplo.
- [`security/`](security) — informes de escaneo de imágenes.
- [`img/`](img) — diagramas y capturas.
