"""drop redundant standalone VIN index"""
from alembic import op

revision = "0002_drop_redundant_vin_index"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL's UNIQUE constraint on vehicles.vin already supplies a B-tree index.
    op.drop_index("ix_vehicles_vin", table_name="vehicles")


def downgrade() -> None:
    op.create_index("ix_vehicles_vin", "vehicles", ["vin"])
