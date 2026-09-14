import type { JobStatus } from "@/lib/types";

const NODE_LABELS: Record<string, string> = {
  init: "작업 준비",
  download_source: "PPT 원본 내려받기",
  parse_ppt: "PPT 내용 분석",
  analyze_slide: "슬라이드 이해",
  web_search: "필요한 외부 정보 검색",
  generate_script: "강의 스크립트 작성",
  validate_script: "스크립트 검증",
  accept_script: "검증 결과 반영",
  mark_validation_failed: "검증 결과 정리",
  tts: "강의 음성 생성",
  make_video: "슬라이드 영상 생성",
  accumulate: "슬라이드 작업 완료",
  concat: "최종 영상 합성",
  final_quality_check: "최종 영상 확인",
};

const STEP_FRACTIONS: Record<string, number> = {
  analyze_slide: 0.08,
  web_search: 0.2,
  generate_script: 0.38,
  validate_script: 0.55,
  accept_script: 0.62,
  mark_validation_failed: 0.62,
  tts: 0.72,
  make_video: 0.9,
  accumulate: 1,
};

export function getNodeLabel(node: string): string {
  return NODE_LABELS[node] ?? "강의 생성 작업";
}

export function getProgress(job: JobStatus): number {
  if (job.status === "completed") return 100;
  if (job.status === "error") return Math.max(3, getRunningProgress(job));
  return getRunningProgress(job);
}

function getRunningProgress(job: JobStatus): number {
  if (job.current_node === "init") return 2;
  if (job.current_node === "download_source") return 3;
  if (job.current_node === "parse_ppt") return 5;
  if (job.current_node === "concat") return 96;
  if (job.current_node === "final_quality_check") return 99;

  const total = Math.max(1, job.total_slides);
  const current = Math.min(total, Math.max(1, job.current_slide || 1));
  const completedSlides = Math.max(0, current - 1);
  const stage = STEP_FRACTIONS[job.current_node] ?? 0;
  return Math.min(95, Math.round(5 + ((completedSlides + stage) / total) * 90));
}
