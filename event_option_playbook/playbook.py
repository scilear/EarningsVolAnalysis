"""Playbook recommendation domain objects."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PlaybookRiskNote:
    """One practical risk note attached to a recommended structure."""

    category: str
    detail: str
    mitigation: str | None = None

    def __post_init__(self) -> None:
        if not self.category.strip():
            raise ValueError("PlaybookRiskNote.category must be non-empty.")
        if not self.detail.strip():
            raise ValueError("PlaybookRiskNote.detail must be non-empty.")


@dataclass(frozen=True)
class PlaybookPolicyConstraint:
    """One deterministic policy rule used to filter or gate recommendations."""

    rule_id: str
    stage: str
    scope: str
    condition: str
    rationale: str
    action: str

    def __post_init__(self) -> None:
        for field_name in ("rule_id", "stage", "scope", "condition", "rationale", "action"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"PlaybookPolicyConstraint.{field_name} must be non-empty.")


@dataclass(frozen=True)
class PlaybookManagementItem:
    """One deterministic management instruction tied to a specific trigger."""

    category: str
    trigger: str
    action: str
    notes: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("category", "trigger", "action"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"PlaybookManagementItem.{field_name} must be non-empty.")


@dataclass(frozen=True)
class PlaybookCandidate:
    """A candidate structure before final recommendation selection."""

    structure_name: str
    thesis: str
    expected_edge: str
    entry_timing: str
    max_risk: str
    score: float | None = None
    practical_risks: list[PlaybookRiskNote] = field(default_factory=list)
    policy_constraints: list[str] = field(default_factory=list)
    management_guidance: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for field_name in (
            "structure_name",
            "thesis",
            "expected_edge",
            "entry_timing",
            "max_risk",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must be non-empty.")


@dataclass(frozen=True)
class PlaybookRecommendation:
    """Final playbook output contract for one event setup."""

    event_key: str
    ranked_candidates: list[PlaybookCandidate] = field(default_factory=list)
    policy_constraints: list[PlaybookPolicyConstraint] = field(default_factory=list)
    recommended: list[PlaybookCandidate] = field(default_factory=list)
    risk_notes: list[PlaybookRiskNote] = field(default_factory=list)
    key_levels: list[str] = field(default_factory=list)
    management_guidance: list[PlaybookManagementItem] = field(default_factory=list)
    management_rules: list[str] = field(default_factory=list)
    no_trade_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.event_key.strip():
            raise ValueError("event_key must be non-empty.")
        if self.no_trade_reason is not None and self.recommended:
            raise ValueError(
                "A no-trade recommendation should not include recommended structures."
            )

    @property
    def is_no_trade(self) -> bool:
        """Return True when the playbook recommends standing aside."""

        return self.no_trade_reason is not None

    def to_dict(self) -> dict[str, object]:
        """Serialize the recommendation contract."""

        return {
            "event_key": self.event_key,
            "ranked_candidates": [
                {
                    "structure_name": item.structure_name,
                    "thesis": item.thesis,
                    "expected_edge": item.expected_edge,
                    "entry_timing": item.entry_timing,
                    "max_risk": item.max_risk,
                    "score": item.score,
                    "practical_risks": [
                        {
                            "category": note.category,
                            "detail": note.detail,
                            "mitigation": note.mitigation,
                        }
                        for note in item.practical_risks
                    ],
                    "policy_constraints": item.policy_constraints,
                    "management_guidance": item.management_guidance,
                }
                for item in self.ranked_candidates
            ],
            "policy_constraints": [
                {
                    "rule_id": rule.rule_id,
                    "stage": rule.stage,
                    "scope": rule.scope,
                    "condition": rule.condition,
                    "rationale": rule.rationale,
                    "action": rule.action,
                }
                for rule in self.policy_constraints
            ],
            "recommended": [
                {
                    "structure_name": item.structure_name,
                    "thesis": item.thesis,
                    "expected_edge": item.expected_edge,
                    "entry_timing": item.entry_timing,
                    "max_risk": item.max_risk,
                    "score": item.score,
                    "practical_risks": [
                        {
                            "category": note.category,
                            "detail": note.detail,
                            "mitigation": note.mitigation,
                        }
                        for note in item.practical_risks
                    ],
                    "policy_constraints": item.policy_constraints,
                    "management_guidance": item.management_guidance,
                }
                for item in self.recommended
            ],
            "risk_notes": [
                {
                    "category": note.category,
                    "detail": note.detail,
                    "mitigation": note.mitigation,
                }
                for note in self.risk_notes
            ],
            "key_levels": self.key_levels,
            "management_guidance": [
                {
                    "category": item.category,
                    "trigger": item.trigger,
                    "action": item.action,
                    "notes": item.notes,
                }
                for item in self.management_guidance
            ],
            "management_rules": self.management_rules,
            "no_trade_reason": self.no_trade_reason,
            "is_no_trade": self.is_no_trade,
        }
