"""update room_members to composite primary key

Revision ID: 3904b480c286
Revises: d249f1e1b51c
Create Date: 2026-11-22 13:47:43.754756

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3904b480c286'
down_revision: Union[str, Sequence[str], None] = 'd249f1e1b51c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(op.f('uq_room_members_room_user'), 'room_members', type_='unique')
    op.drop_column('room_members', 'role')
    op.drop_column('room_members', 'id')
    op.create_primary_key(op.f('pk_room_members'), 'room_members', ['room_id', 'user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('pk_room_members'), 'room_members', type_='primary')
    op.add_column('room_members', sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), autoincrement=False, nullable=False))
    op.create_primary_key(op.f('pk_room_members'), 'room_members', ['id'])
    op.add_column('room_members', sa.Column('role', sa.VARCHAR(length=20), server_default=sa.text("'MEMBER'::character varying"), autoincrement=False, nullable=False))
    op.create_unique_constraint(op.f('uq_room_members_room_user'), 'room_members', ['room_id', 'user_id'])
