import os
import re
import subprocess
import base64
import mimetypes
import platform
from pathlib import Path
from typing import List
from difflib import SequenceMatcher
from urllib.parse import urlparse

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER
from langchain_community.tools.tavily_search import TavilySearchResults

from src.core.config import FFPROBE_CMD


# ============================================================
# 텍스트 유틸리티
# ============================================================

def clean_text(s):
    """공백/줄바꿈 정리"""
    return re.sub(r"\s+", " ", s).strip()


def split_sents(t: str) -> List[str]:
    """문장 단위 분리"""
    parts = re.split(r'([.?!])', t)
    merged = []
    for i in range(0, len(parts) - 1, 2):
        sent = (parts[i] + parts[i + 1]).strip()
        if sent:
            merged.append(sent)
    if len(parts) % 2 == 1 and parts[-1].strip():
        merged.append(parts[-1].strip())
    return [s for s in merged if s]


# ============================================================
# FFprobe 유틸리티
# ============================================================

def ffprobe_duration(path: str) -> float:
    """오디오/비디오 파일의 재생 시간(초) 반환"""
    out = subprocess.check_output([
        FFPROBE_CMD, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path
    ]).decode().strip()
    return float(out)


# ============================================================
# 이미지 유틸리티
# ============================================================

def img_to_data_url(path: str) -> str:
    """이미지를 base64 data URL로 변환"""
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def export_slide_as_png(state: dict, dpi: int = 220) -> dict:
    """PPT 슬라이드 1장을 PNG 이미지로 변환 (LibreOffice + pdftoppm)"""
    work_dir = Path(state["work_dir"]).expanduser().resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    pptx_path = Path(state["pptx_path"]).expanduser().resolve()
    if not pptx_path.exists():
        raise FileNotFoundError(f"PPTX 없음: {pptx_path}")
    idx = int(state.get("slide_index", 0))
    page_no = idx + 1
    out_prefix = work_dir / "slide_img"
    png_path = work_dir / f"{out_prefix.stem}-{page_no}.png"
    env = os.environ.copy()
    env.update({"LANG": "ko_KR.UTF-8", "LC_ALL": "ko_KR.UTF-8"})
    soffice_cmd = "soffice"
    if platform.system() == "Windows":
        if os.path.exists(r"C:\Program Files\LibreOffice\program\soffice.exe"):
            soffice_cmd = r"C:\Program Files\LibreOffice\program\soffice.exe"
    pdf_path = work_dir / f"{pptx_path.stem}.pdf"
    if not pdf_path.exists():
        lo_cmd = [soffice_cmd, "--headless", "--convert-to", "pdf:impress_pdf_Export", "--outdir", str(work_dir), str(pptx_path)]
        if platform.system() != "Windows":
            lo_cmd.insert(2, "-env:UserInstallation=file:///tmp/lo_profile")
        res_pdf = subprocess.run(lo_cmd, capture_output=True, text=True, env=env)
        if res_pdf.returncode != 0:
            raise RuntimeError("PPTX → PDF 변환 실패")
    ppm_cmd = ["pdftoppm", "-f", str(page_no), "-l", str(page_no), "-png", "-r", str(dpi), str(pdf_path), str(out_prefix)]
    subprocess.run(ppm_cmd, capture_output=True, text=True, env=env)
    if png_path.exists():
        state["slide_image"] = str(png_path)
    else:
        print(f"⚠️ 슬라이드 {page_no} PNG 변환 실패")
        state["slide_image"] = ""
    return state


# ============================================================
# 검색 점수 계산 함수 (v3: 도메인 신뢰도, 유사도, 콘텐츠 점수)
# ============================================================

DOMAIN_TRUST = {
    "microsoft.com": 0.95, "learn.microsoft.com": 0.98,
    "docs.python.org": 0.98, "wikipedia.org": 0.9,
    "mozilla.org": 0.9, "naver.com": 0.8,
    "cloud.naver.com": 0.9, "kakao.com": 0.8,
}

