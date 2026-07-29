# Migraciones (Alembic)

El esquema lo gestiona Alembic. La aplicación **ya no lo crea al arrancar**:
`db.create_all()` solo añadía tablas nuevas y nunca modificaba las existentes, así
que no servía para hacer evolucionar el modelo.

La URL de la base de datos no está en `alembic.ini`: `env.py` la pide a
`app.config.url_base_datos()`, la misma función que usa el *factory* de Flask. Una
sola definición de la conexión, y ninguna credencial en un fichero versionado.

## Comandos

Desde `services/api`, o dentro del contenedor (que es donde están las
dependencias y las mismas versiones que en producción):

```bash
# Aplicar todas las migraciones pendientes
docker compose run --rm nutriapp alembic upgrade head

# Ver en qué revisión está la base de datos
docker compose run --rm nutriapp alembic current

# Historial
docker compose run --rm nutriapp alembic history --verbose

# Volver una revisión atrás
docker compose run --rm nutriapp alembic downgrade -1

# Comprobar si los modelos se han desviado del esquema (útil en CI)
docker compose run --rm nutriapp alembic check
```

## Crear una migración nueva

El autogenerado compara los modelos contra la base de datos, así que **la base de
datos tiene que estar en `head` antes de generar**:

```bash
docker compose run --rm nutriapp alembic upgrade head
docker compose run --rm --user root nutriapp \
    alembic revision --autogenerate -m "descripción del cambio"
```

`--user root` porque el contenedor corre como `appuser`, que no puede escribir en
`/app`. Solo hace falta para *generar* el fichero, nunca para aplicarlo.

Como el contenedor no monta el código, hay que sacar el fichero generado:

```bash
docker cp <contenedor>:/app/migrations/versions/. ./services/api/migrations/versions/
```

**Revisa siempre lo que autogenera.** Alembic detecta bien columnas, índices y
tipos, pero no adivina la intención: un `DROP` seguido de un `ADD` es pérdida de
datos donde tú querías un `ALTER`.

## Al añadir un dominio nuevo

Importa sus modelos en `env.py`. Es lo que los registra en `db.metadata`; sin esa
línea, el autogenerado no vería las tablas nuevas y propondría borrar las que no
conoce.
