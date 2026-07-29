"""Recetas e ingredientes.

`recetas.user_id` admite nulo a propósito: nulo significa receta del sistema,
visible para todos, en vez de inventar un usuario "sistema" ficticio.

Las dos claves ajenas de `ingredientes_receta` se comportan distinto y no es un
descuido: borrar una receta se lleva sus ingredientes (CASCADE), pero borrar un
alimento del catálogo NO puede vaciar en silencio las recetas que lo usan
(RESTRICT); el catálogo devuelve 409 y obliga a decidir.

Revision ID: 34ba0c15838f
Revises: 13ca19a2cf56
Create Date: 2026-07-29 13:24:05.261600
"""
from alembic import op
import sqlalchemy as sa


revision = '34ba0c15838f'
down_revision = '13ca19a2cf56'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('recetas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('nombre', sa.String(length=160), nullable=False),
    sa.Column('pasos', sa.Text(), nullable=True),
    sa.Column('metodo_coccion', sa.String(length=20), nullable=True),
    sa.Column('raciones', sa.Integer(), nullable=False),
    sa.Column('origen', sa.String(length=10), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('raciones > 0', name='ck_recetas_raciones_positivas'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recetas_nombre'), 'recetas', ['nombre'], unique=False)
    op.create_index(op.f('ix_recetas_user_id'), 'recetas', ['user_id'], unique=False)
    op.create_table('ingredientes_receta',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('receta_id', sa.Integer(), nullable=False),
    sa.Column('alimento_id', sa.Integer(), nullable=False),
    sa.Column('gramos', sa.Float(), nullable=False),
    sa.CheckConstraint('gramos > 0', name='ck_ingredientes_gramos_positivos'),
    sa.ForeignKeyConstraint(['alimento_id'], ['alimentos.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['receta_id'], ['recetas.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('receta_id', 'alimento_id', name='uq_ingrediente_por_receta')
    )
    op.create_index(op.f('ix_ingredientes_receta_receta_id'), 'ingredientes_receta', ['receta_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_ingredientes_receta_receta_id'), table_name='ingredientes_receta')
    op.drop_table('ingredientes_receta')
    op.drop_index(op.f('ix_recetas_user_id'), table_name='recetas')
    op.drop_index(op.f('ix_recetas_nombre'), table_name='recetas')
    op.drop_table('recetas')
