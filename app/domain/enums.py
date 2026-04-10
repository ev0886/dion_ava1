from __future__ import annotations

from enum import StrEnum


class RoleCode(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    USER = "user"


class UserStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BLOCKED = "blocked"


class DispenseRestrictionPolicy(StrEnum):
    UNLIMITED = "unlimited"
    ONCE_PER_DAY = "once_per_day"


class ItemStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class SlotStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    OUT_OF_SERVICE = "out_of_service"


class SlotType(StrEnum):
    DISPENSE = "dispense"
    RETURN = "return"
    UNIVERSAL = "universal"


class BindingType(StrEnum):
    PRIMARY = "primary"
    RETURN = "return"


class HardwareEndpointType(StrEnum):
    DRUM_CONTROLLER = "drum_controller"
    LOCK_CONTROLLER = "lock_controller"
    RFID_READER = "rfid_reader"


class HardwareEndpointStatus(StrEnum):
    CONFIGURED = "configured"
    DISABLED = "disabled"
    ERROR = "error"


class SessionType(StrEnum):
    DISPENSE = "dispense"
    RETURN = "return"
    REFILL = "refill"
    INVENTORY = "inventory"
    SERVICE = "service"
    RECOVERY = "recovery"


class SessionStatus(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class OperationType(StrEnum):
    DISPENSE = "dispense"
    RETURN = "return"
    REFILL_ITEM = "refill_item"
    INVENTORY_ADJUSTMENT = "inventory_adjustment"
    RECOVERY = "recovery"


class OperationState(StrEnum):
    CREATED = "created"
    AUTHORIZED = "authorized"
    VALIDATION_IN_PROGRESS = "validation_in_progress"
    RETURN_RULES_VALIDATION = "return_rules_validation"
    RETURN_SLOT_RESOLUTION_IN_PROGRESS = "return_slot_resolution_in_progress"
    RETURN_SLOT_RESOLVED = "return_slot_resolved"
    VALIDATED = "validated"
    QUEUED_FOR_EXECUTION = "queued_for_execution"
    POSITIONING_REQUESTED = "positioning_requested"
    POSITIONING_ACKNOWLEDGED = "positioning_acknowledged"
    POSITIONING_IN_PROGRESS = "positioning_in_progress"
    POSITIONING_COMPLETED = "positioning_completed"
    UNLOCK_REQUESTED = "unlock_requested"
    UNLOCK_ACKNOWLEDGED = "unlock_acknowledged"
    UNLOCK_COMPLETED = "unlock_completed"
    USER_ACTION_PENDING = "user_action_pending"
    COMPLETION_VERIFICATION = "completion_verification"
    INVENTORY_WRITE_PENDING = "inventory_write_pending"
    INVENTORY_WRITTEN = "inventory_written"
    SERVICE_MODE_REQUESTED = "service_mode_requested"
    SERVICE_MODE_ACTIVE = "service_mode_active"
    AWAITING_SLOT_SELECTION = "awaiting_slot_selection"
    SLOT_SELECTED = "slot_selected"
    AWAITING_QTY_INPUT = "awaiting_qty_input"
    QTY_ENTERED = "qty_entered"
    BALANCE_UPDATE_PENDING = "balance_update_pending"
    BALANCE_UPDATED = "balance_updated"
    AWAITING_NEXT_ACTION = "awaiting_next_action"
    SESSION_COMPLETION_REQUESTED = "session_completion_requested"
    SESSION_FINALIZATION_IN_PROGRESS = "session_finalization_in_progress"
    SESSION_COMPLETED = "session_completed"
    STARTUP_SCAN = "startup_scan"
    RECOVERY_TARGETS_FOUND = "recovery_targets_found"
    HARDWARE_STATE_REQUESTED = "hardware_state_requested"
    RECOVERY_EVALUATION_IN_PROGRESS = "recovery_evaluation_in_progress"
    OPERATION_RECONCILIATION_IN_PROGRESS = "operation_reconciliation_in_progress"
    MANUAL_CONFIRMATION_REQUIRED = "manual_confirmation_required"
    MANUAL_RECONCILIATION_IN_PROGRESS = "manual_reconciliation_in_progress"
    RECOVERY_ACTIONS_COMMIT_PENDING = "recovery_actions_commit_pending"
    RECOVERY_ACTIONS_COMMITTED = "recovery_actions_committed"
    POST_RECOVERY_SAFETY_CHECK = "post_recovery_safety_check"
    DEGRADED_READY = "degraded_ready"
    SYSTEM_READY = "system_ready"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    FAILED = "failed"
    RECOVERY_REQUIRED = "recovery_required"


class InventoryTransactionType(StrEnum):
    DISPENSE_DEBIT = "dispense_debit"
    RETURN_CREDIT = "return_credit"
    REFILL_SET = "refill_set"
    REFILL_ADD = "refill_add"
    INVENTORY_ADJUSTMENT = "inventory_adjustment"
    RECOVERY_ADJUSTMENT = "recovery_adjustment"


class RecoveryClassification(StrEnum):
    UNCERTAIN_OUTCOME = "uncertain_outcome"
    HARDWARE_STATE_MISMATCH = "hardware_state_mismatch"
    PENDING_INVENTORY_WRITE = "pending_inventory_write"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class RecoveryStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    FAILED = "failed"


class RecoveryActionStatus(StrEnum):
    PLANNED = "planned"
    APPLIED = "applied"
    SKIPPED = "skipped"
    FAILED = "failed"


class ExportStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class BackupStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class StartupReadinessStatus(StrEnum):
    READY = "ready"
    DEGRADED = "degraded"
    NOT_READY = "not_ready"
