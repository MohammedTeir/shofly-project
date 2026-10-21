"""Add ordered encrypted segment references to media assets.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("media_assets", sa.Column("segment_refs_encrypted", sa.JSON(), nullable=True))

def downgrade():
    op.drop_column("media_assets", "segment_refs_encrypted")
