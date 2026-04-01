"""initial schema

Revision ID: 20260401_0001
Revises:
Create Date: 2026-04-01 21:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260401_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    _create_reference_tables()
    _create_user_tables()
    _create_catalog_tables()
    _create_operation_tables()
    _create_log_and_recovery_tables()
    _create_service_tables()


def downgrade() -> None:
    _drop_service_tables()
    _drop_log_and_recovery_tables()
    _drop_operation_tables()
    _drop_catalog_tables()
    _drop_user_tables()
    _drop_reference_tables()


def _create_reference_tables() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("code", name="uq_roles_code"),
    )
    op.create_table(
        "item_groups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.UniqueConstraint("code", name="uq_item_groups_code"),
    )
    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("value_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("key", name="uq_system_settings_key"),
    )
    op.create_table(
        "hardware_endpoints",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("endpoint_type", sa.String(length=15), nullable=False),
        sa.Column("connection_string", sa.String(length=255), nullable=False),
        sa.Column("driver_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("settings_json", sa.JSON(), nullable=True),
        sa.UniqueConstraint("code", name="uq_hardware_endpoints_code"),
    )
    op.create_index("ix_hardware_endpoints_endpoint_type", "hardware_endpoints", ["endpoint_type"])
    op.create_index("ix_hardware_endpoints_status", "hardware_endpoints", ["status"])


def _drop_reference_tables() -> None:
    op.drop_index("ix_hardware_endpoints_status", table_name="hardware_endpoints")
    op.drop_index("ix_hardware_endpoints_endpoint_type", table_name="hardware_endpoints")
    op.drop_table("hardware_endpoints")
    op.drop_table("system_settings")
    op.drop_table("item_groups")
    op.drop_table("roles")


def _create_user_tables() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("user_code", sa.String(length=100), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], name="fk_users_role_id_roles"),
        sa.UniqueConstraint("user_code", name="uq_users_user_code"),
    )
    op.create_index("ix_users_role_id", "users", ["role_id"])
    op.create_index("ix_users_status", "users", ["status"])
    op.create_table(
        "user_credentials",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("pin_hash", sa.String(length=255), nullable=False),
        sa.Column("pin_salt", sa.String(length=255), nullable=False),
        sa.Column("pin_algorithm", sa.String(length=50), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_credentials_user_id_users"),
        sa.UniqueConstraint("user_id", name="uq_user_credentials_user_id"),
    )
    op.create_index("ix_user_credentials_user_id", "user_credentials", ["user_id"])
    op.create_table(
        "user_rfid_cards",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("card_uid", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_user_rfid_cards_user_id_users"),
        sa.UniqueConstraint("card_uid", name="uq_user_rfid_cards_card_uid"),
    )
    op.create_index("ix_user_rfid_cards_user_id", "user_rfid_cards", ["user_id"])


def _drop_user_tables() -> None:
    op.drop_index("ix_user_rfid_cards_user_id", table_name="user_rfid_cards")
    op.drop_table("user_rfid_cards")
    op.drop_index("ix_user_credentials_user_id", table_name="user_credentials")
    op.drop_table("user_credentials")
    op.drop_index("ix_users_status", table_name="users")
    op.drop_index("ix_users_role_id", table_name="users")
    op.drop_table("users")


def _create_catalog_tables() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("item_group_id", sa.Integer(), nullable=True),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column("return_allowed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("min_level", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.ForeignKeyConstraint(["item_group_id"], ["item_groups.id"], name="fk_items_item_group_id_item_groups"),
        sa.UniqueConstraint("sku", name="uq_items_sku"),
    )
    op.create_index("ix_items_item_group_id", "items", ["item_group_id"])
    op.create_index("ix_items_status", "items", ["status"])
    op.create_table(
        "slots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("slot_type", sa.String(length=9), nullable=False),
        sa.Column("drum_position", sa.Integer(), nullable=False),
        sa.Column("board_address", sa.Integer(), nullable=False),
        sa.Column("lock_number", sa.Integer(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=14), nullable=False),
        sa.UniqueConstraint("code", name="uq_slots_code"),
    )
    op.create_index("ix_slots_slot_type", "slots", ["slot_type"])
    op.create_index("ix_slots_status", "slots", ["status"])
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("item_group_id", sa.Integer(), nullable=True),
        sa.Column("can_dispense", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("can_return", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_permissions_user_id_users"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], name="fk_permissions_item_id_items"),
        sa.ForeignKeyConstraint(["item_group_id"], ["item_groups.id"], name="fk_permissions_item_group_id_item_groups"),
    )
    op.create_index("ix_permissions_user_id", "permissions", ["user_id"])
    op.create_index("ix_permissions_item_id", "permissions", ["item_id"])
    op.create_index("ix_permissions_item_group_id", "permissions", ["item_group_id"])
    op.create_table(
        "slot_item_bindings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slot_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("binding_type", sa.String(length=7), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["slot_id"], ["slots.id"], name="fk_slot_item_bindings_slot_id_slots"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], name="fk_slot_item_bindings_item_id_items"),
        sa.UniqueConstraint("slot_id", "item_id", "binding_type", name="uq_slot_item_bindings_slot_item_binding"),
    )
    op.create_index("ix_slot_item_bindings_slot_id", "slot_item_bindings", ["slot_id"])
    op.create_index("ix_slot_item_bindings_item_id", "slot_item_bindings", ["item_id"])
    op.create_index("ix_slot_item_bindings_binding_type", "slot_item_bindings", ["binding_type"])
    op.create_table(
        "inventory_balances",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slot_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["slot_id"], ["slots.id"], name="fk_inventory_balances_slot_id_slots"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], name="fk_inventory_balances_item_id_items"),
        sa.UniqueConstraint("slot_id", "item_id", name="uq_inventory_balances_slot_item"),
    )
    op.create_index("ix_inventory_balances_slot_id", "inventory_balances", ["slot_id"])
    op.create_index("ix_inventory_balances_item_id", "inventory_balances", ["item_id"])


def _drop_catalog_tables() -> None:
    op.drop_index("ix_inventory_balances_item_id", table_name="inventory_balances")
    op.drop_index("ix_inventory_balances_slot_id", table_name="inventory_balances")
    op.drop_table("inventory_balances")
    op.drop_index("ix_slot_item_bindings_binding_type", table_name="slot_item_bindings")
    op.drop_index("ix_slot_item_bindings_item_id", table_name="slot_item_bindings")
    op.drop_index("ix_slot_item_bindings_slot_id", table_name="slot_item_bindings")
    op.drop_table("slot_item_bindings")
    op.drop_index("ix_permissions_item_group_id", table_name="permissions")
    op.drop_index("ix_permissions_item_id", table_name="permissions")
    op.drop_index("ix_permissions_user_id", table_name="permissions")
    op.drop_table("permissions")
    op.drop_index("ix_slots_status", table_name="slots")
    op.drop_index("ix_slots_slot_type", table_name="slots")
    op.drop_table("slots")
    op.drop_index("ix_items_status", table_name="items")
    op.drop_index("ix_items_item_group_id", table_name="items")
    op.drop_table("items")


def _create_operation_tables() -> None:
    op.create_table(
        "operation_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_type", sa.String(length=9), nullable=False),
        sa.Column("status", sa.String(length=9), nullable=False),
        sa.Column("started_by_user_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("context_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["started_by_user_id"],
            ["users.id"],
            name="fk_operation_sessions_started_by_user_id_users",
        ),
    )
    op.create_index("ix_operation_sessions_session_type", "operation_sessions", ["session_type"])
    op.create_index("ix_operation_sessions_status", "operation_sessions", ["status"])
    op.create_index("ix_operation_sessions_started_by_user_id", "operation_sessions", ["started_by_user_id"])

    op.create_table(
        "operations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("operation_type", sa.String(length=20), nullable=False),
        sa.Column("operation_state", sa.String(length=35), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("slot_id", sa.Integer(), nullable=True),
        sa.Column("qty_requested", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("qty_confirmed", sa.Integer(), nullable=True),
        sa.Column("result", sa.String(length=100), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("hardware_context_json", sa.JSON(), nullable=True),
        sa.Column("business_context_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["operation_sessions.id"], name="fk_operations_session_id_operation_sessions"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_operations_user_id_users"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], name="fk_operations_item_id_items"),
        sa.ForeignKeyConstraint(["slot_id"], ["slots.id"], name="fk_operations_slot_id_slots"),
    )
    op.create_index("ix_operations_session_id", "operations", ["session_id"])
    op.create_index("ix_operations_operation_type", "operations", ["operation_type"])
    op.create_index("ix_operations_operation_state", "operations", ["operation_state"])
    op.create_index("ix_operations_user_id", "operations", ["user_id"])
    op.create_index("ix_operations_item_id", "operations", ["item_id"])
    op.create_index("ix_operations_slot_id", "operations", ["slot_id"])

    op.create_table(
        "inventory_transactions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slot_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("operation_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("transaction_type", sa.String(length=20), nullable=False),
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("quantity_before", sa.Integer(), nullable=False),
        sa.Column("quantity_after", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["slot_id"], ["slots.id"], name="fk_inventory_transactions_slot_id_slots"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], name="fk_inventory_transactions_item_id_items"),
        sa.ForeignKeyConstraint(["operation_id"], ["operations.id"], name="fk_inventory_transactions_operation_id_operations"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["operation_sessions.id"],
            name="fk_inventory_transactions_session_id_operation_sessions",
        ),
    )
    op.create_index("ix_inventory_transactions_slot_id", "inventory_transactions", ["slot_id"])
    op.create_index("ix_inventory_transactions_item_id", "inventory_transactions", ["item_id"])
    op.create_index("ix_inventory_transactions_operation_id", "inventory_transactions", ["operation_id"])
    op.create_index("ix_inventory_transactions_session_id", "inventory_transactions", ["session_id"])
    op.create_index("ix_inventory_transactions_transaction_type", "inventory_transactions", ["transaction_type"])

    op.create_table(
        "operation_state_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=35), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("context_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["operation_id"], ["operations.id"], name="fk_operation_state_history_operation_id_operations"),
    )
    op.create_index("ix_operation_state_history_operation_id", "operation_state_history", ["operation_id"])
    op.create_index("ix_operation_state_history_state", "operation_state_history", ["state"])


def _drop_operation_tables() -> None:
    op.drop_index("ix_operation_state_history_state", table_name="operation_state_history")
    op.drop_index("ix_operation_state_history_operation_id", table_name="operation_state_history")
    op.drop_table("operation_state_history")
    op.drop_index("ix_inventory_transactions_transaction_type", table_name="inventory_transactions")
    op.drop_index("ix_inventory_transactions_session_id", table_name="inventory_transactions")
    op.drop_index("ix_inventory_transactions_operation_id", table_name="inventory_transactions")
    op.drop_index("ix_inventory_transactions_item_id", table_name="inventory_transactions")
    op.drop_index("ix_inventory_transactions_slot_id", table_name="inventory_transactions")
    op.drop_table("inventory_transactions")
    op.drop_index("ix_operations_slot_id", table_name="operations")
    op.drop_index("ix_operations_item_id", table_name="operations")
    op.drop_index("ix_operations_user_id", table_name="operations")
    op.drop_index("ix_operations_operation_state", table_name="operations")
    op.drop_index("ix_operations_operation_type", table_name="operations")
    op.drop_index("ix_operations_session_id", table_name="operations")
    op.drop_table("operations")
    op.drop_index("ix_operation_sessions_started_by_user_id", table_name="operation_sessions")
    op.drop_index("ix_operation_sessions_status", table_name="operation_sessions")
    op.drop_index("ix_operation_sessions_session_type", table_name="operation_sessions")
    op.drop_table("operation_sessions")


def _create_log_and_recovery_tables() -> None:
    op.create_table(
        "event_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("level", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("operation_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("slot_id", sa.Integer(), nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("qty", sa.Numeric(10, 2), nullable=True),
        sa.Column("result", sa.String(length=100), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["operation_id"], ["operations.id"], name="fk_event_logs_operation_id_operations"),
        sa.ForeignKeyConstraint(["session_id"], ["operation_sessions.id"], name="fk_event_logs_session_id_operation_sessions"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_event_logs_user_id_users"),
        sa.ForeignKeyConstraint(["slot_id"], ["slots.id"], name="fk_event_logs_slot_id_slots"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], name="fk_event_logs_item_id_items"),
    )
    op.create_index("ix_event_logs_event_type", "event_logs", ["event_type"])
    op.create_index("ix_event_logs_level", "event_logs", ["level"])
    op.create_index("ix_event_logs_operation_id", "event_logs", ["operation_id"])
    op.create_index("ix_event_logs_session_id", "event_logs", ["session_id"])
    op.create_index("ix_event_logs_user_id", "event_logs", ["user_id"])
    op.create_index("ix_event_logs_slot_id", "event_logs", ["slot_id"])
    op.create_index("ix_event_logs_item_id", "event_logs", ["item_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("reason_code", sa.String(length=100), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name="fk_audit_logs_actor_user_id_users"),
    )
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])

    op.create_table(
        "recovery_cases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("classification", sa.String(length=23), nullable=False),
        sa.Column("status", sa.String(length=11), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_recovery_cases_classification", "recovery_cases", ["classification"])
    op.create_index("ix_recovery_cases_status", "recovery_cases", ["status"])

    op.create_table(
        "recovery_case_entities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("recovery_case_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=100), nullable=False),
        sa.Column("decision_outcome", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(
            ["recovery_case_id"],
            ["recovery_cases.id"],
            name="fk_recovery_case_entities_recovery_case_id_recovery_cases",
        ),
    )
    op.create_index("ix_recovery_case_entities_recovery_case_id", "recovery_case_entities", ["recovery_case_id"])

    op.create_table(
        "recovery_actions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("recovery_case_id", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=7), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("context_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(
            ["recovery_case_id"],
            ["recovery_cases.id"],
            name="fk_recovery_actions_recovery_case_id_recovery_cases",
        ),
    )
    op.create_index("ix_recovery_actions_recovery_case_id", "recovery_actions", ["recovery_case_id"])
    op.create_index("ix_recovery_actions_status", "recovery_actions", ["status"])

    op.create_table(
        "manual_resolution_actions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("recovery_case_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("action_type", sa.String(length=100), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("context_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(
            ["recovery_case_id"],
            ["recovery_cases.id"],
            name="fk_manual_resolution_actions_recovery_case_id_recovery_cases",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_manual_resolution_actions_actor_user_id_users",
        ),
    )
    op.create_index("ix_manual_resolution_actions_recovery_case_id", "manual_resolution_actions", ["recovery_case_id"])
    op.create_index("ix_manual_resolution_actions_actor_user_id", "manual_resolution_actions", ["actor_user_id"])


def _drop_log_and_recovery_tables() -> None:
    op.drop_index("ix_manual_resolution_actions_actor_user_id", table_name="manual_resolution_actions")
    op.drop_index("ix_manual_resolution_actions_recovery_case_id", table_name="manual_resolution_actions")
    op.drop_table("manual_resolution_actions")
    op.drop_index("ix_recovery_actions_status", table_name="recovery_actions")
    op.drop_index("ix_recovery_actions_recovery_case_id", table_name="recovery_actions")
    op.drop_table("recovery_actions")
    op.drop_index("ix_recovery_case_entities_recovery_case_id", table_name="recovery_case_entities")
    op.drop_table("recovery_case_entities")
    op.drop_index("ix_recovery_cases_status", table_name="recovery_cases")
    op.drop_index("ix_recovery_cases_classification", table_name="recovery_cases")
    op.drop_table("recovery_cases")
    op.drop_index("ix_audit_logs_actor_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity_type", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_event_logs_item_id", table_name="event_logs")
    op.drop_index("ix_event_logs_slot_id", table_name="event_logs")
    op.drop_index("ix_event_logs_user_id", table_name="event_logs")
    op.drop_index("ix_event_logs_session_id", table_name="event_logs")
    op.drop_index("ix_event_logs_operation_id", table_name="event_logs")
    op.drop_index("ix_event_logs_level", table_name="event_logs")
    op.drop_index("ix_event_logs_event_type", table_name="event_logs")
    op.drop_table("event_logs")


def _create_service_tables() -> None:
    op.create_table(
        "exports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("export_type", sa.String(length=100), nullable=False),
        sa.Column("destination_type", sa.String(length=100), nullable=False),
        sa.Column("destination_path", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=9), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("file_path", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], name="fk_exports_requested_by_user_id_users"),
    )
    op.create_index("ix_exports_requested_by_user_id", "exports", ["requested_by_user_id"])
    op.create_index("ix_exports_status", "exports", ["status"])

    op.create_table(
        "backups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("backup_type", sa.String(length=100), nullable=False),
        sa.Column("target_path", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=9), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("file_path", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], name="fk_backups_requested_by_user_id_users"),
    )
    op.create_index("ix_backups_requested_by_user_id", "backups", ["requested_by_user_id"])
    op.create_index("ix_backups_status", "backups", ["status"])


def _drop_service_tables() -> None:
    op.drop_index("ix_backups_status", table_name="backups")
    op.drop_index("ix_backups_requested_by_user_id", table_name="backups")
    op.drop_table("backups")
    op.drop_index("ix_exports_status", table_name="exports")
    op.drop_index("ix_exports_requested_by_user_id", table_name="exports")
    op.drop_table("exports")
