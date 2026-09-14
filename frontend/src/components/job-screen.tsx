"use client";

import { ErrorState } from "@/components/error-state";
import { JobProgress } from "@/components/job-progress";
import { VideoResult } from "@/components/video-result";
import { useJobStatus } from "@/hooks/use-job-status";

export function JobScreen({ jobId }: { jobId: string }) {
  const { job, error, retry } = useJobStatus(jobId);

  if (error) return <ErrorState message={error} onRetry={retry} />;
  if (!job) {
    return (
      <section className="job-loading-card">
        <div className="spinner" />
        <h1>작업 정보를 불러오고 있습니다</h1>
      </section>
    );
  }
  if (job.status === "error") {
    return (
      <ErrorState
        title="강의 생성이 중단되었습니다"
        message={job.error_message ?? "오류 내용을 확인한 뒤 다시 시도해 주세요."}
      />
    );
  }
  if (job.status === "completed") return <VideoResult job={job} jobId={jobId} />;
  return <JobProgress job={job} />;
}
