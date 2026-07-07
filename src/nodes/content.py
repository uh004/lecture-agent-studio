import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.core.state import State
from src.core.config import LLM_MODEL
from src.core.utils import clean_text, split_sents, img_to_data_url, build_external_block_for_prompt
from src.core.prompts import CONTENT_SYSTEM_PROMPT


def node_generate_page_content(state: State) -> State:
    """v3: 슬라이드 데이터 + 외부 자료 + 이미지 → LLM 요약 노트 (멀티모달)"""
    print("\n--- Node 3: 요약 노트 생성(gen_page_content) 실행 ---")

    idx = int(state.get("slide_index", 0))
    title = clean_text(str(state.get("titles", [])[idx])) if idx < len(state.get("titles", [])) else ""
    texts = clean_text(str(state.get("texts", [])[idx])) if idx < len(state.get("texts", [])) else ""
    shape_texts = state.get("shape_texts", [])[idx] if idx < len(state.get("shape_texts", [])) else []
    tables = state.get("tables", [])[idx] if idx < len(state.get("tables", [])) else []
    images = state.get("images", [])[idx] if idx < len(state.get("images", [])) else []
    slide_image_all = state.get("slide_image", [])
    snapshot_path = slide_image_all[idx] if idx < len(slide_image_all) else ""

    # v3: 발표자 노트
    notes_all = state.get("notes", [])
    slide_note = notes_all[idx] if idx < len(notes_all) else ""

    # 표 텍스트 변환
    table_text = ""
    if tables and isinstance(tables, list) and len(tables) > 0:
        first_table = tables[0][:6] if isinstance(tables[0], list) else []
        table_text = "\n".join([" | ".join(map(str, row)) for row in first_table])

    # 이미지 base64 변환 (멀티모달)
    image_data_urls = []
    if snapshot_path and os.path.exists(snapshot_path):
        try:
            image_data_urls.append(img_to_data_url(snapshot_path))
        except:
            pass
    for img_path in images[:2]:
        if os.path.exists(img_path):
            try:
                image_data_urls.append(img_to_data_url(img_path))
            except:
                pass

    # 외부 검색 결과 블록 생성
    ext = state.get("external_content", {}) or {}
    ext_summary_block = build_external_block_for_prompt(ext)
    ext_ref_block = ""
    if ext.get("references"):
        refs_sorted = sorted(ext["references"], key=lambda r: r.get("score", 0.0), reverse=True)
        ext_ref_block = "\n".join([f"[{i+1}] {clean_text(r.get('title', ''))[:100]} — {r.get('url', '')}" for i, r in enumerate(refs_sorted[:4])])

    # v3: 발표자 노트 섹션 추가
    notes_section = f"\n[발표자 노트]\n{slide_note}" if slide_note else ""

    user_data = f"""제목: {title}
[텍스트]
{texts}
[도형 텍스트]
{shape_texts}
[표]
{table_text}{notes_section}

[외부 보완 자료]
- 핵심 요약: {ext_summary_block if ext_summary_block else '(요약 없음)'}
- 참조 출처: {ext_ref_block if ext_ref_block else '(참고 URL 없음)'}"""

    content_list = [{"type": "text", "text": user_data}]
    for img_url in image_data_urls:
        content_list.append({"type": "image_url", "image_url": {"url": img_url, "detail": "low"}})

    messages = [SystemMessage(content=CONTENT_SYSTEM_PROMPT), HumanMessage(content=content_list)]
    print(f"  [LLM 요청] 모델: {LLM_MODEL}, 이미지: {len(image_data_urls)}장")

    llm = ChatOpenAI(model=LLM_MODEL, temperature=0.1)
    response = llm.invoke(messages)
    page_content = clean_text(response.content)
    state["page_content"] = " ".join(split_sents(page_content))

    print(f"  ✅ 요약 노트 생성 완료 ({len(state['page_content'])}자)")
    return state
