import type { Metadata } from "next";
import Link from "next/link";
import { Decision, LegalPage, Owner, Review } from "@/components/LegalPage";
import { CONTACT, OWNER, SUPPORT_EMAIL } from "@/lib/legal";

// Credits and billing statements match app/ledger.py (reserve and settle once, refunds), app/routes_media.py and
// app/routes_tools.py (what a job reserves), app/worker.py (refund on failure, timeout, cancel), app/plans.py and
// app/plan_grants.py (plans, monthly and yearly grants) and app/routes_billing.py (subscriptions, Stripe refunds).
export const metadata: Metadata = { title: "Terms of Service · ClutchClips" };

const sections = [
  { id: "agreement", title: "This agreement", body: <>
    <p>These terms are an agreement between you and <Owner>{OWNER.entity}</Owner> (&ldquo;ClutchClips&rdquo;, &ldquo;we&rdquo;), the
      operator of clutchclips.io and the ClutchClips API. You accept them when you create an account. The{" "}
      <Link href="/privacy/">Privacy Policy</Link> and the <Link href="/acceptable-use/">Acceptable Use Policy</Link> are part of them,
      and so are the <Link href="/copyright/">Copyright and DMCA Policy</Link> and the <Link href="/refunds/">Refund Policy</Link>.</p>
  </> },
  { id: "account", title: "Your account", body: <>
    <ul>
      <li>You must be 18 or older <Decision>minimum age 18 is proposed; 16 with a parent&apos;s consent is the other option</Decision>.</li>
      <li>Give a real email address you can read. You need to confirm it before you can make clips.</li>
      <li>Keep your password and API keys secret. You are responsible for what is done with your account and keys. Tell us at
        {" "}<a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a> if you think someone else is using them.</li>
      <li>Use the API within its rate limits and the limits of your plan.</li>
    </ul>
  </> },
  { id: "use", title: "Acceptable use", body: <>
    <p>You must follow the <Link href="/acceptable-use/">Acceptable Use Policy</Link>. In short: only upload what you have the right to
      clip, do not impersonate or deceive, and do not try to get around our limits or anyone else&apos;s.</p>
  </> },
  { id: "content", title: "Your content", body: <>
    <p>You keep every right you have in the videos you upload or import and in the clips we make from them. We claim no ownership.</p>
    <p>You give us a licence to store, copy, transcribe, analyse, edit and render your videos and clips, and to send the parts described
      in the <Link href="/privacy/">Privacy Policy</Link> to our service providers, only to run the service for you. The licence is
      worldwide and free, and it ends when the files are deleted, except for copies we must keep by law or to answer a legal claim.</p>
    <p>Files are deleted 7 days after upload (videos) or after the job (clips). Download what you want to keep.</p>
    <p>You decide where your clips are published, and you are responsible for following the rules of the platforms you post them on.</p>
  </> },
  { id: "rights", title: "Rights and consent for what you upload", body: <>
    <p>By uploading or importing a video, you promise that:</p>
    <ul>
      <li>you own it, or the owner has given you permission to clip it;</li>
      <li>you have the rights you need to everything in it, such as music, game footage and overlays, for the way you will use the clips;</li>
      <li>every person whose face, voice or name appears in it agrees to being clipped and published, or the law lets you use them without
        consent. This includes co-streamers, guests and people on camera;</li>
      <li>it is not illegal content and does not break the <Link href="/acceptable-use/">Acceptable Use Policy</Link>.</li>
    </ul>
  </> },
  { id: "import", title: "Importing from a link", body: <>
    <ul>
      <li>Link import only accepts public videos that play in a signed-out browser and are not protected by DRM.</li>
      <li>We never use logins, cookies, accounts, proxies or any other way around a block, paywall, age gate or rate limit. If a site
        refuses, the import fails and you can upload the file instead. YouTube imports are best effort and may fail.</li>
      <li>Every import asks you to confirm that you own the video or have permission to clip it. We log your account, the link, your
        confirmation and the time.</li>
      <li>The site you import from has its own terms, and they apply to you. Our import does not give you rights the site&apos;s terms do not.</li>
      <li>Anything imported can be removed after a takedown request. The owner reviews each request by hand; removal deletes the imported
        upload, its clips and their files, from one link or from all of one account&apos;s imports, and refunds jobs still waiting or running on it.</li>
    </ul>
  </> },
  { id: "credits", title: "Credits", body: <>
    <ul>
      <li>1 credit is 1 minute of source video, rounded up to the next whole minute. A 2-hour video uses 120 credits.</li>
      <li>The price is shown before you start a job. Starting a job reserves its credits. If the job fails, times out or is cancelled, every
        reserved credit comes back automatically.</li>
      <li>Tools that analyse a whole video (such as Clip Maker and Video Finder) use 1 credit per minute of the video. Exports, re-renders
        and tools that render part of a video (such as Reframe and Captions) use 1 credit per started minute they render.</li>
      <li>After a video&apos;s first full-price run, later runs on the same upload charge only for the minutes they render. They reserve up to
        the full amount and give back what they did not use.</li>
      <li>Credits don&apos;t expire while your account exists.</li>
      <li>New accounts get a one-time grant of free credits once the email address is confirmed. The amount is shown on the{" "}
        <Link href="/pricing/">pricing page</Link>.</li>
      <li>Credits have no cash value and cannot be transferred to another account. Unused credits are refunded only as the{" "}
        <Link href="/refunds/">Refund Policy</Link> says.</li>
    </ul>
  </> },
  { id: "plans", title: "Plans and subscriptions", body: <>
    <ul>
      <li>The plans are Free, Starter, Pro and Scale. Prices, credits and limits for each are on the <Link href="/pricing/">pricing page</Link>.</li>
      <li>Free has no monthly credits: it uses the free sign-up credits and any credits you buy.</li>
      <li>Monthly plans add their monthly credits each time an invoice is paid.</li>
      <li>Yearly plans are billed once a year and add the monthly amount of credits each month of the paid year, not the whole year at once.</li>
      <li>Subscriptions renew automatically until you cancel. Payments go through Stripe.</li>
      <li>You can cancel any time in the Stripe billing portal, opened from your account. The plan stays until the end of the period you paid
        for, then the account returns to Free. Credits already in your account stay.</li>
      <li>If a renewal payment fails, Stripe retries it. While it retries you keep your plan. If the payment cannot be collected, the plan
        ends and the account returns to Free.</li>
      <li>Credit packs are one-time top-ups. They are not a subscription.</li>
      <li>Plans sold before 17 November 2026 keep the credits and limits they were sold with for as long as the subscription runs.</li>
    </ul>
    <p>Refunds: see the <Link href="/refunds/">Refund Policy</Link>.</p>
  </> },
  { id: "copyright", title: "Copyright complaints and repeat infringers", body: <>
    <p>We respond to copyright notices as the <Link href="/copyright/">Copyright and DMCA Policy</Link> describes. We terminate the accounts
      of repeat infringers (17 U.S.C. 512(i)): three strikes end an account, and a strike counts only for a valid notice that was not
      withdrawn and not successfully countered. For a serious violation we may terminate an account at once. Today the owner decides each
      case by hand. <Decision>which cases count as serious, and whether strikes expire</Decision></p>
  </> },
  { id: "suspension", title: "Suspension and ending the agreement", body: <>
    <ul>
      <li>You can stop using ClutchClips at any time. To delete your account, email us; self-serve deletion is not available yet.</li>
      <li>We may suspend or close an account at once if it breaks these terms or the Acceptable Use Policy, is used for fraud or abuse, or
        the law requires it. Where we can, we tell you why and give you a chance to respond.</li>
      <li>For any other reason, we give you 30 days&apos; notice by email before we close your account. <Review /></li>
      <li>A suspended account cannot log in or use the API, so it cannot start jobs or use its credits.</li>
      <li>We may change or stop features. <Decision>what happens to unused paid credits if the whole service closes</Decision></li>
    </ul>
  </> },
  { id: "disclaimers", title: "Disclaimers", body: <>
    <ul>
      <li>Clip selection, titles and ratings are made by software, including AI. AI ratings of clips are opinions, not forecasts of how a
        clip will perform. We do not promise views, followers or earnings.</li>
      <li>AI output can be wrong. Check titles, captions and hashtags before you publish.</li>
      <li>The service is provided &ldquo;as is&rdquo; and &ldquo;as available&rdquo;. As far as the law allows, we give no warranties beyond
        those in these terms.</li>
    </ul>
  </> },
  { id: "liability", title: "Limitation of liability", body: <>
    <p>As far as the law allows, we are not liable for indirect or consequential losses, such as lost profits, lost revenue or lost data,
      and our total liability for any claim about the service is limited to the fees you paid us in the 12 months before the claim <Review />.
      Nothing in these terms limits liability that the law does not allow to be limited, or your rights as a consumer under the law where you live.</p>
  </> },
  { id: "law", title: "Governing law", body: <>
    <p>These terms are governed by the laws of the Province of Alberta and the federal laws of Canada that apply there <Review />. The
      courts of Alberta decide any dispute about them <Review />. If you are a consumer, you also keep the protection of the
      mandatory laws of the place where you live.</p>
  </> },
  { id: "changes", title: "Changes to these terms", body: <>
    <p>Each version of these terms has a version number and an effective date, shown at the top. When we change them in a way that affects
      your rights or duties, we give them a new version and ask you to accept it the next time you open the dashboard. Small fixes that
      change no right or duty keep the same version.</p>
  </> },
  { id: "contact", title: "Contact", body: <>
    <p>Questions about these terms: <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>. Privacy:{" "}
      <a href={`mailto:${CONTACT.privacy}`}>{CONTACT.privacy}</a>. Copyright and likeness:{" "}
      <a href={`mailto:${CONTACT.copyright}`}>{CONTACT.copyright}</a>. Anything else:{" "}
      <a href={`mailto:${CONTACT.general}`}>{CONTACT.general}</a>. Post: <Owner>{OWNER.address}</Owner>.</p>
  </> },
];

export default function Terms() {
  return <LegalPage id="terms" sections={sections} intro={<p>The rules for using ClutchClips: your account, your content, credits and plans,
    and what each of us is responsible for.</p>} />;
}
