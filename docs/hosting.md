# Hosting the library

The app is a static bundle that fetches `index.json`, one cue file and one m4a. There is nothing to
keep running: publish the files once and any device can play them.

Cloudflare R2 is the default because the free tier is 10 GB with **no egress charge**, and the whole
64 kbps library is roughly 500 MB.

## One-time setup

1. **Bucket.** Cloudflare dashboard → R2 → create a bucket, e.g. `reader`.
2. **Public access.** Bucket → Settings → Public access → enable the `r2.dev` subdomain and note the
   host: `https://pub-<hash>.r2.dev`. (A custom domain can replace it later; `r2.dev` is rate-limited
   but fine for one listener.)
3. **CORS.** Bucket → Settings → CORS policy:

   ```json
   [
     {
       "AllowedOrigins": ["*"],
       "AllowedMethods": ["GET", "HEAD"],
       "AllowedHeaders": ["Range"],
       "ExposeHeaders": ["Content-Range", "Content-Length", "Accept-Ranges", "ETag"],
       "MaxAgeSeconds": 3600
     }
   ]
   ```

   `AllowedHeaders` must include `Range` or seeks fail once the browser sends it explicitly.
4. **Token.** R2 → Manage API tokens → create a token with Object Read & Write on this bucket. Keep
   the Access Key ID and Secret.
5. **rclone.**

   ```bash
   brew install rclone
   rclone config            # n → name: r2 → storage: s3 → provider: Cloudflare
   ```

   Then set the endpoint to `https://<account-id>.r2.cloudflarestorage.com`, region `auto`, and paste
   the token pair.
6. **`.env`** (already gitignored):

   ```
   PUBLISH_REMOTE=r2
   PUBLISH_BUCKET=reader
   PUBLIC_BASE_URL=https://pub-<hash>.r2.dev
   ```

## Publishing

```bash
./reader publish --stage-only   # transcode into .publish/, no network
./reader publish --dry-run      # show what rclone would send
./reader publish                # transcode + upload
```

Staging transcodes every served m4a to 64 kbps mono with the MP4 index at the front, so a seek does
not stall on a slow link and the tree is about a third of the size. `library/` and `audio/` are never
modified. Repeat publishes only re-encode when the source is newer.

Cache headers: audio and cues `max-age=86400`, `index.json` `no-cache` so a new book appears promptly.
`Content-Type` is set explicitly on upload — R2 infers `.m4a` as `audio/mp4a-latm`, which WKWebView is
inconsistent about.

`rclone sync` skips unchanged objects, and headers are only written on upload. After changing a header,
force a rewrite once:

```bash
./reader publish --reupload
```

## Building the app against the bucket

```bash
cd glasses-reader
VITE_LIB_BASE=$PUBLIC_BASE_URL/library npm run build:prod
npm run pack
```

`build:prod` refuses to run without `VITE_LIB_BASE`, which is what stops a LAN build from being
shipped by accident.

## Before an Even Hub submission

`app.json` already lists the public host under `network.whitelist`. It is an Even-side domain gate and
does not replace CORS. If the library moves to a custom domain, update it there:

```json
{ "name": "network", "desc": "…", "whitelist": ["https://<public host>"] }
```

Then rebuild, re-pack and upload. Private sideloads work without the whitelist.

## Checking a publish

```bash
curl -sI "$PUBLIC_BASE_URL/library/index.json"          # 200 + access-control-allow-origin
curl -s -r 0-99 -D- -o /dev/null \
  "$PUBLIC_BASE_URL/library/archer/archer.m4a"          # 206, Content-Range, audio/mp4
```

If the app shows `library unreachable`, it is nearly always one of: the bucket is not public, the CORS
policy is missing, or `VITE_LIB_BASE` has a trailing slash (the app trims one, but a stale build will
not).
