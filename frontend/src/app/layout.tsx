import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "AI 강사 Agent",
  description: "PPT를 분석해 강의 영상을 자동으로 제작합니다.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
