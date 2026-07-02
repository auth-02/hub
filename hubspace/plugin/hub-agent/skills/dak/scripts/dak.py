#!/usr/bin/env python3
"""
dak.py — turn a local artifact into a shareable URL via Cloudflare Workers.

First run:
    python3 scripts/dak.py setup

After setup:
    python3 scripts/dak.py <path> [--mode snapshot|live] [--slug NAME] [--title T]
    python3 scripts/dak.py list
    python3 scripts/dak.py unpublish <worker-name>
    python3 scripts/dak.py doctor

URL format:  https://<worker-name>.<your-subdomain>.workers.dev
Subdomain convention: <username>-dak  (e.g. atharva-dak)
"""
import argparse
import getpass
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME        = Path(os.path.expanduser("~"))
STATE_DIR   = HOME / ".dak"
MANIFEST    = STATE_DIR / "manifest.json"
CONFIG_FILE = STATE_DIR / "config.json"
COMPAT_DATE = "2025-01-01"

RENDERABLE_TEXT = {".html", ".htm"}
MARKDOWN_EXT    = {".md", ".markdown"}
EMBEDDABLE      = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


# ── config ────────────────────────────────────────────────────────────────────
def load_config():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_config(cfg):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


def get_cfg(key, env_fallback=None):
    """Read from config file, falling back to environment variable."""
    cfg = load_config()
    val = cfg.get(key)
    if not val and env_fallback:
        val = os.environ.get(env_fallback)
    return val


# ── helpers ───────────────────────────────────────────────────────────────────
def log(msg):
    print(msg, file=sys.stderr)


def die(msg, code=1):
    log(f"error: {msg}")
    sys.exit(code)


def slugify(text):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s[:63] or "artifact"


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def which_wrangler():
    if shutil.which("wrangler"):
        return ["wrangler"]
    if shutil.which("npx"):
        return ["npx", "--yes", "wrangler"]
    return None


def load_manifest():
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text())
        except Exception:
            return {"entries": []}
    return {"entries": []}


def save_manifest(data):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(data, indent=2))


# ── CF API ────────────────────────────────────────────────────────────────────
def cf_get(path, token, account_id):
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code


# ── setup ─────────────────────────────────────────────────────────────────────
def cmd_setup(_args):
    cfg = load_config()
    print("── dak setup ──────────────────────────────────")
    print("This runs once. Values are saved to ~/.dak/config.json")
    print("Press Enter to keep an existing value shown in [brackets].\n")

    # 1. API token
    current_token = cfg.get("api_token") or os.environ.get("CLOUDFLARE_API_TOKEN", "")
    display = f"[set ({len(current_token)} chars)]" if current_token else "[not set]"
    print(f"Cloudflare API token {display}")
    print("  Needs: Workers Scripts:Edit  (dash.cloudflare.com/profile/api-tokens)")
    raw = getpass.getpass("  Token (input hidden): ").strip()
    token = raw or current_token
    if not token:
        die("API token is required.")

    # 2. Account ID
    current_account = cfg.get("account_id") or os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    display = f"[{current_account}]" if current_account else "[not set]"
    print(f"\nCloudflare Account ID {display}")
    print("  Found at: dash.cloudflare.com → Workers & Pages (right sidebar)")
    raw = input("  Account ID: ").strip()
    account_id = raw or current_account
    if not account_id:
        die("Account ID is required.")

    # 3. Verify credentials by hitting the subdomain endpoint
    print("\nVerifying credentials...")
    res, code = cf_get("/workers/subdomain", token, account_id)
    if code and code not in (404, None):
        die(f"Auth failed (HTTP {code}). Check your token and account ID.")

    current_cf_subdomain = res.get("result", {}) or {}
    current_cf_subdomain = current_cf_subdomain.get("subdomain") if isinstance(current_cf_subdomain, dict) else None
    print(f"  ✓ credentials valid")
    if current_cf_subdomain:
        print(f"  Current workers.dev subdomain: {current_cf_subdomain}")

    # 4. workers.dev subdomain (stored locally, not changed via API)
    current_sub = cfg.get("subdomain") or current_cf_subdomain or ""
    # suggest <username>-dak from account email or existing subdomain
    suggestion = current_sub or f"{getpass.getuser()}-dak"
    print(f"\nYour workers.dev subdomain [{current_sub or suggestion}]")
    print("  Convention: <username>-dak  (e.g. atharva-dak)")
    print("  This must match what's set in your Cloudflare account.")
    print("  To check/set it: dash.cloudflare.com → Workers & Pages → 'Your subdomain'")
    raw = input(f"  Subdomain [{current_sub or suggestion}]: ").strip()
    subdomain = raw or current_sub or suggestion

    # 5. Save
    cfg.update({
        "api_token":  token,
        "account_id": account_id,
        "subdomain":  subdomain,
    })
    save_config(cfg)

    print(f"\n✓ Saved to {CONFIG_FILE}")
    print(f"  Workers will deploy to: https://<name>.{subdomain}.workers.dev")
    print(f"\nReady. Try:")
    print(f"  python3 scripts/dak.py examples/sample-report.md --mode live --slug intro")
    return 0


