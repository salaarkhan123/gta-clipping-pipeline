# ClutchClips website

Next.js, exported as static files. No Node process runs on the server; Caddy serves `../web`.

```bash
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev        # local, against a local API
NEXT_PUBLIC_API_URL=https://api.clutchclips.io npm run build # writes ./out
rm -rf ../web && cp -r out ../web                            # then scp ../web to the server
```
