import { Check, Download, Film, Presentation, RotateCcw, ShieldCheck, Timer } from "lucide-react";
import Link from "next/link";

import { getVideoUrl } from "@/lib/api";
import type { JobStatus } from "@/lib/types";

function formatDuration(seconds = 0): string {
  const rounded = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(rounded / 60);
  const rest = rounded % 60;
  return minutes > 0 ? `${minutes}분 ${rest}초` : `${rest}초`;
}

export function VideoResult({ job, jobId }: { job: JobStatus; jobId: string }) {
  const videoUrl = getVideoUrl(jobId);
  const qa = job.final_qa ?? {};
  const isPartial = job.final_status === "partial_completed";

  return (
    <>
      <section className="result-heading">
        <span className="success-mark"><Check size={28} /></span>
        <div>
          <span className="eyebrow">LECTURE COMPLETE</span>
          <h1>강의 영상이 완성되었습니다</h1>
          <p>{isPartial ? "일부 슬라이드를 제외하고 영상을 완성했습니다." : "모든 슬라이드의 영상 생성을 완료했습니다."}</p>
        </div>
      </section>

      <div className="step-strip compact-steps" aria-label="강의 생성 단계">
        <div className="step-item is-done"><span><Check size={16} /></span><strong>PPT 업로드</strong></div>
        <div className="step-line is-done" />
        <div className="step-item is-done"><span><Check size={16} /></span><strong>강의 생성</strong></div>
        <div className="step-line is-done" />
        <div className="step-item is-active"><span>3</span><strong>영상 확인</strong></div>
      </div>

      <section className="result-grid">
        <div className="video-card">
          <video controls playsInline preload="metadata" src={videoUrl}>
            브라우저가 영상 재생을 지원하지 않습니다.
          </video>
          <div className="video-actions">
            <div>
              <span className={`result-badge${isPartial ? " is-warning" : ""}`}>
                <ShieldCheck size={17} /> {isPartial ? "부분 완료" : "검증 완료"}
              </span>
              <p>완성된 강의 영상을 확인해 보세요.</p>
            </div>
            <a className="button button-primary button-small" download href={videoUrl}>
              <Download size={18} /> MP4 다운로드
            </a>
          </div>
        </div>

        <aside className="result-summary">
          <h2>생성 결과</h2>
          <div className="summary-item">
            <span><Presentation size={20} /></span>
            <div><small>전체 슬라이드</small><strong>{qa.expected_slides ?? job.total_slides}장</strong></div>
          </div>
          <div className="summary-item">
            <span><Timer size={20} /></span>
            <div><small>영상 길이</small><strong>{formatDuration(qa.duration)}</strong></div>
          </div>
          <div className="summary-item">
            <span><Film size={20} /></span>
            <div><small>생성된 슬라이드</small><strong>{qa.generated_clips ?? job.total_slides}장</strong></div>
          </div>
          <Link className="button button-secondary new-lecture-button" href="/">
            <RotateCcw size={18} /> 새 강의 만들기
          </Link>
        </aside>
      </section>
    </>
  );
}
