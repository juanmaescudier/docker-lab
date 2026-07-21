# ADR-0002: Punto de montaje del volumen de PostgreSQL

- **Estado:** Aceptado
- **Fecha:** 2026-07-21

## Contexto

El servicio de base de datos usa la imagen oficial `postgres:18`. A partir de la versión 18, la imagen cambia la convención de almacenamiento: guarda los datos en un subdirectorio con el número de versión mayor, para reflejar mejor cómo funciona PostgreSQL y facilitar las actualizaciones con `pg_upgrade`.

Montar el volumen en `/var/lib/postgresql/data` (la convención habitual hasta la versión 17) provoca que el contenedor no arranque: la propia imagen avisa de que ese punto de montaje ya no es el adecuado.

## Decisión

Montar el volumen con nombre `pgdata` en el directorio padre **`/var/lib/postgresql`**, tal como recomienda la imagen 18+. PostgreSQL coloca entonces los datos en el subdirectorio versionado correspondiente dentro de ese volumen.

```yaml
volumes:
  - pgdata:/var/lib/postgresql
```

## Alternativas consideradas

- **Fijar `postgres:17`**, que mantiene la convención clásica `/var/lib/postgresql/data`. Descartado: prefiero mantenerme en la versión actual y aprender el esquema nuevo.

## Consecuencias

- El almacenamiento queda alineado con el esquema versionado de PostgreSQL 18+, lo que simplifica futuras actualizaciones mayores.
- Al cambiar de versión mayor de PostgreSQL conviene revisar el punto de montaje y el proceso de migración de datos.
- Un volumen inicializado con la convención antigua no es compatible: hay que recrearlo (`docker compose down -v`) al adoptar el nuevo punto de montaje.
