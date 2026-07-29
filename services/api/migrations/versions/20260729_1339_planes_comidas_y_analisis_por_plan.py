"""Planes, comidas planificadas y el enlace de Analisis con su plan.

El índice `uq_plan_activo_por_usuario` es lo que garantiza **un solo plan activo
por usuario** (decisión 3.1). Es parcial —solo sobre las filas con `activo`—
porque los planes archivados son muchos y ahí no hay unicidad que imponer. La
comprobación equivalente en Python no bastaría: dos peticiones simultáneas la
pasarían las dos.

`analisis.plan_id` admite nulo por los análisis anteriores a que existieran los
planes; los nuevos siempre lo llevan.

Revision ID: 8cd6e0e4254b
Revises: 34ba0c15838f
Create Date: 2026-07-29 13:39:19.163105
"""
from alembic import op
import sqlalchemy as sa


revision = '8cd6e0e4254b'
down_revision = '34ba0c15838f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('planes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=160), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('origen', sa.String(length=10), nullable=False),
    sa.Column('creado_en', sa.DateTime(timezone=True), nullable=True),
    sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_planes_user_id'), 'planes', ['user_id'], unique=False)
    op.create_index('uq_plan_activo_por_usuario', 'planes', ['user_id'], unique=True, postgresql_where=sa.text('activo'))
    op.create_table('comidas_planificadas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('plan_id', sa.Integer(), nullable=False),
    sa.Column('dia_semana', sa.String(length=10), nullable=False),
    sa.Column('momento', sa.String(length=15), nullable=False),
    sa.Column('receta_id', sa.Integer(), nullable=False),
    sa.Column('raciones', sa.Float(), nullable=False),
    sa.CheckConstraint('raciones > 0', name='ck_comidas_raciones_positivas'),
    sa.ForeignKeyConstraint(['plan_id'], ['planes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['receta_id'], ['recetas.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_comidas_planificadas_plan_id'), 'comidas_planificadas', ['plan_id'], unique=False)
    op.add_column('analisis', sa.Column('plan_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_analisis_plan_id'), 'analisis', ['plan_id'], unique=False)
    # Nombre explícito: Alembic la autogeneró sin nombre y entonces el downgrade
    # no tiene forma de referirse a ella para borrarla.
    op.create_foreign_key(
        'analisis_plan_id_fkey', 'analisis', 'planes', ['plan_id'], ['id'],
        ondelete='CASCADE',
    )


def downgrade():
    op.drop_constraint('analisis_plan_id_fkey', 'analisis', type_='foreignkey')
    op.drop_index(op.f('ix_analisis_plan_id'), table_name='analisis')
    op.drop_column('analisis', 'plan_id')
    op.drop_index(op.f('ix_comidas_planificadas_plan_id'), table_name='comidas_planificadas')
    op.drop_table('comidas_planificadas')
    op.drop_index('uq_plan_activo_por_usuario', table_name='planes', postgresql_where=sa.text('activo'))
    op.drop_index(op.f('ix_planes_user_id'), table_name='planes')
    op.drop_table('planes')
