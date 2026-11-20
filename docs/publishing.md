# Publishing: research and design (Stage 1)

Status: research and proposal only. Nothing is built, registered, paid for or posted. Stage 2 (the build, behind `PUBLISHING=false`) starts after the owner answers section 8.

Scope: customers connect their accounts once, then publish or schedule a finished clip to YouTube (Shorts), Instagram (Reels), TikTok, Facebook, LinkedIn and X from the clip page, with a title and caption per platform. This is SPEC.md section 13 items 4.0 to 4.2 and the "E2" row in `docs/CONTRACTS.md`.

How to read this: every platform fact below comes from the platform's own documentation or terms, read on **2026-11-18**, with the URL next to it. Where a page did not state something, this document says "not stated" instead of filling the gap. Limits and prices change; re-check the linked page before acting on a number.

## 1. Summary

| Platform | Official API | Review before the public can use it | Stated timeline | Cost | Main limits |
|---|---|---|---|---|---|
| YouTube (Shorts) | YouTube Data API v3 `videos.insert` | Google OAuth app verification (brand, and scope verification if the upload scope is classed sensitive). A YouTube compliance audit only to raise quota | Not stated for our case. Google says verification "might require several months" depending on the data | Free | **100 uploads a day for the whole project** (all customers together), 256 GB a file, Shorts up to 3 minutes |
| TikTok | Content Posting API, Direct Post | App review for the `video.publish` scope, then an **audit**. Until the audit passes every post is private and only 5 users can post a day | Not stated | Free | About 15 posts a day per creator, 4 GB, length per creator (3 to 10 minutes) |
| Instagram (Reels) | Instagram Platform content publishing (Instagram Login) | Meta App Review for Advanced Access, plus Business Verification | App Review: "typically less than one week, often 2–3 days". Business Verification: not stated | Free | Professional accounts only, 300 MB, 3 s to 15 min, 100 posts per 24 h (another page says 50) |
| Facebook | Reels Publishing API, Pages only | Same Meta app, review and verification as Instagram | Same as Instagram | Free | Pages only (no personal profiles), 3 to 90 s, 9:16, 30 reels per 24 h per Page |
| X | X API v2 `POST /2/tweets` with chunked media upload | No app review. A use-case description that is binding | Immediate | **Paid per request: $0.015 a post, $0.20 if the post contains a URL** | 20 min and 8 GB (125 min and 16 GB for Premium accounts) |
| LinkedIn | Videos API and Posts API | Video posting is documented under the Community Management API: vetting of a **registered legal organization**, Development tier, then a Standard tier review | Not stated | Free | 3 s to 30 min, 75 KB to 500 MB, MP4 only. Development tier: 500 calls a day per app |

Recommended order (section 7): YouTube, then TikTok (start its audit paperwork first, it is the slowest gate), then Instagram and Facebook together, then X if the owner accepts a per-post cost, LinkedIn last or not at all.

## 2. Per platform

### 2.1 YouTube (Shorts)

| Item | Finding | Source |
|---|---|---|
| API | `videos.insert` (resumable upload). There is no separate Shorts endpoint | https://developers.google.com/youtube/v3/docs/videos/insert (page dated 2026-11-12) |
| What makes it a Short | Help Center: Shorts are "up to 3 minutes long", vertical, with a maximum resolution of 1080p. How an API upload is classed as a Short is **not stated** on the pages read; to be confirmed with a test upload on the owner's own channel | https://support.google.com/youtube/answer/10059070 |
| Scopes | `youtube.upload` is enough to upload. We also need the channel's name to show which account is connected: `youtube.readonly` (`channels.list`, 1 unit) | videos/insert page, "Authorization" |
| Unreviewed apps post privately? | **No longer.** Revision history, November 2, 2026: uploads "from unverified API projects are no longer restricted to private viewing mode. This change reverses the policy announced on July 28, 2020" | https://developers.google.com/youtube/v3/revision_history |
| Default privacy | If `status.privacyStatus` is not sent the video is **public**. We must always send it | videos/insert page |
| Quota | "100 search.list calls, 100 videos.insert calls, and 10,000 units per day combined for all other endpoints". `videos.insert` costs 1 unit in its own "Video Uploads" bucket. `videos.update` 50, `thumbnails.set` 50, `channels.list` 1 | https://developers.google.com/youtube/v3/determine_quota_cost (2026-11-12) |
| Raising quota | Needs a compliance audit: "YouTube API Services - Audit and Quota Extension Form". Timeline: "as soon as possible", no number | https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits (2026-11-12) |
| File limits | 256 GB; MIME `video/*` or `application/octet-stream` | videos/insert page |
| Scheduling | `status.publishAt` exists. We do not need it; see section 4.4 | videos/insert page |
| Other fields to send | `status.selfDeclaredMadeForKids`, `status.containsSyntheticMedia`. Since 2026-11 `paidProductPlacementDetails.hasPaidProductPlacement` no longer defaults to false, so we send it explicitly from the customer's choice | revision history, November 2026 |
| OAuth app verification | Apps that use sensitive or restricted scopes "must complete Google's OAuth app verification". Until verified: an "unverified app" screen and a cap of **100 new users in total**. Needs: homepage on a verified domain (not just a login page), privacy policy on the same domain, domain verified in Search Console, and for sensitive scopes a demo video of the whole flow including the consent screen | https://support.google.com/cloud/answer/13463073 · https://support.google.com/cloud/answer/13464321 · https://support.google.com/cloud/answer/7454865 |
| Is `youtube.upload` sensitive? | **Not stated** on the pages read. The Cloud Console shows the class when the scope is added. Plan for "yes" | – |
| Testing mode | A project with consent screen in "Testing" issues refresh tokens that expire in 7 days. Limit: 100 refresh tokens per Google account per client | https://developers.google.com/identity/protocols/oauth2 (2026-10-29) |
| Revoke | `POST https://oauth2.googleapis.com/revoke` | https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps |
| Fees | None | – |

