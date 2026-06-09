from __future__ import annotations

from app.config.time import utc_now

INTERACTION_STATE_READY = "ready"
INTERACTION_STATE_VALIDATING = "validating"
INTERACTION_STATE_WAITING = "waiting"

BUSY_REASON_SEND = "send"
BUSY_REASON_ATTACH_FILE = "attach_file"
BUSY_REASON_DELETE_FILE = "delete_file"
BUSY_REASON_DELETE_HISTORY = "delete_history"


def apply_history_interaction_state(
    history,
    *,
    interaction_state: str,
    busy_reason: str | None,
) -> None:
    history.interaction_state = interaction_state
    history.busy_reason = busy_reason
    history.state_updated_at = utc_now()

