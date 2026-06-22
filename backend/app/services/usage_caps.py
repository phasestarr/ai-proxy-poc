from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.auth.types import SessionContext
from app.config.settings import settings
from app.db.postgres.models.user_usage_cap import UserUsageCap
from app.providers.types import ProviderRoute
from app.schemas.chat import ChatCompletionRequest
from app.services.chat.errors import ChatProxyError
from app.services.usage_ledger import get_user_estimated_usage_usd


@dataclass(slots=True, frozen=True)
class UserUsageCapState:
    user_id: str
    current_usage_usd: Decimal
    baseline_usage_usd: Decimal
    effective_usage_usd: Decimal
    cap_usd: Decimal
    enabled: bool


def enforce_user_usage_cap(
    db: Session,
    *,
    session: SessionContext,
    payload: ChatCompletionRequest,
    route: ProviderRoute,
) -> None:
    cap_state = get_user_usage_cap_state(db, user_id=session.user_id)
    if not cap_state.enabled:
        return
    if cap_state.effective_usage_usd < cap_state.cap_usd:
        return

    detail = (
        f"user usage cap reached: effective=${cap_state.effective_usage_usd}, "
        f"cap=${cap_state.cap_usd}"
    )
    raise ChatProxyError(
        code="usage_cap_exceeded",
        origin="proxy",
        detail=detail,
        http_status=429,
    )


def get_user_usage_cap_state(db: Session, *, user_id: str) -> UserUsageCapState:
    current_usage = get_user_estimated_usage_usd(db, user_id=user_id)
    cap = db.get(UserUsageCap, user_id)
    if cap is None:
        cap_usd = _decimal(settings.usage_default_cap_usd)
        baseline = Decimal("0")
        enabled = True
    else:
        cap_usd = _decimal(cap.cap_usd)
        baseline = _decimal(cap.baseline_estimated_price_usd)
        enabled = bool(cap.enabled)
    effective = current_usage - baseline
    if effective < Decimal("0"):
        effective = Decimal("0")
    return UserUsageCapState(
        user_id=user_id,
        current_usage_usd=current_usage,
        baseline_usage_usd=baseline,
        effective_usage_usd=effective,
        cap_usd=cap_usd,
        enabled=enabled,
    )


def _decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.000001"))
    return Decimal(str(value or "0")).quantize(Decimal("0.000001"))
