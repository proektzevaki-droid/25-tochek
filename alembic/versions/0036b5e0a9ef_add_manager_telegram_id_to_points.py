"""add_manager_telegram_id_to_points

Revision ID: 0036b5e0a9ef
Revises: ab1cc1f44513
Create Date: 2025-12-10 20:04:20.949904

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0036b5e0a9ef'
down_revision: Union[str, Sequence[str], None] = 'ab1cc1f44513'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Добавляем поле manager_telegram_id в таблицу points
    op.add_column('points', sa.Column('manager_telegram_id', sa.String(), nullable=True, comment='Telegram ID управляющих (можно несколько через запятую)'))


def downgrade() -> None:
    """Downgrade schema."""
    # Удаляем поле manager_telegram_id из таблицы points
    op.drop_column('points', 'manager_telegram_id')
