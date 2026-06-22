"""add insights tables

Revision ID: 002_insights
Revises: 001_initial
Create Date: 2026-06-21 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002_insights'
down_revision = '001'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table('county_insights',
        sa.Column('fips', sa.String(length=5), nullable=False),
        sa.Column('avg_response_gap_days', sa.Float(), nullable=True),
        sa.Column('national_rank', sa.Integer(), nullable=True),
        sa.Column('national_percentile', sa.Float(), nullable=True),
        sa.Column('comparable_counties', sa.JSON(), nullable=True),
        sa.Column('historical_trend', sa.JSON(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fips'], ['counties.fips'], ),
        sa.PrimaryKeyConstraint('fips')
    )
    op.create_table('state_insights',
        sa.Column('state', sa.String(length=2), nullable=False),
        sa.Column('avg_response_gap_days', sa.Float(), nullable=True),
        sa.Column('national_rank', sa.Integer(), nullable=True),
        sa.Column('historical_trend', sa.JSON(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('state')
    )

def downgrade() -> None:
    op.drop_table('state_insights')
    op.drop_table('county_insights')