What the 100-a-day cap means: it is per Google Cloud project, not per customer. With the default quota all ClutchClips customers together can publish 100 videos to YouTube a day. More needs the audit.

### 2.2 TikTok

| Item | Finding | Source |
|---|---|---|
| API | Content Posting API, Direct Post: `creator_info/query`, `video/init`, `status/fetch` | https://developers.tiktok.com/doc/content-posting-api-get-started · https://developers.tiktok.com/doc/content-posting-api-reference-direct-post |
| Scopes | `video.publish` (app "must be approved for the video.publish scope"), plus `user.info.basic` to show the account | get-started page · https://developers.tiktok.com/doc/tiktok-api-scopes |
| Unreviewed apps post privately? | **Yes.** "All content posted by unaudited clients will be restricted to private viewing mode." Unaudited: up to 5 users can post in 24 hours, their accounts must be private, and posts are `SELF_ONLY` | https://developers.tiktok.com/doc/content-sharing-guidelines |
| App review | App name must match the site, a "fully developed" website (not a landing or login page) with Privacy Policy and Terms links visible without opening a menu, an explanation of each scope, and at least one demo video of the end-to-end flow (up to 5 videos, 50 MB each) | https://developers.tiktok.com/doc/app-review-guidelines |
| Audit | Separate from app review; lifts the private-only restriction. The application includes usage estimates that set a 24-hour active creator cap. Timeline **not stated** | content-sharing-guidelines |
| Intended use | "API Clients should facilitate authentic creators to post original content". Listed as not acceptable: "An app that copies arbitrary contents from other platforms to TikTok" and "A utility tool to help upload contents to the account(s) you or your team manages" | content-sharing-guidelines |
| Required screen (checked in the audit) | Show the creator's nickname. Privacy chosen by the user from `privacy_level_options` **with no default**. Comment, Duet and Stitch switches, **off by default**, greyed out when the creator disabled them. Commercial content disclosure switch (your brand, branded content) with the exact label texts. The line "By posting, you agree to TikTok's Music Usage Confirmation" before the button. A preview of the video. Title and hashtags editable. Tell the user processing can take a few minutes. Stop when `creator_info` says the creator cannot post now, and check `max_video_post_duration_sec` | content-sharing-guidelines |
| Watermarks | No "brand name, logo, watermark, other promotional branding, link or promotional text" on or in content shared to TikTok. Also in the Developer Terms | content-sharing-guidelines · https://www.tiktok.com/legal/page/global/tik-tok-developer-terms-of-service/en |
| Media transfer | If the file is already on our server: "do not use FILE_UPLOAD; use PULL_FROM_URL instead". The URL must be https, must not redirect, must stay reachable for up to one hour, and must be under a **domain or URL prefix verified in the TikTok developer portal** | https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide |
| Video limits | MP4 (recommended), WebM, MOV. H.264 (recommended), H.265, VP8, VP9. 23 to 60 FPS. 360 to 4096 px each side. Max 4 GB. "All TikTok creators can post 3-minute videos, while some have access to post 5-minute or 10-minute videos" | media-transfer-guide |
| Caption | `title`, max 2200 UTF-16 units, hashtags and mentions inline | direct-post reference |
| Limits | Post init: 6 requests a minute per user token. Status fetch: 30 a minute. Posting cap "typically around 15 posts per day/creator account", shared across all apps | direct-post reference · https://developers.tiktok.com/doc/content-posting-api-reference-get-video-status · content-sharing-guidelines |
| Tokens | Access and refresh tokens with `expires_in` and `refresh_expires_in`; the doc says to schedule refreshes from those fields. Revoke endpoint exists and must be called when the user disconnects | https://developers.tiktok.com/doc/oauth-user-access-token-management |
| Scheduling | No scheduling field in Direct Post. We schedule on our side | direct-post reference |
| Fees | None | – |

### 2.3 Instagram (Reels)

