from __future__ import annotations

import argparse
from decimal import Decimal

from sqlalchemy import text

from app.config.settings import settings
from app.config.time import utc_now
from app.db.postgres.models.user import User
from app.db.postgres.models.user_usage_cap import UserUsageCap
from app.db.postgres.session import SessionLocal
from app.services.usage_caps import get_user_estimated_usage_usd


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect and manage per-user usage caps.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List users by effective usage descending.")
    list_parser.add_argument("--limit", type=int, default=50)

    set_parser = subparsers.add_parser("set-cap", help="Set or replace one user's cap.")
    set_parser.add_argument("user_id")
    set_parser.add_argument("cap_usd")
    set_parser.add_argument("--reason", default=None)

    reset_parser = subparsers.add_parser("reset-cap", help="Reset cap accounting baseline to current usage.")
    reset_scope = reset_parser.add_mutually_exclusive_group(required=True)
    reset_scope.add_argument("--user-id")
    reset_scope.add_argument("--all", action="store_true")
    reset_parser.add_argument("--reason", default="operator reset")

    disable_parser = subparsers.add_parser("disable-cap", help="Disable one user's cap row.")
    disable_parser.add_argument("user_id")
    disable_parser.add_argument("--reason", default="operator disabled")

    args = parser.parse_args()
    with SessionLocal() as db:
        if args.command == "list":
            list_usage_caps(db, limit=max(1, args.limit))
        elif args.command == "set-cap":
            set_cap(db, user_id=args.user_id, cap_usd=_decimal(args.cap_usd), reason=args.reason)
        elif args.command == "reset-cap":
            if args.all:
                reset_all_caps(db, reason=args.reason)
            else:
                reset_cap(db, user_id=args.user_id, reason=args.reason)
        elif args.command == "disable-cap":
            disable_cap(db, user_id=args.user_id, reason=args.reason)


def list_usage_caps(db, *, limit: int) -> None:
    rows = db.execute(
        text(
            """
            WITH usage_by_user AS (
                SELECT
                    ch.user_id,
                    COALESCE(SUM((cm.usage->'price_estimate'->>'total_cost_usd')::numeric), 0) AS current_usage_usd
                FROM chat_histories ch
                LEFT JOIN chat_messages cm
                  ON cm.chat_history_id = ch.id
                 AND cm.role = 'assistant'
                 AND cm.usage IS NOT NULL
                 AND cm.usage->'price_estimate' IS NOT NULL
                GROUP BY ch.user_id
            )
            SELECT
                u.id,
                u.account_type,
                COALESCE(u.email, u.display_name) AS label,
                COALESCE(ubu.current_usage_usd, 0) AS current_usage_usd,
                COALESCE(uuc.baseline_estimated_price_usd, 0) AS baseline_usage_usd,
                GREATEST(COALESCE(ubu.current_usage_usd, 0) - COALESCE(uuc.baseline_estimated_price_usd, 0), 0) AS effective_usage_usd,
                COALESCE(uuc.cap_usd, :default_cap) AS cap_usd,
                COALESCE(uuc.enabled, TRUE) AS enabled
            FROM users u
            LEFT JOIN usage_by_user ubu ON ubu.user_id = u.id
            LEFT JOIN user_usage_caps uuc ON uuc.user_id = u.id
            ORDER BY effective_usage_usd DESC, current_usage_usd DESC, u.created_at DESC
            LIMIT :limit
            """
        ),
        {"default_cap": _decimal(settings.usage_default_cap_usd), "limit": limit},
    ).mappings()
    print("user_id\taccount_type\tlabel\tcurrent_usd\tbaseline_usd\teffective_usd\tcap_usd\tenabled")
    for row in rows:
        print(
            "\t".join(
                [
                    str(row["id"]),
                    str(row["account_type"]),
                    str(row["label"]),
                    str(row["current_usage_usd"]),
                    str(row["baseline_usage_usd"]),
                    str(row["effective_usage_usd"]),
                    str(row["cap_usd"]),
                    str(row["enabled"]),
                ]
            )
        )


def set_cap(db, *, user_id: str, cap_usd: Decimal, reason: str | None) -> None:
    _require_user(db, user_id=user_id)
    now = utc_now()
    cap = db.get(UserUsageCap, user_id)
    if cap is None:
        cap = UserUsageCap(
            user_id=user_id,
            cap_usd=cap_usd,
            baseline_estimated_price_usd=Decimal("0"),
            enabled=True,
            reason=reason,
            created_at=now,
            updated_at=now,
        )
        db.add(cap)
    else:
        cap.cap_usd = cap_usd
        cap.enabled = True
        cap.reason = reason
        cap.updated_at = now
    db.commit()
    print(f"set cap for {user_id}: ${cap_usd}")


def reset_cap(db, *, user_id: str, reason: str | None) -> None:
    _require_user(db, user_id=user_id)
    _reset_cap_row(db, user_id=user_id, reason=reason)
    db.commit()
    print(f"reset cap baseline for {user_id}")


def reset_all_caps(db, *, reason: str | None) -> None:
    user_ids = db.execute(text("SELECT id FROM users ORDER BY created_at")).scalars().all()
    for user_id in user_ids:
        _reset_cap_row(db, user_id=str(user_id), reason=reason)
    db.commit()
    print(f"reset cap baseline for {len(user_ids)} users")


def disable_cap(db, *, user_id: str, reason: str | None) -> None:
    _require_user(db, user_id=user_id)
    now = utc_now()
    cap = db.get(UserUsageCap, user_id)
    if cap is None:
        cap = UserUsageCap(
            user_id=user_id,
            cap_usd=_decimal(settings.usage_default_cap_usd),
            baseline_estimated_price_usd=get_user_estimated_usage_usd(db, user_id=user_id),
            enabled=False,
            reason=reason,
            created_at=now,
            updated_at=now,
        )
        db.add(cap)
    else:
        cap.enabled = False
        cap.reason = reason
        cap.updated_at = now
    db.commit()
    print(f"disabled cap for {user_id}")


def _reset_cap_row(db, *, user_id: str, reason: str | None) -> None:
    now = utc_now()
    current_usage = get_user_estimated_usage_usd(db, user_id=user_id)
    cap = db.get(UserUsageCap, user_id)
    if cap is None:
        cap = UserUsageCap(
            user_id=user_id,
            cap_usd=_decimal(settings.usage_default_cap_usd),
            baseline_estimated_price_usd=current_usage,
            enabled=True,
            reason=reason,
            created_at=now,
            updated_at=now,
        )
        db.add(cap)
        return
    cap.baseline_estimated_price_usd = current_usage
    cap.enabled = True
    cap.reason = reason
    cap.updated_at = now


def _require_user(db, *, user_id: str) -> None:
    if db.get(User, user_id) is None:
        raise SystemExit(f"user not found: {user_id}")


def _decimal(value: object) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"))


if __name__ == "__main__":
    main()
