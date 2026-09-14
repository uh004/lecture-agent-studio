"use client";

import { RotateCcw } from "lucide-react";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="centered-state">
      <div className="error-icon">!</div>
      <h1>화면을 불러오지 못했습니다</h1>
      <p>잠시 후 다시 시도해 주세요.</p>
      <button className="button button-primary button-small" onClick={reset}>
        <RotateCcw size={17} /> 다시 시도
      </button>
    </main>
  );
}
