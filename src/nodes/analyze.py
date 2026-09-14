"""Node 2: 현재 슬라이드를 멀티모달로 분석하고 검색 계획을 만듭니다."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.core.config import LLM_MODEL
from src.core.prompts import SLIDE_ANALYSIS_SYSTEM_PROMPT
from src.core.schemas import SlideAnalysis, model_to_dict
from src.core.state import AgentState
from src.core.utils import (
    build_visible_slide_context,
    clean_text,
    get_current_slide,
    img_to_data_url,
    record_error,
    reset_slide_runtime,
    safe_print,
    split_sents,
)


print = safe_print


def normalize_search_tasks(tasks: Any, max_tasks: int = 2) -> List[Dict[str, Any]]:
    allowed_purposes = {
        "definition", "statistic", "current_info", "law_policy", "product_spec", "example"
    }
    allowed_policies = {
        "official_only", "primary_preferred", "academic_preferred", "reputable_secondary_allowed"
    }
    normalized: List[Dict[str, Any]] = []
    seen = set()
    for raw_task in tasks or []:
        task = raw_task if isinstance(raw_task, dict) else model_to_dict(raw_task)
        claim = clean_text(task.get("claim_to_verify", ""))
        query = clean_text(task.get("query", ""))
        purpose = clean_text(task.get("purpose", ""))
        policy = clean_text(task.get("source_policy", ""))
        key = (claim.lower(), query.lower())
        if (
            not claim
            or not query
            or purpose not in allowed_purposes
            or policy not in allowed_policies
            or key in seen
        ):
            continue
        domains = [
            clean_text(domain).lower()
            for domain in task.get("preferred_domains", [])
            if clean_text(domain)
        ]
        normalized.append({
            "claim_to_verify": claim,
            "purpose": purpose,
            "query": query,
            "source_policy": policy,
            "freshness_required": bool(task.get("freshness_required", False)),
            "preferred_domains": list(dict.fromkeys(domains))[:10],
        })
        seen.add(key)
        if len(normalized) >= max_tasks:
            break
    return normalized


def node_analyze_slide(state: AgentState) -> AgentState:
    index = int(state.get("slide_index", 0))
    print(f"\n--- Node 2: 슬라이드 {index + 1} 멀티모달 분석 ---")
    reset_slide_runtime(state)
    slide = get_current_slide(state)

    analysis_payload = build_visible_slide_context(slide)
    user_text = (
        "다음 슬라이드를 분석하고 외부 검색 필요 여부를 결정하세요.\n\n"
        + json.dumps(analysis_payload, ensure_ascii=False, indent=2, default=str)
    )

    content: List[Dict[str, Any]] = [{"type": "text", "text": user_text}]
    candidate_images = [slide.get("slide_image", "")] + list(slide.get("images", []))[:2]
    image_count = 0
    for image_path in dict.fromkeys(path for path in candidate_images if path):
        if Path(image_path).exists():
            try:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": img_to_data_url(image_path), "detail": "low"},
                })
                image_count += 1
            except Exception as exc:
                record_error(state, f"슬라이드 {index + 1} 분석 이미지 변환 실패: {exc}")

    try:
        llm = ChatOpenAI(model=LLM_MODEL, temperature=0)
        structured_llm = llm.with_structured_output(SlideAnalysis)
        result = structured_llm.invoke([
            SystemMessage(content=SLIDE_ANALYSIS_SYSTEM_PROMPT),
            HumanMessage(content=content),
        ])
        analysis = model_to_dict(result)
    except Exception as exc:
        record_error(state, f"슬라이드 {index + 1} 멀티모달 분석 실패, 텍스트 fallback 사용: {exc}")
        fallback_facts = [
            value for value in [analysis_payload["title"], analysis_payload["body_text"][:1200]]
            if value
        ]
        analysis = model_to_dict(SlideAnalysis(
            slide_facts=fallback_facts,
            key_points=split_sents(analysis_payload["body_text"])[:4],
            visual_summary="멀티모달 분석을 완료하지 못해 추출 텍스트만 사용합니다.",
            search_needed=False,
            search_reason="분석 오류로 인해 검색을 자동 요청하지 않았습니다.",
            search_tasks=[],
        ))

    analysis["search_tasks"] = normalize_search_tasks(analysis.get("search_tasks", []))
    if analysis.get("search_needed") and not analysis["search_tasks"]:
        analysis["search_needed"] = False
        analysis["search_reason"] = "확인할 주장과 출처 조건이 없는 검색은 안전하지 않아 생략했습니다."
    if not analysis.get("search_needed"):
        analysis["search_tasks"] = []

    state["slide_analysis"] = analysis
    state["search_needed"] = bool(analysis.get("search_needed"))
    state["search_tasks"] = analysis.get("search_tasks", [])
    print(
        f"✅ 분석 완료: facts={len(analysis.get('slide_facts', []))}, "
        f"검색={'필요' if state['search_needed'] else '불필요'}, 이미지={image_count}장"
    )
    return state
