import { Footer, Nav } from "@/components/Chrome";

export default function Contact() {
  return (
    <>
      <Nav />
      <main>
        <header className="page-head">
          <div className="container">
            <span className="pill"><span className="dot" />CONTACT</span>
            <h1>Talk to <span className="grad">us</span></h1>
            <p>Questions, bugs, billing, or a clip you think we got wrong. Email us and a person replies.</p>
          </div>
        </header>
        <section className="flush">
          <div className="container contact-grid">
            <a className="tool" href="mailto:support@clutchclips.io?subject=Support"><div className="ico">🛟</div><h3>Support</h3><p>support@clutchclips.io</p></a>
            <a className="tool" href="mailto:support@clutchclips.io?subject=Agency%20plan"><div className="ico">🏢</div><h3>Agencies and teams</h3><p>Custom credit amounts and limits.</p></a>
            <a className="tool" href="mailto:support@clutchclips.io?subject=Takedown%20request"><div className="ico">⚖️</div><h3>Takedown requests</h3><p>Report content uploaded without permission.</p></a>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
}
