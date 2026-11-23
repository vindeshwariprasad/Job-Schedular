# ─── Priority-tiered ready queues ──────────────────────
QUEUE_READY_HIGH = "queue:ready:high"
QUEUE_READY_MEDIUM = "queue:ready:medium"
QUEUE_READY_LOW = "queue:ready:low"

ALL_READY_QUEUES = [QUEUE_READY_HIGH, QUEUE_READY_MEDIUM, QUEUE_READY_LOW]

# ─── Processing & failed (single, no priority split) ──
QUEUE_PROCESSING = "queue:processing"
QUEUE_FAILED = "queue:failed"

# ─── Priority values ──────────────────────────────────
PRIORITY_HIGH = "HIGH"
PRIORITY_MEDIUM = "MEDIUM"
PRIORITY_LOW = "LOW"
VALID_PRIORITIES = {PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW}


def queue_for_priority(priority: str) -> str:
    """Return the correct ready queue for a given priority level."""
    mapping = {
        PRIORITY_HIGH: QUEUE_READY_HIGH,
        PRIORITY_MEDIUM: QUEUE_READY_MEDIUM,
        PRIORITY_LOW: QUEUE_READY_LOW,
    }
    return mapping.get(priority, QUEUE_READY_MEDIUM)
