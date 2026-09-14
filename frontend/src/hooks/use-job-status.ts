"use client";

import { useCallback, useEffect, useState } from "react";

import { getJobStatus } from "@/lib/api";
import type { JobStatus } from "@/lib/types";

const POLL_INTERVAL_MS = 1500;

export function useJobStatus(jobId: string) {
  const [job, setJob] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const retry = useCallback(() => {
    setError(null);
    setRefreshKey((value) => value + 1);
  }, []);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const nextJob = await getJobStatus(jobId);
        if (!active) return;
        setJob(nextJob);
        setError(null);

        if (nextJob.status === "pending" || nextJob.status === "running") {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch (caught) {
        if (!active) return;
        setError(caught instanceof Error ? caught.message : "작업 상태를 불러오지 못했습니다.");
      }
    };

    void poll();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [jobId, refreshKey]);

  return { job, error, retry };
}
