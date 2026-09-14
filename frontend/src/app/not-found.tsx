import Link from "next/link";

export default function NotFound() {
  return (
    <main className="centered-state">
      <div className="error-icon">?</div>
      <h1>페이지를 찾을 수 없습니다</h1>
      <Link className="button button-primary button-small" href="/">처음으로 돌아가기</Link>
    </main>
  );
}
