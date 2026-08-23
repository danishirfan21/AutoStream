"""support deterministic latest observation retrieval"""
from alembic import op
import sqlalchemy as sa

revision = "0004_observation_latest_index"
down_revision = "0003_vehicle_enrichments"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_index("ix_observations_vehicle_latest", "vehicle_price_observations", ["vehicle_id", sa.text("observed_at DESC"), sa.text("id DESC")])

def downgrade() -> None:
    op.drop_index("ix_observations_vehicle_latest", table_name="vehicle_price_observations")
