"""The rule data and the review date, parsed once and passed to every check. Nothing here reads the clock."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.validation.deadlines import Rule, read_rule

_NOT_BEFORE = re.compile(r"dated_not_before_(\d{4}-\d{2}-\d{2})")
_PERIOD = re.compile(r"pay_period=(\d{4}-\d{2})")


@dataclass(frozen=True)
class RuleContext:
    as_of: date
    required: tuple[str, ...] = ()
    letter_not_before: date | None = None
    pay_periods: Mapping[str, str] = field(default_factory=dict)
    # Field key to regular expression. The document rules do not define any today, so the check is skipped.
    reference_patterns: Mapping[str, str] = field(default_factory=dict)
    deadline: Rule | None = None


def parse_document_rules(body: Mapping[str, Any], as_of: date, deadline: Rule | None = None) -> RuleContext:
    required, not_before, periods = [], None, {}
    for item in body.get("required_document_categories", []):
        required.append(item["category"])
        for test in item.get("tests", []):
            if m := _NOT_BEFORE.fullmatch(test):
                not_before = date.fromisoformat(m.group(1))
            if m := _PERIOD.fullmatch(test):
                periods[item["category"]] = m.group(1)
    patterns = dict(body.get("reference_patterns") or {})
    return RuleContext(as_of, tuple(required), not_before, periods, patterns, deadline)


def build_context(document_body: Mapping[str, Any] | None, deadline_body: Mapping[str, Any] | None, as_of: date) -> RuleContext:
    return parse_document_rules(document_body or {}, as_of, read_rule(dict(deadline_body or {})))
