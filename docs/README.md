# docs/ — Documentación y decisiones

Aquí guardo las **decisiones de arquitectura** del proyecto en forma de **ADR** (*Architecture Decision Record*): un registro corto de cada decisión importante, explicando el contexto, qué decidí y qué consecuencias tiene.

Uso ADRs porque en un proyecto real el "por qué se hizo así" se pierde con el tiempo. Dejarlo escrito demuestra criterio y facilita que cualquiera (o yo mismo dentro de meses) entienda las decisiones sin tener que preguntar.

## Estructura

- [`adr/0000-template.md`](adr/0000-template.md) — plantilla para nuevos ADRs.
- [`adr/0001-arquitectura-y-alcance-inicial.md`](adr/0001-arquitectura-y-alcance-inicial.md) — decisiones de arranque del proyecto.

Los ADRs se numeran de forma incremental y **no se editan** una vez aceptados: si una decisión cambia, se crea un ADR nuevo que reemplaza al anterior (y se marca el viejo como *Superseded*).
