# Hub — Option A Architecture Plan

**Self-shipping Claude Code plugin, offline, no duplicated engine.**

Version target: `0.3.0` · Status: plan

---

## The one-sentence architecture

The `hubspaces` Python package remains the *only* place the engine (indexer +
backend + UI + viewer + CLI) is authored. The `hub-agent` plugin ships the
producer skills, the `/hub` command, and a **vendored copy of the exact
published wheel**, so it runs fully offline the moment it is installed — without
reimplementing any engine code.

"Self-shipping" here means **self-sufficient at install time**, not "contains a
second copy of the source."

---

## Division of labor

| Concern | Package (`hubspaces`) | Plugin (`hub-agent`) |
|---|---|---|
| Indexer / backend | ✅ authored here | ▶ runs the vendored wheel |
| UI / viewer | ✅ authored here | ▶ runs the vendored wheel |
| CLI (`hub`, `hub serve`) | ✅ authored here | ▶ invoked via the wheel |
| Producer skills (manifest, stacked, kagaz, dak) | — | ✅ shipped here |
| `/hub` command | — | ✅ shipped here |
| Offline guarantee | ✅ standalone | ✅ via bundled wheel |

Single source of truth: the engine is edited in one repo path only. The plugin
carries a **frozen build output**, never source.

---

## Core decisions (locked)

1. **Vendor the pinned wheel.** The plugin repo contains
   `hub-agent/vendor/hubspaces-<version>-py3-none-any.whl`, overwritten on each
   release. Only the current wheel lives in the working tree; older versions
   remain in git history and on PyPI.
2. **Run via `uv` against the local wheel.** `/hub` executes
   `uvx --from <bundled-wheel> hub serve`. This is offline (wheel is local),
   hermetic (isolated env + provisioned interpreter), and never touches PyPI.
3. **The plugin always uses its bundled wheel.** It never runs a user's
   separately-installed `hubspaces`, eliminating version skew.
4. **External requirement = `uv` present only.** No network requirement, no
   ambient Python-package requirement. (`uv` is near-ubiquitous for this
   audience.)

### Fallback (only if "requires uv" proves to be real friction)
`/hub` pip-installs the bundled wheel into a plugin-local venv on first run
using system Python 3.11+. Still offline, more moving parts. Do not build this
first; keep it in reserve.

---

## Why A (summary of rationale)

- **Brand consistency** — Hub's promise is *local-first, nothing leaves your
  machine*. Option B (fetch from PyPI on first run) contradicts that on first
  use. A keeps the promise literally true.
- **The usual cost of vendoring does not apply** — the wheel is ~70 kB,
  stdlib-only, `py3-none-any`, zero transitive deps. Close to the ideal case for
  bundling.
- **No source duplication** — the plugin ships a snapshot, not a second engine.
- **No version skew** — the hermetic-wheel rule removes the "which engine runs?"
  question entirely.
- The only genuine cost — release friction — reduces to one automatable CI step.

---

## Work breakdown

### Phase 0 — Prerequisite
- [ ] Land the current stacked PR train (43 → 51) and confirm the engine builds
      a clean `hubspaces` wheel via existing `publish.yml`.

### Phase 1 — Plugin repo layout
- [ ] Create `hub-agent/vendor/` and commit the current
      `hubspaces-<version>-py3-none-any.whl`.
- [ ] Add `.gitattributes` if needed so the wheel is treated as binary.
- [ ] Confirm `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`
      exist and validate against the Claude Code schema.

### Phase 2 — The `/hub` command
- [ ] Write `commands/hub.md` so `/hub` resolves the bundled wheel path and runs
      `uvx --from <wheel> hub serve` (with `--demo` passthrough optional).
- [ ] Handle the "uv not found" case with a clear, actionable error message.
- [ ] Verify `/hub` works with **no** `hubspaces` on the system and **no**
      network.

### Phase 3 — Skills bundling
- [ ] Confirm the four producer skills (manifest, stacked, kagaz, dak) are
      shipped under the plugin and load on install.
- [ ] Verify the `manifest` skill emits the *exact* `tasks/<slug>/` structure the
      package's indexer and lineage graph expect (one contract, verified).

### Phase 4 — Release automation (kills the friction)
- [ ] Extend the package release workflow: on a tagged `hubspaces` release, a CI
      job copies the freshly built wheel into `hub-agent/vendor/`, overwrites the
      old one, bumps the plugin version, and opens a bump PR.
- [ ] Tag the plugin version to match the engine version it vendors (or track the
      mapping explicitly).

### Phase 5 — Verification matrix
- [ ] Clean machine, no `hubspaces`, no network, `uv` present → `/plugin install`
      → `/hub` serves successfully.
- [ ] Machine with a *different* `hubspaces` installed → `/hub` still runs the
      **bundled** wheel, not the ambient one.
- [ ] `hub serve --demo` works through the plugin path.
- [ ] Standalone package path (`pipx install hubspaces && hub serve`) unaffected.

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Release friction (re-vendor every version) | CI step auto-copies wheel + opens bump PR (Phase 4). |
| Version skew (plugin vs ambient package) | Hermetic rule: plugin only ever runs its bundled wheel. |
| Repo size creep | Keep only the current wheel in the tree; history holds the rest. |
| `uv` not present | Clear error + documented one-line install; fallback venv path in reserve. |
| Python interpreter absent | `uv` provisions the interpreter; fallback requires system 3.11+. |

---

## Definition of done

- A user with only `uv` installed can `/plugin install hub-agent@hub` and run
  `/hub` **offline**, getting the full indexer + UI + viewer.
- The engine exists as source in exactly one repo path.
- A tagged engine release automatically re-vendors the wheel into the plugin.
- The standalone `pip install hubspaces` experience is unchanged.
