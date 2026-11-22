# ClutchClips website

Next.js, exported as static files. No Node process runs on the server; Caddy serves `../web`.

```bash
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev        # local, against a local API
NEXT_PUBLIC_API_URL=https://api.clutchclips.io npm run build # writes ./out
rm -rf ../web && cp -r out ../web                            # commit ../web in the same PR
```

Production Caddy mounts `clip-api/web/` from the git checkout. `deploy.sh` rebuilds
only `api` and `worker`; it does **not** run `npm run build`. Every PR that changes
`web-src/` must rebuild and commit `web/`, or the live site stays on the previous
export even when the deploy of that commit succeeds. `tests/test_web_export.py`
fails if a source route is missing from the committed export.

## Legal pages: draft preview

`/privacy`, `/terms`, `/copyright`, `/cookies`, `/refunds` and `/acceptable-use` are drafts with `[OWNER: …]`
placeholders for facts the owner has not confirmed. A normal build shows a short "This policy is being finalised"
page on those routes, and `npm run build` fails (`scripts/check-legal.mjs`) if any built page still shows a
placeholder. To read the drafts, build or run with `LEGAL_PREVIEW=1`. Never copy a preview build into `../web`:

```bash
LEGAL_PREVIEW=1 NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev         # drafts, local
LEGAL_PREVIEW=1 NEXT_PUBLIC_API_URL=https://api.clutchclips.io npm run build  # drafts in ./out, for review only
```

When the owner fills every placeholder in `lib/legal.ts` and removes the markers, the drafts can ship: drop the
stub in `components/LegalPage.tsx` and the guard passes on its own. See `../../docs/launch-checklist.md`.
