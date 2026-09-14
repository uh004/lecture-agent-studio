import { Check, LoaderCircle, Presentation, Sparkles } from "lucide-react";

import { getNodeLabel, getProgress } from "@/lib/node-labels";
import type { JobStatus } from "@/lib/types";

export function JobProgress({ job }: { job: JobStatus }) {
  const progress = getProgress(job);
  const slideText = job.total_slides > 0
    ? `${Math.min(job.current_slide, job.total_slides)} / ${job.total_slides} 슬라이드`
    : "슬라이드를 확인하고 있습니다";

  return (
    <>
      <section className="job-hero">
        <span className="status-orb"><Sparkles size={27} /></span>
        <span className="eyebrow">LECTURE IN PROGRESS</span>
        <h1>강의 영상을 만들고 있습니다</h1>
        <p>브라우저를 닫지 않고 잠시만 기다려 주세요.</p>
      </section>

      <div className="step-strip compact-steps" aria-label="강의 생성 단계">
        <div className="step-item is-done"><span><Check size={16} /></span><strong>PPT 업로드</strong></div>
        <div className="step-line is-done" />
        <div className="step-item is-active"><span>2</span><strong>강의 생성</strong></div>
        <div className="step-line" />
        <div className="step-item"><span>3</span><strong>영상 확인</strong></div>
      </div>

      <section className="progress-card">
        <div className="progress-topline">
          <div className="progress-title">
            <span className="progress-icon"><LoaderCircle className="spin" size={25} /></span>
            <div>
              <span>현재 작업</span>
              <h2>{getNodeLabel(job.current_node)}</h2>
            </div>
          </div>
          <strong className="progress-percent">{progress}%</strong>
        </div>

        <div
          aria-label={`전체 진행률 ${progress}%`}
          aria-valuemax={100}
          aria-valuemin={0}
          aria-valuenow={progress}
          className="progress-track"
          role="progressbar"
        >
          <span style={{ width: `${progress}%` }} />
        </div>

        <div className="progress-details">
          <span><Presentation size={18} /> {slideText}</span>
          <span>슬라이드마다 분석과 검증을 진행합니다.</span>
        </div>
      </section>
    </>
  );
}
