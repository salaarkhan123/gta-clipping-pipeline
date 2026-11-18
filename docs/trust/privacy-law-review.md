# Privacy and copyright law review

> **Draft for a lawyer, not legal advice.** Written by an AI agent from the code and from public sources read on
> 2026-11-17. The owner must have it reviewed by a lawyer licensed in Alberta (Canada), and by EU/UK data
> protection counsel before targeting users there. Facts only the owner knows are marked **[OWNER: …]**.

The facts about what we collect are in [data-map.md](data-map.md). This file says which laws apply, what each one
asks for, what the code does today, the gaps, and the decisions the owner has to make.

## 1. Who we are, for these laws

- An individual (sole proprietor) in Edmonton, Alberta, selling a paid online service to users anywhere.
  **[OWNER: legal entity name, if incorporated; postal address; privacy contact email.]**
- We are the **controller** (EU/UK term) or the **organization** (Canadian term) for account, billing and usage
  data. For the videos users upload we also act as controller: we decide how they are processed (no customer
  contract makes us a processor today).
- We do not sell personal data, show ads, or use tracking cookies.

## 2. Which laws apply

| Law | Applies? | Why |
|---|---|---|
| **Alberta PIPA** | Yes | Private-sector organisation in Alberta; PIPA covers its collection, use and disclosure within Alberta |
| **PIPEDA** (federal) | Yes | Personal information crossing provincial or national borders in commercial activity (users outside Alberta, US providers) |
| **Quebec Law 25** (Act respecting the protection of personal information in the private sector) | Only if we serve Quebec residents | It covers businesses that collect personal information of people in Quebec. **[OWNER: do we accept Quebec users?]** Safe default: assume yes, the site is open to all of Canada |
| **GDPR** | Likely, if we offer the service to people in the EU (Art. 3(2)(a)): open sign-up, prices in USD, English site | Not "targeting" by itself, but any marketing to EU users or EU-specific pricing would settle it. **[OWNER: do we target the EU?]** |
| **UK GDPR** | Same test as GDPR | |
| **CCPA/CPRA** (California) | Not yet | Thresholds: over US$25 m revenue (adjusted), or buy/sell/share data of 100,000+ consumers, or 50%+ revenue from selling/sharing. We meet none |
| Other US state laws (Virginia, Colorado, Texas, …) | Not yet | Thresholds are 100,000 residents' data (Texas: any business that is not a small business, but its own small-business exemption covers us) |
| **COPPA** (US) and children's codes | Must not apply | The Terms must set a minimum age (proposal: 18, or 16 with parental consent: **owner decision**) |

## 3. Canada: PIPEDA and Alberta PIPA

