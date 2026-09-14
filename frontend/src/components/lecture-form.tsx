"use client";

import { ChevronDown, Clock3, Gauge, Mic2, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { UploadDropzone } from "@/components/upload-dropzone";
import { createLecture } from "@/lib/api";

const DEFAULT_TONE = "친절하고 명료한 강사 톤";
const DEFAULT_STYLE = "핵심을 쉬운 표현으로 자연스럽게 설명";

export function LectureForm() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [voice, setVoice] = useState("친절한 튜토리얼");
  const [speed, setSpeed] = useState(1.15);
  const [targetDurationSec, setTargetDurationSec] = useState(70);
  const [tone, setTone] = useState(DEFAULT_TONE);
  const [style, setStyle] = useState(DEFAULT_STYLE);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file) {
      setError("먼저 PPTX 파일을 선택해 주세요.");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const response = await createLecture({
        file,
        tone,
        style,
        voice,
        speed,
        targetDurationSec,
      });
      router.push(`/jobs/${response.job_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "강의 생성을 시작하지 못했습니다.");
      setIsSubmitting(false);
    }
  };

  return (
    <form className="creation-card" onSubmit={handleSubmit}>
      <section className="form-section upload-section">
        <div className="section-heading">
          <span className="section-icon"><UploadCloudIcon /></span>
          <div>
            <h2>PPT 파일 업로드</h2>
            <p>강의로 만들 한 개의 PPTX 파일을 선택해 주세요.</p>
          </div>
        </div>
        <UploadDropzone
          disabled={isSubmitting}
          file={file}
          onError={setError}
          onFileChange={setFile}
        />
      </section>

      <section className="form-section settings-section">
        <div className="section-heading">
          <span className="section-icon"><Sparkles size={21} /></span>
          <div>
            <h2>강의 설정</h2>
            <p>원하는 길이와 음성을 선택하세요.</p>
          </div>
        </div>

        <div className="field-grid">
          <label className="form-field">
            <span><Clock3 size={17} /> 슬라이드당 설명 길이</span>
            <select
              disabled={isSubmitting}
              onChange={(event) => setTargetDurationSec(Number(event.target.value))}
              value={targetDurationSec}
            >
              <option value={40}>약 40초 · 간결하게</option>
              <option value={70}>약 70초 · 기본</option>
              <option value={100}>약 100초 · 자세하게</option>
            </select>
          </label>

          <label className="form-field">
            <span><Mic2 size={17} /> 음성</span>
            <select disabled={isSubmitting} onChange={(event) => setVoice(event.target.value)} value={voice}>
              <option>친절한 튜토리얼</option>
              <option>부드러운 설명형</option>
              <option>교수님 톤</option>
              <option>명확한 설명형</option>
            </select>
          </label>

          <label className="form-field field-full">
            <span><Gauge size={17} /> 말하기 속도</span>
            <div className="speed-options">
              {[0.9, 1, 1.15, 1.3].map((value) => (
                <button
                  className={speed === value ? "is-selected" : ""}
                  disabled={isSubmitting}
                  key={value}
                  onClick={() => setSpeed(value)}
                  type="button"
                >
                  {value === 1 ? "보통" : `${value}x`}
                </button>
              ))}
            </div>
          </label>
        </div>

        <button
          aria-expanded={showAdvanced}
          className="advanced-toggle"
          disabled={isSubmitting}
          onClick={() => setShowAdvanced((value) => !value)}
          type="button"
        >
          추가 설정
          <ChevronDown className={showAdvanced ? "is-open" : ""} size={18} />
        </button>

        {showAdvanced && (
          <div className="advanced-fields">
            <label className="form-field">
              <span>강의 말투</span>
              <input disabled={isSubmitting} maxLength={200} onChange={(event) => setTone(event.target.value)} value={tone} />
            </label>
            <label className="form-field">
              <span>설명 방식</span>
              <input disabled={isSubmitting} maxLength={300} onChange={(event) => setStyle(event.target.value)} value={style} />
            </label>
          </div>
        )}
      </section>

      {error && <p className="form-error" role="alert">{error}</p>}

      <button className="button button-primary submit-button" disabled={isSubmitting} type="submit">
        {isSubmitting ? <span className="button-spinner" /> : <Sparkles size={20} />}
        {isSubmitting ? "업로드하는 중..." : "강의 영상 만들기"}
      </button>
    </form>
  );
}

function UploadCloudIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="22" viewBox="0 0 24 24" width="22">
      <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
    </svg>
  );
}
