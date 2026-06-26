"""Add is_admin to users, create system_settings table

Revision ID: 0002_admin_and_settings
Revises: 0001_initial
Create Date: 2026-06-26 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_admin_and_settings"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("value", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_system_settings_key", "system_settings", ["key"])

    op.execute(sa.text("INSERT INTO system_settings (key, value) VALUES ('registration_enabled', 'true')"))


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM system_settings"))
    op.drop_index("ix_system_settings_key", table_name="system_settings")
    op.drop_table("system_settings")
    op.drop_column("users", "is_admin")