import copy
from datetime import datetime, timezone
from typing import Any, Dict, List


ORDER_STEP_SEQUENCE = ["ORDERED", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"]
RETURN_STEP_SEQUENCE = [
    "REQUESTED",
    "UNDER_REVIEW",
    "APPROVED",
    "PICKUP_SCHEDULED",
    "REFUND_INITIATED",
    "REFUNDED",
]


def sync_timeline_status(
    history: List[Dict[str, Any]],
    status_value: str,
    step_sequence: List[str],
    now_iso: str | None = None,
) -> List[Dict[str, Any]]:
    """Returns a deep-copied timeline with completion flags and timestamps synchronized to status_value."""
    timeline = copy.deepcopy(history or [])
    if status_value not in step_sequence:
        return timeline

    timestamp = now_iso or datetime.now(timezone.utc).isoformat()
    target_idx = step_sequence.index(status_value)
    for i, item in enumerate(timeline):
        if i <= target_idx:
            item["completed"] = True
            if not item.get("time"):
                item["time"] = timestamp
        else:
            item["completed"] = False
    return timeline
