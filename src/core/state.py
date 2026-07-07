from typing import TypedDict, List, Dict, Any

class State(TypedDict, total=False):
    """
    LangGraph 전체 상태 스키마 (v3 노트북과 동일)
    total=False: 모든 필드가 선택적(Optional)
    """
    # 입력/기본
    pptx_path: str
    work_dir: str
    prompt: Dict
    slide_index: int
    total_slides: int

    # 추출 산출물
    titles: List[str]
    texts: List[str]
    notes: List[str]              # v3 추가: 발표자 노트
    tables: List[List[List[str]]]
    images: List[str]
    slide_image: List[str]
    external_content: Dict[str, List[Dict[str, str]]]
    shape_texts: List[List[str]]
    links: List[List[str]]

    # 생성 산출물
    page_content: str
    script: str
    all_scripts: List[str]
    used_expressions: List[str]   # v3 추가: 반복 방지용

    # 미디어 산출물
    audio: str
    video_path: str
    video_paths: List[str]
    final_video: str
    failed_slides: List[int]
