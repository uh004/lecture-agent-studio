"use client";

import { FileCheck2, UploadCloud, X } from "lucide-react";
import { useRef, useState } from "react";

type UploadDropzoneProps = {
  file: File | null;
  disabled?: boolean;
  onFileChange: (file: File | null) => void;
  onError: (message: string | null) => void;
};

const MAX_FILE_SIZE = 100 * 1024 * 1024;

function formatFileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

export function UploadDropzone({
  file,
  disabled = false,
  onFileChange,
  onError,
}: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const acceptFile = (nextFile?: File) => {
    if (!nextFile) return;
    if (!nextFile.name.toLowerCase().endsWith(".pptx")) {
      onError(".pptx 파일만 업로드할 수 있습니다.");
      return;
    }
    if (nextFile.size > MAX_FILE_SIZE) {
      onError("파일 크기는 100MB 이하여야 합니다.");
      return;
    }
    onError(null);
    onFileChange(nextFile);
  };

  if (file) {
    return (
      <div className="selected-file">
        <span className="selected-file-icon"><FileCheck2 size={25} /></span>
        <div>
          <strong>{file.name}</strong>
          <span>{formatFileSize(file.size)} · 업로드 준비 완료</span>
        </div>
        <button
          aria-label="선택한 파일 제거"
          className="icon-button"
          disabled={disabled}
          onClick={() => onFileChange(null)}
          type="button"
        >
          <X size={19} />
        </button>
      </div>
    );
  }

  return (
    <div
      className={`upload-dropzone${isDragging ? " is-dragging" : ""}`}
      onClick={() => !disabled && inputRef.current?.click()}
      onDragEnter={(event) => {
        event.preventDefault();
        if (!disabled) setIsDragging(true);
      }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => {
        event.preventDefault();
        setIsDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        setIsDragging(false);
        if (!disabled) acceptFile(event.dataTransfer.files[0]);
      }}
      role="button"
      tabIndex={disabled ? -1 : 0}
      onKeyDown={(event) => {
        if ((event.key === "Enter" || event.key === " ") && !disabled) inputRef.current?.click();
      }}
    >
      <input
        ref={inputRef}
        accept=".pptx,application/vnd.openxmlformats-officedocument.presentationml.presentation"
        disabled={disabled}
        hidden
        onChange={(event) => acceptFile(event.target.files?.[0])}
        type="file"
      />
      <span className="upload-icon"><UploadCloud size={31} /></span>
      <strong>PPTX 파일을 끌어놓거나 선택하세요</strong>
      <p>최대 100MB까지 업로드할 수 있습니다.</p>
      <button className="button button-secondary button-small" disabled={disabled} type="button">
        파일 선택
      </button>
    </div>
  );
}
