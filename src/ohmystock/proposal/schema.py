"""ProposalDraft frozen pydantic model.

Spec: openspec/changes/phase5-review-mvp/specs/proposal-writer/spec.md
SSOT: proposals/README.md §4 template (8 必填段落 + frontmatter)

The model deliberately omits ``status``: ``writer.write_proposal`` always
forces ``status: pending`` per design Decision 6, so a draft cannot
encode a non-pending status. Any extra field passed in raises
``ValidationError`` (``extra="forbid"``).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


_TOPIC_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_TOPIC_MAX_LEN = 40
_METRICS_POINTER_TOKEN = "metrics.json#"


class ProposalDraft(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    topic: str
    target_section: str
    created_by: str
    created_at: datetime
    review_id: str | None
    priority: Literal["high", "medium", "low"]
    description: str
    motivation: str
    diff_draft: str
    expected_impact: str
    risk_assessment: str
    validation_plan: str
    expected_improvement: str

    @field_validator("topic")
    @classmethod
    def _validate_topic(cls, value: str) -> str:
        if len(value) < 1 or len(value) > _TOPIC_MAX_LEN:
            raise ValueError(
                f"topic length must be 1..{_TOPIC_MAX_LEN}, got {len(value)}"
            )
        if not _TOPIC_RE.match(value):
            raise ValueError(
                "topic must be kebab-case matching ^[a-z0-9]+(-[a-z0-9]+)*$, "
                f"got {value!r}"
            )
        return value

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware (ISO-8601 with offset)")
        return value

    @field_validator("motivation")
    @classmethod
    def _validate_motivation_pointer(cls, value: str) -> str:
        if _METRICS_POINTER_TOKEN not in value:
            raise ValueError(
                "motivation must reference at least one metrics.json# JSON pointer "
                "(per post-trade-review-rubric.md §7 攻擊性檢查)"
            )
        return value
