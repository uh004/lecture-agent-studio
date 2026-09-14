import { GraduationCap, Plus } from "lucide-react";
import Link from "next/link";

export function AppHeader() {
  return (
    <header className="app-header">
      <div className="header-inner">
        <Link className="brand" href="/" aria-label="AI 강사 Agent 홈">
          <span className="brand-mark"><GraduationCap size={23} /></span>
          <span>AI 강사 <strong>Agent</strong></span>
        </Link>
        <Link className="header-action" href="/">
          <Plus size={17} /> 새 강의
        </Link>
      </div>
    </header>
  );
}
