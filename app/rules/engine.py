"""Posting rules engine.

Checks all applicable destination rules before a post is dispatched.
Rules checked:
  - frequency_cap: how often posts are allowed (e.g. "1/week")
  - self_promo: whether self-promotion is allowed
  - link_policy: link rules
  - ai_disclosure: whether AI content must be disclosed

Returns a list of violations (empty = all rules pass).
Each violation includes a canonical error code and a reschedule hint.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.errors import ErrorCode
from app.core.logging import get_logger

logger = get_logger(__name__)


class RuleViolation:
    def __init__(self, rule_type: str, code: ErrorCode, message: str, retryable: bool | str = False) -> None:
        self.rule_type = rule_type
        self.code = code
        self.message = message
        self.retryable = retryable

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_type": self.rule_type,
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


def evaluate_rules(
    destination: dict[str, Any],
    rendition: dict[str, Any],
    recent_publications: list[dict[str, Any]] | None = None,
) -> list[RuleViolation]:
    """Evaluate all posting rules for a destination.

    Args:
        destination: Destination record dict (from catalogue).
        rendition: Content rendition to be posted.
        recent_publications: List of recent publication records for this destination
                             (used for frequency cap check).

    Returns:
        List of RuleViolation objects. Empty list means all rules pass.
    """
    violations: list[RuleViolation] = []
    recent = recent_publications or []

    # ── Frequency cap ─────────────────────────────────────────────────────────
    freq_cap = destination.get("frequency_cap")
    if freq_cap and recent:
        violation = _check_frequency_cap(freq_cap, recent)
        if violation:
            violations.append(violation)

    # ── Self-promotion ────────────────────────────────────────────────────────
    self_promo_allowed = destination.get("self_promo_allowed")
    if self_promo_allowed is False:
        is_promotional = rendition.get("is_promotional", False)
        if is_promotional:
            violations.append(RuleViolation(
                rule_type="self_promo",
                code=ErrorCode.DEST_SPEC_VIOLATION,
                message="Self-promotion is not allowed at this destination.",
                retryable=False,
            ))

    # ── AI disclosure ─────────────────────────────────────────────────────────
    disclosure_required = destination.get("disclosure_required")
    if disclosure_required:
        has_disclosure = rendition.get("ai_disclosed", False)
        if not has_disclosure:
            violations.append(RuleViolation(
                rule_type="ai_disclosure",
                code=ErrorCode.DEST_SPEC_VIOLATION,
                message="AI-content disclosure is required at this destination.",
                retryable=False,
            ))

    # ── Automation allowed ────────────────────────────────────────────────────
    automation_allowed = destination.get("automation_allowed")
    if automation_allowed is False:
        violations.append(RuleViolation(
            rule_type="automation",
            code=ErrorCode.DEST_SPEC_VIOLATION,
            message="Automated posting is not allowed at this destination. Use the assisted connector.",
            retryable=False,
        ))

    if violations:
        logger.warning("rule_violations", count=len(violations), destination=destination.get("url"))

    return violations


def _check_frequency_cap(cap: str, recent_publications: list[dict]) -> RuleViolation | None:
    """Parse frequency cap (e.g. '1/week', '2/day') and check recent posts."""
    try:
        count_str, period = cap.strip().lower().split("/")
        allowed = int(count_str.strip())
    except (ValueError, AttributeError):
        return None  # unparseable cap — skip

    now = datetime.now(timezone.utc)
    period_seconds = {"day": 86400, "week": 604800, "month": 2592000}.get(period.strip(), 0)
    if not period_seconds:
        return None

    cutoff = now.timestamp() - period_seconds
    posts_in_window = [
        p for p in recent_publications
        if p.get("created_at_ts", 0) > cutoff
    ]

    if len(posts_in_window) >= allowed:
        return RuleViolation(
            rule_type="frequency_cap",
            code=ErrorCode.DEST_RULE_FREQUENCY_CAP,
            message=f"Frequency cap reached: {cap}. {len(posts_in_window)} posts in the last {period}.",
            retryable="Later",
        )
    return None
