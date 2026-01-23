"""add product_id and suppliers_id to order_items

Revision ID: 890326fb26b8
Revises: dfc50b21bca5
Create Date: 2025-11-15 19:12:15.543204

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '890326fb26b8'
down_revision: Union[str, Sequence[str], None] = 'dfc50b21bca5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Проверяем, существуют ли уже колонки
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('order_items')]
    
    # SQLite не поддерживает ALTER для добавления внешних ключей, используем batch mode
    # Добавляем колонки только если их еще нет
    with op.batch_alter_table('order_items', schema=None) as batch_op:
        if 'product_id' not in existing_columns:
            batch_op.add_column(sa.Column('product_id', sa.Integer(), nullable=True, comment='ID товара'))
        if 'suppliers_id' not in existing_columns:
            batch_op.add_column(sa.Column('suppliers_id', sa.Integer(), nullable=True, comment='ID поставщика'))
    
    # В SQLite внешние ключи не поддерживаются через ALTER TABLE
    # Они будут определены на уровне приложения через SQLAlchemy relationships
    # Если нужны внешние ключи на уровне БД, потребуется пересоздание таблицы


def downgrade() -> None:
    """Downgrade schema."""
    # SQLite не поддерживает ALTER для удаления колонок, используем batch mode
    with op.batch_alter_table('order_items', schema=None) as batch_op:
        batch_op.drop_column('suppliers_id')
        batch_op.drop_column('product_id')
