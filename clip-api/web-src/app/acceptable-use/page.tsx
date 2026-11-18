import type { Metadata } from "next";
import Link from "next/link";
import { LegalPage, Owner } from "@/components/LegalPage";
import { OWNER, SUPPORT_EMAIL } from "@/lib/legal";

export const metadata: Metadata = { title: "Acceptable Use Policy · ClutchClips" };

const sections = [
  { id: "content", title: "Content you must not upload", body: <>
    <ul>
      <li>Videos you do not own and have no permission to clip, or anything else that infringes copyright, trademarks or other rights.</li>
      <li>Videos that show people, or use their voice or name, without the rights and consents you need. See the{" "}
        <Link href="/terms/">Terms of Service</Link>.</li>
      <li>Any sexual content involving a minor. We report it to the authorities.</li>
      <li>Content that is illegal where you live or in Canada, including content that threatens, incites violence or promotes terrorism.</li>
    </ul>
  </> },
  { id: "people", title: "Respect for real people", body: <>
    <ul>
      <li>Do not use clips, titles or captions to impersonate a real person in a way meant to deceive.</li>
      <li>Do not make or publish synthetic or altered content of a real person (face, voice or body) without their consent, or present it as real.</li>
      <li>Do not use ClutchClips to harass, bully, threaten, dox or shame anyone.</li>
    </ul>
  </> },
  { id: "service", title: "Using the service fairly", body: <>
    <ul>
      <li>Do not use link import to get around a site&apos;s block, paywall, age gate, login or rate limit, or to import DRM-protected or
        private videos. Import only public videos you own or may clip.</li>
      <li>Do not abuse the API: stay within the rate limits and your plan&apos;s limits, and do not overload or disrupt the service.</li>
      <li>Do not reverse engineer, probe or work around our limits, credit checks or security, and do not access accounts or data that are not yours.</li>
      <li>Do not create several accounts to collect free credits.</li>
      <li>Do not sell, rent or share your account or API keys. Agencies that clip for several creators can contact us for a team setup.</li>
      <li>Do not use the service to send spam or malware.</li>
    </ul>
  </> },
  { id: "report", title: "How to report a problem", body: <>
    <ul>
      <li>Copyright: send a notice to our designated agent, as the <Link href="/copyright/">Copyright and DMCA Policy</Link> explains.</li>
      <li>Your face, voice or name used without consent, impersonation, or anything else in this policy: email{" "}
        <a href={`mailto:${SUPPORT_EMAIL}?subject=Likeness%20report`}>{SUPPORT_EMAIL}</a> with the clip or source link and what is wrong.</li>
      <li>Privacy: email our privacy contact, <Owner>{OWNER.privacyEmail}</Owner>.</li>
    </ul>
    <p>The owner of ClutchClips reads and reviews every report by hand, and replies by email.</p>
  </> },
  { id: "enforcement", title: "What we do", body: <>
    <p>Depending on how serious it is, we may remove content, suspend or close the account, and report illegal content to
      the authorities. We terminate the accounts of repeat infringers (17 U.S.C. 512(i)) after three strikes, as the{" "}
      <Link href="/copyright/">Copyright and DMCA Policy</Link> explains, and may terminate an account at once for a serious violation.
      Where we can, we tell you what we did and why, and you can reply to the same email to ask us to look again.</p>
  </> },
];

export default function AcceptableUse() {
  return <LegalPage id="acceptable-use" sections={sections} intro={<p>What you can and cannot do with ClutchClips. It is part of the{" "}
    <Link href="/terms/">Terms of Service</Link>.</p>} />;
}
