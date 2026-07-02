# Cloudflare setup (one time)

The `dak` skill deploys to **Cloudflare Pages**, whose free tier has unlimited
bandwidth and requests, no credit card, and allows commercial use. You need a free
account and an API token. This takes a few minutes once.

## 1. Create a free Cloudflare account

Sign up at https://dash.cloudflare.com/sign-up. No paid plan or domain is required —
`*.pages.dev` URLs are included free.

## 2. Find your Account ID

In the Cloudflare dashboard, open **Workers & Pages**. Your **Account ID** is shown in
the right sidebar (also visible in the URL: `dash.cloudflare.com/<ACCOUNT_ID>/...`).
Copy it.

## 3. Create an API token

1. Go to **My Profile → API Tokens → Create Token**
   (https://dash.cloudflare.com/profile/api-tokens).
2. Use **Create Custom Token**.
3. Give it one permission: **Account → Cloudflare Pages → Edit**.
4. Scope **Account Resources** to your account.
5. Create the token and copy it. You won't be able to see it again.

> Prefer a custom token over a global API key — it's scoped to just Pages and can be
> revoked independently.

## 4. Export the credentials

Wrangler (invoked by the skill via `npx`) reads these from the environment:

```bash
export CLOUDFLARE_API_TOKEN="your-token-here"
export CLOUDFLARE_ACCOUNT_ID="your-account-id-here"
```

Put them in your shell profile (`~/.zshrc`, `~/.bashrc`) or a project `.env` you source,
so every session has them. **Never commit these to a repo.**

## 5. Verify

```bash
python3 scripts/dak.py doctor
```

You should see `wrangler: found`, both env vars `set`, and the default project name.
Then a dry run to confirm command construction without deploying:

```bash
python3 scripts/dak.py some-file.html --dry-run
```

## How the project is created

On the first real publish, the skill runs (idempotently):

```bash
npx wrangler pages project create dak --production-branch main
```

If the project already exists, that's fine — the error is ignored. All publishes go to
**branches** of this one project (never the production branch), which is why one project
can hold many independent live aliases plus every snapshot.

> **Pages subdomains are global.** Your URLs are literally `<project>.pages.dev`, so the
> project name must be unique across all of Cloudflare — `dak` may already be taken. If
> project creation fails with a name conflict, pick your own (e.g. `dak-atharva`) and set
> `export DAK_PROJECT="dak-atharva"`. Your links then become `<slug>.dak-atharva.pages.dev`.

## Troubleshooting

- **`Authentication error [code: 10000]`** — token missing the Pages:Edit permission, or
  `CLOUDFLARE_ACCOUNT_ID` not set / wrong account.
- **`wrangler: MISSING`** — Node isn't installed or `npx` isn't on PATH. Install Node 18+.
- **`A project with this name already exists`** — harmless; the skill ignores it.
- **File too large** — Pages rejects files over 25 MiB. Split or compress large assets.
- **Sandboxed/offline environment** — if the machine can't reach `api.cloudflare.com`,
  publishing will fail at the deploy step. Use `--dry-run` to validate staging offline.
