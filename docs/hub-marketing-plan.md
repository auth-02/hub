# Hub — Marketing Plan (0.3.0 launch)

**Positioning, copy, surfaces, and rollout for the current + landing state.**

Scope: market what ships now (v0.2.3 + the 43–51 train landing as 0.3.0).
Upcoming features appear only as a short, uncommitted roadmap.

---

## 1. Positioning

**Core idea:** Hub is a decision-and-reasoning ledger for agent-driven work. The
manifest records *what you decided, what the agent decided, what it found, and
the plan*; lineage makes that record navigable. Most AI-dev tools market the
generation — Hub markets the *record of why*.

**Primary tagline**
> Your agent produces. Hub links it. You trace it.

**Support line (concrete anchor, keep from the old hero)**
> Point it at a folder — every task, decision, run, and diagram becomes one
> searchable, traceable page. Stdlib-only Python; nothing leaves your machine.

**Two-artifact story**
- **Package (`hubspaces`)** — Hub, standalone. `pip install`, point at any folder.
- **Plugin (`hub-agent`)** — Hub, batteries-included for Claude Code: producer
  skills + the full engine bundled in, works offline on install (Option A).

**The through-line: lineage.** Not "task lineage tracing" (mechanism) but
"nothing your agent makes floats free" (payoff). Every run, artifact, prompt, and
diagram traces back to the task and the decision that produced it.

---

## 2. The announcement peg

**0.3.0 — diagrams, in place.** Hub can now *draw*, not just display: create
Excalidraw diagrams in the UI, offline, and task diagrams become first-class
lineage nodes. This is the concrete proof of the read → write shift and the
reason the launch is newsworthy rather than "another markdown viewer."

Do **not** launch on 0.2.3. Cut 0.3.0 when 43 → 51 merge, then launch.

---

## 3. Surfaces & copy status

| Surface | What changes | Auto-updates on release? |
|---|---|---|
| README hero + features + roadmap | Rewrite top ~15 lines; reorder features; add roadmap | Propagates to PyPI on publish |
| `pyproject.toml` `description` + `keywords` | New summary + audience-correct tags | Drives PyPI search |
| PyPI long description | = README | ✅ auto |
| GitHub repo description + topics | Currently empty — fill both | ❌ manual (UI) |
| Pages site (`auth-02.github.io/hub`) hero + install block + meta-description + version | New hero, two-path install, ribbon | ❌ manual |
| `marketplace.json` description | Picker one-liner | ❌ manual |
| `plugin.json` description + keywords | Plugin manifest | ❌ manual |
| Plugin `README.md` | Full storefront (batteries-included framing) | ❌ manual |

> All prepared copy for these surfaces lives in the working notes / prior drafts;
> this plan tracks *what* changes and *when*, not the full text.

---

## 4. Assets to produce

1. **Lineage trace-walk GIF** (highest value) — agent runs a task → files appear
   → click an artifact → `// trace` walks back to the manifest → the decision is
   visible. ~6 seconds. This *is* the product; a static banner can't convey it.
   Use as README banner (`?v=0.3.0` cache-bust) and in the launch post.
2. **Diagrams-in-place clip** — creating an Excalidraw diagram and seeing it
   appear in the task trace. Supports the 0.3.0 peg.
3. **Two-path install graphic** (optional) — package vs plugin, side by side.

---

## 5. Audience & channels

Decide the **primary** target; the two-path framing serves both, but the lead
determines hero order and first post.

- **General local-first / dev crowd** — Show HN, r/LocalLLaMA, package-first.
  Lead with `pip install`, stdlib-only, offline. Differentiator: legibility over
  agent output without cloud or deps.
- **Claude Code / AI-dev crowd** — plugin-first, AI-dev channels. Lead with
  "the board fills itself," offline batteries-included plugin. Differentiator:
  zero-effort provenance.

**Recommended:** lead general (Show HN / local-first) for credibility — the
standalone, no-deps viewer is the trust anchor — then follow with a plugin-focused
post for the Claude Code audience a few days later.

---

