"""add vehicle enrichments"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_vehicle_enrichments"
down_revision = "0002_drop_redundant_vin_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("vehicle_enrichments", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False), sa.Column("source_name", sa.String(50), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("payload_hash", sa.String(64), nullable=False), sa.Column("selected_attributes", postgresql.JSONB, nullable=False), sa.Column("raw_payload", postgresql.JSONB, nullable=False), sa.Column("error_message", sa.Text), sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint("vehicle_id", "source_name", "payload_hash", name="uq_enrichment_payload"))
    op.create_index("ix_vehicle_enrichments_vehicle_id", "vehicle_enrichments", ["vehicle_id"])
    op.create_index("ix_observations_vehicle_observed", "vehicle_price_observations", ["vehicle_id", "observed_at"])


def downgrade() -> None:
    op.drop_index("ix_observations_vehicle_observed", table_name="vehicle_price_observations")
    op.drop_index("ix_vehicle_enrichments_vehicle_id", table_name="vehicle_enrichments")
    op.drop_table("vehicle_enrichments")
