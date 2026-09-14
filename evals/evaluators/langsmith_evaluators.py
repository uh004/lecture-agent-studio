from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from evals.evaluators.code_metrics import evaluate_parser


RUBRIC_DIR = Path(__file__).resolve().parents[1] / "rubrics"


class SearchQualityScore(BaseModel):
    retrieval_relevance: int = Field(ge=1, le=5)
    information_coverage: int = Field(ge=1, le=5)
    source_quality: int = Field(ge=1, le=5)
    reasoning: str


class ScriptQualityScore(BaseModel):
    groundedness: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)
    educational_clarity: int = Field(ge=1, le=5)
    continuity: int = Field(ge=1, le=5)
    non_repetition: int = Field(ge=1, le=5)
    atomic_claim_count: int = Field(ge=0)
    unsupported_claim_count: int = Field(ge=0)
    reasoning: str


def parser_code_evaluator(
    outputs: Dict[str, Any], reference_outputs: Dict[str, Any]
) -> List[Dict[str, Any]]:
    metrics = evaluate_parser(
        (reference_outputs or {}).get("parser", {}),
        (outputs or {}).get("parser", {}),
    )
    return [{"key": key, "score": score} for key, score in metrics.items()]


def search_decision_evaluator(
    outputs: Dict[str, Any], reference_outputs: Dict[str, Any]
) -> Dict[str, Any]:
    expected = bool(((reference_outputs or {}).get("search") or {}).get("needed", False))
    actual = bool(((outputs or {}).get("search") or {}).get("needed", False))
    return {"key": "search_decision_correct", "score": float(expected == actual)}


def validation_status_evaluator(
    outputs: Dict[str, Any], reference_outputs: Dict[str, Any]
) -> Dict[str, Any]:
    expected = str(((reference_outputs or {}).get("validation") or {}).get("status", "")).upper()
    if expected not in {"PASS", "FAIL"}:
        return {"key": "validation_status_applicable", "value": "not_applicable"}
    validation = (outputs or {}).get("validation") or {}
    actual = str(validation.get("initial_status") or validation.get("status") or "").upper()
    return {"key": "validation_status_correct", "score": float(expected == actual)}


def _load_rubric(filename: str) -> str:
    return (RUBRIC_DIR / filename).read_text(encoding="utf-8")


def make_search_quality_evaluator(model: str) -> Callable[..., List[Dict[str, Any]]]:
    rubric = _load_rubric("search_quality.md")
    judge = ChatOpenAI(model=model, temperature=0).with_structured_output(SearchQualityScore)

    def search_quality(
        inputs: Dict[str, Any], outputs: Dict[str, Any], reference_outputs: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        expected_search = bool(((reference_outputs or {}).get("search") or {}).get("needed", False))
        actual_search = (outputs or {}).get("search") or {}
        if not expected_search and not actual_search.get("needed"):
            return [{"key": "search_quality_applicable", "value": "not_applicable"}]
        payload = {
            "inputs": inputs,
            "actual_search": actual_search,
            "reference": (reference_outputs or {}).get("search", {}),
        }
        result = judge.invoke([
            ("system", rubric),
            ("human", json.dumps(payload, ensure_ascii=False, default=str)),
        ])
        return [
            {"key": "retrieval_relevance", "score": result.retrieval_relevance, "comment": result.reasoning},
            {"key": "information_coverage", "score": result.information_coverage, "comment": result.reasoning},
            {"key": "source_quality", "score": result.source_quality, "comment": result.reasoning},
        ]

    return search_quality


def make_script_quality_evaluator(model: str) -> Callable[..., List[Dict[str, Any]]]:
    rubric = _load_rubric("script_quality.md")
    judge = ChatOpenAI(model=model, temperature=0).with_structured_output(ScriptQualityScore)

    def script_quality(
        inputs: Dict[str, Any], outputs: Dict[str, Any], reference_outputs: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        payload = {
            "inputs": inputs,
            "actual_analysis": (outputs or {}).get("analysis", {}),
            "actual_evidence": ((outputs or {}).get("search") or {}).get("evidence", []),
            "actual_script": ((outputs or {}).get("script") or {}).get("final", ""),
            "reference": (reference_outputs or {}).get("script", {}),
        }
        result = judge.invoke([
            ("system", rubric),
            ("human", json.dumps(payload, ensure_ascii=False, default=str)),
        ])
        unsupported_rate = (
            result.unsupported_claim_count / result.atomic_claim_count
            if result.atomic_claim_count
            else 0.0
        )
        return [
            {"key": "script_groundedness", "score": result.groundedness, "comment": result.reasoning},
            {"key": "script_completeness", "score": result.completeness, "comment": result.reasoning},
            {"key": "script_educational_clarity", "score": result.educational_clarity, "comment": result.reasoning},
            {"key": "script_continuity", "score": result.continuity, "comment": result.reasoning},
            {"key": "script_non_repetition", "score": result.non_repetition, "comment": result.reasoning},
            {"key": "script_unsupported_claim_rate", "score": unsupported_rate, "comment": result.reasoning},
        ]

    return script_quality
