export type JobLifecycleStatus = "pending" | "running" | "completed" | "error";

export interface LectureSettings {
  tone: string;
  style: string;
  voice: string;
  speed: number;
  targetDurationSec: number;
}

export interface CreateLectureInput extends LectureSettings {
  file: File;
}

export interface GenerateResponse {
  job_id: string;
  message: string;
}

export interface FinalQa {
  passed?: boolean;
  duration?: number;
  expected_slides?: number;
  generated_clips?: number;
  missing_slide_numbers?: number[];
  failed_slides?: number[];
  errors?: string[];
}

export interface JobStatus {
  status: JobLifecycleStatus;
  current_node: string;
  current_slide: number;
  total_slides: number;
  final_status?: "running" | "completed" | "partial_completed" | "failed";
  final_qa?: FinalQa;
  errors?: string[];
  error_message?: string | null;
  video_url?: string | null;
}
