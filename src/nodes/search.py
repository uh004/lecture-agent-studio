"""Node 3: 조건부 Tavily 검색과 원문 기반 Evidence 선별."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List
from urllib.parse import urlparse

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from tavily import TavilyClient

from src.core.config import (
    LLM_MODEL,
    MAX_CANDIDATES_PER_TASK,
    MAX_EVIDENCE_PER_TASK,
    MAX_RAW_CONTENT_CHARS,
    MAX_SEARCH_TASKS,
    TAVILY_API_KEY,
)
from src.core.prompts import EVIDENCE_REVIEW_SYSTEM_PROMPT
from src.core.schemas import EvidenceReview, model_to_dict
from src.core.state import AgentState
from src.core.utils import clean_text, record_error, safe_print
from src.nodes.analyze import normalize_search_tasks


print = safe_print


def compact_text(value: Any, limit: int) -> str:
    return clean_text(value)[:limit]


def choose_extraction_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    per_domain: Dict[str, int] = {}
    seen_urls = set()
    for candidate in sorted(candidates, key=lambda item: item.get("tavily_score", 0.0), reverse=True):
        url = candidate.get("url", "")
        domain = candidate.get("domain", "")
        if not url or url in seen_urls or per_domain.get(domain, 0) >= 2:
            continue
        seen_urls.add(url)
        per_domain[domain] = per_domain.get(domain, 0) + 1
        selected.append(candidate)
        if len(selected) >= MAX_CANDIDATES_PER_TASK:
            break
    return selected


def tavily_search_candidates(client: TavilyClient, task: Dict[str, Any]) -> List[Dict[str, Any]]:
    """검색 후보 URL을 찾되 아직 Evidence로 채택하지 않습니다."""
    params: Dict[str, Any] = {
        "query": task["query"],
        "max_results": 8,
        "search_depth": "basic",
        "topic": "general",
        "include_answer": False,
        "include_raw_content": False,
    }
    if task.get("preferred_domains"):
        params["include_domains"] = task["preferred_domains"]
    if task.get("freshness_required"):
        params["time_range"] = "year"

    response = client.search(**params) or {}
    raw_results = response.get("results", []) if isinstance(response, dict) else []
    candidates: List[Dict[str, Any]] = []
    seen_urls = set()
    for item in raw_results:
        url = clean_text(item.get("url", ""))
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        candidates.append({
            "claim_to_verify": task["claim_to_verify"],
            "purpose": task["purpose"],
            "source_policy": task["source_policy"],
            "query": task["query"],
            "title": clean_text(item.get("title", "")),
            "url": url,
            "domain": urlparse(url).netloc.lower(),
            "snippet": compact_text(item.get("content", ""), 800),
            "tavily_score": float(item.get("score") or 0.0),
        })
    return candidates


def extract_candidate_pages(
    client: TavilyClient,
    task: Dict[str, Any],
    candidates: List[Dict[str, Any]],
) -> Dict[str, str]:
    """선별한 후보 URL의 원문을 가져옵니다."""
    urls = [candidate["url"] for candidate in candidates if candidate.get("url")]
    if not urls:
        return {}
    try:
        response = client.extract(
            urls=urls,
            query=task["claim_to_verify"],
            extract_depth="advanced",
            chunks_per_source=2,
        )
    except TypeError:
        response = client.extract(urls=urls)

    raw_results = response.get("results", []) if isinstance(response, dict) else []
    extracted: Dict[str, str] = {}
    for item in raw_results:
        url = clean_text(item.get("url", ""))
        content = compact_text(
            item.get("raw_content") or item.get("content", ""),
            MAX_RAW_CONTENT_CHARS,
        )
        if url and content:
            extracted[url] = content
    return extracted


def review_candidate_evidence(
    task: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    extracted_pages: Dict[str, str],
) -> List[Dict[str, Any]]:
    """원문이 주장과 출처 정책을 모두 만족할 때만 Evidence로 채택합니다."""
    review_candidates = []
    candidate_map: Dict[str, Dict[str, Any]] = {}
    for position, candidate in enumerate(candidates, start=1):
        page_content = extracted_pages.get(candidate.get("url", ""), "")
        if not page_content:
            continue
        candidate_id = f"candidate_{position}"
        candidate_map[candidate_id] = candidate
        review_candidates.append({
            "candidate_id": candidate_id,
            "title": candidate.get("title", ""),
            "url": candidate.get("url", ""),
            "domain": candidate.get("domain", ""),
            "page_content": page_content,
        })
    if not review_candidates:
        return []

    payload = {"search_task": task, "candidates": review_candidates}
    llm = ChatOpenAI(model=LLM_MODEL, temperature=0)
    reviewer = llm.with_structured_output(EvidenceReview)
    review = model_to_dict(reviewer.invoke([
        SystemMessage(content=EVIDENCE_REVIEW_SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False, default=str)),
    ]))

    accepted: List[Dict[str, Any]] = []
    seen_urls = set()
    for assessment in review.get("assessments", []):
        candidate_id = clean_text(assessment.get("candidate_id", ""))
        candidate = candidate_map.get(candidate_id)
        if not candidate or candidate.get("url") in seen_urls:
            continue
        excerpt = compact_text(assessment.get("supporting_excerpt", ""), 500)
        page_content = extracted_pages.get(candidate.get("url", ""), "")
        accepted_by_review = (
            bool(assessment.get("use_as_evidence"))
            and bool(assessment.get("directly_supports_claim"))
            and bool(assessment.get("source_policy_satisfied"))
        )
        if not accepted_by_review or not excerpt or excerpt not in page_content:
            continue
        seen_urls.add(candidate["url"])
        accepted.append({
            "claim_to_verify": task["claim_to_verify"],
            "purpose": task["purpose"],
            "source_policy": task["source_policy"],
            "freshness_required": task["freshness_required"],
            "title": candidate.get("title", ""),
            "url": candidate["url"],
            "domain": candidate.get("domain", ""),
            "source_type": assessment.get("source_type", "unknown"),
            "supporting_excerpt": excerpt,
            "directly_supports_claim": True,
            "source_policy_satisfied": True,
            "selection_reason": clean_text(assessment.get("selection_reason", ""))[:300],
        })
        if len(accepted) >= MAX_EVIDENCE_PER_TASK:
            break
    return accepted


def search_router(state: AgentState) -> str:
    needs_search = bool(state.get("search_needed"))
    has_tasks = bool(normalize_search_tasks(state.get("search_tasks", []), max_tasks=MAX_SEARCH_TASKS))
    route = "search" if needs_search and has_tasks else "skip"
    print(f"🔀 Search Router: {route}")
    return route


def node_web_search(state: AgentState) -> AgentState:
    index = int(state.get("slide_index", 0))
    print(f"\n--- Node 3: 슬라이드 {index + 1} Web Search ---")
    state["search_results"] = []
    state["evidence"] = []
    tasks = normalize_search_tasks(state.get("search_tasks", []), max_tasks=MAX_SEARCH_TASKS)

    if not tasks:
        print("ℹ️ 실행할 안전한 검색 계획이 없습니다.")
        return state
    if not TAVILY_API_KEY:
        record_error(state, f"슬라이드 {index + 1} Tavily API 키가 없습니다.")
        return state

    all_results: List[Dict[str, Any]] = []
    all_evidence: List[Dict[str, Any]] = []
    try:
        tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
    except Exception as exc:
        record_error(state, f"슬라이드 {index + 1} Tavily 초기화 실패: {exc}")
        return state

    for task_number, task in enumerate(tasks, start=1):
        try:
            candidates = tavily_search_candidates(tavily_client, task)
            all_results.extend(candidates)
            extraction_targets = choose_extraction_candidates(candidates)
            extracted_pages = extract_candidate_pages(tavily_client, task, extraction_targets)
            accepted = review_candidate_evidence(task, extraction_targets, extracted_pages)
            all_evidence.extend(accepted)
            print(
                f"  Task {task_number}: 후보 {len(candidates)}건 → "
                f"원문 {len(extracted_pages)}건 → 근거 {len(accepted)}건"
            )
            time.sleep(0.2)
        except Exception as exc:
            record_error(
                state,
                f"슬라이드 {index + 1} 검색 Task 실패 "
                f"({task.get('claim_to_verify', '')}): {exc}",
            )

    deduplicated: Dict[str, Dict[str, Any]] = {}
    for result in all_results:
        url = result.get("url", "")
        if url and (
            url not in deduplicated
            or result.get("tavily_score", 0.0) > deduplicated[url].get("tavily_score", 0.0)
        ):
            deduplicated[url] = result

    state["search_results"] = sorted(
        deduplicated.values(), key=lambda item: item.get("tavily_score", 0.0), reverse=True
    )
    for evidence_number, item in enumerate(all_evidence, start=1):
        item["evidence_id"] = f"slide{index + 1}_evidence{evidence_number}"
    state["evidence"] = all_evidence
    print(
        f"✅ 검색 완료: 후보 {len(state['search_results'])}건, "
        f"Evidence {len(state['evidence'])}건"
    )
    return state