| Item | Finding | Source |
|---|---|---|
| API | Instagram Platform content publishing: create a container (`POST /<IG_ID>/media`, `media_type=REELS`), poll `status_code`, then `POST /<IG_ID>/media_publish` | https://developers.facebook.com/docs/instagram-platform/content-publishing |
| Account type | Instagram **professional** accounts only (business or creator). Personal accounts cannot be published to. With Instagram Login no Facebook Page is needed | https://developers.facebook.com/docs/instagram-platform/overview · https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login |
| Scopes | Instagram Login: `instagram_business_basic`, `instagram_business_content_publish`. (Facebook Login variant: `instagram_basic`, `instagram_content_publish`, `pages_read_engagement`) | content-publishing page |
| Unreviewed apps | Standard Access works only for people with a role on the app. Serving other accounts needs **Advanced Access, which "requires App Review and Business Verification"** | overview page · https://developers.facebook.com/docs/graph-api/overview/access-levels |
| App Review | Reviewers test the live app; one successful API call per requested permission within the 30 days before submitting; screen recording. "It typically takes us less than one week to process your submission, and often takes only 2–3 days, but may take longer during peak periods" | https://developers.facebook.com/docs/resp-plat-initiatives/individual-processes/app-review/submission-guide · https://developers.facebook.com/docs/app-review/introduction |
| Business Verification | Meta verifies "your identity as a business entity" (business documents). Timeline **not stated** on the pages read. Yearly Data Use Checkup afterwards | https://developers.facebook.com/docs/development/release/business-verification · access-levels page |
| Media transfer | "We cURL media used in publishing attempts, so the media must be hosted on a publicly accessible server at the time of the attempt." Resumable upload is only for apps using Facebook Login | content-publishing page |
| Reel limits | MOV or MP4, moov atom at the front, H.264 or HEVC, AAC up to 48 kHz, 23 to 60 FPS, max 1920 px wide, 9:16 recommended, 25 Mbps max, **3 s to 15 min, 300 MB max** | https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media |
| Caption | Max 2200 characters, 30 hashtags, 20 @ tags | same page |
| Limits | "100 API-published posts within a 24-hour moving period" (content-publishing page); the carousel section and the limit endpoint's reference say 50. We read `quota_total` from `GET /<IG_ID>/content_publishing_limit` at run time and never assume | content-publishing page · https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/content_publishing_limit |
| Tokens | Short-lived token exchanged for a long-lived one valid 60 days; `refresh_access_token` extends it another 60 days | https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login |
| Scheduling | None in the API (a container expires if not published within 24 hours). We schedule on our side | content-publishing page |
| Fees | None | – |

### 2.4 Facebook

| Item | Finding | Source |
|---|---|---|
| API | Reels Publishing API: `POST /{page_id}/video_reels` (start, upload to `rupload.facebook.com`, finish) | https://developers.facebook.com/docs/video-api/guides/reels-publishing |
| Account type | "You can only publish Reels to Facebook Pages". Personal profiles are not supported | same page |
| Scopes | `pages_show_list`, `pages_read_engagement`, `pages_manage_posts` (Facebook Login) | same page |
| Unreviewed apps | Same Meta rules as Instagram: Advanced Access through App Review plus Business Verification before non-role users can connect | section 2.3 sources |
| Reel limits | 9:16, 1080×1920 recommended, minimum 540×960, 24 to 60 FPS, **3 to 90 seconds**, H.264 or H.265, fixed frame rate | same page |
| Longer clips | A clip over 90 s cannot be a Reel. It can go out as a Page video (Video API, same three permissions). The Page video size and length limits were **not stated** on the pages read | https://developers.facebook.com/docs/video-api/guides/publishing |
| Limits | "30 API-published posts within a 24-hour moving period" per Page for reels | reels-publishing page |
| Audience | "Publishing to a Page has implicit public scope, and only the 'Public' option should be available" | same page |
| Scheduling | `video_state=SCHEDULED` with `scheduled_publish_time` (more than 10 minutes ahead, within 29 days). We schedule on our side instead; see section 4.4 | same page |
| Tokens | Long-lived user token about 60 days; Page tokens are obtained from it | https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived |
| Fees | None | – |

### 2.5 X

| Item | Finding | Source |
|---|---|---|
| API | Chunked upload `POST /2/media/upload/initialize`, `/{id}/append`, `/{id}/finalize` with `media_category=tweet_video`, then `POST /2/tweets` | https://docs.x.com/x-api/media/quickstart/best-practices |
| Scopes | OAuth 2.0 with PKCE: `tweet.write`, `users.read`, `media.write`, `offline.access` (without it the token lasts two hours and there is no refresh token) | https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code |
| Review | No app review. "Your use case description is binding on you"; a changed use case needs approval first. One app per use case; no white-label copies | https://docs.x.com/developer-terms/policy |
| Fees | "The X API uses pay-per-usage pricing with no subscriptions." Credits are bought up front. **Post: Create $0.015 per request. Post: Create (with URL) $0.200 per request.** User read $0.010 per resource (to show the account name on connect). Media upload is not in the price table; to be confirmed in the Developer Console before launch. "Prices are subject to change" | https://docs.x.com/x-api/getting-started/pricing |
| Scale clause | Developer Agreement (last updated April 27, 2026), "Self-Serve Use": pay-per-use "is designed for hobbyists, commercial prototyping, initial development, early-stage X product integrations, and supporting applications with a limited number of end-users. If you use the X API beyond this scope, then you must apply (or already subscribe to) an Enterprise plan". Enterprise price not public | https://docs.x.com/developer-terms/agreement |
| Video limits | Default accounts: 0.5 s to 20 min, 8 GB. Premium: 125 min, 16 GB. H.264 High, AAC LC (not HE-AAC), 60 FPS or less, aspect between 1:3 and 3:1, YUV 4:2:0. Recommended 720×1280 portrait; "Unsubscribed users can upload a 720p video and get a 720p playback". The "Advanced" list also says dimensions "must be between 32x32 and 1280x1024", which conflicts with the 1080p line; to be settled with a test on the owner's account | best-practices page |
| Rate limits | `POST /2/tweets`: 100 per 15 min per user, 10,000 per 24 h per app. Media upload initialize, append, finalize: 1,875 per 15 min per user | https://docs.x.com/x-api/fundamentals/rate-limits |
| Scheduling | None in the API. We schedule on our side | – |