# ── rendering ─────────────────────────────────────────────────────────────────
DEFAULT_PAGE_CSS = """
:root { color-scheme: light dark; }
body { max-width: 46rem; margin: 4rem auto; padding: 0 1.25rem;
  font: 17px/1.65 ui-serif, Georgia, 'Times New Roman', serif;
  color: #1d1b16; background: #fbf9f3; }
@media (prefers-color-scheme: dark) { body { color:#e7e3d8; background:#1a1916; } }
h1,h2,h3,h4 { font-weight: 600; line-height: 1.2; letter-spacing: -0.01em; }
h1 { font-size: 2rem; margin: 0 0 1.5rem; }
code,pre { font-family: ui-monospace, 'JetBrains Mono', SFMono-Regular, Menlo, monospace; }
pre { background: rgba(127,127,127,.12); padding: 1rem; border-radius: 6px;
  overflow:auto; font-size:.9em; }
code { background: rgba(127,127,127,.14); padding: .1em .35em;
  border-radius: 4px; font-size:.9em; }
pre code { background: none; padding: 0; }
a { color: #c0622a; }
blockquote { border-left: 3px solid #c0622a; margin: 1rem 0;
  padding: .2rem 1rem; opacity:.85; }
hr { border: none; border-top: 1px solid rgba(127,127,127,.3); margin: 2rem 0; }
img { max-width: 100%; height: auto; }
table { border-collapse: collapse; }
td,th { border:1px solid rgba(127,127,127,.3); padding:.4rem .7rem; }
footer { margin-top: 4rem; font-size:.8rem; opacity:.5;
  font-family: ui-monospace, monospace; }
"""

def render_markdown(md_text, title):
    try:
        import markdown
        body = markdown.markdown(
            md_text,
            extensions=["fenced_code", "tables", "toc", "sane_lists", "codehilite"],
            extension_configs={"codehilite": {"noclasses": True}},
        )
    except Exception:
        body = _fallback_md(md_text)
    return _html_doc(title, body)


