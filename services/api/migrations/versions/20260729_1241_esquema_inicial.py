"""Esquema inicial: users, analisis y alimentos.

Recoge el esquema tal y como lo dejaba `db.create_all()` en el factory, para que
Alembic parta del estado real que ya había en producción y no de cero.

Revision ID: 72466d8e3e29
Revises: 
Create Date: 2026-07-29 12:41:48.212231
"""
from alembic import op
import sqlalchemy as sa


revision = '72466d8e3e29'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('alimentos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=160), nullable=False),
    sa.Column('nombre_normalizado', sa.String(length=160), nullable=False),
    sa.Column('categoria', sa.String(length=60), nullable=True),
    sa.Column('estado', sa.String(length=20), nullable=True),
    sa.Column('energia_kcal', sa.Float(), nullable=True),
    sa.Column('grasas_g', sa.Float(), nullable=True),
    sa.Column('grasas_saturadas_g', sa.Float(), nullable=True),
    sa.Column('hidratos_g', sa.Float(), nullable=True),
    sa.Column('azucares_g', sa.Float(), nullable=True),
    sa.Column('fibra_g', sa.Float(), nullable=True),
    sa.Column('proteinas_g', sa.Float(), nullable=True),
    sa.Column('sal_g', sa.Float(), nullable=True),
    sa.Column('nutrientes_extra', sa.JSON(), nullable=True),
    sa.Column('origen', sa.String(length=10), nullable=False),
    sa.Column('id_externo', sa.String(length=40), nullable=True),
    sa.Column('nombre_externo', sa.String(length=255), nullable=True),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_alimentos_categoria'), 'alimentos', ['categoria'], unique=False)
    op.create_index('ix_alimentos_id_externo_unico', 'alimentos', ['id_externo'], unique=True, postgresql_where=sa.text('id_externo IS NOT NULL'))
    op.create_index(op.f('ix_alimentos_nombre'), 'alimentos', ['nombre'], unique=False)
    op.create_index(op.f('ix_alimentos_nombre_normalizado'), 'alimentos', ['nombre_normalizado'], unique=False)
    op.create_index(op.f('ix_alimentos_origen'), 'alimentos', ['origen'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=True),
    sa.Column('age', sa.Integer(), nullable=True),
    sa.Column('height_cm', sa.Integer(), nullable=True),
    sa.Column('weight_kg', sa.Float(), nullable=True),
    sa.Column('goal', sa.String(length=120), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('analisis',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('estado', sa.String(length=20), nullable=False),
    sa.Column('entrada', sa.JSON(), nullable=False),
    sa.Column('resultado', sa.JSON(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('intentos', sa.Integer(), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analisis_estado'), 'analisis', ['estado'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_analisis_estado'), table_name='analisis')
    op.drop_table('analisis')
    op.drop_table('users')
    op.drop_index(op.f('ix_alimentos_origen'), table_name='alimentos')
    op.drop_index(op.f('ix_alimentos_nombre_normalizado'), table_name='alimentos')
    op.drop_index(op.f('ix_alimentos_nombre'), table_name='alimentos')
    op.drop_index('ix_alimentos_id_externo_unico', table_name='alimentos', postgresql_where=sa.text('id_externo IS NOT NULL'))
    op.drop_index(op.f('ix_alimentos_categoria'), table_name='alimentos')
    op.drop_table('alimentos')
