"""initial extensions pg_trgm and pgcrypto

Revision ID: 0001_initial_extensions
Revises:
Create Date: 2026-11-22 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001_initial_extensions'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable PostgreSQL pg_trgm (fuzzy text search) and pgcrypto (cryptographic functions & UUIDs)
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')


def downgrade() -> None:
    # Drop extensions if rolled back
    op.execute('DROP EXTENSION IF EXISTS "pgcrypto"')
    op.execute('DROP EXTENSION IF EXISTS "pg_trgm"')
