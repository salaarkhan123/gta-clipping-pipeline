import type { Metadata } from "next";
import Link from "next/link";
import { Decision, Ext, LegalPage, Owner } from "@/components/LegalPage";
import { OWNER, SUPPORT_EMAIL } from "@/lib/legal";

// Matches docs/trust/privacy-law-review.md section 7 (Copyright Act ss. 41.25-41.27, 17 U.S.C. 512) and
// app/ingest/takedown.py (removal of everything from a source link or account). The online form is #148.
export const metadata: Metadata = { title: "Copyright and DMCA Policy · ClutchClips" };

const sections = [
  { id: "summary", title: "In short", body: <>
    <ul>
      <li>Only upload or import videos you own or have permission to clip.</li>
      <li>If you own the copyright in something on ClutchClips and did not allow it, send a notice by email. A person reviews every notice.</li>
      <li>Nothing is removed automatically on a complaint that has not been checked. Content can be disabled while we review it.</li>
      <li>If your content was removed by mistake, you can send a counter-notice.</li>
    </ul>
  </> },
  { id: "notice", title: "How to send a copyright notice", body: <>
    <p>Email your notice to our designated agent (details below). To be valid under the US Digital Millennium Copyright Act
      (17 U.S.C. 512(c)(3)), it must include:</p>
    <ol>
      <li>a physical or electronic signature of the copyright owner or of a person authorised to act for them;</li>
      <li>the copyrighted work you say is infringed (or, for several works, a representative list);</li>
      <li>the material you say infringes, with enough detail for us to find it, such as the clip link or the source video link;</li>
      <li>your name, postal address, phone number and email address;</li>
      <li>a statement that you believe in good faith that the use is not authorised by the copyright owner, its agent or the law;</li>
      <li>a statement that the information in the notice is accurate and, under penalty of perjury, that you are the copyright owner or
        authorised to act for them.</li>
    </ol>
    <p>For Canadian law, please also give the date and time of the claimed infringement and your interest in the work (owner, exclusive
      licensee or agent).</p>
  </> },
  { id: "agent", title: "Our designated agent", body: <>
    <p><Owner>{OWNER.dmcaAgent}</Owner></p>
    <p>Email: <Owner>{OWNER.dmcaEmail}</Owner></p>
    <p>The same agent is listed in the US Copyright Office&apos;s{" "}
      <Ext href="https://www.copyright.gov/dmca-directory/">DMCA Designated Agent Directory</Ext>. <Owner>register the agent at
      dmca.copyright.gov and renew every 3 years</Owner></p>
  </> },
  { id: "canada", title: "Canada: notice and notice", body: <>
    <p>Under Canada&apos;s Copyright Act (sections 41.25 to 41.27), when we receive a notice of claimed infringement that meets the Act&apos;s
      requirements, we:</p>
    <ul>
      <li>forward the notice by email to the account holder it concerns, and tell the person who sent it that we did, or why we could not;</li>
      <li>keep records that identify that account holder for 6 months, or for 1 year if the claimant starts court proceedings and tells us
        within those 6 months.</li>
    </ul>
    <p>A notice that includes an offer to settle or a demand for payment does not have to be forwarded. Forwarding a notice does not mean
      the account holder infringed, and the law does not require us to remove the content. We still review it under this policy.</p>
  </> },
  { id: "process", title: "What we do with a notice", body: <>
    <ul>
      <li>An administrator reviews every notice. We may ask for missing details.</li>
      <li>While we review, we may disable access to the content.</li>
      <li>Nothing is removed automatically on a notice we have not verified. The administrator decides.</li>
      <li>If the notice is valid, we remove the content. For imported videos we can remove everything that came from that link, or all of
        one account&apos;s imports: the uploads, every clip and every file. Credits held for their unfinished jobs go back to the account.</li>
      <li>We tell the account holder what was removed and why, and how to send a counter-notice.</li>
    </ul>
  </> },
  { id: "counter", title: "Counter-notice", body: <>
    <p>If you believe your content was removed by mistake or because it was misidentified, email a counter-notice to our designated agent.
      Under 17 U.S.C. 512(g)(3) it must include:</p>
    <ol>
      <li>your physical or electronic signature;</li>
      <li>the material that was removed or disabled, and where it appeared before;</li>
      <li>a statement, under penalty of perjury, that you believe in good faith the material was removed or disabled because of a mistake or
        misidentification;</li>
      <li>your name, address and phone number, and a statement that you consent to the jurisdiction of the US Federal District Court for the
        judicial district of your address (or, if you are outside the United States, any judicial district in which we may be found), and
        that you will accept service of process from the person who sent the notice or their agent.</li>
    </ol>
    <p>We forward a valid counter-notice, including your name and address, to the person who sent the notice. We restore the content in 10
      to 14 business days after we receive it, unless that person tells us they have filed a court action to stop the infringement.</p>
    <p>Files are deleted 7 days after upload or after the job, so content that has already expired cannot be restored.</p>
  </> },
  { id: "repeat", title: "Repeat infringers", body: <>
    <p>We suspend the account of a repeat infringer. An account that receives 3 verified copyright strikes within 365 days is suspended
      <Decision>3 verified strikes in 365 days is proposed</Decision>. A strike is a notice we verified and acted on.</p>
  </> },
  { id: "misrepresentation", title: "False notices", body: <>
    <p>Under 17 U.S.C. 512(f), a person who knowingly and materially misrepresents that material infringes, or that it was removed by
      mistake, can be liable for damages, including costs and lawyers&apos; fees. Before you send a notice, consider whether the use could be
      fair use or fair dealing.</p>
  </> },
  { id: "likeness", title: "Your face, voice or name", body: <>
    <p>If a clip on ClutchClips shows you, uses your voice, or impersonates you without your consent, email{" "}
      <a href={`mailto:${SUPPORT_EMAIL}?subject=Likeness%20report`}>{SUPPORT_EMAIL}</a> with the subject &ldquo;Likeness report&rdquo;.
      Include the clip or source link, who you are, and what is wrong. An administrator reviews it the same way as a copyright notice.
      The <Link href="/acceptable-use/">Acceptable Use Policy</Link> bans deceptive impersonation and synthetic content of real people
      without their consent.</p>
  </> },
];

export default function Copyright() {
  return <LegalPage id="copyright" sections={sections} intro={<p>How to report content that infringes your copyright or uses your likeness,
    what we do with a report, and how to respond if your content was removed.</p>} />;
}
