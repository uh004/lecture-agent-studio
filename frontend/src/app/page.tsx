import { AppHeader } from "@/components/app-header";
import { LectureForm } from "@/components/lecture-form";

export default function HomePage() {
  return (
    <div className="site-shell">
      <AppHeader />
      <main className="page-container">
        <section className="hero-section">
          <span className="eyebrow">AI LECTURE STUDIO</span>
          <h1>PPT 한 파일로<br />강의 영상을 만들어보세요</h1>
          <p>슬라이드를 분석하고 스크립트, 음성, 영상을 순서대로 생성합니다.</p>
        </section>

        <div className="step-strip" aria-label="강의 생성 단계">
          <div className="step-item is-active"><span>1</span><strong>PPT 업로드</strong></div>
          <div className="step-line" />
          <div className="step-item"><span>2</span><strong>강의 생성</strong></div>
          <div className="step-line" />
          <div className="step-item"><span>3</span><strong>영상 확인</strong></div>
        </div>

        <LectureForm />
      </main>
    </div>
  );
}
