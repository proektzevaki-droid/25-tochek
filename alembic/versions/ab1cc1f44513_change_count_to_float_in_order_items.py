"""change_count_to_float_in_order_items

Revision ID: ab1cc1f44513
Revises: f3f27c8a9139
Create Date: 2025-12-01 08:07:23.245061

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab1cc1f44513'
down_revision: Union[str, Sequence[str], None] = 'f3f27c8a9139'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Изменяем тип колонки count с Integer на Float
    # Используем batch_alter_table для SQLite
    with op.batch_alter_table('order_items', schema=None) as batch_op:
        batch_op.alter_column('count',
                    existing_type=sa.INTEGER(),
                    type_=sa.Float(),
                    existing_nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    # Возвращаем тип колонки count обратно в Integer
    # Внимание: при downgrade дробные значения будут округлены или потеряны
    # Используем batch_alter_table для SQLite
    with op.batch_alter_table('order_items', schema=None) as batch_op:
        batch_op.alter_column('count',
                    existing_type=sa.Float(),
                    type_=sa.INTEGER(),
                    existing_nullable=True)
