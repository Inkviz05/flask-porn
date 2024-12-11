from alembic import op
import sqlalchemy as sa

revision = 'add_contract_to_reservation'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('reservation', sa.Column('contract', sa.Text(), nullable=True))

def downgrade():
    op.drop_column('reservation', 'contract')

