"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthForm } from "@/components/Auth";
import { Nav } from "@/components/Chrome";

export default function Login() {
  const router = useRouter();
  const [q, setQ] = useState<{ isNew: boolean; verified: boolean } | null>(null);
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    setQ({ isNew: p.has("new"), verified: p.has("verified") });
  }, []);
  return (
    <>
      <Nav />
      <main className="narrow">
        {q && <AuthForm initial={q.isNew ? "signup" : "login"} onDone={() => router.push("/dashboard/")}
          note={q.verified ? "Email confirmed. Log in to pick up where you left off." : undefined} />}
      </main>
    </>
  );
}
