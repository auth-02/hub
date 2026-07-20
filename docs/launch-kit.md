# Hub — 0.3.0 Launch Kit

Ready-to-post copy + the banner GIF storyboard. Sequenced general-first
(local-first crowd for credibility), then a plugin-focused follow-up a few days
later. See [hub-marketing-plan.md](hub-marketing-plan.md) for positioning.

---

## 1. Banner: lineage trace-walk GIF

**Why a GIF, not a static shot:** the product *is* the trace-walk — a static
banner can't show "click an artifact → walk back to the decision." ~6 seconds.

### Storyboard (record against the dogfood/demo hub, never `/tifin`)
Run `uvx --from hubspaces hub serve --demo`, then capture at ~1280×640:

| t (s) | Frame | Action |
|-------|-------|--------|
| 0.0–1.0 | Index | Land on the index — rows grouped by repo, kind chips (incl. **DRAW**), a task with a status badge. |
| 1.0–2.0 | Agent produces | Show a fresh run/artifact appearing under a task (or scroll to a task with runs + a DRAW diagram). |
| 2.0–3.5 | Open artifact | Click an artifact row → split-pane preview opens. |
| 3.5–5.0 | `// trace` | The `// trace` panel walks back: artifact → run → parent task → the decision in the manifest. |
| 5.0–6.0 | Payoff | Rest on the manifest's decision text. Optional caption: *"nothing your agent makes floats free."* |

### Encoding
- ~1280×640 (2:1), <8 MB, loop, ~12–15 fps. Tools: Kap / LICEcap / `ffmpeg` from a screen recording.
- Save as `assets/screenshots/banner.png` (keep the name; the README/site point at it) **or** add `banner.gif` and update both references.

### One-step swap when the asset is ready
- **README** line 1: bump the cache-bust — `...banner.png?v=0.2.3` → `?v=0.3.0`
  (forces GitHub/PyPI to re-fetch). If switching to a GIF, change the filename too.
- **site/index.html**: the `.shot img` `src="banner.png"` — update if the filename changes.
- Proof/preview images for PRs still go on the `screenshots` orphan branch, never `assets/`.

---

## 2. Launch posts

### 2a. Show HN — general / local-first (post first)

**Title** (pick one):
- Show HN: Hub – a local, dependency-free index for the work your coding agent does
- Show HN: Hub – turn your agent's manifests, runs, and diagrams into one traceable page

**Body:**

> Coding agents are great at *producing* — runs, artifacts, diagrams, half-finished
> plans. What gets lost is the **record of why**: which decision led to which output,
> and how it all connects.
>
> Hub is a local, dependency-free ledger for that. Point it at a folder and every
> task, decision, run, and diagram becomes one searchable, traceable page. A task's
> `manifest.md` is the decision log — what you decided, what the agent decided, what
> it found, the plan — and lineage links every output back to it. Click an artifact,
> and a `// trace` panel walks you back to the decision that produced it.
>
> Two ways in:
> - **Package:** `pipx install hubspaces`, then `hub serve` in any folder.
> - **Plugin (Claude Code):** `/plugin install hub@hub` — producer skills *and* the
>   full engine bundled in, working offline the moment it installs.
>
> It's deliberately boring under the hood: **stdlib-only Python, no npm, no
> framework, zero runtime dependencies, nothing leaves your machine.** It indexes
> into SQLite with full-text search and serves a local browser that rebuilds on
> change.
>
> New in 0.3.0: **diagrams in place** — create Excalidraw diagrams right in the UI,
> offline, and they become first-class lineage nodes alongside runs and artifacts.
>
> Try it in one command (no install):
>
>     uvx --from hubspaces hub serve --demo
>
> Roadmap direction (not commitment): comments → one-click sharing → an open Hub
> spec any agent can emit → agent (MCP) retrieval over the lineage graph.
>
> Repo: https://github.com/auth-02/hub · Docs/demo: https://auth-02.github.io/hub/

**First-comment (HN convention — context/limitations):**
> Author here. Built this because my agent runs were piling up with no through-line
> back to the decisions behind them. Design choices: stdlib-only (no supply chain,
> installs anywhere with Python 3.11+), everything local, and the producer/consumer
> split so the viewer works with or without an agent. macOS is the best-tested
> surface (launchd helpers); Linux/Windows run the core fine. Happy to answer
> anything about the lineage model or the offline plugin.

---

### 2b. Plugin-focused follow-up — Claude Code / AI-dev crowd (a few days later)

**Title / hook:** *The board fills itself: a batteries-included Hub for Claude Code*

**Body:**

> If you drive work with Claude Code, the `hub` plugin gives you provenance for
> free. Install once (`/plugin install hub@hub`) and you get both halves:
>
> - **Producers** — skills (`/hub:manifest`, `/hub:stacked`, `/hub:kagaz`,
>   `/hub:dak`) that scaffold structured work as you go: task manifests, runs,
>   artifacts, diagrams.
> - **Consumer** — `/hub:serve` builds and serves the browsable, cross-linked
>   dashboard. The board, trace, and timeline fill themselves in from what the
>   producers emit.
>
> It's **offline and self-contained**: the plugin ships a pinned engine wheel and
> runs it via `uv`, so nothing is fetched from PyPI and there's no version skew —
> it always runs its own bundled engine. Only requirement: `uv`.
>
> Zero-effort provenance: every run, artifact, and Excalidraw diagram traces back
> to the task and the decision that produced it. You don't manage any of it — you
> just work, and the record assembles itself.
>
> https://github.com/auth-02/hub

---

## 3. Channels & sequencing
- **Day 0:** Show HN (2a) + r/LocalLLaMA. Lead with `pip install`, stdlib-only, offline.
- **Day 2–3:** Plugin post (2b) in Claude Code / AI-dev channels.
- Pin the demo one-liner (`uvx --from hubspaces hub serve --demo`) in every post.