| Duty | What we do today | Gap / action |
|---|---|---|
| Accountability: a named person responsible | Nobody is named | Name the owner as privacy officer on `/privacy` **[OWNER: title and email]** |
| Identify purposes; consent | Purposes will be on `/privacy`. Sign-up records acceptance of the Terms and the Privacy Policy (this PR) | Website must send `accept_policies` (#147) |
| Limit collection | We collect email, password, sign-up IP, videos | Sign-up IP has no stated purpose beyond abuse checks: keep for 90 days, then clear (proposal, #150) |
| Limit use, disclosure, retention | Videos and clips: 7 days. Others: no limit | Retention durations (#150) |
| Accuracy | Users can change their password, not their email | Email change is a gap (low priority) |
| Safeguards | argon2 passwords, hashed API keys, private bucket, signed links (1 h), HTTPS | Breach response plan (below) |
| Openness | `/privacy` (#147) | |
| Individual access | No export | `GET /v1/me/export` (#149). PIPEDA: answer within 30 days |
| Challenging compliance | — | Privacy contact on `/privacy` |
| **Breach reporting** | No process | Report to the OPC (and Alberta OIPC, PIPA s.34.1) and notify people when a breach creates a "real risk of significant harm"; keep a record of **every** breach for 24 months ([OPC](https://www.priv.gc.ca/en/privacy-topics/privacy-for-businesses/privacy-breaches-at-your-business/breach_101/breach_records/), [OIPC](https://oipc.ab.ca/breach-notification/)). Owner keeps a breach log |
| Transfers outside Canada | Anthropic (US), Stripe (US), Sentry (US/EU) | Allowed under PIPEDA with notice; `/privacy` must say data may be processed in the US. PIPA s.13.1 requires notice of service providers outside Canada and a contact for questions |

## 4. Quebec Law 25 (if we serve Quebec)

| Duty | Status |
|---|---|
| Person in charge of personal information: by default the person with the highest authority; title and contact published on the website ([CAI](https://www.cai.gouv.qc.ca/protection-renseignements-personnels/sujets-et-domaines-dinteret/principaux-changements-loi-25)) | The owner. Publish on `/privacy` **[OWNER]** |
| Privacy impact assessment **before** communicating personal information outside Quebec | Needed for Anthropic, Stripe, DigitalOcean (outside Quebec, even Toronto), Sentry. A short written assessment per provider. **Owner action** |
| Confidentiality incident register and notification to the CAI | Same breach log as above |
| Privacy by default; consent in clear terms, separately for each purpose | No tracking at all; AI processing is part of the service and is stated |
| Right to data portability (structured format) | `GET /v1/me/export` JSON (#149) |
| Automated decisions: inform people when a decision is based exclusively on automated processing | Our AI ranks and titles clips; it makes no decision about the person. State it on `/privacy` |
| Policy in French | Law 25 and the Charter of the French language expect French for Quebec consumers. **Owner decision**: translate `/privacy` and `/terms` before marketing in Quebec |

## 5. GDPR and UK GDPR (if offered to EU/UK users)

**Lawful bases (proposal):**

| Processing | Basis |
|---|---|
| Account, login, running jobs, storing videos and clips, emails about the account | Contract (Art. 6(1)(b)) |
| Payments, invoices, ledger, tax records | Contract; legal obligation (6(1)(c)) for tax records |
| AI judge, titles, transcripts | Contract: it is the service the user asks for |
| Sign-up IP, rate limits, abuse and fraud checks, import log, takedown records | Legitimate interests (6(1)(f)): security, defending legal claims, copyright duties |
| Error monitoring (Sentry) | Legitimate interests |
| Policy acceptance records | Legal obligation / legitimate interests (proof of consent and terms) |
| Faces and voices in uploaded videos | Not special-category data as we use it: face detection finds a box for layout and creates no biometric template for identification (Art. 9 covers biometric data "for the purpose of uniquely identifying"). **Counsel to confirm** |

**Rights** (access, rectification, erasure, restriction, portability, objection): access and portability via
`GET /v1/me/export`, erasure via account deletion (#149), others by email to the privacy contact. Answer within one
month.

**International transfers:** our own servers are in Canada, which has an EU adequacy decision for commercial
organisations under PIPEDA. Onward transfers to US providers: Stripe and DigitalOcean are certified under the
EU-US Data Privacy Framework and also offer SCCs; Anthropic's DPA incorporates SCCs (Modules 2 and 3) and the UK
addendum; Sentry is DPF-certified with SCCs as fallback. **Owner action:** accept each provider's DPA in its
dashboard.

**Representative (Art. 27):** a controller outside the EU that offers services to people in the EU must appoint an
EU representative unless processing is occasional, not large-scale special-category data, and unlikely to risk
people's rights. Our processing is continuous, so the exemption is doubtful. Same for a UK representative.
**Owner decision:** appoint representatives (paid services exist) before marketing in the EU/UK, or state that the
service is not offered there.

**Records of processing (Art. 30)** and a **DPIA** (Art. 35) for AI processing of videos with faces: the data map is
a start; counsel to decide whether a DPIA is required.

## 6. US state laws (CCPA/CPRA and similar)

We are below every threshold today, so these laws do not apply yet. We still write `/privacy` so it would meet
them: notice at collection (categories and purposes are in the policy), a plain statement that we do **not sell or
share** personal information for cross-context behavioural advertising (true: no ads, no trackers), no sensitive
personal information used to infer characteristics, and the same rights process for everyone. Re-check when
revenue passes US$25 m or 100,000 California users.

## 7. Copyright: Canada and the US

### Canada: notice-and-notice (Copyright Act ss. 41.25–41.27)

- A copyright owner may send a notice of claimed infringement to a provider of "digital memory" (us, hosting
  uploads). We must **forward it to the person** whose account it concerns and tell the claimant we did, or why we
  could not, and **keep records** that identify that person for **6 months**, or **1 year** if the claimant starts
  court proceedings and tells us within those 6 months
  ([s. 41.26](https://laws-lois.justice.gc.ca/eng/acts/C-42/section-41.26.html)).
- The regime does not require us to remove anything. Hosting immunity (s. 31.1(4)) is lost if we know of a court
  decision that the content infringes.
- **How we meet it:** the takedown form (#145) records the notice; case decisions (#146) email the reported user
  with the notice and record that it was forwarded; case records are kept at least 1 year (#150).

### United States: DMCA safe harbour (17 U.S.C. 512(c))

To keep the safe harbour we must:

1. **Designate an agent** with the US Copyright Office (online directory, US$6 per designation, renewed every
   3 years: [copyright.gov](https://www.copyright.gov/dmca-directory/faq.html)) and publish the same contact on the
   site. **Owner action:** register at https://dmca.copyright.gov/osp/ and fill **[OWNER: DMCA agent name, address,
   email, phone]** on `/copyright`.
2. Act **expeditiously** to remove or disable access on a notice that substantially complies with 512(c)(3).
   Our process: an admin reviews and disables pending review (#146). Nothing is removed automatically on an
   unverified complaint; the admin decides.
3. On a valid **counter-notice** (512(g)(3)), forward it to the claimant and restore the content in 10 to 14
   business days unless the claimant files a court action (#146).
4. Adopt and reasonably implement a **repeat-infringer policy** (512(i)) and say so in the Terms: default 3 verified
   strikes in 365 days suspends the account (#146, owner decision).
5. Not have actual knowledge or red-flag knowledge and not receive a financial benefit directly from infringement
   we can control.

## 8. Likeness, AI and synthetic content

- Users upload streams that show their face and voice and, often, other people (co-streamers, chat names).
  The Terms require users to have the rights and consents for everything they upload and every face in it.
- Alberta has no general statutory personality right; the common-law tort of appropriation of personality applies.
  Quebec's Civil Code (arts. 3, 35–36) protects image and reputation. Many US states have right-of-publicity laws.
- AI thumbnails (#140) edit a frame that contains a face. The Acceptable Use Policy bans deceptive impersonation and
  synthetic content of a real person without consent; the likeness report path (#145) handles complaints.
- Provider rules we pass through: Google bans impersonation "without explicit disclosure, in order to deceive";
  the first premium thumbnail of a clip needs the user's confirmation that they are the streamer or have their
  permission, and each confirmation is recorded (#152).

## 9. Link imports and platform terms

YouTube's terms ban downloading without express authorisation, Kick's ban scraping and access by means other
than those it provides, and Twitch's (could not be fetched; search snippets only) ban data gathering tools.
User consent does not override a platform's terms, which bind the user and arguably us. We import only public,
non-DRM videos the user says they own or may clip, never evade a block, and log every import (`import_log`).
**Owner decision:** counsel should look at whether link import should stay on, particularly for YouTube.

## <a id="providers"></a>10. Providers

| Provider | Role | Retention (their documents, read 2026-11-17) | Training on our data | Transfer basis |
|---|---|---|---|---|
| DigitalOcean (droplet, Spaces) | Processor: hosting | Deleted within 30 days of account deactivation; backups until disposed ([DPA](https://www.digitalocean.com/legal/data-processing-agreement)) | No | DPF, SCCs |
| Anthropic (Claude API) | Processor | Inputs and outputs deleted within 30 days; flagged content up to 2 years ([privacy center](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data)). The developer docs say prompts are not retained by default except for some models; we state 30 days unless a zero-retention agreement is signed | No ([commercial terms](https://www.anthropic.com/legal/commercial-terms)) | SCCs in the [DPA](https://www.anthropic.com/legal/data-processing-addendum); storage at rest in the US |
| Stripe | Processor for payments; independent controller for fraud, AML and its own purposes ([DPA](https://stripe.com/legal/dpa)) | As long as it provides the service, longer for legal duties ([privacy](https://stripe.com/privacy)) | n/a | DPF, SCCs, UK IDTA |
| Sentry (optional) | Processor | 30 days (Developer) or 90 days (Team) for errors ([docs](https://docs.sentry.io/security-legal-pii/security/data-retention-periods/)) | No | DPF, SCCs |
| Email provider | Processor | Not chosen. Postmark 45 days, Resend 30 days by default | — | — |
| Google Gemini, paid tier (#152, off) | Processor | 55 days for abuse monitoring ([policy](https://aistudio.google.com/docs/usage-policies)); requests sent with `store: false` | Not on the paid tier ([terms](https://aistudio.google.com/docs/terms)). The free tier trains on inputs: never used | Google DPA |
| Black Forest Labs | **Not used** (removed in #152) | "As long as reasonably necessary" ([privacy](https://bfl.ai/legal/privacy-policy)) | **Yes by default**, with no API flag or account setting to turn it off | — |
| Twitch, Kick, YouTube | Sources of imported videos | n/a: we receive data from them | — | — |

## 11. Owner decisions

| # | Decision | Safe default used in the code and drafts |
|---|---|---|
| 1 | Legal entity name, address, privacy contact, DMCA agent | Placeholders `[OWNER: …]` on every page |
| 2 | Governing law and courts | Placeholder; suggestion: Alberta, courts in Edmonton |
| 3 | Serve Quebec? Translate policies to French? | Assume yes; English drafts only |
| 4 | Target the EU/UK? Appoint representatives? | Not targeted; no representative; drafts still give GDPR rights to everyone |
| 5 | Minimum age | 18 (16 with a parent's consent is an option) |
| 6 | Require terms acceptance from API clients (`REQUIRE_TERMS_ACCEPTANCE`) | Off; the website always sends it |
| 7 | Retention durations (#150) | Proposed in #150 |
| 8 | Zero-data-retention agreement with Anthropic | Not signed; policy states 30 days |
| 9 | Image providers for premium thumbnails | Decided (owner, 2026-11-18): Gemini paid tier only, `store: false`; no provider that trains on API inputs. BFL removed |
| 10 | Keep YouTube link import | Unchanged (best effort, "may fail") pending counsel |
| 11 | Quebec privacy impact assessments, provider DPAs accepted | Owner action |

## 12. Outstanding compliance items

Decided by the owner on 2026-11-18 as still open, not solved. The legal pages (#147) mark them.

| Item | Status |
|---|---|
| French versions of `/privacy` and `/terms` for Quebec (Law 25, Charter of the French language) | Open: needed before marketing in Quebec |
| EU and UK representatives (GDPR and UK GDPR Art. 27) | Open: appoint before marketing in the EU or UK, or state the service is not offered there |
| EU/UK 14-day withdrawal: checkout does not yet ask for consent to immediate use | Open: counsel to confirm wording and whether Stripe Checkout must ask |
