# Launch checklist: legal and compliance

What must be done before the legal pages (#147) can go live, and before marketing outside Canada. Until every row
that unblocks "production legal pages" is done, a production build shows a short "This policy is being finalised"
page on `/privacy`, `/terms`, `/copyright`, `/cookies`, `/refunds` and `/acceptable-use`, and `npm run build` fails
if any page still shows an `[OWNER …]` placeholder (`clip-api/web-src/scripts/check-legal.mjs`). The drafts are
visible only in a preview build (`LEGAL_PREVIEW=1`, see `clip-api/web-src/README.md`).

Sources: [privacy-law-review.md](trust/privacy-law-review.md) (sections 7, 10, 11, 12) and
[data-map.md](trust/data-map.md). Owner decisions dated 2026-11-18.

| # | Item | Status | Owner | Blocker | Unblocks |
|---|---|---|---|---|---|
| 1 | Incorporate (or confirm operating as a sole proprietor) | Open | Owner | Decision on the business structure | The legal entity name and postal address in the Terms and Privacy Policy (`OWNER.entity`, `OWNER.address`) |
| 2 | Register the DMCA designated agent at [dmca.copyright.gov](https://dmca.copyright.gov/osp/) (US$6, renewed every 3 years) | Open | Owner | Item 1 (the registration names the service provider and its address) | The agent's name and address on `/copyright`; the DMCA safe harbour (17 U.S.C. 512(c)(2)). Notices already go to copyright@clutchclips.io |
| 3 | Accept data processing agreements: Resend, Anthropic, the transcription provider once one is chosen (transcription runs on our own server today), Gemini paid tier, and storage (Cloudflare R2 or DigitalOcean Spaces) | Open | Owner | Item 1 for the contracting party; provider choices for transcription and storage | The transfer-safeguard statement on `/privacy` (`OWNER.dpas`); Gemini for premium thumbnails (#152) |
| 4 | Quebec: French versions of `/privacy` and `/terms` (Charter of the French language as amended by Law 96; Law 25), and privacy impact assessments for transfers outside Quebec | Open | Owner, translator | Final English text (item 6) | Marketing in Quebec |
| 5 | EU and UK: appoint an Art. 27 representative in each, and have the GDPR / UK GDPR position reviewed (lawful bases, transfers, whether a DPIA is needed) | Open | Owner, EU/UK counsel | Decision to market in the EU or UK | Marketing in the EU or UK |
| 6 | Lawyer's review of all six policies, ideally a lawyer licensed in Alberta | Open | Owner, lawyer | Items 1, 7 | Removing "Draft: pending legal review" and every "[Subject to legal review]" mark |
| 7 | Appoint the privacy officer; their name and title are published on `/privacy` | Open | Owner | None | `OWNER.privacyOfficer`; PIPEDA and Law 25 accountability. Requests already go to privacy@clutchclips.io |
| 8 | Confirm the remaining facts: Resend sending region, object storage region, whether Sentry is used and its region | Open | Owner | None | `OWNER.resendRegion`, `OWNER.spacesRegion`, `OWNER.sentryRegion` on `/privacy` |
| 9 | Settle the open owner decisions: which violations count as serious, whether strikes expire, counter-notice handling, minimum age, unused paid credits if the service closes | Open | Owner | Item 6 for the wording | The `[OWNER DECISION: …]` marks on the pages |
| 10 | Remove every placeholder: fill `OWNER` in `clip-api/web-src/lib/legal.ts`, resolve every `[OWNER DECISION]`, then drop the stub in `components/LegalPage.tsx` | Open | Owner, builder | Items 1–9 | The production guard passes and the policies go live |
