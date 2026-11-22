import "./app.css";
import { Shell } from "@/components/dash/Shell";

// data-theme="app" switches the tokens (app/tokens.css) to the app's charcoal surfaces, Inter and rounded-rectangle controls.
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return <div data-theme="app" className="min-h-screen font-sans"><Shell>{children}</Shell></div>;
}
