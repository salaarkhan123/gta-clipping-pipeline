// The site's legal policies, the same list the API serves (GET /v1/legal/policies, app/legal.py).
// tests/test_legal_pages.py fails when an id, version, effective date or path here differs from app/legal.py,
// or when a page file is missing. A material change gets a new version in app/legal.py first, then here.
export type Policy = { id: string; title: string; version: string; effective: string; path: string; required: boolean };

export const POLICIES: Policy[] = [
  { id: "terms", title: "Terms of Service", version: "1.0-draft", effective: "2026-11-18", path: "/terms/", required: true },
  { id: "privacy", title: "Privacy Policy", version: "1.0-draft", effective: "2026-11-18", path: "/privacy/", required: true },
  { id: "acceptable-use", title: "Acceptable Use Policy", version: "1.0-draft", effective: "2026-11-18", path: "/acceptable-use/", required: true },
  { id: "copyright", title: "Copyright and DMCA Policy", version: "1.0-draft", effective: "2026-11-18", path: "/copyright/", required: false },
  { id: "refunds", title: "Refund Policy", version: "1.0-draft", effective: "2026-11-18", path: "/refunds/", required: false },
  { id: "cookies", title: "Cookie Notice", version: "1.0-draft", effective: "2026-11-18", path: "/cookies/", required: false },
];

export const policy = (id: string): Policy => {
  const p = POLICIES.find((x) => x.id === id);
  if (!p) throw new Error(`No policy ${id}`);
  return p;
};

// Facts only the owner can give. Each renders as a visible [OWNER: …] marker (components/LegalPage.tsx `Owner`)
// until the owner replaces the text here with the real value and removes the marker. A production build refuses
// to ship a page that still shows one (scripts/check-legal.mjs); LEGAL_PREVIEW=1 builds the drafts.
export const OWNER = {
  entity: "legal entity name (or your full name as a sole proprietor)",
  address: "postal address",
  privacyOfficer: "privacy officer's name and title",
  dmcaAgent: "designated DMCA agent: name and postal address",
  dmcaRegistration: "register the agent at dmca.copyright.gov (US$6, renewed every 3 years); not done yet",
  resendRegion: "Resend's sending region",
  spacesRegion: "confirm the object storage region (expected Toronto, TOR1)",
  sentryRegion: "confirm whether Sentry is used and its region (US or EU)",
  dpas: "confirm each provider's data processing agreement is accepted (Resend, Anthropic, DigitalOcean, Stripe, Sentry)",
} as const;

// The site's email addresses (owner, 2026-11-18).
export const CONTACT = {
  privacy: "privacy@clutchclips.io",       // privacy requests; the privacy officer
  copyright: "copyright@clutchclips.io",   // copyright and DMCA notices, likeness reports
  support: "support@clutchclips.io",       // support and questions about the Terms
  general: "contact@clutchclips.io",       // general contact
} as const;
export const SUPPORT_EMAIL = CONTACT.support;
