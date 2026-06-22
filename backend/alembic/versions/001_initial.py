"""initial

Revision ID: 001
Revises: 
Create Date: 2026-06-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Counties
    op.create_table('counties',
        sa.Column('fips', sa.String(length=5), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('state', sa.String(length=2), nullable=False),
        sa.Column('population', sa.Integer(), nullable=True),
        sa.Column('median_income', sa.Float(), nullable=True),
        sa.Column('income_percentile', sa.Float(), nullable=True),
        sa.Column('rural_urban_code', sa.Integer(), nullable=True),
        sa.Column('is_rural', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('fips')
    )
    op.create_index(op.f('ix_counties_state'), 'counties', ['state'], unique=False)
    op.create_index(op.f('ix_counties_median_income'), 'counties', ['median_income'], unique=False)
    op.create_index('ix_counties_state_income', 'counties', ['state', 'median_income'], unique=False)

    # Disasters
    op.create_table('disasters',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=False),
        sa.Column('incident_type', sa.String(length=64), nullable=False),
        sa.Column('declaration_date', sa.Date(), nullable=False),
        sa.Column('state', sa.String(length=2), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_disasters_incident_type'), 'disasters', ['incident_type'], unique=False)
    op.create_index(op.f('ix_disasters_declaration_date'), 'disasters', ['declaration_date'], unique=False)
    op.create_index(op.f('ix_disasters_state'), 'disasters', ['state'], unique=False)
    op.create_index('ix_disasters_type_date', 'disasters', ['incident_type', 'declaration_date'], unique=False)

    # Disbursements
    op.create_table('disbursements',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('disaster_id', sa.String(length=32), nullable=False),
        sa.Column('county_fips', sa.String(length=5), nullable=False),
        sa.Column('disbursement_date', sa.Date(), nullable=True),
        sa.Column('amount_disbursed', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['county_fips'], ['counties.fips'], ),
        sa.ForeignKeyConstraint(['disaster_id'], ['disasters.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_disbursements_county_fips'), 'disbursements', ['county_fips'], unique=False)
    op.create_index(op.f('ix_disbursements_disaster_id'), 'disbursements', ['disaster_id'], unique=False)
    op.create_index('ix_disbursements_county_date', 'disbursements', ['county_fips', 'disbursement_date'], unique=False)

    # Metrics
    op.create_table('metrics',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('disaster_id', sa.String(length=32), nullable=False),
        sa.Column('county_fips', sa.String(length=5), nullable=False),
        sa.Column('response_gap_days', sa.Integer(), nullable=True),
        sa.Column('amount_per_capita', sa.Float(), nullable=True),
        sa.Column('computed_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['county_fips'], ['counties.fips'], ),
        sa.ForeignKeyConstraint(['disaster_id'], ['disasters.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_metrics_county_fips'), 'metrics', ['county_fips'], unique=False)
    op.create_index(op.f('ix_metrics_disaster_id'), 'metrics', ['disaster_id'], unique=False)
    op.create_index(op.f('ix_metrics_response_gap_days'), 'metrics', ['response_gap_days'], unique=False)
    op.create_index('ix_metrics_county_disaster', 'metrics', ['county_fips', 'disaster_id'], unique=True)
    op.create_index('ix_metrics_gap_fips', 'metrics', ['response_gap_days', 'county_fips'], unique=False)

    # AnalyticsCache
    op.create_table('analytics_cache',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('data', sa.String(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('key')
    )

def downgrade() -> None:
    op.drop_table('analytics_cache')
    op.drop_table('metrics')
    op.drop_table('disbursements')
    op.drop_table('disasters')
    op.drop_table('counties')
