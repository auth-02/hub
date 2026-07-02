# Pretty short URLs (optional enhancement)

By default the skill returns `*.pages.dev` URLs:

- snapshot: `https://<hash>.dak.pages.dev`
- live: `https://<slug>.dak.pages.dev`

These work everywhere and cost nothing. The vision-doc format
`https://share.example.com/r/8F3K2A` is **not** free out of the box — it needs a domain.
Only set this up if the user explicitly wants branded or short links.

## Option A — custom domain on the project (simplest, recommended)

Gives you `https://<slug>.share.theirdomain.com` style links. Requires owning a domain
managed by Cloudflare (free DNS).

1. Add the domain to Cloudflare (Websites → Add a site) and point its nameservers at
   Cloudflare. Free.
2. In **Workers & Pages → dak → Custom domains**, add e.g. `share.theirdomain.com`.
   Cloudflare provisions the certificate automatically.
3. Now the production deployment is reachable at the custom domain. Branch aliases still
   use `*.pages.dev`; for per-artifact custom subdomains you'd map each one, which is why
   Option B is usually better for the `/r/<code>` pattern.

## Option B — Worker shortener for `/r/<code>` links

This reproduces the exact `https://share.example.com/r/8F3K2A` shape. A tiny Cloudflare
Worker maps short codes to the real `pages.dev` URLs using a KV namespace.

### 1. Create a KV namespace

```bash
npx wrangler kv namespace create LINKS
```

### 2. Worker (`shortener/src/index.js`)

```js
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const code = url.pathname.replace(/^\/r\//, "").replace(/\/$/, "");
    if (!code) return new Response("dak shortener", { status: 200 });
    const target = await env.LINKS.get(code);
    if (!target) return new Response("Not found", { status: 404 });
    return Response.redirect(target, 302);
  },
};
```

### 3. `shortener/wrangler.toml`

```toml
name = "dak-share"
main = "src/index.js"
compatibility_date = "2024-11-01"

kv_namespaces = [
  { binding = "LINKS", id = "<KV_NAMESPACE_ID_FROM_STEP_1>" }
]

# Attach a route on your domain, e.g.:
# routes = [{ pattern = "share.theirdomain.com/r/*", zone_name = "theirdomain.com" }]
```

### 4. Deploy and register codes

```bash
cd shortener && npx wrangler deploy

# after each publish, map a short code -> the returned pages.dev URL:
npx wrangler kv key put --binding=LINKS "8F3K2A" "https://a1b2c3.dak.pages.dev"
```

Now `https://share.theirdomain.com/r/8F3K2A` 302-redirects to the artifact.

### Wiring it into the skill

To make `dak.py` emit short links automatically, after a successful deploy: generate
a random code, `wrangler kv key put` it to the target URL, and print
`https://<DAK_DOMAIN>/r/<code>` instead of the raw URL. Gate this on a
`DAK_DOMAIN` env var so it's a no-op until configured. This is left as an opt-in
extension rather than a default, since it presumes a domain.
