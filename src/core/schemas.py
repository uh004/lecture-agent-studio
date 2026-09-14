"""LLM 구조화 출력에 사용하는 Pydantic Schema."""

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field


class SearchTask(BaseModel):
    claim_to_verify: str
    purpose: Literal[
        "definition", "statistic", "current_info", "law_policy", "product_spec", "example"
    ]
    query: str
    source_policy: Literal[
        "official_only", "primary_preferred", "academic_preferred", "reputable_secondary_allowed"
    ]
    freshness_required: bool = False
    preferred_domains: List[str] = Field(default_factory=list)


class SlideAnalysis(BaseModel):
    slide_facts: List[str] = Field(default_factory=list)
    key_points: List[str] = Field(default_factory=list)
    visual_summary: str = ""
    search_needed: bool = False
    search_reason: str = ""
    search_tasks: List[SearchTask] = Field(default_factory=list)


class EvidenceAssessment(BaseModel):
    candidate_id: str
    use_as_evidence: bool
    directly_supports_claim: bool
    source_type: Literal["official", "primary", "academic", "secondary", "community", "unknown"]
    source_policy_satisfied: bool
    supporting_excerpt: str = ""
    selection_reason: str = ""


class EvidenceReview(BaseModel):
    assessments: List[EvidenceAssessment] = Field(default_factory=list)


class ScriptDraftResult(BaseModel):
    script: str
    used_evidence_ids: List[str] = Field(default_factory=list)
    external_claims_used: List[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    status: Literal["PASS", "FAIL"]
    unsupported_claims: List[str] = Field(default_factory=list)
    missing_points: List[str] = Field(default_factory=list)
    distortions: List[str] = Field(default_factory=list)
    revision_instructions: List[str] = Field(default_factory=list)


def model_to_dict(model: BaseModel) -> dict:
    """Pydantic v1과 v2 모두에서 일반 dict를 반환합니다."""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
