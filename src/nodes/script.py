"""Node 4: 근거 기반 강의 Script Draft 생성."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.core.config import LLM_MODEL, MAX_EVIDENCE_PER_TASK, MAX_SEARCH_TASKS
from src.core.prompts import BANNED_PHRASES, SCRIPT_SYSTEM_PROMPT
from src.core.schemas import ScriptDraftResult, model_to_dict
from src.core.state import AgentState
from src.core.utils import (
    build_visible_slide_context,
    clean_text,
    get_current_slide,
    record_error,
    safe_print,
    split_sents,
)


print = safe_print


def extract_openers(scripts: List[str]) -> List[str]:
    openers = []
    for script in scripts:
        sentences = split_sents(script)
        if sentences and len(sentences[0]) > 5:
            openers.append(sentences[0])
    return openers


def limit_word(text: str, word: str, max_count: int = 1) -> str:
    count = 0
    kept_sentences = []
    for sentence in split_sents(text):
        occurrences = sentence.count(word)
        allowed = max(0, max_count - count)
        if occurrences > allowed:
            remove_count = occurrences - allowed
            sentence = sentence.replace(word, "", remove_count)
        count += min(occurrences, allowed)
        sentence = clean_text(sentence)
        if sentence:
            kept_sentences.append(sentence)
    return " ".join(kept_sentences)


def build_script_evidence(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """직접 근거 및 출처 정책 검토를 모두 통과한 필드만 Script에 전달합니다."""
    allowed_keys = [
        "evidence_id", "claim_to_verify", "purpose", "title", "url", "source_type",
        "supporting_excerpt", "selection_reason",
    ]
    return [
        {key: item.get(key, "") for key in allowed_keys}
        for item in evidence
        if item.get("directly_supports_claim") and item.get("source_policy_satisfied")
    ]


def build_recent_script_context(
    scripts: List[str], max_scripts: int = 2, max_chars: int = 400
) -> str:
    recent = [
        clean_text(script)[:max_chars]
        for script in scripts[-max_scripts:]
        if clean_text(script)
    ]
    return "\n".join(
        f"- 최근 대본 {position}: {script}"
        for position, script in enumerate(recent, start=1)
    ) or "(없음)"


def build_previous_slide_tail(scripts: List[str], max_sentences: int = 2) -> str:
    if not scripts:
        return "(직전 승인 슬라이드 없음)"
    sentences = split_sents(clean_text(scripts[-1]))
    return " ".join(sentences[-max_sentences:]) or "(직전 승인 슬라이드의 마무리를 찾지 못함)"


def build_slide_flow_instruction(index: int, total_slides: int, has_previous_script: bool) -> str:
    if index == 0:
        return "첫 슬라이드입니다. 인사나 '오늘은'으로 시작하지 말고, 슬라이드의 핵심 주제로 바로 시작하세요."
    if not has_previous_script:
        return (
            "직전 승인 영상이 없어 독립적으로 시작합니다. '오늘은', '이번 시간에는', '지금부터'로 시작하지 말고 "
            "현재 슬라이드의 핵심 사실·개념을 바로 설명하세요."
        )
    if index == total_slides - 1:
        return (
            "마지막 슬라이드입니다. 직전 슬라이드의 마무리와 현재 핵심을 한 문장으로 연결한 뒤, "
            "새 주제를 다시 소개하지 말고 핵심을 정리해 마무리하세요."
        )
    return (
        "중간 슬라이드입니다. 첫 문장은 직전 슬라이드의 마무리를 받아 현재 핵심으로 이어가세요. "
        "'오늘은', '이번 시간에는', '지금부터', '먼저'로 시작하거나 새 강의처럼 재소개하지 마세요."
    )


def remove_repetitive_opening(draft: str) -> str:
    pattern = (
        r"^(?:(?:네|자|그럼|그러면)\s*[,，]?\s*)?"
        r"(?:오늘은|이번 시간에는|이번 시간|이번 슬라이드에서는|지금부터|먼저)\s*[,，]?\s*"
    )
    return clean_text(re.sub(pattern, "", clean_text(draft)))


def build_forbidden_claims(validation_result: Dict[str, Any], max_claims: int = 4) -> str:
    claims: List[str] = []
    for key in ("unsupported_claims", "distortions"):
        for value in (validation_result or {}).get(key, []) or []:
            claim = clean_text(value)
            if claim and claim not in claims:
                claims.append(claim)
    if not claims:
        return "(없음)"
    return "\n".join(
        f"- 이 주장 또는 같은 뜻의 표현을 대본에서 제거: {claim}"
        for claim in claims[:max_claims]
    )


def normalize_script_draft_result(
    result: Dict[str, Any], evidence: List[Dict[str, Any]]
) -> Dict[str, Any]:
    known_ids = {clean_text(item.get("evidence_id", "")) for item in evidence}
    used_ids = list(dict.fromkeys(
        clean_text(value)
        for value in result.get("used_evidence_ids", [])
        if clean_text(value)
    ))[:MAX_EVIDENCE_PER_TASK * MAX_SEARCH_TASKS]
    external_claims = list(dict.fromkeys(
        clean_text(value)
        for value in result.get("external_claims_used", [])
        if clean_text(value)
    ))[:4]
    return {
        "script": clean_text(result.get("script", "")),
        "used_evidence_ids": used_ids,
        "external_claims_used": external_claims,
        "invalid_evidence_ids": [value for value in used_ids if value not in known_ids],
    }


def node_generate_script(state: AgentState) -> AgentState:
    index = int(state.get("slide_index", 0))
    print(f"\n--- Node 4: 슬라이드 {index + 1} Script Draft 생성 ---")
    slide = build_visible_slide_context(get_current_slide(state))
    analysis = state.get("slide_analysis", {})
    evidence = build_script_evidence(state.get("evidence", []))
    lecture_config = state.get("lecture_config", {}) or {}
    accepted_scripts = state.get("all_scripts", [])
    recent_scripts = build_recent_script_context(accepted_scripts)
    previous_slide_tail = build_previous_slide_tail(accepted_scripts)
    recent_openers = extract_openers(accepted_scripts)[-3:]
    feedback = state.get("validation_feedback", [])
    forbidden_claims = build_forbidden_claims(state.get("validation_result", {}))

    total_slides = int(state.get("total_slides", len(state.get("slides", []))))
    flow_instruction = build_slide_flow_instruction(index, total_slides, bool(accepted_scripts))

    target_seconds = int(lecture_config.get("target_duration_sec", 60))
    minimum_chars = target_seconds * 9
    maximum_chars = target_seconds * 13
    prompt = ChatPromptTemplate.from_messages([
        ("system", SCRIPT_SYSTEM_PROMPT),
        ("human", """[현재 슬라이드]
{slide}

