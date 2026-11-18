import type { Metadata } from "next";
import Link from "next/link";
import { LegalPage, Review } from "@/components/LegalPage";
import { SUPPORT_EMAIL } from "@/lib/legal";

// "What happens automatically" matches the code: app/ledger.py (settle once; claw_back stops at zero),
// app/worker.py (failed, timed-out, cancelled and lost jobs are released), app/routes_billing.py (charge.refunded
// in proportion, charge.dispute.created in full) and app/plan_grants.py (a refunded yearly payment grants no more
// months). "Money refunds" is a proposal for the owner.
export const metadata: Metadata = { title: "Refund Policy · ClutchClips" };

const sections = [
  { id: "credits", title: "Credits for jobs that do not finish", body: <>
    <p>Starting a job reserves its credits. If the job fails, times out, is cancelled, or stops because our server lost it, every reserved
      credit goes back to your account automatically. You do not need to ask.</p>
    <p>A job that finishes keeps only the credits it used. When a run is charged for the minutes it renders, it gives back whatever it
      reserved and did not use. Each job is settled exactly once, so credits are never charged or refunded twice.</p>
    <p>If an imported video is removed after a takedown request, jobs still waiting or running on it are stopped and their credits go back too.</p>
  </> },
  { id: "stripe", title: "When a payment is refunded or disputed", body: <>
    <ul>
      <li>If a payment is refunded through Stripe, the credits that payment added are taken back, in proportion to the part refunded. A half
        refund takes back half of the credits.</li>
      <li>If you dispute a payment with your bank (a chargeback), all the credits that payment added are taken back.</li>
      <li>Credits are never taken below a zero balance. Credits you already spent are not owed back.</li>
      <li>For a yearly plan, a refunded or disputed payment also stops the monthly credits still to come from that year.</li>
    </ul>
  </> },
  { id: "money", title: "Money refunds", body: <>
    <p><mark className="rounded-[4px] bg-[rgba(255,182,72,.16)] px-1 font-semibold text-warn">[Draft, subject to legal review]</mark></p>
    <ul>
      <li><strong>Credit packs.</strong> You can ask for a refund of a credit pack within 14 days of buying it, as long as none of its credits
        have been used.</li>
      <li><strong>Used credits.</strong> Credits that have been used are not refunded.</li>
      <li><strong>Subscriptions.</strong> You can cancel at any time and keep the plan until the end of the period you paid for. Refunds of
        subscription payments are at our discretion, for example when you were charged after cancelling or by mistake.</li>
      <li><strong>Failed jobs.</strong> Credits for jobs that fail, time out or are cancelled come back automatically (see above).</li>
      <li><strong>Mistakes and outages.</strong> If we charged you in error or the service did not work, tell us and we will put it right.</li>
    </ul>
    <p>This does not limit rights you have under the law where you live.</p>
    <p>To ask for a refund, email <a href={`mailto:${SUPPORT_EMAIL}?subject=Refund%20request`}>{SUPPORT_EMAIL}</a> from the address on your
      account, with the date and amount of the payment. Approved refunds go back to the card you paid with, through Stripe.</p>
  </> },
  { id: "statutory", title: "Your legal rights", body: <>
    <p>This policy does not limit rights you have under the law where you live.</p>
    <p>If you live in the EU or UK, you normally have 14 days to withdraw from an online purchase without giving a reason. Credits are digital
      content you can use straight away. If you ask for immediate access and agree that you lose the right of withdrawal once you start
      using the credits, the right ends when you use them. Credits you have not used stay within the 14-day right. <Review /></p>
  </> },
  { id: "more", title: "More", body: <>
    <p>How credits and plans work is in the <Link href="/terms/">Terms of Service</Link>. Prices are on the{" "}
      <Link href="/pricing/">pricing page</Link>.</p>
  </> },
];

export default function Refunds() {
  return <LegalPage id="refunds" sections={sections} intro={<p>What happens to your credits when a job does not finish or a payment is
    refunded, and how to ask for your money back.</p>} />;
}