## 6. Launch copy (ready angles)

**Show HN title options**
- Show HN: Hub — a local, dependency-free index for the work your coding agent does
- Show HN: Hub — turn your agent's manifests, runs, and diagrams into one traceable page

**Body beats (order matters):**
1. The problem: agent output is easy, the *record of why* is lost.
2. What Hub does: manifest = decision log; lineage connects every output back.
3. Two ways in: standalone package / batteries-included plugin.
4. Trust: stdlib-only, no npm, no framework, nothing leaves your machine.
5. The peg: diagrams in place, now first-class lineage nodes.
6. One-command try: `uvx --from hubspaces hub serve --demo`.
7. Roadmap teaser (one line): comments → sharing → an open Hub spec → agent (MCP) retrieval.

---

## 7. Roadmap teaser (uncommitted, in this order)

Everything below feeds or exposes the **lineage graph** — the one asset the whole
product sits on. Ordered by build sequence; label publicly as "direction, not
commitment."

**Prerequisite (internal, not marketed): spec data-model core.** Lock the node
types and lineage relations — including how comments attach — before building
comments. A design decision, not a shipped feature; front-loads into the comments
work to prevent retrofitting the spec later.

1. **Comments** — notes on a manifest or artifact that the agent can read and
   close the loop on, human ↔ agent, in one place. Built as a spec-compliant
   lineage node from day one.
2. **Sharing** — one-click publish of any asset, or a whole task with its full
   lineage (manifest, runs, artifacts, draws), to a shareable review link
   (built on Dak, already bundled in the plugin).
3. **Hub Spec** — the producer contract, published and versioned: emit this
   structure and *any* agent or tool works with Hub. Turns Hub from "a thing for
   Claude Code" into a standard for agent-work legibility. Formalized *after*
   comments have battle-tested the model, so it documents reality, not a guess.
   Ships with a version field + compatibility stance from v1.
4. **Agent retrieval (MCP)** — a surface so coding agents find the right task and
   its context themselves, over a now-stable, spec-documented graph.
5. **Faster indexer / rebuild** — position-flexible: at the end if rebuild is
   fine at current scale, or pulled to right after comments if it is *already*
   hurting on real repos. (Open question — confirm before locking the order.)

Narrative arc: **close the loop in place → share it out → make the contract open
→ let agents query it themselves.**

### Marketing note on the Hub Spec
When it goes public it becomes a commitment surface — once other tools emit
"Hub-compliant" structure, the layout can't change casually. That is a *good*
problem (it signals adoption) and worth leaning into as a positioning milestone:
"Hub isn't just a tool, it's a spec." But the launch of the spec must include
versioning and a compatibility promise, or early adopters get burned.

---

## 8. Metadata punch-list (highest-leverage, low-effort)

- [ ] `pyproject.toml` `description` → agent-driven-work summary (drives PyPI search).
- [ ] `pyproject.toml` `keywords` → add `claude-code`, `agents`, `ai`,
      `local-first`, `lineage`, `task-tracking`.
- [ ] GitHub repo **description** (currently empty) + **topics**.
- [ ] Pages `meta-description` + hero + two-path install block + `v0.3.0` footer.
- [ ] Kind chip list includes `DRAW` everywhere it's enumerated.

---

## 9. Rollout order

1. Merge 43 → 51; bump to **0.3.0** in `pyproject.toml`.
2. Apply README (hero + features + roadmap) and `description`/`keywords` in the
   same commit.
3. Set GitHub repo description + topics (UI, ~30 s).
4. Update Pages hero + install block + meta-description + version.
5. Update plugin storefront (`marketplace.json`, `plugin.json`, plugin README) —
   batteries-included / offline framing per Option A.
6. Record the lineage GIF; drop into `assets/screenshots/banner.png`.
7. Tag release → PyPI auto-publishes → README propagates.
8. Post launch (general first), then plugin-focused follow-up.

**Only auto-updating surfaces:** PyPI long description (= README). Everything
else — repo metadata, Pages, plugin storefront — is manual and must ship in the
same window as the release.
