import { ReactNode } from "react";
import { Link } from "react-router-dom";
import { BudgetIndicator } from "./BudgetIndicator";
import { VoicePicker } from "./VoicePicker";

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <header className="border-b bg-white px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <span className="font-semibold text-slate-900">English Tutor</span>
          <nav className="flex gap-3 text-sm text-slate-600">
            <Link to="/" className="hover:text-slate-900">Scenarios</Link>
            <Link to="/review" className="hover:text-slate-900">Review</Link>
            <Link to="/practice" className="hover:text-slate-900">Practice</Link>
            <Link to="/stats" className="hover:text-slate-900">Stats</Link>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <VoicePicker />
          <BudgetIndicator />
        </div>
      </header>
      <main className="flex-1 flex flex-col">{children}</main>
    </div>
  );
}