def _fallback_md(md):
    import html as _html
    out, in_code = [], False
    for line in md.splitlines():
        if line.strip().startswith("```"):
            out.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(_html.escape(line))
            continue
        m = re.match(r"(#{1,6})\s+(.*)", line)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{_html.escape(m.group(2))}</h{lvl}>")
        elif line.strip() == "":
            out.append("")
        elif re.match(r"\s*[-*]\s+", line):
            out.append("<li>" + _html.escape(re.sub(r"\s*[-*]\s+", "", line)) + "</li>")
        else:
            out.append("<p>" + _html.escape(line) + "</p>")
    text = "\n".join(out)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def _html_doc(title, body):
    import html as _html
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(title)}</title>
<style>{DEFAULT_PAGE_CSS}</style></head>
<body>{body}
<footer>Published {now_iso()} &middot; via dak</footer>
</body></html>"""


def render_embed_index(filename, title):
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        viewer = (f'<embed src="{filename}" type="application/pdf" '
                  f'style="width:100%;height:90vh;border:none">')
    elif ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
        viewer = f'<img src="{filename}" alt="{title}">'
    else:
        viewer = f'<p>Download: <a href="{filename}">{filename}</a></p>'
    return _html_doc(title, f"<h1>{title}</h1>{viewer}")


def render_dir_index(staging, title):
    files = sorted(p.name for p in staging.iterdir() if p.is_file())
    items = "\n".join(f'<li><a href="{f}">{f}</a></li>' for f in files)
    return _html_doc(title, f"<h1>{title}</h1><ul>{items}</ul>")


# ── staging ───────────────────────────────────────────────────────────────────
def build_staging(src: Path, title: str) -> Path:
    staging = Path(tempfile.mkdtemp(prefix="dak-"))
    if src.is_dir():
        for item in src.iterdir():
            if item.name.startswith("."):
                continue
            dest = staging / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        if not (staging / "index.html").exists() and not (staging / "index.htm").exists():
            (staging / "index.html").write_text(render_dir_index(staging, title))
        return staging

    ext = src.suffix.lower()
    if ext in RENDERABLE_TEXT:
        shutil.copy2(src, staging / "index.html")
    elif ext in MARKDOWN_EXT:
        (staging / "index.html").write_text(render_markdown(src.read_text(), title))
    elif ext in EMBEDDABLE:
        shutil.copy2(src, staging / src.name)
        (staging / "index.html").write_text(render_embed_index(src.name, title))
    else:
        shutil.copy2(src, staging / src.name)
        (staging / "index.html").write_text(render_embed_index(src.name, title))
    return staging


# ── deploy ────────────────────────────────────────────────────────────────────
def write_wrangler_config(staging: Path, worker_name: str):
    config = {
        "name": worker_name,
        "compatibility_date": COMPAT_DATE,
        "assets": {"directory": "./"},
    }
    (staging / "wrangler.jsonc").write_text(json.dumps(config, indent=2))


def deploy(wrangler, staging: Path, worker_name: str, token: str, account_id: str):
    write_wrangler_config(staging, worker_name)
    env = {**os.environ, "CLOUDFLARE_API_TOKEN": token, "CLOUDFLARE_ACCOUNT_ID": account_id}
    cmd = wrangler + ["deploy", "--config", str(staging / "wrangler.jsonc")]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(staging), env=env)
    blob = res.stdout + "\n" + res.stderr
    log(blob)
    if res.returncode != 0:
        die("wrangler deploy failed")


# ── commands ──────────────────────────────────────────────────────────────────
def cmd_publish(args):
    cfg = load_config()

    # credentials: config file > environment
    token      = cfg.get("api_token")      or os.environ.get("CLOUDFLARE_API_TOKEN")
    account_id = cfg.get("account_id")     or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    subdomain  = cfg.get("subdomain")

    if not token or not account_id or not subdomain:
        die("Not configured. Run: python3 scripts/dak.py setup")

    src = Path(args.path).expanduser().resolve()
    if not src.exists():
        die(f"no such file or directory: {src}")

    title = args.title or src.stem.replace("-", " ").replace("_", " ").title()
    mode  = args.mode

    if mode == "live":
        worker_name = slugify(args.slug or src.stem)
    else:
        seed = f"{src}-{time.time()}"
        base = slugify(args.slug or src.stem)
        suffix = hashlib.sha1(seed.encode()).hexdigest()[:6]
        worker_name = f"{base}-{suffix}"[:63]

    # URL is known before deploying — no regex needed
    url = f"https://{worker_name}.{subdomain}.workers.dev"

    wrangler = which_wrangler()
    if wrangler is None:
        die("wrangler not found. Install Node, then `npm i -g wrangler` (or rely on npx).")

    if args.dry_run:
        log(f"staged (dry-run)  worker={worker_name}  url={url}")
        print(url)
        return 0

    staging = build_staging(src, title)
    log(f"staged {src.name} -> {staging}  (mode={mode}, worker={worker_name})")

    deploy(wrangler, staging, worker_name, token, account_id)
    shutil.rmtree(staging, ignore_errors=True)

    # record
    data = load_manifest()
    data["entries"] = [
        e for e in data["entries"]
        if not (mode == "live" and e.get("worker") == worker_name)
    ]
    data["entries"].insert(0, {
        "worker": worker_name, "mode": mode, "url": url,
        "source": str(src), "title": title, "published_at": now_iso(),
    })
    save_manifest(data)

    print(url)
    return 0


def cmd_list(_args):
    data = load_manifest()
    if not data["entries"]:
        log("nothing published yet.")
        return 0
    for e in data["entries"]:
        mark = "live " if e["mode"] == "live" else "snap "
        print(f"{mark} {e['url']}")
        log(f"        {e['title']}  ({e['source']})  {e['published_at']}")
    return 0


def cmd_unpublish(args):
    wrangler = which_wrangler()
    data = load_manifest()
    target = next((e for e in data["entries"] if e["worker"] == args.slug), None)
    if not target:
        die(f"no published entry with worker name '{args.slug}'")
    log(f"To delete '{args.slug}' from Cloudflare:")
    log(f"  {' '.join(wrangler or ['npx','wrangler'])} delete --name {args.slug}")
    data["entries"] = [e for e in data["entries"] if e["worker"] != args.slug]
    save_manifest(data)
    log("(removed from local manifest)")
    return 0


def cmd_doctor(_args):
    cfg = load_config()
    token      = cfg.get("api_token")  or os.environ.get("CLOUDFLARE_API_TOKEN")
    account_id = cfg.get("account_id") or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    subdomain  = cfg.get("subdomain")
    wrangler   = which_wrangler()
    ok = True

    print(f"wrangler:    {'found via ' + wrangler[0] if wrangler else 'MISSING'}")
    print(f"api_token:   {'set' if token else 'MISSING'}")
    print(f"account_id:  {'set' if account_id else 'MISSING'}")
    print(f"subdomain:   {subdomain or 'MISSING — run setup'}")
    print(f"config file: {CONFIG_FILE} ({'exists' if CONFIG_FILE.exists() else 'none yet'})")
    print(f"manifest:    {MANIFEST} ({'exists' if MANIFEST.exists() else 'none yet'})")

    if not wrangler or not token or not account_id or not subdomain:
        ok = False

    if not ok:
        log("\nRun: python3 scripts/dak.py setup")
        return 1
    log(f"\nReady. URLs will be: https://<name>.{subdomain}.workers.dev")
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    argv = sys.argv[1:]
    cmd  = argv[0] if argv else None

    if cmd == "setup":
        return cmd_setup(None)
    if cmd == "list":
        return cmd_list(None)
    if cmd == "doctor":
        return cmd_doctor(None)
    if cmd == "unpublish":
        ap = argparse.ArgumentParser(prog="dak unpublish")
        ap.add_argument("slug")
        return cmd_unpublish(ap.parse_args(argv[1:]))

    if cmd == "publish":
        argv = argv[1:]
    if not argv:
        print(__doc__)
        return 1

    ap = argparse.ArgumentParser(prog="dak", description="Share a local artifact as a URL.")
    ap.add_argument("path")
    ap.add_argument("--mode", choices=["snapshot", "live"], default="snapshot")
    ap.add_argument("--slug")
    ap.add_argument("--title")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    return cmd_publish(args)


if __name__ == "__main__":
    sys.exit(main())
