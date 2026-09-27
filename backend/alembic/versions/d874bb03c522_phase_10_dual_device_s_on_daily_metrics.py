"""phase 10: dual_device_s on daily_metrics

Revision ID: d874bb03c522
Revises: 6fec57d5fdee
Create Date: 2026-09-27 16:46:44.279871

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd874bb03c522'
down_revision: Union[str, None] = '6fec57d5fdee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'daily_metrics',
        sa.Column('dual_device_s', sa.Numeric(precision=10, scale=2), server_default='0', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('daily_metrics', 'dual_device_s')