EXCLUDE_DOMAINS = [
    "blog.naver.com", "m.blog.naver.com", "tistory.com",
    "brunch.co.kr", "medium.com", "velog.io",
    "kin.naver.com", "reddit.com", "youtube.com"
]


def _norm_text(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^가-힣a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def similarity_score(query: str, snippet: str) -> float:
    q, t = _norm_text(query), _norm_text(snippet)
    if not q or not t:
        return 0.0
    q_tokens, t_tokens = set(q.split()), set(t.split())
    overlap = len(q_tokens & t_tokens) / len(q_tokens) if q_tokens and t_tokens else 0.0
    seq_sim = SequenceMatcher(None, q, t).ratio()
    return (overlap + seq_sim) / 2.0


def domain_score(domain: str) -> float:
    domain = (domain or "").lower()
    for key, score in DOMAIN_TRUST.items():
        if key in domain:
            return score
    if not domain:
        return 0.4
    return max(0.45, min(0.5 + min(len(domain) / 50.0, 0.15), 0.65))


def content_score(snippet: str, max_len: int = 400) -> float:
    if not snippet:
        return 0.0
    return max(0.1, min(len(snippet) / max_len, 1.0))


def tavily_search(title: str, num: int = 4) -> list:
    """Tavily 검색 (v3: 점수 기반 필터링, 제외 도메인 적용)"""
    query = f"{title} " + " ".join([f"-site:{d}" for d in EXCLUDE_DOMAINS])
    candidate_k = max(num * 3, num + 2)
    res_tool = TavilySearchResults(
        max_results=candidate_k, search_depth="basic", topic="general",
        exclude_domains=EXCLUDE_DOMAINS, include_answer=False, include_raw_content=False,
    )
    data = res_tool.invoke(query) or []
    results, seen_urls = [], set()
    for item in data:
        url = item.get("url", "")
        if not url or url in seen_urls:
            continue
        domain = urlparse(url).netloc
        if any(ex in domain for ex in EXCLUDE_DOMAINS):
            continue
        seen_urls.add(url)
        snippet_res = item.get("content", "") or ""
        s_sim = similarity_score(title, snippet_res)
        s_dom = domain_score(domain)
        s_cont = content_score(snippet_res)
        score = 0.5 * s_sim + 0.3 * s_dom + 0.2 * s_cont
        results.append({
            "title": item.get("title", ""), "url": url,
            "snippet": snippet_res, "domain": domain,
            "score": round(score, 4),
        })
    results_sorted = sorted(results, key=lambda x: x["score"], reverse=True)
    return results_sorted[:num]


# ============================================================
# 텍스트 청킹 (node_generate_page_content에서 사용)
# ============================================================

def split_text_to_chunks(text: str, max_len: int = 220) -> list:
    text = (text or "").strip()
    if not text:
        return []
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, buf = [], ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if len(buf) + len(s) + 1 > max_len:
            if buf:
                chunks.append(buf.strip())
            buf = s
        else:
            buf = (buf + " " + s).strip() if buf else s
    if buf:
        chunks.append(buf.strip())
    return chunks


def build_external_block_for_prompt(ext, max_sources=3, max_chunks_per_source=2, max_total_chars=1500, chunk_len=220):
    """외부 검색 결과를 프롬프트용 텍스트 블록으로 변환"""
    summaries = sorted(ext.get("summaries", []) or [], key=lambda s: s.get("score", 0.0), reverse=True)
    lines, total_len = [], 0
    for s in summaries[:max_sources]:
        source = clean_text(str(s.get("source", "")))
        text = clean_text(str(s.get("text", "")))
        if not text:
            continue
        chunks = split_text_to_chunks(text, max_len=chunk_len)
        for ch in chunks[:max_chunks_per_source]:
            line = f"[{source}] {ch}"
            if total_len + len(line) + 1 > max_total_chars:
                return "\n".join(lines)
            lines.append(line)
            total_len += len(line) + 1
    return "\n".join(lines)
