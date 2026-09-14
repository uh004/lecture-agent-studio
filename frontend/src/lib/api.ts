import type { CreateLectureInput, GenerateResponse, JobStatus } from "@/lib/types";

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

async function readError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as {
      detail?: string | Array<{ msg?: string }>;
      message?: string;
    };
    if (typeof payload.detail === "string") return payload.detail;
    if (Array.isArray(payload.detail)) {
      return payload.detail.map((item) => item.msg).filter(Boolean).join(", ");
    }
    return payload.message ?? "요청을 처리하지 못했습니다.";
  } catch {
    return "서버 응답을 확인하지 못했습니다.";
  }
}

export async function createLecture(input: CreateLectureInput): Promise<GenerateResponse> {
  const formData = new FormData();
  formData.append("file", input.file);
  formData.append("tone", input.tone);
  formData.append("style", input.style);
  formData.append("voice", input.voice);
  formData.append("speed", String(input.speed));
  formData.append("target_duration_sec", String(input.targetDurationSec));

  const response = await fetch(`${API_BASE_URL}/api/generate`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json() as Promise<GenerateResponse>;
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const response = await fetch(`${API_BASE_URL}/api/status/${encodeURIComponent(jobId)}`, {
    cache: "no-store",
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json() as Promise<JobStatus>;
}

export function getVideoUrl(jobId: string): string {
  return `${API_BASE_URL}/api/video/${encodeURIComponent(jobId)}`;
}
