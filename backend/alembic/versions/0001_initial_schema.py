"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-19 23:40:05.409708
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


APPEND_ONLY_FN = """
CREATE OR REPLACE FUNCTION action_logs_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'action_logs is append-only';
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.create_table('businesses',
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('timezone', sa.String(length=64), server_default='Asia/Kolkata', nullable=False),
    sa.Column('default_language', sa.String(length=16), server_default='hi-Latn', nullable=False),
    sa.Column('currency', sa.String(length=3), server_default='INR', nullable=False),
    sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_businesses'))
    )
    op.create_table('users',
    sa.Column('email', postgresql.CITEXT(), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('preferred_language', sa.String(length=16), nullable=True),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('action_logs',
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('actor_user_id', sa.UUID(), nullable=True),
    sa.Column('action_type', sa.String(length=64), nullable=False),
    sa.Column('entity_type', sa.String(length=64), nullable=True),
    sa.Column('entity_id', sa.UUID(), nullable=True),
    sa.Column('outcome', sa.String(length=16), server_default='success', nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_action_logs_actor_user_id_users')),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_action_logs_business_id_businesses')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_action_logs'))
    )
    op.create_index('ix_action_logs_business_created', 'action_logs', ['business_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_action_logs_business_id'), 'action_logs', ['business_id'], unique=False)
    op.create_table('agents',
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('language', sa.String(length=16), server_default='hi-Latn', nullable=False),
    sa.Column('instructions', sa.Text(), server_default='', nullable=False),
    sa.Column('enabled_tools', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('knowledge_sources', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='draft', nullable=False),
    sa.Column('config_version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('draft','active','archived')", name=op.f('ck_agents_status_valid')),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_agents_business_id_businesses'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agents'))
    )
    op.create_index(op.f('ix_agents_business_id'), 'agents', ['business_id'], unique=False)
    op.create_table('business_members',
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('owner','admin','member')", name=op.f('ck_business_members_role_valid')),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_business_members_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_business_members_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_business_members')),
    sa.UniqueConstraint('business_id', 'user_id', name=op.f('uq_business_members_business_id_user_id'))
    )
    op.create_index(op.f('ix_business_members_business_id'), 'business_members', ['business_id'], unique=False)
    op.create_index(op.f('ix_business_members_user_id'), 'business_members', ['user_id'], unique=False)
    op.create_table('customers',
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('name_normalized', sa.String(length=160), nullable=False),
    sa.Column('phone_e164', sa.String(length=20), nullable=True),
    sa.Column('email', sa.String(length=254), nullable=True),
    sa.Column('external_ref', sa.String(length=120), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_customers_business_id_businesses'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_customers'))
    )
    op.create_index(op.f('ix_customers_business_id'), 'customers', ['business_id'], unique=False)
    op.create_index('ix_customers_business_phone', 'customers', ['business_id', 'phone_e164'], unique=False)
    op.create_index('ix_customers_name_trgm', 'customers', ['name_normalized'], unique=False, postgresql_using='gin', postgresql_ops={'name_normalized': 'gin_trgm_ops'})
    op.create_table('idempotency_keys',
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('route', sa.String(length=255), nullable=False),
    sa.Column('key', sa.String(length=255), nullable=False),
    sa.Column('request_hash', sa.String(length=64), nullable=False),
    sa.Column('response_body', sa.Text(), nullable=True),
    sa.Column('status_code', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_idempotency_keys_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_idempotency_keys_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_idempotency_keys')),
    sa.UniqueConstraint('business_id', 'user_id', 'route', 'key', name=op.f('uq_idempotency_keys_business_id_user_id_route_key'))
    )
    op.create_index(op.f('ix_idempotency_keys_business_id'), 'idempotency_keys', ['business_id'], unique=False)
    op.create_table('integrations',
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('provider', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=32), server_default='pending', nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('secret_encrypted', sa.Text(), nullable=True),
    sa.Column('connected_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_integrations_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['connected_by'], ['users.id'], name=op.f('fk_integrations_connected_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_integrations')),
    sa.UniqueConstraint('business_id', 'provider', name=op.f('uq_integrations_business_id_provider'))
    )
    op.create_index(op.f('ix_integrations_business_id'), 'integrations', ['business_id'], unique=False)
    op.create_table('invitations',
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('email', postgresql.CITEXT(), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('invited_by', sa.UUID(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('admin','member')", name=op.f('ck_invitations_role_valid')),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_invitations_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['invited_by'], ['users.id'], name=op.f('fk_invitations_invited_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_invitations')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_invitations_token_hash'))
    )
    op.create_index(op.f('ix_invitations_business_id'), 'invitations', ['business_id'], unique=False)
    op.create_table('password_resets',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_password_resets_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_password_resets')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_password_resets_token_hash'))
    )
    op.create_index(op.f('ix_password_resets_user_id'), 'password_resets', ['user_id'], unique=False)
    op.create_table('refresh_tokens',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('family_id', sa.UUID(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('replaced_by', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_refresh_tokens_token_hash'))
    )
    op.create_index(op.f('ix_refresh_tokens_family_id'), 'refresh_tokens', ['family_id'], unique=False)
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)
    op.create_table('usage_records',
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('metric', sa.String(length=64), nullable=False),
    sa.Column('period', sa.String(length=7), nullable=False),
    sa.Column('count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_usage_records_business_id_businesses'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_usage_records')),
    sa.UniqueConstraint('business_id', 'metric', 'period', name=op.f('uq_usage_records_business_id_metric_period'))
    )
    op.create_index(op.f('ix_usage_records_business_id'), 'usage_records', ['business_id'], unique=False)
    op.create_table('conversations',
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('agent_id', sa.UUID(), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=160), nullable=True),
    sa.Column('language', sa.String(length=16), nullable=True),
    sa.Column('state', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('is_test', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], name=op.f('fk_conversations_agent_id_agents'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_conversations_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_conversations_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations'))
    )
    op.create_index(op.f('ix_conversations_agent_id'), 'conversations', ['agent_id'], unique=False)
    op.create_index(op.f('ix_conversations_business_id'), 'conversations', ['business_id'], unique=False)
    op.create_index(op.f('ix_conversations_user_id'), 'conversations', ['user_id'], unique=False)
    op.create_table('invoices',
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('number', sa.String(length=64), nullable=False),
    sa.Column('total_paise', sa.BigInteger(), nullable=False),
    sa.Column('issued_on', sa.Date(), nullable=False),
    sa.Column('due_on', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='open', nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('open','paid','void')", name=op.f('ck_invoices_status_valid')),
    sa.CheckConstraint('total_paise > 0', name=op.f('ck_invoices_total_positive')),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_invoices_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_invoices_customer_id_customers'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_invoices')),
    sa.UniqueConstraint('business_id', 'number', name=op.f('uq_invoices_business_id_number'))
    )
    op.create_index(op.f('ix_invoices_business_id'), 'invoices', ['business_id'], unique=False)
    op.create_index(op.f('ix_invoices_customer_id'), 'invoices', ['customer_id'], unique=False)
    op.create_table('messages',
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('intent', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('tool_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('language', sa.String(length=16), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('user','assistant','system')", name=op.f('ck_messages_role_valid')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_messages_conversation_id_conversations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages'))
    )
    op.create_index('ix_messages_conversation_created', 'messages', ['conversation_id', 'created_at'], unique=False)
    op.create_table('payment_commitments',
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('invoice_id', sa.UUID(), nullable=True),
    sa.Column('promised_amount_paise', sa.BigInteger(), nullable=True),
    sa.Column('promised_on', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='open', nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('source_action_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('open','kept','broken','cancelled')", name=op.f('ck_payment_commitments_status_valid')),
    sa.CheckConstraint('promised_amount_paise IS NULL OR promised_amount_paise > 0', name=op.f('ck_payment_commitments_amount_positive')),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_payment_commitments_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_payment_commitments_customer_id_customers'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], name=op.f('fk_payment_commitments_invoice_id_invoices'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payment_commitments')),
    sa.UniqueConstraint('source_action_id', name=op.f('uq_payment_commitments_source_action_id'))
    )
    op.create_index(op.f('ix_payment_commitments_business_id'), 'payment_commitments', ['business_id'], unique=False)
    op.create_index(op.f('ix_payment_commitments_customer_id'), 'payment_commitments', ['customer_id'], unique=False)
    op.create_index(op.f('ix_payment_commitments_invoice_id'), 'payment_commitments', ['invoice_id'], unique=False)
    op.create_table('payments',
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('invoice_id', sa.UUID(), nullable=False),
    sa.Column('amount_paise', sa.BigInteger(), nullable=False),
    sa.Column('paid_on', sa.Date(), nullable=False),
    sa.Column('method', sa.String(length=32), server_default='cash', nullable=False),
    sa.Column('source_action_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('amount_paise > 0', name=op.f('ck_payments_amount_positive')),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_payments_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], name=op.f('fk_payments_invoice_id_invoices'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_payments')),
    sa.UniqueConstraint('source_action_id', name=op.f('uq_payments_source_action_id'))
    )
    op.create_index(op.f('ix_payments_business_id'), 'payments', ['business_id'], unique=False)
    op.create_index(op.f('ix_payments_invoice_id'), 'payments', ['invoice_id'], unique=False)
    op.create_table('pending_actions',
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('conversation_id', sa.UUID(), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.String(length=64), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('preview', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=32), server_default='pending_confirmation', nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('confirmed_by', sa.UUID(), nullable=True),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error', sa.String(length=255), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('pending_confirmation','processing','completed','failed','cancelled','expired')", name=op.f('ck_pending_actions_status_valid')),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_pending_actions_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['confirmed_by'], ['users.id'], name=op.f('fk_pending_actions_confirmed_by_users')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_pending_actions_conversation_id_conversations'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_pending_actions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_pending_actions'))
    )
    op.create_index(op.f('ix_pending_actions_business_id'), 'pending_actions', ['business_id'], unique=False)
    op.create_index(op.f('ix_pending_actions_conversation_id'), 'pending_actions', ['conversation_id'], unique=False)
    op.create_index('ix_pending_actions_status_expires', 'pending_actions', ['status', 'expires_at'], unique=False)
    op.create_table('reminders',
    sa.Column('business_id', sa.UUID(), nullable=False),
    sa.Column('customer_id', sa.UUID(), nullable=False),
    sa.Column('invoice_id', sa.UUID(), nullable=True),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('channel', sa.String(length=16), server_default='whatsapp', nullable=False),
    sa.Column('status', sa.String(length=16), server_default='scheduled', nullable=False),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('creation_source', sa.String(length=16), server_default='api', nullable=False),
    sa.Column('delivery_attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.String(length=255), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('source_action_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("channel IN ('whatsapp','sms','call','in_app')", name=op.f('ck_reminders_channel_valid')),
    sa.CheckConstraint("status IN ('scheduled','due','delivered','failed','cancelled','completed')", name=op.f('ck_reminders_status_valid')),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], name=op.f('fk_reminders_business_id_businesses'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], name=op.f('fk_reminders_customer_id_customers'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], name=op.f('fk_reminders_invoice_id_invoices'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reminders')),
    sa.UniqueConstraint('source_action_id', name=op.f('uq_reminders_source_action_id'))
    )
    op.create_index(op.f('ix_reminders_business_id'), 'reminders', ['business_id'], unique=False)
    op.create_index(op.f('ix_reminders_customer_id'), 'reminders', ['customer_id'], unique=False)
    op.create_index('ix_reminders_due_poll', 'reminders', ['status', 'next_attempt_at'], unique=False)
    op.create_index(op.f('ix_reminders_invoice_id'), 'reminders', ['invoice_id'], unique=False)
    # ### end Alembic commands ###
    op.execute(APPEND_ONLY_FN)
    op.execute("CREATE TRIGGER action_logs_no_update BEFORE UPDATE OR DELETE ON action_logs "
               "FOR EACH ROW EXECUTE FUNCTION action_logs_append_only()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS action_logs_no_update ON action_logs")
    op.execute("DROP FUNCTION IF EXISTS action_logs_append_only()")
    op.drop_index(op.f('ix_reminders_invoice_id'), table_name='reminders')
    op.drop_index('ix_reminders_due_poll', table_name='reminders')
    op.drop_index(op.f('ix_reminders_customer_id'), table_name='reminders')
    op.drop_index(op.f('ix_reminders_business_id'), table_name='reminders')
    op.drop_table('reminders')
    op.drop_index('ix_pending_actions_status_expires', table_name='pending_actions')
    op.drop_index(op.f('ix_pending_actions_conversation_id'), table_name='pending_actions')
    op.drop_index(op.f('ix_pending_actions_business_id'), table_name='pending_actions')
    op.drop_table('pending_actions')
    op.drop_index(op.f('ix_payments_invoice_id'), table_name='payments')
    op.drop_index(op.f('ix_payments_business_id'), table_name='payments')
    op.drop_table('payments')
    op.drop_index(op.f('ix_payment_commitments_invoice_id'), table_name='payment_commitments')
    op.drop_index(op.f('ix_payment_commitments_customer_id'), table_name='payment_commitments')
    op.drop_index(op.f('ix_payment_commitments_business_id'), table_name='payment_commitments')
    op.drop_table('payment_commitments')
    op.drop_index('ix_messages_conversation_created', table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_invoices_customer_id'), table_name='invoices')
    op.drop_index(op.f('ix_invoices_business_id'), table_name='invoices')
    op.drop_table('invoices')
    op.drop_index(op.f('ix_conversations_user_id'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_business_id'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_agent_id'), table_name='conversations')
    op.drop_table('conversations')
    op.drop_index(op.f('ix_usage_records_business_id'), table_name='usage_records')
    op.drop_table('usage_records')
    op.drop_index(op.f('ix_refresh_tokens_user_id'), table_name='refresh_tokens')
    op.drop_index(op.f('ix_refresh_tokens_family_id'), table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
    op.drop_index(op.f('ix_password_resets_user_id'), table_name='password_resets')
    op.drop_table('password_resets')
    op.drop_index(op.f('ix_invitations_business_id'), table_name='invitations')
    op.drop_table('invitations')
    op.drop_index(op.f('ix_integrations_business_id'), table_name='integrations')
    op.drop_table('integrations')
    op.drop_index(op.f('ix_idempotency_keys_business_id'), table_name='idempotency_keys')
    op.drop_table('idempotency_keys')
    op.drop_index('ix_customers_name_trgm', table_name='customers', postgresql_using='gin', postgresql_ops={'name_normalized': 'gin_trgm_ops'})
    op.drop_index('ix_customers_business_phone', table_name='customers')
    op.drop_index(op.f('ix_customers_business_id'), table_name='customers')
    op.drop_table('customers')
    op.drop_index(op.f('ix_business_members_user_id'), table_name='business_members')
    op.drop_index(op.f('ix_business_members_business_id'), table_name='business_members')
    op.drop_table('business_members')
    op.drop_index(op.f('ix_agents_business_id'), table_name='agents')
    op.drop_table('agents')
    op.drop_index(op.f('ix_action_logs_business_id'), table_name='action_logs')
    op.drop_index('ix_action_logs_business_created', table_name='action_logs')
    op.drop_table('action_logs')
    op.drop_table('users')
    op.drop_table('businesses')
    # ### end Alembic commands ###
