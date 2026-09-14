"""Node 5: Script 사실성 검증, Router, 승인 및 실패 처리."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.core.config import LLM_MODEL
from src.core.prompts import SCRIPT_VALIDATION_SYSTEM_PROMPT
from src.core.schemas import ValidationResult, model_to_dict
from src.core.state import AgentState
from src.core.utils import (
    add_failed_slide,
    build_visible_slide_context,
    clean_text,
    get_current_slide,
    img_to_data_url,
    record_error,
    safe_print,
)
from src.nodes.script import build_script_evidence


print = safe_print


def build_validation_feedback(result: Dict[str, Any]) -> List[str]:
    feedback: List[str] = []
    labels = [
        ("지원되지 않은 주장", "unsupported_claims"),
        ("누락된 핵심", "missing_points"),
        ("왜곡", "distortions"),
        ("수정 지시", "revision_instructions"),
    ]
    for label, key in labels:
        for item in result.get(key, []) or []:
            value = clean_text(item)
            if value:
                feedback.append(f"{label}: {value}")
    return feedback


def build_validation_preflight(
    draft_meta: Dict[str, Any], evidence: List[Dict[str, Any]]
) -> List[str]:
    available_ids = {clean_text(item.get("evidence_id", "")) for item in evidence}
    used_ids = [
        clean_text(value)
        for value in draft_meta.get("used_evidence_ids", [])
        if clean_text(value)
    ]
    issues = [
        f"존재하지 않는 Evidence ID 사용: {value}"
        for value in used_ids
        if value not in available_ids
    ]
    if draft_meta.get("external_claims_used") and not used_ids:
        issues.append("외부 주장을 기록했지만 사용 Evidence ID가 없습니다.")
    return issues


def build_approved_visual_facts(analysis: Dict[str, Any]) -> List[str]:
    facts: List[str] = []
    for raw_fact in analysis.get("slide_facts", []) or []:
        fact = clean_text(raw_fact)
        if fact and fact not in facts:
            facts.append(fact)
    return facts[:7]


def build_validation_message_content(
    state: AgentState, payload: Dict[str, Any], index: int
) -> List[Dict[str, Any]]:
    """전체 슬라이드와 삽입 이미지 원본을 고해상도 근거로 전달합니다."""
    content: List[Dict[str, Any]] = [
        {"type": "text", "text": json.dumps(payload, ensure_ascii=False, default=str)}
    ]
    slide = get_current_slide(state)
    candidate_paths = [slide.get("slide_image", "")] + list(slide.get("images", []) or [])[:2]
    unique_paths: List[str] = []
    for raw_path in candidate_paths:
        image_path = clean_text(raw_path)
        if image_path and image_path not in unique_paths:
            unique_paths.append(image_path)

    for image_order, image_path in enumerate(unique_paths, start=1):
        if not Path(image_path).exists():
            continue
        try:
            content.append({
                "type": "image_url",
                "image_url": {"url": img_to_data_url(image_path), "detail": "high"},
            })
        except Exception as exc:
            record_error(
                state,
                f"슬라이드 {index + 1} 검증 이미지 {image_order} 변환 실패: {exc}",
            )
    return content


def node_validate_script(state: AgentState) -> AgentState:
    index = int(state.get("slide_index", 0))
    print(f"\n--- Node 5: 슬라이드 {index + 1} Script Validation ---")
    draft = clean_text(state.get("script_draft", ""))
    state["validation_system_error"] = False

    if not draft:
        validation = model_to_dict(ValidationResult(
            status="FAIL",
            unsupported_claims=[],
            missing_points=["검증할 Script Draft가 비어 있습니다."],
            distortions=[],
            revision_instructions=["PPT 근거를 사용해 Script Draft를 다시 생성하세요."],
        ))
        state["validation_error_attempt"] = 0
    else:
        draft_meta = state.get("script_draft_meta", {}) or {}
        verified_evidence = build_script_evidence(state.get("evidence", []))
        preflight_issues = build_validation_preflight(draft_meta, verified_evidence)
        analysis = state.get("slide_analysis", {}) or {}
        payload = {
            "slide": build_visible_slide_context(get_current_slide(state)),
            "approved_visual_facts": build_approved_visual_facts(analysis),
            "slide_analysis": {
                "key_points": analysis.get("key_points", []) or [],
                "visual_summary": clean_text(analysis.get("visual_summary", "")),
            },
            "evidence": verified_evidence,
            "script_draft": draft,
            "script_draft_meta": draft_meta,
        }
        try:
            llm = ChatOpenAI(model=LLM_MODEL, temperature=0)
            structured_llm = llm.with_structured_output(ValidationResult)
            response = structured_llm.invoke([
                SystemMessage(content=SCRIPT_VALIDATION_SYSTEM_PROMPT),
                HumanMessage(content=build_validation_message_content(state, payload, index)),
            ])
            validation = model_to_dict(response)
            state["validation_error_attempt"] = 0
        except Exception as exc:
            record_error(state, f"슬라이드 {index + 1} Script Validation 호출 실패: {exc}")
            state["validation_system_error"] = True
            state["validation_error_attempt"] = int(state.get("validation_error_attempt", 0)) + 1
            validation = model_to_dict(ValidationResult(
                status="FAIL",
                unsupported_claims=[],
                missing_points=[],
                distortions=[],
                revision_instructions=[
                    "검증 호출에 실패했습니다. 근거 범위 안에서 Script를 다시 생성하세요."
                ],
            ))
        if preflight_issues:
            validation["unsupported_claims"] = (
                list(validation.get("unsupported_claims", [])) + preflight_issues
            )

    factual_issues = (
        validation.get("unsupported_claims", [])
        + validation.get("missing_points", [])
        + validation.get("distortions", [])
    )
    if factual_issues:
        validation["status"] = "FAIL"

    state["validation_result"] = validation
    if state.get("validation_system_error"):
        state["validation_feedback"] = []
    elif validation.get("status") == "PASS":
        state["validation_feedback"] = []
    else:
        state["validation_attempt"] = int(state.get("validation_attempt", 0)) + 1
        state["validation_feedback"] = build_validation_feedback(validation)

    if state.get("validation_system_error"):
        print(
            f"⚠️ Validation 시스템 오류 {state.get('validation_error_attempt', 0)}/"
            f"{state.get('max_validation_error_retries', 1) + 1}회"
        )
    else:
        print(
            f"✅ Validation 결과: {validation.get('status')} "
            f"(내용 FAIL {state.get('validation_attempt', 0)}/"
            f"재생성 한도 {state.get('max_validation_attempts', 2)})"
        )
    return state


def validation_router(state: AgentState) -> str:
    status = (state.get("validation_result", {}) or {}).get("status", "FAIL")
    failed_attempts = int(state.get("validation_attempt", 0))
    max_retries = int(state.get("max_validation_attempts", 2))
    validation_error_attempt = int(state.get("validation_error_attempt", 0))
    max_error_retries = int(state.get("max_validation_error_retries", 1))

    if state.get("validation_system_error"):
        route = "recheck" if validation_error_attempt <= max_error_retries else "system_error"
    elif status == "PASS":
        route = "pass"
    elif failed_attempts <= max_retries:
        route = "retry"
    else:
        route = "exhausted"
    print(f"🔀 Validation Router: {route}")
    return route


def node_accept_script(state: AgentState) -> AgentState:
    index = int(state.get("slide_index", 0))
    status = (state.get("validation_result", {}) or {}).get("status")
    draft = clean_text(state.get("script_draft", ""))
    if status != "PASS" or not draft:
        raise RuntimeError("PASS하지 않은 Script는 확정할 수 없습니다.")

    state["script_final"] = draft
    state.setdefault("all_scripts", []).append(draft)
    work_dir = Path(state.get("work_dir", "./output_v4"))
    work_dir.mkdir(parents=True, exist_ok=True)
    final_script_path = work_dir / f"script_final_slide{index + 1}.txt"
    final_script_path.write_text(draft, encoding="utf-8")
    print(f"✅ 슬라이드 {index + 1} Script 승인: {final_script_path}")
    return state


def record_failed_slide_detail(
    state: AgentState, index: int, failure_type: str, reason: str
) -> None:
    details = state.setdefault("failed_slide_details", [])
    detail = {
        "slide_index": index,
        "failure_type": failure_type,
        "reason": reason,
        "last_script_draft": clean_text(state.get("script_draft", "")),
        "script_draft_meta": dict(state.get("script_draft_meta", {}) or {}),
        "validation_result": dict(state.get("validation_result", {}) or {}),
        "validation_attempt": int(state.get("validation_attempt", 0)),
        "validation_error_attempt": int(state.get("validation_error_attempt", 0)),
    }
    details[:] = [item for item in details if item.get("slide_index") != index]
    details.append(detail)


def node_mark_validation_failed(state: AgentState) -> AgentState:
    index = int(state.get("slide_index", 0))
    add_failed_slide(state, index)
    if state.get("validation_system_error"):
        failure_type = "validation_system_error"
        reason = (
            f"Validation 시스템 오류 재시도 한도 초과 "
            f"({state.get('validation_error_attempt', 0)}회)"
        )
    else:
        failure_type = "validation_content_failed"
        reason = (
            f"Validation 내용 FAIL 재생성 한도 초과 "
            f"({state.get('validation_attempt', 0)}회)"
        )
    record_failed_slide_detail(state, index, failure_type, reason)
    state["script_final"] = ""
    state["audio_path"] = ""
    state["video_path"] = ""
    record_error(state, f"슬라이드 {index + 1} {reason}: 미디어 생성을 건너뜁니다.")
    return state
