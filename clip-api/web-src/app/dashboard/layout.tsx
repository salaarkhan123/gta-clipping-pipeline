import "./app.css";
import { Shell } from "@/components/dash/Shell";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return <Shell>{children}</Shell>;
}
