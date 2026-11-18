import type { Metadata } from "next";
import Link from "next/link";
import { Decision, Ext, LegalPage, Outstanding, Owner, Table } from "@/components/LegalPage";
import { OWNER } from "@/lib/legal";

// Every statement here matches docs/trust/data-map.md (what the code collects, keeps and sends) and
// docs/trust/privacy-law-review.md (laws, lawful bases, providers). Change those files and this page together.
export const metadata: Metadata = { title: "Privacy Policy · ClutchClips" };

const sections = [
  { id: "who", title: "Who we are", body: <>
    <p>ClutchClips is run by <Owner>{OWNER.entity}</Owner>, <Owner>{OWNER.address}</Owner>, in Edmonton, Alberta, Canada.
      We decide how the personal information on this service is used, so we are responsible for it (the &ldquo;organization&rdquo;
      under Canadian law and the &ldquo;controller&rdquo; under the GDPR). That includes the videos you upload.</p>
    <p>Our privacy officer is <Owner>{OWNER.privacyOfficer}</Owner>. Write to <Owner>{OWNER.privacyEmail}</Owner> with any
      question, request or complaint about your personal information. For Quebec, this person is also the person in charge
      of the protection of personal information.</p>
  </> },
  { id: "collect", title: "What we collect", body: <>
    <h3>Your account</h3>
    <ul>
      <li>Your email address and a password. We store only an argon2 hash of the password; nobody can read the password itself.</li>
      <li>The IP address you signed up from, kept so we can look into abuse of the service.</li>
      <li>Whether your email is confirmed, your plan, account status and when the account was created.</li>
      <li>Your API keys, stored only as a hash, with the name you gave each key, its first characters and when it was last used.
        Revoked keys stay on record.</li>
      <li>Your webhook signing secret.</li>
      <li>Which version of each policy you accepted, how (at sign-up or later) and when.</li>
      <li>Short-lived request counters, keyed by IP address or account, that enforce rate limits. They are kept in memory for up to one hour.</li>
    </ul>
    <h3>Your videos and what we make from them</h3>
    <ul>
      <li>The videos you upload or import, with the file name, size, length and a fingerprint (hash) of the file. A video can show your
        face and voice, other people and chat usernames.</li>
      <li>For a link import: the link, the site it came from, and a log of your account, the link, your confirmation that you own the
        video or may clip it, and the time.</li>
      <li>The transcript of what is said in the video (words with times) and a search index of the video.</li>
      <li>The clips we make: video, thumbnail, captions, preview and exports, plus the titles, hook, description, hashtags, rating and
        reason the AI writes for each clip.</li>
      <li>The options you choose for a job, including any free-text prompt and project name, your edits in the editor, and the looks
        (templates) you save.</li>
      <li>Which clips you keep, like or bookmark, and the measurements we use to rank clips. We use these to improve how clips are ranked.</li>
    </ul>
    <h3>Payments</h3>
    <ul>
      <li>Stripe collects your card details on its own pages. They never reach us.</li>
      <li>We keep your Stripe customer and subscription ids, your subscription status, a record of each payment (Stripe reference,
        amount, credits granted, refunds) and a ledger of every credit added to or taken from your account.</li>
    </ul>
    <h3>Email</h3>
    <p>We send you email to confirm your address (a link valid for 48 hours) and to reset your password (a link valid for one hour).
      We do not send marketing email.</p>
    <h3>Logs and errors</h3>
    <ul>
      <li>Our servers log each request: IP address, path and result. Imports log your account id, the site and the first 200 characters of
        the link. Billing logs record your account id, plan and invoice id.</li>
      <li>When error monitoring is on, error reports go to Sentry. We do not turn on Sentry&apos;s option to send extra personal data.</li>
      <li>If you set a webhook, we record each delivery: job id, your URL and the response code.</li>
    </ul>
    <h3>The website</h3>
    <p>The website sets no cookies and has no analytics, advertising or tracking. Your browser keeps your login token and unsent editor
      drafts in its own storage. See the <Link href="/cookies/">Cookie Notice</Link>.</p>
  </> },
  { id: "why", title: "Why we use it", body: <>
    <p>We use your information to run the service you sign up for, to take payment, to keep the service safe and to meet our legal duties.
      For people in the EU and UK, these are the lawful bases we rely on:</p>
    <Table head={["What we do", "Lawful basis (GDPR / UK GDPR)"]} rows={[
      ["Your account and login, running jobs, storing videos and clips, emails about your account", "Contract (Art. 6(1)(b))"],
      ["Payments, invoices and the credit ledger", "Contract; legal obligation (Art. 6(1)(c)) for tax records"],
      ["AI clip judging, titles and transcripts", "Contract: it is the service you ask for"],
      ["Sign-up IP, rate limits, abuse and fraud checks, the import log, copyright and likeness reports", "Legitimate interests (Art. 6(1)(f)): security, defending legal claims, our copyright duties"],
      ["Error monitoring", "Legitimate interests: keeping the service working"],
      ["Records of which policies you accepted", "Legal obligation and legitimate interests: proof of what you agreed to"],
    ]} />
    <p>Faces and voices in your videos: we detect where a face is so we can place the facecam in the clip. This finds a box on the screen.
      It does not create a face template and it does not identify anyone.</p>
    <p>We do not use your information for advertising, and we do not use it to work out sensitive things about you, such as health,
      ethnicity, religion or sexual orientation.</p>
  </> },
  { id: "ai", title: "AI processing", body: <>
    <ul>
      <li><strong>Transcription</strong> runs on our own server (faster-whisper). Your audio does not leave it.</li>
      <li><strong>Visual search and face detection</strong> run on our own server. Nothing leaves it.</li>
      <li><strong>The AI judge</strong> writes each clip&apos;s titles, hook, rating and reason and helps choose where the clip starts and ends.
        It uses Anthropic&apos;s Claude API. For each clip, Anthropic receives one still frame from the clip, an excerpt of the clip&apos;s
        timed transcript, the scores that made us pick the moment, and the prompt you typed for the job, if any. Anthropic deletes these
        inputs and outputs within 30 days (content flagged for a policy breach can be kept up to 2 years) and does not train its models on them.</li>
      <li><strong>Translation and summaries</strong> use Anthropic only when that setting is switched on. Then the transcript text is sent
        to Anthropic, under the same terms.</li>
      <li>We do not offer AI-generated thumbnails, and no image-generation company receives your videos or frames.</li>
    </ul>
    <p>The AI ranks and titles clips. It makes no decision about you as a person. Its ratings and virality scores are opinions about clips,
      not forecasts.</p>
  </> },
  { id: "share", title: "Who receives it", body: <>
    <p>We do not sell your personal information and we do not share it for advertising. These companies process it for us:</p>
    <Table head={["Company", "What for", "What they receive", "How long they keep it"]} rows={[
      [<Ext key="do" href="https://www.digitalocean.com/legal/data-processing-agreement">DigitalOcean</Ext>, "Our server, database and file storage",
        "Everything stored on the service", "Deleted within 30 days after our account closes; backups until they are disposed of"],
      [<Ext key="an" href="https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data">Anthropic</Ext>, "The AI judge; translation and summaries when switched on",
        "A frame, a transcript excerpt and your prompt per clip; transcript text for translation or summaries", "Up to 30 days; flagged content up to 2 years; no training"],
      [<Ext key="st" href="https://stripe.com/privacy">Stripe</Ext>, "Payments. Stripe is also responsible on its own for fraud and anti-money-laundering checks",
        "Your email, account id, card and payment details", "As long as it provides the service, longer where the law requires"],
      [<Ext key="se" href="https://docs.sentry.io/security-legal-pii/security/data-retention-periods/">Sentry</Ext>, "Error reports, when switched on",
        "Technical details of the error", "30 or 90 days, by plan"],
      ["Email provider", "Sending account email", "Your email address and the message", <Owner key="em">{OWNER.emailProvider}</Owner>],
    ]} />
    <p>When you import a link, we contact the site it points to (for example Twitch, Kick, YouTube, Google Drive or Dropbox) to download the
      video. If you set a webhook, we send the job id and status to your own server. If you send us a copyright counter-notice, the owner forwards it by email,
      with the name and address in it, to the person who complained (see the <Link href="/copyright/">Copyright and DMCA Policy</Link>).
      Otherwise we disclose information only when the law requires it or to defend legal claims.</p>
  </> },
  { id: "where", title: "Where it is stored", body: <>
    <ul>
      <li>Our server and database are in Toronto, Canada (DigitalOcean). Files are kept on that server or in DigitalOcean object storage
        (<Owner>{OWNER.spacesRegion}</Owner>).</li>
      <li>Anthropic and Stripe are in the United States, and Stripe also works in other regions. Sentry stores data in the US or the EU
        (<Owner>{OWNER.sentryRegion}</Owner>).</li>
    </ul>
    <p>So your information may be processed in the United States, where the law may let authorities access it. You can ask our privacy
      officer about how these service providers outside Canada handle it.</p>
    <p>For people in the EU and UK: Canada has an EU adequacy decision for businesses covered by PIPEDA. For transfers to the US we rely on
      the EU-US Data Privacy Framework (Stripe, DigitalOcean, Sentry) and on Standard Contractual Clauses with the UK addendum in each
      provider&apos;s data processing agreement (Anthropic, and the others as a fallback). <Owner>{OWNER.dpas}</Owner></p>
  </> },
  { id: "keep", title: "How long we keep it", body: <>
    <Table head={["Information", "How long"]} rows={[
      ["Uploaded and imported videos, their transcripts and search index", "Deleted 7 days after upload"],
      ["Clip files: video, thumbnail, captions, preview and the latest export", "Deleted 7 days after the job"],
      ["Earlier exports of the same clip", "No limit yet: today they can outlive the 7 days. We are fixing this"],
      ["Your account: email, password hash, sign-up IP, API keys, Stripe ids", "Until your account is deleted"],
      ["Records of the policies you accepted", "For the life of your account"],
      ["Payment records and the credit ledger", "Kept: we need them for accounting and tax. Ledger rows are never deleted"],
      ["Import log, AI titles and ratings, ranking data and feedback, job options and prompts, editor changes, webhook delivery records", "No limit yet"],
      ["Server logs", "No limit yet"],
      ["Rate-limit counters", "Up to 1 hour"],
      ["Your login token (in your browser)", "7 days, or until you log out"],
    ]} />
    <p>Where this table says &ldquo;no limit yet&rdquo;, we have not set a period. We will set one and update this policy.</p>
    <p>You cannot delete your account from the dashboard yet. Email the privacy contact to ask for deletion; we handle these requests by hand.</p>
  </> },
  { id: "rights", title: "Your rights", body: <>
    <p>Wherever you live, you can ask us to:</p>
    <ul>
      <li>give you a copy of your personal information, in a structured, machine-readable format where you ask for one (access and portability);</li>
      <li>correct information that is wrong;</li>
      <li>delete your information and your account;</li>
      <li>stop or limit a use of it, or object to a use based on our legitimate interests;</li>
      <li>withdraw a consent you gave (this does not undo what was lawfully done before).</li>
    </ul>
    <p>To use a right, email <Owner>{OWNER.privacyEmail}</Owner> from the address on your account. We may ask you to confirm who you are.
      We answer within 30 days (one month under the GDPR). Self-serve export and deletion in the dashboard are not available yet.</p>
    <p>Some records we must keep even after a deletion request, such as payment and credit records needed for tax, and the import log and the
      copyright and likeness reports we receive, needed to answer legal claims.</p>
    <p>You can complain to a privacy regulator at any time:</p>
    <ul>
      <li><Ext href="https://www.priv.gc.ca/">Office of the Privacy Commissioner of Canada</Ext></li>
      <li><Ext href="https://oipc.ab.ca/">Office of the Information and Privacy Commissioner of Alberta</Ext></li>
      <li>In Quebec: the <Ext href="https://www.cai.gouv.qc.ca/">Commission d&apos;accès à l&apos;information</Ext></li>
      <li>In the EU or UK: the data protection authority where you live or work (in the UK, the <Ext href="https://ico.org.uk/">ICO</Ext>)</li>
    </ul>
  </> },
  { id: "security", title: "Security and breaches", body: <>
    <p>We hash passwords with argon2 and store API keys only as hashes. Files are in private storage and are shared only through
      download links that expire after one hour. All traffic uses HTTPS.</p>
    <p>If a breach of security creates a real risk of significant harm to you, we will tell you and report it to the Privacy Commissioner
      of Canada and Alberta&apos;s Information and Privacy Commissioner (and Quebec&apos;s Commission d&apos;accès à l&apos;information, or
      the EU/UK authority, where their laws apply). We keep a record of every breach for at least 24 months.</p>
  </> },
  { id: "children", title: "Children", body: <>
    <p>ClutchClips is not for children. You must be 18 or older to create an account <Decision>minimum age 18 is proposed; 16 with a
      parent&apos;s consent is the other option</Decision>. If we learn that an account belongs to someone under the minimum age, we close
      it and delete its information.</p>
  </> },
  { id: "regions", title: "Quebec, the EU and the UK", body: <>
    <p><strong>Quebec.</strong> The person in charge of the protection of personal information is our privacy officer (see
      &ldquo;Who we are&rdquo;). We tell you here that the service uses automated processing to rank and title clips; it makes no decision
      about you. This policy is in English only for now. <Outstanding>French versions of this policy and the Terms, before we market in Quebec</Outstanding></p>
    <p><strong>EU and UK.</strong> The rights above include all GDPR rights. <Outstanding>an EU and a UK representative (GDPR Art. 27),
      before we market to people there</Outstanding></p>
    <p><strong>United States.</strong> We do not sell or share personal information for cross-context behavioural advertising, and we do not
      use sensitive personal information to infer characteristics about you.</p>
  </> },
  { id: "changes", title: "Changes to this policy", body: <>
    <p>Each version of this policy has a version number and an effective date, shown at the top. When we change it in a way that affects
      your rights, we give it a new version and ask you to accept it the next time you open the dashboard. We record which version you
      accepted and when. Small fixes that change no right or duty keep the same version.</p>
  </> },
];

export default function Privacy() {
  return <LegalPage id="privacy" sections={sections} intro={<p>What personal information ClutchClips collects, why, who receives it,
    how long we keep it, and what you can do about it. In plain words.</p>} />;
}
