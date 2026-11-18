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
    <div className="grid min-h-screen grid-rows-[auto_1fr]">
      <Nav />
      <main className="grid place-items-center px-4 pb-16 pt-8 [background:radial-gradient(ellipse_at_50%_0%,rgba(184,255,60,.10),transparent_55%),radial-gradient(ellipse_at_100%_100%,rgba(60,240,255,.07),transparent_50%)]">
        <div className="w-[min(100%,420px)] rounded-20 border border-solid border-line bg-panel p-[30px] shadow-[0_30px_80px_rgba(0,0,0,.5)] [&_.auth_h2]:text-[24px] [&_.btn.primary]:w-full">
          {q && <AuthForm initial={q.isNew ? "signup" : "login"} onDone={() => router.push("/dashboard/")}
            note={q.verified ? "Email confirmed. Log in to pick up where you left off." : undefined} />}
          <ul className="mt-[18px] grid list-none gap-2 border-0 border-t border-solid border-line pt-4 text-[13.5px] text-muted [&_.ico]:text-lime [&_li]:flex [&_li]:items-center [&_li]:gap-2">
            <li><Icon name="bolt" size={16} />{FREE_CREDITS} free credits when you confirm your email</li>
            <li><Icon name="check" size={16} />No card needed to start</li>
            <li><Icon name="check" size={16} />Clips ranked by score, with your facecam and captions</li>
          </ul>
        </div>
      </main>
    </div>
  );
}