[구조화 분석]
{analysis}

[외부 Evidence]
{evidence}

[최근 승인 Script]
{recent_scripts}

[직전 슬라이드의 마무리]
{previous_slide_tail}

[최근 사용한 시작 표현]
{recent_openers}

[Validation 수정 지시]
{feedback}

[이번 재생성에서 제거할 주장]
{forbidden_claims}

[강의 설정]
- 톤: {tone}
- 스타일: {style}
- 목표 길이: {target_seconds}초, 약 {minimum_chars}~{maximum_chars}자
- 흐름: {flow_instruction}

위 재료만 사용해 구조화된 결과를 작성하세요."""),
    ])

    try:
        llm = ChatOpenAI(model=LLM_MODEL, temperature=0 if feedback else 0.2)
        structured_llm = llm.with_structured_output(ScriptDraftResult)
        response = structured_llm.invoke(prompt.format_messages(
            slide=json.dumps(slide, ensure_ascii=False, default=str),
            analysis=json.dumps(analysis, ensure_ascii=False, default=str),
            evidence=json.dumps(evidence, ensure_ascii=False, default=str),
            recent_scripts=recent_scripts,
            previous_slide_tail=previous_slide_tail,
            recent_openers="\n".join(f"- {item}" for item in recent_openers) or "(없음)",
            feedback="\n".join(f"- {item}" for item in feedback) or "(없음)",
            forbidden_claims=forbidden_claims,
            tone=lecture_config.get("tone", "친절하고 명료한 톤"),
            style=lecture_config.get("style", "자연스럽고 설명적인 말투"),
            target_seconds=target_seconds,
            minimum_chars=minimum_chars,
            maximum_chars=maximum_chars,
            flow_instruction=flow_instruction,
        ))
        draft_result = normalize_script_draft_result(model_to_dict(response), evidence)
        draft = draft_result["script"]
    except Exception as exc:
        record_error(state, f"슬라이드 {index + 1} Script 생성 실패: {exc}")
        state["script_draft"] = ""
        state["script_draft_meta"] = {}
        return state

    draft = remove_repetitive_opening(draft)
    for phrase in BANNED_PHRASES:
        draft = draft.replace(phrase, "")
    draft = limit_word(clean_text(draft), "여러분", max_count=1)
    state["script_draft"] = draft
    draft_result["script"] = draft
    state["script_draft_meta"] = draft_result

    work_dir = Path(state.get("work_dir", "./output_v4"))
    work_dir.mkdir(parents=True, exist_ok=True)
    attempt = int(state.get("validation_attempt", 0))
    draft_path = work_dir / f"script_draft_slide{index + 1}_attempt{attempt + 1}.txt"
    draft_path.write_text(draft, encoding="utf-8")

    if len(draft) < minimum_chars or len(draft) > maximum_chars:
        print(
            f"⚠️ 권장 길이 범위 밖: {len(draft)}자 "
            f"(권장 {minimum_chars}~{maximum_chars}자)"
        )
    print(f"✅ Script Draft 생성 완료: {len(draft)}자")
    return state