Cost example: 1,000 posts a month without links is $15; the same posts with a link in the text would be $200. Captions sent to X must not contain URLs unless the customer adds one and the price shown reflects it.

### 2.6 LinkedIn

| Item | Finding | Source |
|---|---|---|
| API | Videos API (upload, gives `urn:li:video:{id}`), then Posts API | https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/videos-api · https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api |
| Scopes | `w_member_social` (post as the member) or `w_organization_social` (post as a Page; the member must be an admin or content admin) | videos-api page |
| Member vs organization, and which product | The self-serve "Share on LinkedIn" product grants `w_member_social` without review, but its guide covers "text, URLs, and images" only. Video upload is documented in the Community Management API. Whether a Share-on-LinkedIn-only app may call the Videos API is **not stated**. Organization posting always needs the Community Management API | https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin · https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access |
| Community Management API vetting | "only available to registered legal organizations for commercial use cases". Business email (personal addresses fail), legal name, registered address, website, privacy policy; a super admin of the organization's LinkedIn Page must verify the app; the app name must not contain "Linked" or "In". A rejected app cannot re-apply; a new app is needed. Development tier first (500 calls a day per app, 100 per member, integration within twelve months), then a Standard tier form with a screen recording. Timeline **not stated** | https://learn.microsoft.com/en-us/linkedin/marketing/community-management-app-review · https://learn.microsoft.com/en-us/linkedin/marketing/increasing-access |
| Video limits | "Length: Three seconds to 30 minutes. File size: Between 75kb and 500MB. File format: MP4." | videos-api page |
| Rate limits | Per app and per member, per day, reset at midnight UTC. "Standard rate limits are not published in documentation"; they are shown in the Developer Portal | https://learn.microsoft.com/en-us/linkedin/shared/api-guide/concepts/rate-limits |
| Tokens | Access tokens 60 days. Programmatic refresh tokens (365 days) are "for all approved Marketing Developer Platform (MDP) partners"; otherwise the member re-authorizes every 60 days | https://learn.microsoft.com/en-us/linkedin/shared/authentication/programmatic-refresh-tokens |
| Scheduling | None in the API. We schedule on our side | – |
| Fees | None | – |

## 3. Terms that affect us

