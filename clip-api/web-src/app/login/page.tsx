"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthForm } from "@/components/Auth";
import { Nav } from "@/components/Chrome";
import { Icon } from "@/components/dash/Icon";
import { FREE_CREDITS } from "@/lib/api";

export default function Login() {
  const router = useRouter();
  const [q, setQ] = useState<{ isNew: boolean; verified: boolean } | null>(null);
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    setQ({ isNew: p.has("new"), verified: p.has("verified") });
  }, []);
  return (
    <div className="auth-page">
      <Nav />
      <main>
        <div className="auth-card">
          {q && <AuthForm initial={q.isNew ? "signup" : "login"} onDone={() => router.push("/dashboard/")}
            note={q.verified ? "Email confirmed. Log in to pick up where you left off." : undefined} />}
          <ul className="auth-perks">
            <li><Icon name="bolt" size={16} />{FREE_CREDITS} free credits when you confirm your email</li>
            <li><Icon name="check" size={16} />No card needed to start</li>
            <li><Icon name="check" size={16} />Clips ranked by score, with your facecam and captions</li>
          </ul>
        </div>
      </main>
    </div>
  );
}
