"""initial AutoStream schema"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("vehicles", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("vin", sa.String(17), nullable=False, unique=True), sa.Column("year", sa.Integer), sa.Column("make", sa.String(80)), sa.Column("model", sa.String(80)), sa.Column("trim", sa.String(80)), sa.Column("body_class", sa.String(80)), sa.Column("vehicle_type", sa.String(80)), sa.Column("fuel_type", sa.String(80)), sa.Column("engine_cylinders", sa.Integer), sa.Column("engine_displacement", sa.Numeric(4, 1)), sa.Column("drive_type", sa.String(80)), sa.Column("transmission", sa.String(80)), sa.Column("manufacturer", sa.String(120)), sa.Column("plant_country", sa.String(80)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_vehicles_vin", "vehicles", ["vin"])
    op.create_index("ix_vehicles_make_model_year", "vehicles", ["make", "model", "year"])
    op.create_table("ingestion_runs", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("source_name", sa.String(50), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("total_records", sa.Integer, nullable=False), sa.Column("inserted_records", sa.Integer, nullable=False), sa.Column("updated_records", sa.Integer, nullable=False), sa.Column("duplicate_records", sa.Integer, nullable=False), sa.Column("invalid_records", sa.Integer, nullable=False), sa.Column("failed_records", sa.Integer, nullable=False), sa.Column("error_message", sa.Text))
    op.create_index("ix_ingestion_runs_source_name", "ingestion_runs", ["source_name"])
    op.create_table("vehicle_source_records", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False), sa.Column("source_name", sa.String(50), nullable=False), sa.Column("source_record_id", sa.String(160), nullable=False), sa.Column("raw_payload", postgresql.JSONB, nullable=False), sa.Column("source_timestamp", sa.DateTime(timezone=True)), sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.func.now()), sa.Column("payload_hash", sa.String(64), nullable=False), sa.UniqueConstraint("source_name", "source_record_id", "payload_hash", name="uq_source_record_payload"))
    op.create_index("ix_vehicle_source_records_vehicle_id", "vehicle_source_records", ["vehicle_id"])
    op.create_index("ix_vehicle_source_records_source_name", "vehicle_source_records", ["source_name"])
    op.create_table("vehicle_price_observations", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False), sa.Column("source_name", sa.String(50), nullable=False), sa.Column("price", sa.Numeric(12, 2)), sa.Column("mileage", sa.Integer), sa.Column("location", sa.String(120)), sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("vehicle_id", "source_name", "observed_at", "price", "mileage", name="uq_price_observation"))
    op.create_table("ingestion_errors", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("source_record_id", sa.String(160)), sa.Column("error_type", sa.String(80), nullable=False), sa.Column("error_message", sa.Text, nullable=False), sa.Column("raw_payload", postgresql.JSONB, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index("ix_vehicle_price_observations_vehicle_id", "vehicle_price_observations", ["vehicle_id"])
    op.create_index("ix_vehicle_price_observations_source_name", "vehicle_price_observations", ["source_name"])
    op.create_index("ix_vehicle_price_observations_price", "vehicle_price_observations", ["price"])
    op.create_index("ix_vehicle_price_observations_mileage", "vehicle_price_observations", ["mileage"])
    op.create_index("ix_vehicle_price_observations_observed_at", "vehicle_price_observations", ["observed_at"])
    op.create_index("ix_ingestion_errors_ingestion_run_id", "ingestion_errors", ["ingestion_run_id"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_errors_ingestion_run_id", table_name="ingestion_errors")
    op.drop_index("ix_vehicle_price_observations_observed_at", table_name="vehicle_price_observations")
    op.drop_index("ix_vehicle_price_observations_mileage", table_name="vehicle_price_observations")
    op.drop_index("ix_vehicle_price_observations_price", table_name="vehicle_price_observations")
    op.drop_index("ix_vehicle_price_observations_source_name", table_name="vehicle_price_observations")
    op.drop_index("ix_vehicle_price_observations_vehicle_id", table_name="vehicle_price_observations")
    op.drop_index("ix_vehicle_source_records_source_name", table_name="vehicle_source_records")
    op.drop_table("ingestion_errors")
    op.drop_table("vehicle_price_observations")
    op.drop_table("vehicle_source_records")
    op.drop_table("ingestion_runs")
    op.drop_table("vehicles")