| Topic | What the terms say | What we do |
|---|---|---|
| Storing tokens | LinkedIn: "You may store the Application-specific Member tokens and authentication tokens". Meta: maintain "administrative, physical, and technical safeguards". TikTok: keep `client_secret` confidential. None forbids storing tokens for the purpose the user agreed to | Tokens encrypted at rest (section 4.1), never logged, never returned by the API |
| Delete on disconnect | YouTube (Developer Policies, III.D.2 and III.E.4): on revocation through us the token must be revoked "right away" and stored data deleted "within 7 calendar days"; on revocation at Google, "within 30 calendar days". TikTok: revoke when the user disconnects. Meta: delete Platform Data when the user asks or "no longer has an account with you". LinkedIn: "immediately delete all Content ... including the Member Token and the OAuth Access Token, upon request by that User, or when the User closes their account with you" | Disconnect revokes at the platform, then deletes the tokens and profile fields in the same request. Account deletion does the same for every connected account. A daily check drops accounts whose token the platform reports as revoked |
| Data deletion requests | Meta: the privacy policy must explain how to request deletion; a data deletion request callback (signed request in, status URL and confirmation code out) is supported | Build the Meta callback; add a "delete my connected-account data" line to the privacy page |
| Keeping platform data fresh | YouTube: stored API data must be deleted or refreshed after 30 calendar days. LinkedIn: member profile data may be cached 24 hours | We keep only an account id, display name and avatar URL, refreshed on each use; for LinkedIn we store the id only and fetch the name when the page is shown |
| Privacy policy and links | YouTube Developer Policies (page dated 2026-11-06, https://developers.google.com/youtube/terms/developer-policies): the app must link YouTube's Terms of Service, "notify users that the API Client uses YouTube API Services", link the Google Privacy Policy and the Google security settings page (https://security.google.com/settings/security/permissions). Google, Meta and TikTok all require a public privacy policy on the app's own domain | Owner approves the privacy and terms text (DRAFT legal pages, phase 5). Connect screen shows the required links |
| One project per app | YouTube: "exactly one (1) API Project" per API client. X and LinkedIn: no multiple apps for the same use case | One developer app per platform, shared by staging and production through separate redirect URIs |
| Branding | Google: connect buttons follow Google's branding guidelines. YouTube brand features must not suggest our content "is originating from YouTube". TikTok logo only under its Brand and Use Guidelines. LinkedIn: our app name must not contain "Linked" or "In". Meta: follow the Brand Resource Center | Use each platform's official icon unmodified next to its name, nothing else. No "partner" or "official" wording |
| Watermarks | TikTok forbids any brand, logo, watermark, link or promotional text added by the app | No ClutchClips mark is ever added to a published clip. If a watermark is ever introduced for free plans, TikTok publishing must be excluded from it |
| Automation | YouTube: "you must not automate or trigger ... uploads ... without the user's prior specific and express consent", and consent "prior to their actual execution". Meta: "Obtain consent from people before publishing content or taking any other action on their behalf". TikTok: start sending content only "after the user has expressly consent to the upload". X: "Never post identical or substantially similar content across multiple accounts". LinkedIn API Terms (2022-12-13): you must not "Use the Content or the APIs to automate posting on the LinkedIn Services" | Every post starts from the customer pressing Publish or Schedule on a clip they have previewed, per account. No auto-publish rule, no "post everything" default. The same clip to two accounts of the same platform asks for a confirmation. The LinkedIn clause is a reason to ask LinkedIn whether customer-created schedules are acceptable before building it |
| Content rights | TikTok intended use excludes apps that copy "arbitrary contents from other platforms". Facebook runs a copyright check on reels at upload | The clips come from the customer's own recordings (uploads) or imports made with the ownership confirmation we already log. The publish screen repeats the "I have the rights to post this" line |

Two risks that are my reading, not something a platform page states:
- A YouTube compliance audit or a TikTok audit looks at the whole product. Our best-effort YouTube link import (it does not use the YouTube API) and "clips from Twitch and Kick" may draw questions. The owner should be ready to show the consent step and the takedown flow.
- TikTok's audit asks for usage estimates and a product "intended for a wide audience". Applying before the site is public is likely to fail.

## 4. Design

Publishing only happens when a customer presses Publish, or at a time the customer set on a schedule they created. Nothing publishes automatically.

Files, as assigned in `docs/CONTRACTS.md`: `app/publish/**` and `app/routes_publish.py`. The orchestrator wires `models.py`, the migration, `config.py`, `main.py` and the worker loop. `run_pipeline` is not touched.

### 4.1 Connected accounts

Table `social_accounts` (new, additive, revision 0008):

| Column | Notes |
|---|---|
| `id`, `account_id` (FK accounts), `platform` | `youtube`, `tiktok`, `instagram`, `facebook`, `x`, `linkedin` |
| `external_id`, `display_name`, `avatar_url` | Unique on (`account_id`, `platform`, `external_id`). For Facebook the external id is the Page id |
| `access_token_enc`, `refresh_token_enc` | Encrypted; see below |
| `access_expires_at`, `refresh_expires_at`, `scopes` | From the token response, never hard-coded |
| `status` | `active`, `needs_reconnect`, `revoked` |
| `created_at`, `updated_at`, `last_used_at`, `disconnected_at` | A disconnected row keeps its id for post history and has its token and profile columns set to null |

- Encryption: authenticated symmetric encryption (Fernet from the `cryptography` package, a new dependency) with the key from `PUBLISH_TOKEN_KEY`. A second variable, `PUBLISH_TOKEN_KEY_OLD`, lets the key be rotated without a flag day. With `PUBLISHING=true` and no key the app refuses to start, the same way `SECRET_KEY` is checked today. Tokens never appear in logs (`app/log_redact.py` gets the token field names), API responses or error messages.
- Connect: `POST /v1/social-accounts/{platform}/connect` returns the platform's authorize URL. The `state` is a signed, 10-minute token from `security.make_token` carrying the account id and a nonce; PKCE is used where the platform supports it (X requires it). `GET /v1/social-accounts/{platform}/callback` checks the state, exchanges the code, stores the tokens and redirects to the website. Only the scopes in section 2 are requested.
- Website session only for connect and disconnect, like API keys today.
- Refresh: before each use, when the access token expires within 10 minutes, under a row lock so two workers cannot spend the same refresh token. A sweep refreshes long-lived tokens ahead of expiry (Instagram and Facebook every 50 days). A refused refresh sets `needs_reconnect`, fails the waiting posts with `reconnect_required` and emails the customer once.
- Disconnect: `DELETE /v1/social-accounts/{id}` cancels that account's unsent posts, calls the platform's revoke endpoint (best effort, 10-second timeout), then nulls the tokens and profile fields. If the revoke call fails the local delete still happens.
- Account deletion: there is no delete-account endpoint in the API today. Stage 2 adds a `disconnect_all(account_id)` function and calls it from the takedown flow; when account deletion is built it must call it too. Listed as a decision in section 8.
- A platform appears in `GET /v1/publish/platforms` only when its client id and secret are set in the environment (the rule already in CONTRACTS.md).

### 4.2 Publish job

Table `scheduled_posts` (new, additive, revision 0008), one row per clip and connected account:

| Column | Notes |
|---|---|
| `id`, `account_id`, `clip_id`, `social_account_id`, `platform` | |
| `request_key` | From the `Idempotency-Key` header. Unique on (`clip_id`, `social_account_id`, `request_key`) |
| `title`, `caption`, `hashtags` (JSON), `privacy`, `options` (JSON) | Exactly what the customer confirmed. `options` holds the platform switches (TikTok comment, duet, stitch, disclosure; YouTube made-for-kids, synthetic media, paid placement) |
| `publish_at` | Null for "now" |
| `status` | `SCHEDULED`, `QUEUED`, `UPLOADING`, `PROCESSING`, `PUBLISHED`, `FAILED`, `CANCELED` |
| `attempts`, `next_attempt_at`, `claimed_at` | |
| `step`, `external_ref` | The last completed step and the platform's id for it (upload session, container id, publish id), so a retry resumes instead of starting again |
| `external_id`, `external_url` | The published post |
| `error_code`, `error_message` | Ours, plus the platform's text shortened |
| `created_at`, `updated_at`, `published_at` | |

- Idempotent: the same clip, account and `Idempotency-Key` returns the existing row. A second publish of the same clip to the same account with a new key is allowed only after the website shows "already posted here on <date>" and the customer confirms.
- Worker: a loop in the existing worker process claims due rows with the same conditional `UPDATE` pattern as `claim_job`, so one row has one worker on Postgres and SQLite. A stale claim (no progress for 15 minutes) is released.
- At most one post: every platform's flow is "transfer the file, then one call that makes it public". The transfer is retried freely. The final call is made once. If its answer is lost (timeout, connection reset) the worker does not repeat it: it asks the platform for the status of `external_ref` and continues from what it finds; if the platform cannot say, the row fails with `outcome_unknown` and the customer is told to check the account before retrying.
- Retries: network errors, 5xx and 429 retry with backoff (1, 5, 15, 60 minutes; `Retry-After` and the platform's reset headers win), at most 5 attempts. 4xx validation, permission and quota-exhausted errors do not retry. An expired token is refreshed once, then `reconnect_required`.
- Our own caps, enforced before any platform call: the platform's documented per-account daily limit (TikTok's `creator_info` and Instagram's `content_publishing_limit` are read live), the YouTube project quota of 100 uploads a day (a counter; when it is used up posts stay queued until the quota resets at midnight Pacific Time and the customer is told), and a per-account cap in `config.py`.
- File hand-off, through `app/storage.py` only:

| Platform | How the file gets there |
|---|---|
| YouTube, Facebook, LinkedIn, X | The worker fetches the export from storage and uploads the bytes (resumable or chunked) |
| Instagram | Meta downloads from a public URL: a signed storage URL made for this post, valid long enough for processing (longer than today's 1-hour default) |
| TikTok | `PULL_FROM_URL`, as TikTok requires for server-side files. The URL must sit under a domain or prefix the owner verified in the TikTok portal, must not redirect and must work for an hour. This fits Spaces/R2 with a custom domain; it does not fit local-disk storage |

- The file published is the clip's full-quality export (`clips.export_key`). If the clip has only a preview, the customer is sent to export first; publishing never starts a render by itself, because exports are a money path.
- Before queueing, the file is checked against the platform's limits in section 2 (length, size, aspect, container) with `ffprobe` under the existing whitelist and timeout rule. A clip that does not fit is refused with the reason, for example "Facebook Reels are 3 to 90 seconds; this clip is 2:10".
- Job webhooks: a `post.published` and `post.failed` event to the account's webhook URL, signed like job webhooks.

### 4.3 Captions and hashtags

Defaults come from `clips.meta` (`title`, `titles`, `description`, `hashtags`), filled in per platform and always editable before confirm (TikTok requires that preset text is editable):

| Platform | Title | Caption | Hashtags | Limits applied |
|---|---|---|---|---|
| YouTube | `meta.title` | `meta.description` | Appended to the description; `#Shorts` is not forced | Not read; taken from the `videos` resource page in Stage 2 |
| TikTok | – | `meta.title` then hashtags | Inline | 2200 UTF-16 units |
| Instagram | – | `meta.title`, blank line, hashtags | Inline | 2200 characters, 30 hashtags, 20 mentions |
| Facebook | `meta.title` | `description` with hashtags | Inline | Not stated on the pages read |
| X | – | `meta.title` and up to 3 hashtags | Inline | No URLs by default (the $0.20 price); length limit to be re-checked in Stage 2 |
| LinkedIn | Video title | `commentary` | Inline | Not stated on the pages read |

Text longer than a limit is never cut silently: the field shows the count and the form will not submit.

### 4.4 Scheduling

- One queue, ours: a scheduled post is a `scheduled_posts` row with `publish_at` in the future. The worker picks it up when due. We do not use YouTube's `publishAt` or Facebook's `scheduled_publish_time`: with our own queue, cancel, edit and reschedule work the same on every platform, nothing sits on the platform before the customer's time, and a disconnected account cannot post later.
- Times are stored in UTC and shown in the customer's time zone. Minimum 5 minutes ahead; maximum 90 days (a `config.py` value).
- The files must outlive the schedule: a clip with a pending post is exempt from the `RETENTION_DAYS` sweep until the post is sent, canceled or failed.
- `POST /v1/posts/{id}/cancel` and `PATCH /v1/posts/{id}` (text, time) work while the row is `SCHEDULED`.
- A post that comes due while the token is dead, the plan no longer allows it, or `PUBLISHING` is off fails with a clear reason and an email; it is never sent late without the customer asking again.
- Missed window: if the worker was down and a post is more than 60 minutes late, it is not sent; it fails with `missed_schedule` and the customer can re-send with one click.

### 4.5 Before confirm

Matches the reference screenshot (per account: caption, description, visibility, now or scheduled, connect or disconnect), plus what the platforms require. For each selected account the confirm panel shows:

- The platform and the account's name and avatar, fetched fresh.
- The clip preview, its length and aspect, and whether it fits the platform.
- Title, caption and hashtags, editable, with counters.
- Visibility. YouTube: public, unlisted, private. TikTok: the options `creator_info` returns, **no default**. Instagram and Facebook: public only. X and LinkedIn: public.
- Platform switches: TikTok comment, duet, stitch (off by default), commercial content disclosure and the Music Usage line; YouTube made for kids, altered or synthetic content, paid promotion.
- When: now, or the date and time in the customer's time zone.
- Cost: "Free", or the credit price if the owner chooses one (section 5).
- The rights line and the platform's terms links.
- For TikTok before our audit passes: "This post will be private (only you) until TikTok approves ClutchClips."

Nothing is sent to any platform until Publish or Schedule is pressed on this panel.

### 4.6 Failures

| Case | Result |
|---|---|
| Token expired or revoked | Refresh once; otherwise `reconnect_required`, account marked `needs_reconnect`, one email |
| Platform rate or daily limit | Stays queued until the limit resets, shown as "waiting for <platform> limit"; fails after 24 hours |
| Clip does not fit the platform | Refused before queueing with the exact limit |
| Platform rejects the video in processing | `FAILED` with the platform's reason; no retry |
| Lost answer on the final call | Status check, never a blind repeat; `outcome_unknown` if unresolved |
| Clip or export deleted, or source taken down | Pending posts canceled with the reason. Already-published posts stay on the platform; the takedown report lists their URLs so the owner can ask the customer to remove them |
| `PUBLISHING` turned off | New requests get 503 `publishing_disabled`; scheduled rows wait up to 60 minutes, then fail as a missed schedule |
| One of several targets fails | The others still go out; each row has its own status |

If the owner prices publishing, a charged post that fails is refunded exactly once, with a test, under the ledger rules in CLAUDE.md.

### 4.7 API (proposal for the website contract)

```
GET    /v1/publish/platforms                 configured platforms with their limits and fields
GET    /v1/social-accounts                   the caller's connected accounts (no tokens)
POST   /v1/social-accounts/{platform}/connect      -> {authorize_url}        (website session)
GET    /v1/social-accounts/{platform}/callback     OAuth redirect target
DELETE /v1/social-accounts/{id}              disconnect, revoke, delete      (website session)
POST   /v1/clips/{id}/publish/check          validate targets and text; returns what the confirm panel shows; sends nothing
POST   /v1/clips/{id}/publish                Idempotency-Key; {targets: [{social_account_id, title, caption, hashtags, privacy, options}], publish_at?} -> 202 {posts: [...]}
GET    /v1/posts?clip_id=&status=&from=&to=  list, also feeds the calendar
GET    /v1/posts/{id}
PATCH  /v1/posts/{id}                        text or time, while SCHEDULED
POST   /v1/posts/{id}/cancel
POST   /webhooks/meta/data-deletion          Meta's data deletion request callback
```

With `PUBLISHING=false` every route above returns 404 and `GET /v1/options` does not mention publishing, so the website keeps "Coming soon".

### 4.8 Tests (Stage 2)

All platform calls go through one small HTTP client per platform, replaced in tests by a fake server (httpx mock transport). No test posts anywhere. Covered: token encryption round trip and key rotation; state and PKCE checks on callback; refresh and reconnect; idempotent submit; the at-most-once final call including the lost-answer case; each retry class; caps; schedule, cancel, missed window; disconnect deletes tokens and cancels posts; the flag off; refund-once if priced.

## 5. Credits (owner decides; nothing is charged until approved)

Our cost per post: bandwidth and a few seconds of worker time for every platform, plus $0.015 per post on X.

| Option | What the customer pays | For | Against |
|---|---|---|---|
| A. Free, with plan limits | Nothing per post. Plans limit connected accounts and scheduled posts (the limits Wayin's plans list, PARITY.md line 96) | Matches competitors; no ledger work for the five free platforms | Plan limits are a pricing change and need the owner's OK. X's cost is absorbed |
| B. Free, X priced | Free everywhere; X posts cost credits (for example 1 credit per post, shown before confirm) | Passes on the only real per-post cost | A different rule for one platform |
| C. Flat price | A small credit price per post on every platform | Simple | Worse than competitors; every failure path needs a refund test |
| D. Free at launch, no X | Free; X is not offered | Zero spend, zero money code | One platform fewer |

Recommendation: D for the first release, then A when plan limits are next reviewed, adding X under B if customers ask for it.

## 6. What the owner must register or pay for

I register nothing and spend nothing. For each platform the owner approves, the owner does the following and puts the client id and secret in the server environment (names only in `.env.example`).

Needed by all: the public website live at clutchclips.io with real (not DRAFT) Privacy Policy and Terms pages linked from the home page, and a way for reviewers to log in and test (a demo account with credits).

| Platform | Owner's steps | Cost |
|---|---|---|
| YouTube | a. Create one Google Cloud project and enable YouTube Data API v3. b. Configure the OAuth consent screen (external), add the scopes, add the redirect URIs. c. Verify clutchclips.io in Search Console. d. Submit for OAuth verification with a demo video (I can script and record the flow on staging once built). e. Later, when 100 uploads a day is not enough: the Audit and Quota Extension Form | Free |
| TikTok | a. Register on TikTok for Developers and create the app. b. Add Login Kit and Content Posting API with Direct Post. c. Verify the storage domain or URL prefix under URL properties. d. Submit app review for `video.publish` with demo videos. e. Apply for the audit with usage estimates | Free |
| Instagram and Facebook | a. Create a Meta developer account and a business portfolio. b. Complete Business Verification (business documents). c. Create one app with Instagram (Instagram Login) and Facebook Login for Business. d. Set the data deletion callback URL and privacy policy URL. e. Submit App Review for the five permissions with screen recordings and reviewer login. f. Yearly Data Use Checkup | Free. Needs a legal business that Meta can verify |
| X | a. Create a developer account and app, write the use-case description. b. Buy credits and set a spending limit. c. Decide whether the "limited number of end-users" clause is acceptable, or ask X about Enterprise | $0.015 a post, prepaid. Enterprise price unknown |
| LinkedIn | a. Create a LinkedIn Page for the company and a developer app verified by the Page's super admin. b. Apply for the Community Management API (legal name, registered address, business email). c. After Development tier and a built integration, apply for Standard tier with a screen recording | Free. Needs a registered legal organization |

## 7. Recommended rollout

| Order | Platform | Why here |
|---|---|---|
| 1 | YouTube Shorts | Highest value for gaming creators. Since 2026-11-02 uploads from an unverified project can be public, so the owner's own channel and the first 100 users work before verification finishes. Free. The limit to watch is 100 uploads a day for the whole project |
| 2 | TikTok | Same value as YouTube for this audience, but the slowest gate: app review, then an audit, private-only until it passes. Start the paperwork at the same time as YouTube; build second. The confirm panel has to follow TikTok's required layout exactly |
| 3 | Instagram Reels | Third for gaming clips. One Meta app review, but Business Verification needs a legal business, and customers need a professional account |
| 4 | Facebook Pages | Low value for this audience, cheap once Instagram is done (same app, same review). Reels are capped at 90 seconds and Pages only |
| 5 | X | No review and quick to build, but the only one that costs money per post and the only one with a scale clause. Build only with a pricing decision |
| 6 | LinkedIn | Lowest value for gaming creators and the heaviest paperwork; its API terms forbid using the API "to automate posting". Recommend leaving it "Coming soon" |

Stage 2 would ship as: PR 1 the model, encryption, connect and disconnect, the publish and schedule queue and the fake-platform tests (flag off; auth, so human merge); PR 2 YouTube; then one PR per platform as the owner's apps are approved.

## 8. Decisions needed from the owner

1. Which platforms to build now. Recommended: YouTube and TikTok first, Instagram and Facebook next, X and LinkedIn held.
2. Credits: option A, B, C or D in section 5.
3. Is there a registered business that Meta and LinkedIn can verify, and under what legal name? Without it Instagram, Facebook and LinkedIn cannot go public.
4. X: accept $0.015 a post and the "limited number of end-users" clause, or skip X.
5. LinkedIn: skip, or ask LinkedIn first whether customer-created schedules are allowed under the "automate posting" clause.
6. Storage: TikTok and Instagram fetch the file from a public https URL, and TikTok needs that domain verified. Confirm production uses Spaces/R2 with a domain the owner controls.
7. May API-key callers publish, or only the website session? Recommended: website only at first, since every platform wants the person to see and confirm the post.
8. Account deletion does not exist in the API yet. Build `DELETE /v1/me` together with publishing (it must revoke and delete connected accounts), or keep deletion a support request for now?
9. Plan limits on connected accounts and scheduled posts: none at launch, or set numbers (a pricing change).
10. Go-ahead to make the Privacy Policy and Terms pages final, with the YouTube, Google and Meta wording from section 3. No platform review can start while they are DRAFT.

## 9. Not confirmed from official pages

These were not stated on the pages read and are not guessed here. Each is checked before the platform's Stage 2 PR.

- Google: whether `youtube.upload` is classed sensitive, and a verification timeline for it.
- YouTube: how an API upload is classed as a Short; current title and description length limits.
- TikTok: review and audit timelines; exact access and refresh token lifetimes (read from the token response).
- Meta: Business Verification timeline; Page (non-reel) video size and length limits; Facebook description length.
- Instagram: whether the daily limit is 100 or 50 (the docs give both; read live).
- X: whether media upload calls are billed; the 1280×1024 dimension line versus 1080p for Premium; the Enterprise price.
- LinkedIn: whether video upload works with the self-serve Share on LinkedIn product; review timelines; commentary length.
