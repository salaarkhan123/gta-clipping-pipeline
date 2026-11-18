import type { Metadata } from "next";
import Link from "next/link";
import { Decision, Ext, LegalPage, Mail, Owner } from "@/components/LegalPage";
import { CONTACT, OWNER } from "@/lib/legal";

// Matches docs/trust/privacy-law-review.md section 7 (Copyright Act ss. 41.25-41.27, 17 U.S.C. 512) and
// what runs today: notices by email, reviewed by the owner by hand, removal with `scripts/admin.py takedown`
// (app/ingest/takedown.py, DEPLOY.md "Link import and takedowns"). The form, cases and strikes are #145, #146, #148.
export const metadata: Metadata = { title: "Copyright and DMCA Policy · ClutchClips" };

const sections = [
  { id: "summary", title: "In short", body: <>
    <ul>
      <li>Only upload or import videos you own or have permission to clip.</li>
      <li>If you own the copyright in something on ClutchClips and did not allow it, send a notice by email to the contact below.</li>
      <li>The owner of ClutchClips reads and reviews every notice by hand. Nothing is removed automatically.</li>
      <li>If your content was removed by mistake, you can send a counter-notice by email.</li>
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
    <p>Email: <Mail to={CONTACT.copyright} subject="Copyright notice" /></p>
    <p>The agent is not yet registered in the US Copyright Office&apos;s{" "}
      <Ext href="https://www.copyright.gov/dmca-directory/">DMCA Designated Agent Directory</Ext>. <Owner>{OWNER.dmcaRegistration}</Owner></p>
  </> },
  { id: "canada", title: "Canada: notice and notice", body: <>
    <p>Under Canada&apos;s Copyright Act (sections 41.25 to 41.27), when we receive a notice of claimed infringement that meets the Act&apos;s
      requirements, we:</p>
    <ul>
      <li>forward the notice by email, by hand, to the account holder it concerns, and tell the person who sent it that we did, or why we could not;</li>
      <li>keep records that identify that account holder for 6 months, or for 1 year if the claimant starts court proceedings and tells us
        within those 6 months.</li>
    </ul>
    <p>A notice that includes an offer to settle or a demand for payment does not have to be forwarded. Forwarding a notice does not mean
      the account holder infringed, and the law does not require us to remove the content. The owner still reviews it as described below.</p>
  </> },
  { id: "process", title: "What we do with a notice", body: <>
    <ul>
      <li>The owner of ClutchClips reads every notice and reviews it by hand. We may ask for missing details. Nothing is removed until the
        owner has decided.</li>
      <li>If the notice is valid, the owner removes the content with an admin command. For a video imported from a link, it deletes the
        imported upload, every clip made from it and all their files, from that link or from all of one account&apos;s imports. Jobs still
        waiting or running on it are stopped and their credits go back to the account. Removed files are deleted, not hidden.</li>
      <li>A video uploaded as a file is removed by hand. All videos are deleted 7 days after upload in any case.</li>
      <li>The owner tells the account holder by email what was removed and why, and how to send a counter-notice.</li>
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
    <p>The owner reviews a counter-notice by hand and forwards a valid one, including your name and address, to the person who sent the
      notice. Under the DMCA, removed material may be put back 10 to 14 business days after a valid counter-notice unless that person
      tells us they have filed a court action.</p>
    <p>Removal deletes the files, so we cannot restore them ourselves. Once that period passes without a court action, you may upload the
      video again. <Decision>how a valid counter-notice is handled, given that removal deletes the files</Decision></p>
  </> },
  { id: "repeat", title: "Repeat infringers", body: <>
    <p>We terminate the accounts of repeat infringers (17 U.S.C. 512(i)):</p>
    <ul>
      <li>An account is terminated when it receives three strikes.</li>
      <li>A strike counts only for a valid notice that was not withdrawn and was not successfully countered.</li>
      <li>For a serious violation, we may terminate an account at once, without three strikes.</li>
    </ul>
    <p>Today the owner keeps the count and decides each case by hand, and tells the account holder by email. <Decision>which cases count as serious, and whether strikes expire</Decision></p>
  </> },
  { id: "misrepresentation", title: "False notices", body: <>
    <p>Under 17 U.S.C. 512(f), a person who knowingly and materially misrepresents that material infringes, or that it was removed by
      mistake, can be liable for damages, including costs and lawyers&apos; fees. Before you send a notice, consider whether the use could be
      fair use or fair dealing.</p>
  </> },
  { id: "likeness", title: "Your face, voice or name", body: <>
    <p>If a clip on ClutchClips shows you, uses your voice, or impersonates you without your consent, email{" "}
      <Mail to={CONTACT.copyright} subject="Likeness report" /> with the subject &ldquo;Likeness report&rdquo;.
      Include the clip or source link, who you are, and what is wrong. The owner reviews it by hand, the same way as a copyright notice.
      The <Link href="/acceptable-use/">Acceptable Use Policy</Link> bans deceptive impersonation and synthetic content of real people
      without their consent.</p>
  </> },
];

export default function Copyright() {
  return <LegalPage id="copyright" sections={sections} intro={<p>How to report content that infringes your copyright or uses your likeness,
    what we do with a report, and how to respond if your content was removed.</p>} />;
}
