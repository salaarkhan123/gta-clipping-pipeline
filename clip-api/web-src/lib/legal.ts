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
// until the owner replaces the text here with the real value and removes the marker.
export const OWNER = {
  entity: "legal entity name (or your full name as a sole proprietor)",
  address: "postal address",
  privacyOfficer: "privacy officer's name and title",
  privacyEmail: "privacy contact email",
  dmcaAgent: "designated DMCA agent: name, postal address, email and phone, as registered with the US Copyright Office",
  dmcaEmail: "DMCA agent email",
  governingLaw: "governing law and courts (suggested: the Province of Alberta, courts in Edmonton)",
  emailProvider: "email provider, its region and how long it keeps messages",
  spacesRegion: "confirm the object storage region (expected Toronto, TOR1)",
  sentryRegion: "confirm whether Sentry is used and its region (US or EU)",
  dpas: "confirm each provider's data processing agreement is accepted in its dashboard",
} as const;

// The site's existing support address (contact page, footer).
export const SUPPORT_EMAIL = "support@clutchclips.io";
