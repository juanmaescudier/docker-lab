"""Perfil de usuario: campos del modelo de dominio y nombres en español.

Alembic autogeneró estos cambios como DROP + ADD. Se han reescrito como
renombrados donde de verdad lo son: un DROP seguido de un ADD vacía la columna,
y aquí los datos (nombre, altura, peso) tienen que sobrevivir.

La única excepción es `age`, que **no** es un renombrado de `fecha_nacimiento`:
de una edad no se puede recuperar una fecha de nacimiento, así que se pierde a
propósito. Es el precio de dejar de guardar un valor derivado (decisión 3.5).

`objetivo` lleva además una **migración de datos**: cambiar el tipo no basta,
porque el texto libre que había ("bajar peso") no es ninguno de los tres valores
de la lista cerrada y quedaría inválido para siempre.

Revision ID: 13ca19a2cf56
Revises: 72466d8e3e29
Create Date: 2026-07-29 13:03:03.718669
"""
from alembic import op
import sqlalchemy as sa


revision = '13ca19a2cf56'
down_revision = '72466d8e3e29'
branch_labels = None
depends_on = None

# Lo que no se reconozca cae aquí. `mantener` es el neutro de los tres: pasar a
# alguien de "perder grasa" a "ganar músculo" por una traducción fallida sería
# peor que dejarlo en el punto medio y que lo corrija.
OBJETIVO_POR_DEFECTO = 'mantener'

# Traducción del texto libre a la lista cerrada.
#
# `translate` quita los acentos sin depender de la extensión `unaccent`, que
# habría que instalar en el servidor de base de datos. Se calcula una sola vez en
# la subconsulta en lugar de repetirlo en cada rama del CASE.
#
# La primera rama hace la migración idempotente: un valor que ya está en la lista
# se deja como está, así que volver a ejecutarla no lo estropea.
TRADUCIR_A_LISTA_CERRADA = f"""
UPDATE users AS u
   SET objetivo = CASE
       WHEN n.norm IN ('perder_grasa', 'mantener', 'ganar_musculo') THEN n.norm
       WHEN n.norm ~ '(perder|bajar|adelgaz|definir|deficit|grasa)' THEN 'perder_grasa'
       WHEN n.norm ~ '(ganar|subir|aumentar|muscul|volumen|masa)'   THEN 'ganar_musculo'
       WHEN n.norm ~ 'manten'                                       THEN 'mantener'
       ELSE '{OBJETIVO_POR_DEFECTO}'
   END
  FROM (
      SELECT id, translate(lower(trim(objetivo)), 'áéíóúü', 'aeiouu') AS norm
        FROM users
       WHERE objetivo IS NOT NULL
  ) AS n
 WHERE u.id = n.id
"""

# Vuelta a texto legible. No recupera la redacción original —"bajar peso" se
# perdió al traducir—, pero deja la columna coherente con lo que era: texto para
# leer, no un identificador. Nulo sigue siendo nulo: no haber declarado objetivo
# no es lo mismo que querer mantenerse.
TRADUCIR_A_TEXTO_LIBRE = """
UPDATE users
   SET objetivo = CASE objetivo
       WHEN 'perder_grasa'  THEN 'perder grasa'
       WHEN 'ganar_musculo' THEN 'ganar músculo'
       WHEN 'mantener'      THEN 'mantener'
       ELSE objetivo
   END
 WHERE objetivo IS NOT NULL
"""


def upgrade():
    # --- Renombrados: la columna y su contenido se conservan ---
    op.alter_column('users', 'name', new_column_name='nombre')
    op.alter_column('users', 'height_cm', new_column_name='altura_cm')
    op.alter_column('users', 'weight_kg', new_column_name='peso_kg')

    # `goal` pasa de texto libre a lista cerrada (3.7).
    op.alter_column('users', 'goal', new_column_name='objetivo')

    # El orden importa: primero se traducen los datos y después se estrecha la
    # columna. Al revés, un "quiero bajar peso y ganar algo de músculo" se habría
    # truncado a 20 caracteres antes de poder interpretarlo.
    op.execute(sa.text(TRADUCIR_A_LISTA_CERRADA))

    # Tras la traducción todos los valores son de la lista cerrada y el más largo
    # ocupa 13 caracteres, así que estrechar a 20 no puede truncar nada.
    op.alter_column(
        'users', 'objetivo',
        type_=sa.String(length=20),
        existing_type=sa.String(length=120),
    )

    # --- Campos nuevos del perfil ---
    op.add_column('users', sa.Column('sexo', sa.String(length=10), nullable=True))
    op.add_column('users', sa.Column('fecha_nacimiento', sa.Date(), nullable=True))
    op.add_column('users', sa.Column('nivel_actividad', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('comidas_por_dia', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('preferencia_alimentaria', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('composicion_corporal', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('perimetro_cintura_cm', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('perimetro_cadera_cm', sa.Float(), nullable=True))
    op.add_column('users', sa.Column('perimetro_cuello_cm', sa.Float(), nullable=True))

    # La edad deja de guardarse: se deriva de fecha_nacimiento (3.5).
    op.drop_column('users', 'age')

    # Sin CASCADE, la clave ajena impide borrar a un usuario que ya haya pedido
    # un análisis, y DELETE /users/<id> devolvería un 500.
    op.drop_constraint('analisis_user_id_fkey', 'analisis', type_='foreignkey')
    op.create_foreign_key(
        'analisis_user_id_fkey', 'analisis', 'users', ['user_id'], ['id'],
        ondelete='CASCADE',
    )


def downgrade():
    op.drop_constraint('analisis_user_id_fkey', 'analisis', type_='foreignkey')
    op.create_foreign_key(
        'analisis_user_id_fkey', 'analisis', 'users', ['user_id'], ['id'],
    )

    # Vuelve la columna, pero vacía: la edad que hubiera antes ya no existe.
    op.add_column('users', sa.Column('age', sa.INTEGER(), nullable=True))

    op.drop_column('users', 'perimetro_cuello_cm')
    op.drop_column('users', 'perimetro_cadera_cm')
    op.drop_column('users', 'perimetro_cintura_cm')
    op.drop_column('users', 'composicion_corporal')
    op.drop_column('users', 'preferencia_alimentaria')
    op.drop_column('users', 'comidas_por_dia')
    op.drop_column('users', 'nivel_actividad')
    op.drop_column('users', 'fecha_nacimiento')
    op.drop_column('users', 'sexo')

    # Se ensancha primero para que quepa el texto con espacios y acentos.
    op.alter_column(
        'users', 'objetivo',
        type_=sa.String(length=120),
        existing_type=sa.String(length=20),
    )
    op.execute(sa.text(TRADUCIR_A_TEXTO_LIBRE))
    op.alter_column('users', 'objetivo', new_column_name='goal')
    op.alter_column('users', 'peso_kg', new_column_name='weight_kg')
    op.alter_column('users', 'altura_cm', new_column_name='height_cm')
    op.alter_column('users', 'nombre', new_column_name='name')
