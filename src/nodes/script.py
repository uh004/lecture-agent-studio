import os
import re

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from src.core.state import State
from src.core.config import LLM_MODEL
from src.core.utils import clean_text
from src.core.prompts import (
    BANNED_PHRASES, SCRIPT_SYSTEM_PROMPT, SCRIPT_HUMAN_TEMPLATE,
    extract_openers, count_word, limit_word
)


def node_generate_script(state: dict) -> dict:
    """v3: 반복 방지 + 금지 표현 확대 + 글자 수 검증"""
    print("\n--- Node 4: 강의 스크립트 생성(gen_script) v3 실행 ---")

    all_titles = state.get("titles", [])
    total_slides = len(all_titles)
    idx = int(state.get("slide_index", 0))
    current_title = all_titles[idx] if idx < len(all_titles) else f"슬라이드 {idx+1}"
    page_content = clean_text(state.get("page_content", ""))
    work_dir = state.get("work_dir", "./")

    prev_scripts = state.get("all_scripts", [])
    previous_script = prev_scripts[-1] if prev_scripts else "(첫 슬라이드이므로 없음)"

    if not page_content.strip():
        page_content = f"{current_title}의 핵심 개념을 설명해 주세요."

    prompt_data = state.get("prompt", {})
    if isinstance(prompt_data, str):
        final_tone, final_style, final_sec = prompt_data, "자연스럽고 설명적인 말투", 50
    else:
        final_tone = prompt_data.get("tone", "친절하고 명료한 톤")
        final_style = prompt_data.get("style", "자연스럽고 설명적인 말투")
        final_sec = prompt_data.get("target_duration_sec", 50)

    # 슬라이드 위치별 흐름 지시
    if idx == 0:
        flow_instruction = "전체 강의의 첫 슬라이드입니다. 자연스럽고 매끄럽게 주제로 바로 진입하세요."
    elif idx == total_slides - 1:
        flow_instruction = "마지막 슬라이드입니다. 핵심을 간결하게 정리하고 마무리하세요."
    else:
        flow_instruction = "중간 슬라이드입니다. 앞 내용과 자연스럽게 연결하되, 이전과 다른 연결어를 사용하세요."

    # v3: 이전 스크립트에서 시작 표현 추출 → 금지 목록에 추가
    prev_openers = extract_openers(prev_scripts)
    prev_openers_text = "\n".join([f"- {op}" for op in prev_openers[-3:]]) if prev_openers else "(없음)"

    # v3: 풍부한 프롬프트
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", SCRIPT_SYSTEM_PROMPT),
        ("human", SCRIPT_HUMAN_TEMPLATE)
    ])

    llm = ChatOpenAI(model=LLM_MODEL, temperature=0.3)
    output_parser = StrOutputParser()
    chain = prompt_template | llm | output_parser

    min_chars = int(final_sec * 9)
    max_chars = int(final_sec * 13)

    raw_script = chain.invoke({
        "all_titles": all_titles, "idx": idx, "current_title": current_title,
        "previous_script": previous_script[:300], "page_content": page_content,
        "tone": final_tone, "style": final_style, "target_sec": final_sec,
        "flow_instruction": flow_instruction, "prev_openers_text": prev_openers_text,
        "min_chars": min_chars, "max_chars": max_chars,
    })

    # 태그 제거 + 금지 표현 제거
    script = raw_script.replace("[스크립트 시작]", "").replace("[스크립트 종료]", "").strip()
    for phrase in BANNED_PHRASES:
        script = script.replace(phrase, "")

    # v3: "여러분" 횟수 제한 (최대 1회)
    script = limit_word(script, "여러분", max_count=1)

    # 연속 공백 정리
    script = re.sub(r"\s+", " ", script).strip()

    # v3: 글자 수 검증
    script_len = len(script)
    if script_len < min_chars:
        print(f"  ⚠️ 스크립트가 너무 짧습니다 ({script_len}자 < {min_chars}자)")
    elif script_len > max_chars:
        print(f"  ⚠️ 스크립트가 너무 깁니다 ({script_len}자 > {max_chars}자)")

    # state 저장
    state["script"] = script
    if "all_scripts" not in state:
        state["all_scripts"] = []
    state["all_scripts"].append(script)

    os.makedirs(work_dir, exist_ok=True)
    out_path = os.path.join(work_dir, f"script_{idx}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(script)

    print(f"  ✅ 스크립트 생성 완료: {out_path} ({script_len}자, '여러분' {count_word(script, '여러분')}회)")
    return state
