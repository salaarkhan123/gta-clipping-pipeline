import type { Metadata } from "next";
import Link from "next/link";
import { Ext, LegalPage, Table } from "@/components/LegalPage";

// Matches docs/trust/data-map.md section 7: no cookies, no analytics; localStorage keys from lib/api.ts (cc_token)
// and lib/edit.ts (unsent editor drafts).
export const metadata: Metadata = { title: "Cookie Notice · ClutchClips" };

const sections = [
  { id: "cookies", title: "Cookies", body: <>
    <p>The ClutchClips website and API set no cookies. We use no analytics, no advertising and no tracking pixels, so there is nothing to
      accept or refuse.</p>
  </> },
  { id: "storage", title: "What your browser keeps", body: <>
    <p>The website keeps two things in your browser&apos;s local storage. Both are needed for the service to work, and neither is sent to
      anyone else.</p>
    <Table head={["Item", "What it is for", "How long"]} rows={[
      [<code key="t" className="whitespace-nowrap">cc_token</code>, "Keeps you logged in. It is sent only to the ClutchClips API.", "Valid for 7 days; removed when you log out"],
      ["Editor drafts", "Clip edits you have not saved yet, so they are not lost if the page closes.", "Until you save or discard the edit"],
    ]} />
    <p>You can clear them in your browser&apos;s settings at any time. You will then be logged out, and unsaved edits are lost.</p>
  </> },
  { id: "others", title: "Other sites", body: <>
    <ul>
      <li>Payments and the billing portal are Stripe&apos;s own pages. Stripe sets its own cookies there; see{" "}
        <Ext href="https://stripe.com/legal/cookies-policy">Stripe&apos;s cookie policy</Ext>.</li>
      <li>Fonts are bundled with the website, so no request goes to Google Fonts or any other font service.</li>
      <li>The API reference at api.clutchclips.io/docs loads its viewer from the jsDelivr CDN, which sees your IP address and browser
        details like any website you visit.</li>
    </ul>
  </> },
  { id: "changes", title: "Changes", body: <>
    <p>If we ever add cookies or analytics that are not strictly needed, we will update this notice first and ask for your consent where
      the law requires it. Our <Link href="/privacy/">Privacy Policy</Link> covers everything else we collect.</p>
  </> },
];

export default function Cookies() {
  return <LegalPage id="cookies" sections={sections} intro={<p>The short version: no cookies, no tracking.</p>} />;
}
