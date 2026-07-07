import re
import time
from difflib import SequenceMatcher

from src.core.state import State
from src.core.utils import tavily_search


def node_tool_search(state: State) -> State:
    """외부 검색 노드 (v3: 다중 쿼리 + 교차 검증 필터링)"""
    print("\n--- Node 2: 외부 검색(tool_search) 실행 ---")

    state["external_content"] = {"queries": [], "summaries": [], "references": []}

    idx = state.get("slide_index", 0)
    titles = state.get("titles", [])
    texts_all = state.get("texts", [])
    tables_all = state.get("tables", [])
    images_all = state.get("images", [])

    title = titles[idx] if idx < len(titles) else ""
    texts = texts_all[idx] if idx < len(texts_all) else ""
    tables = tables_all[idx] if idx < len(tables_all) else []
    images = images_all[idx] if idx < len(images_all) else []

    print(f"  슬라이드 {idx+1} | 제목: {title}")

    # 질의 생성 (v3: 다중 쿼리)
    queries = []
    if title:
        queries.append({"text": title, "context": "title"})
    if title and texts:
        queries.append({"text": f"{title} {texts[:80]}", "context": "title+text"})
    if title and tables and tables[0] and tables[0][0]:
        head = " ".join(map(str, tables[0][0][:5]))
        queries.append({"text": f"{title} {head}", "context": "title+table"})
    if not queries and texts:
        queries.append({"text": texts[:100], "context": "text_only"})

    print(f"  생성된 쿼리 {len(queries)}개")

    # 검색 수행
    all_results = []
    for q in queries:
        results = tavily_search(q["text"], num=4)
        all_results.extend(results)
        time.sleep(0.2)

    # 일관성/신뢰도 필터 (v3: 교차 검증)
    def norm(s):
        return re.sub(r"\s+", " ", (s or "").lower().strip())

    def similar(a, b, thr=0.82):
        return bool(a and b) and SequenceMatcher(None, norm(a), norm(b)).ratio() >= thr

    groups = []
    for r in all_results:
        snip, dom = r.get("snippet", ""), r.get("domain", "")
        if not snip:
            continue
        placed = False
        for g in groups:
            if similar(snip, g["rep"]):
                g["items"].append(r)
                if dom:
                    g["domains"].add(dom)
                placed = True
                break
        if not placed:
            groups.append({"rep": snip, "items": [r], "domains": set([dom] if dom else [])})

    picked = [g for g in groups if len(g["items"]) >= 2 and len(g["domains"]) >= 2]

    if not picked:
        summaries = [{"text": r["snippet"], "source": r["title"], "score": r.get("score", 0.0)} for r in all_results if r.get("snippet")]
        references = [{"title": r["title"], "url": r["url"], "score": r.get("score", 0.0)} for r in all_results]
    else:
        summaries, references, seen_dom = [], [], set()
        picked.sort(key=lambda g: max((it.get("score", 0.0) for it in g["items"]), default=0.0), reverse=True)
        for g in picked:
            top = max(g["items"], key=lambda it: it.get("score", 0.0))
            summaries.append({"text": top.get("snippet", ""), "source": top.get("title", ""), "score": top.get("score", 0.0)})
            dom_pick = {}
            for item in g["items"]:
                d = item.get("domain")
                if d and d not in dom_pick:
                    dom_pick[d] = {"title": item.get("title", ""), "url": item.get("url", ""), "score": item.get("score", 0.0)}
            for d, ref in dom_pick.items():
                if d not in seen_dom:
                    seen_dom.add(d)
                    references.append(ref)

    summaries.sort(key=lambda s: s.get("score", 0.0), reverse=True)
    references.sort(key=lambda r: r.get("score", 0.0), reverse=True)

    state["external_content"] = {"queries": queries, "summaries": summaries, "references": references}
    print(f"  ✅ 검색 완료: 요약 {len(summaries)}건, 참조 {len(references)}건")
    return state
