"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthForm } from "@/components/Auth";
import { Nav } from "@/components/Chrome";
import { Icon } from "@/components/dash/Icon";
import { freeCredits, useSignupCredits } from "@/lib/plans";

export default function Login() {
  const router = useRouter();
  const [q, setQ] = useState<{ isNew: boolean; verified: boolean } | null>(null);
  const signup = useSignupCredits();
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    setQ({ isNew: p.has("new"), verified: p.has("verified") });
  }, []);
  return (
    <div className="grid min-h-screen grid-rows-[auto_1fr]">
      <Nav />
      <main className="grid place-items-center px-4 pb-16 pt-10 [background:radial-gradient(ellipse_at_50%_-10%,rgba(255,255,255,.07),transparent_55%)]">
        <div className="w-[min(100%,420px)] rounded-[24px] border border-solid border-line-soft bg-card p-8 shadow-[0_30px_80px_rgba(0,0,0,.6)] narrow:p-6 [&_.auth_h2]:text-[26px] [&_.auth_h2]:font-semibold [&_.auth_h2]:tracking-[-0.02em] [&_.btn.primary]:w-full [&_input:not([type=checkbox])]:rounded-full [&_input:not([type=checkbox])]:px-[18px]">
          {q && <AuthForm initial={q.isNew ? "signup" : "login"} onDone={() => router.push("/dashboard/")}
            note={q.verified ? "Email confirmed. Log in to pick up where you left off." : undefined} />}
          <ul className="mt-[18px] grid list-none gap-2 border-0 border-t border-solid border-line pt-4 text-[13.5px] text-muted [&_.ico]:text-lime [&_li]:flex [&_li]:items-center [&_li]:gap-2">
            <li><Icon name="bolt" size={16} />{freeCredits(signup)} when you confirm your email</li>
            <li><Icon name="check" size={16} />No card needed to start</li>
            <li><Icon name="check" size={16} />Clips ranked by AI rating, with your facecam and captions</li>
          </ul>
        </div>
      </main>
    </div>
  );
}
