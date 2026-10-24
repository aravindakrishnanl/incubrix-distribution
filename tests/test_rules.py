"""Rules engine tests."""

from __future__ import annotations

import time
import pytest

from app.rules.engine import evaluate_rules, RuleViolation
from app.core.errors import ErrorCode


def test_no_rules_passes():
    violations = evaluate_rules(
        destination={},
        rendition={"title": "Hello"},
    )
    assert violations == []


def test_frequency_cap_blocks_excess_posts():
    now = time.time()
    recent = [{"created_at_ts": now - 100}]  # 1 post in last 100 seconds
    violations = evaluate_rules(
        destination={"frequency_cap": "1/week"},
        rendition={"title": "Hello"},
        recent_publications=recent,
    )
    assert len(violations) == 1
    assert violations[0].code == ErrorCode.DEST_RULE_FREQUENCY_CAP
    assert violations[0].retryable == "Later"


def test_frequency_cap_allows_first_post():
    violations = evaluate_rules(
        destination={"frequency_cap": "1/week"},
        rendition={"title": "Hello"},
        recent_publications=[],  # no recent posts
    )
    assert violations == []


def test_self_promo_blocked():
    violations = evaluate_rules(
        destination={"self_promo_allowed": False},
        rendition={"title": "Hello", "is_promotional": True},
    )
    codes = [v.code for v in violations]
    assert ErrorCode.DEST_SPEC_VIOLATION in codes


def test_self_promo_allowed():
    violations = evaluate_rules(
        destination={"self_promo_allowed": True},
        rendition={"title": "Hello", "is_promotional": True},
    )
    assert violations == []


def test_ai_disclosure_required():
    violations = evaluate_rules(
        destination={"disclosure_required": True},
        rendition={"title": "Hello", "ai_disclosed": False},
    )
    codes = [v.code for v in violations]
    assert ErrorCode.DEST_SPEC_VIOLATION in codes


def test_ai_disclosure_provided():
    violations = evaluate_rules(
        destination={"disclosure_required": True},
        rendition={"title": "Hello", "ai_disclosed": True},
    )
    assert violations == []


def test_automation_not_allowed():
    violations = evaluate_rules(
        destination={"automation_allowed": False},
        rendition={"title": "Hello"},
    )
    codes = [v.code for v in violations]
    assert ErrorCode.DEST_SPEC_VIOLATION in codes
