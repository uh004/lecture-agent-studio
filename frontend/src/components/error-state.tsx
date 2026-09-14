import { AlertCircle, Home, RotateCcw } from "lucide-react";
import Link from "next/link";

type ErrorStateProps = {
  title?: string;
  message: string;
  onRetry?: () => void;
};

export function ErrorState({ title = "작업을 확인하지 못했습니다", message, onRetry }: ErrorStateProps) {
  return (
    <section className="job-error-card">
      <span className="job-error-icon"><AlertCircle size={28} /></span>
      <h1>{title}</h1>
      <p>{message}</p>
      <div className="error-actions">
        {onRetry && (
          <button className="button button-primary button-small" onClick={onRetry} type="button">
            <RotateCcw size={17} /> 다시 확인
          </button>
        )}
        <Link className="button button-secondary button-small" href="/">
          <Home size={17} /> 처음으로
        </Link>
      </div>
    </section>
  );
}
