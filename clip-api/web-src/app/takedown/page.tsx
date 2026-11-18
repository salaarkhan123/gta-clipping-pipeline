import type { Metadata } from "next";
import { Footer, Nav } from "@/components/Chrome";
import { TakedownForm } from "@/components/trust/TakedownForm";

export const metadata: Metadata = {
  title: "Report content: ClutchClips",
  description: "Send a copyright notice or a likeness report about content on ClutchClips. A person reviews every report.",
};

export default function Takedown() {
  return (
    <>
      <Nav />
      <main>
        <header className="page-head">
          <div className="container">
            <span className="pill"><span className="dot" />REPORT CONTENT</span>
            <h1>Report <span className="grad">content</span></h1>
            <p>Content on ClutchClips copies your work, or shows you without your permission? Tell us here. No account needed.
              You get a case reference by email, and a person reviews every report.</p>
          </div>
        </header>
        <section className="flush">
          <div className="container relative mx-auto max-w-[760px]">
            <TakedownForm />
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
