---
name: manifest
description: Use when starting work on a non-trivial feature, migration, refactor, or multi-step task in ANY repo. Creates and maintains a markdown manifest at `<repo-root>/tasks/<slug>/manifest.md` (inside the repo being worked on — NEVER inside the skill directory or ~/), with sibling `data/` (datasets, PDFs, spreadsheets), `artifacts/` (probes, inspection notes, scripts), and `runs/<date>/` (validation outputs) subfolders created lazily as needed. Captures the problem, decisions, exploration results, plan, open questions, test + rollout plans, and a final review — updating it continuously as the work progresses. Trigger when the user asks to "build X", "add X", "migrate X", "refactor X", when the task needs 3+ steps, or any time an explicit plan-before-code loop would help. Do NOT use for single-line fixes, obvious bugs, or one-shot questions.
---

# manifest

Every feature gets a **manifest** — a living markdown doc that declares the problem, the plan, the findings, and the eventual outcome. It lives inside the repo you are working on, right next to the code, so reviewers and future sessions read it alongside the diff. The deliverable is not just the code — it is the manifest that explains what/why/how.

## Where the manifest lives

**Always inside the repo being worked on**, at `<repo-root>/tasks/<slug>/manifest.md`. Resolve `<repo-root>` from the current working directory: the nearest ancestor that is a repo root (contains `.git` / `pyproject.toml` / `package.json` / similar). In a multi-repo workspace, that is the specific repo the work belongs to — not the workspace root above it.

**Never** write to:
- The workspace root above any repo. Manifest-collection tooling scans each repo's `tasks/`, so a manifest placed above a repo would be invisible.
- The skills directory (`~/skills`) or the skill directory itself.
- Anywhere outside a repo.

If the current working directory is a multi-repo workspace root (not inside a specific repo) and the user hasn't named a target repo, **ask which repo this work belongs to** before creating the file. Don't guess.

**Why this matters:** tooling that collects manifest docs looks for `manifest.md` files under each repo's `tasks/**/manifest.md`. A manifest in the wrong location (or named anything other than `manifest.md`) won't be picked up, defeating the proactive-update workflow below.

Create the `tasks/` directory if it does not exist. **Every task gets its own subfolder.** At init, create **only** `tasks/<slug>/manifest.md` — do **not** pre-create `data/`, `artifacts/`, or `runs/` upfront. Each subdir is created **lazily, only when something actually needs to go in it** (the first data file → `data/`, the first probe note/script → `artifacts/`, the first validation run → `runs/<date>/`). Empty scaffolding directories are noise; a fresh task is just its `manifest.md`.

```
<repo-root>/tasks/
└── <slug>/
    ├── manifest.md      # the living manifest          (template: templates/manifest.md)
    ├── data/            # referenced/source inputs only: PDFs, Excel, CSVs, datasets, JSON
    ├── artifacts/       # inspection notes, scripts,   (template: templates/inspection.md)
    │                    # probe outputs
    └── runs/            # dated outputs from actual test/validation runs
        └── YYYY-MM-DD/  # one folder per run date; SSE logs, tables, run CSVs go here
```

Rules:
- The manifest is always named **`manifest.md`** (never `<slug>.md`) — this makes it predictable for tooling (standup collection, grep).
- **`data/`** holds **referenced / source inputs only** — files given to or consumed by the task (example workbooks, sample PDFs/Excel/CSVs, datasets, JSON inputs). Create it on demand when such a file first enters the task (subfolders OK, e.g. `data/results/`). Keep generated virtualenvs, `node_modules`, and caches **out** of the task tree entirely.
- **`artifacts/`** holds **everything I generate** — inspection notes, one-off scripts/probes, AND generated output deliverables (PDFs, guides, derived spreadsheets). Generated files are **never** put in `data/`; if I produced it, it goes here (dated run outputs go in `runs/`).
- **`runs/`** holds time-stamped outputs from actually firing queries or running validation: SSE logs, parsed tables, benchmark results. One subfolder per date (`YYYY-MM-DD/`). Run outputs stay under their dated folder — they are not moved into `data/`.
- Never put inspection files, data files, or run outputs at the `tasks/<slug>/` root — keep the root clean (just `manifest.md` + the subdirs).

Copy from `~/skills/manifest/templates/<name>.md` when creating the manifest — fill in the title, ask, and any decisions already captured, then leave the rest as placeholders.

Slug: lowercase, hyphenated, imperative (`ndjson-to-parquet-migration`, `add-sso-login`, `refactor-payment-flow`).

The `tasks/` directory is **gitignored** — manifests, their `data/`, `artifacts/`, and `runs/` are **local-only** and never committed or pushed. Don't try to `git add` them. (When setting up a brand-new repo, add `tasks/` to its `.gitignore` first.)

## Core principle

**Write the manifest before the code, then keep it honest.** Every user answer, every surprise from exploration, every change of plan lands in the manifest in the same session. If the manifest drifts from reality, the workflow has failed.

## When to trigger

Invoke at the **start** of:

- A feature build (e.g. "add X", "support Y", "integrate with Z").
- A migration (format, schema, dependency, infrastructure).
- A refactor touching 3+ files.
- Anything where the user says "plan" / "first figure out" / "explore" / "let's design".
- Any task requiring exploration before implementation is sensible.

Skip for: typo fixes, single-line bug fixes, renames, answering a question, trivial one-shot edits.

## The manifest structure

Use these sections in this order. Sections can be empty with placeholder text; don't skip them.

```markdown
# <Feature / Task Title>

## Context
One paragraph on the ask as you understood it from the user, plus any business or technical background. Not the plan — the problem.

### Decisions
Numbered list of decisions the user has already made (or made during the session). Each line should stand alone.
1. <decision> — captured <date or "from session">.
2. ...

## Exploration Results
What you found in the codebase. Cross-link `file:line` for every claim. Sections suggested (adapt as needed):
### Consumers / callers
### Data shape / schema
### Related subsystems
### Out of scope
### Not found
(Keep this section factual. No plan verbs like "we will" or "let's".)

## Plan
Checkbox list of steps. Each step: one line heading + a few sub-bullets describing the edit. Update checkbox state (`[x]`) as you go.

- [ ] **Step 1 — <name>** `<path/to/file>`
  - What to change
  - Why / what it unblocks

## Open questions
Numbered list. When the user answers, append `-> <answer>` inline on the same line; do not delete the question.
1. <question>?
2. <question>? -> <user's answer, captured inline>

## Confirmed findings (after real exploration)
Populate AFTER running exploration code / probes. Distinguish "assumed" from "confirmed". Includes:
- Tables of concrete observations (blob names, schemas, counts).
- Callouts for surprises that invalidate the initial plan — use ⚠️.

## Testing plan
Concrete steps. Day-by-day if multi-day. Include: parity baselines, canary, fallback tests, scheduled runs, exit gate.

## Rollout plan
Stages, rollback procedure, coordination notes, gotchas.

## Review
Fill in at the end. Files changed (with one-line per-file summary), how to cut over, known follow-ups, what was flagged out-of-scope.
```

## Workflow stages

### 1. Capture the ask (before any tool calls other than creating the manifest)

- Read the user's message carefully. Paraphrase the problem back in one sentence before doing anything.
- Create `tasks/<slug>/manifest.md` (with `artifacts/` and `runs/` subfolders alongside) populated from the ask. "Exploration Results" and "Confirmed findings" are empty placeholders. "Plan" has rough shape only — don't overcommit before exploring.
- If the user gave a spec/list/table, paste it verbatim under **Context** so it's not lost.
- **After creating the manifest**, write the slug to `tasks/.current-task` (one line, no newline padding) so the shell prompt can display it: `echo -n "<slug>" > tasks/.current-task`. This file is the prompt's source of truth — update it whenever the active task changes mid-session (e.g. user switches to a different task on the same branch).

### 2. Explore

- Use grep / read / file-listing to find consumers, patterns, and current behaviour. Delegate to subagents (Explore / general-purpose) for broad sweeps. Limit direct reads to files you've identified.
- Write findings to **Exploration Results** as you go — `file:line` references, not summaries.
- For anything that requires real-world data (bucket contents, DB schema, external API shape), write a **read-only** probe script/asset/query, run it, and save the output under `artifacts/` (e.g. `artifacts/inspection.md`, `artifacts/<probe>.csv`). Never guess what remote state looks like.
- Flag surprises immediately in **Confirmed findings** with ⚠️ — e.g. "field X is dropped from the new schema", "file is unsharded where docs said sharded".

### 3. Plan + open questions

- Convert exploration into a step-by-step **Plan** with checkboxes. Keep each step minimal — bug fix-sized if possible.
- Extract decisions the user must make into **Open questions**. Ask them all at once, numbered, so the user can answer inline.
- When the user answers, edit the manifest: append `-> <answer>` to each question. Then merge the answer into **Decisions**.

### 4. Implement

- Update the plan's checkboxes as steps complete. Don't batch — mark each done when it's actually done.
- When a step reveals something unexpected (a missing field, a broken assumption), stop, update **Confirmed findings**, update the plan if scope changed, then continue.
- For risky writes (DBs, buckets, external systems shared with other envs), design a **local/dev-only gate** (e.g. a `local_csv_output_dir` config, a `dry_run` flag, a `dev_only` toggle) — then document it in a dedicated subsection of the manifest.

### 5. Tests + rollout

- Write a **Testing plan** with explicit parity baselines ("diff row counts vs main"), canary (one asset / one file at a time), fallback verification, and an exit gate.
- Write a **Rollout plan** with stages, a rollback procedure (ideally config-only, no redeploy), and coordination notes (who needs to know before flipping production).
- If the user has constraints like "don't touch demo", "dev only", "keep fallback" — surface them at the top of the rollout plan.

### 6. Finalize

- Populate the **Review** section: files changed (with a one-line summary each), how to cut over, follow-ups, out-of-scope items.
- Offer the next natural step (branch + push + MR, schedule a cleanup agent, etc.) but don't take destructive/shared actions without confirmation.
- On `git commit` / branch creation: the commit message should mirror the Review summary. Keep the manifest out of the commit if it's gitignored — otherwise include it.

## Operating rules

- **One manifest per task.** Don't create tiers/sub-docs unless the user asks for it.
- **Append-only for decisions and open questions.** Never delete history; strike-through or annotate if a decision reverses.
- **Real data over assumptions.** If the manifest makes a schema claim, it must be backed by a probe saved alongside.
- **Update in the same session.** Don't defer updates with "I'll record this later".
- **Cross-link everything.** `file:line` for code claims; relative paths to inspection files; commit SHAs in the Review.
- **Defer code until the plan is agreed.** If the user hasn't confirmed direction, don't start edits — unless they explicitly said "just do it".
- **Protect shared infra.** When the work touches DBs, buckets, queues, or external services used by demo/prod, add an isolation knob early and document it.
- **Never invent skill / subagent / tool names.** Only use ones that exist in the environment.

## Proactive updating — do this without being asked

Updating the manifest is **part of the task**, not an extra chore the user has to request. Once a manifest exists for the current work, treat every one of the events below as an automatic trigger to edit it in the **same turn** the event happens — before moving on, before the next reply, before running more tools. The user should never have to say "write this down" / "log the decision" / "update the task file".

Triggers that automatically update the manifest (in the same turn):

1. **User answers an Open Question** → append `-> <answer>` inline on that question, then promote the answer to **Decisions** (numbered, dated).
2. **User reverses or refines an earlier decision** → strike-through the old decision, add the new one with a date and a `Superseded (YYYY-MM-DD)` tag; never delete the old line.
3. **User approves a course of action** ("ok", "do it", "that's fine", "whatever you choose") → record the concrete choice that was on the table as a Decision before executing.
4. **Exploration reveals something that invalidates the plan** → add a ⚠️ entry to **Confirmed findings** and update the affected Plan step, in the same turn.
5. **A plan step completes** → flip its checkbox `[ ]` → `[x]` immediately; if the step split into sub-steps, list them inline.
6. **New scope added mid-session** → either add a new Plan step or (for a genuinely separate task) spin up a second manifest file; do not silently grow an existing step.
7. **A follow-up iteration after "Review"** (user asks for a tweak after you declared done) → add a **Follow-up increments** subsection under Review with what changed and why, in the same turn. Don't reopen the main Plan unless the change is large.
8. **Files are edited, created, or deleted** → update **Files changed** in Review the same turn (don't wait until the user asks for a summary).
9. **`gitignore` / `tasks/` visibility** → if `tasks/` is not in `.gitignore`, note it; if the user wants it local, add it to `.gitignore` without asking again after the first confirmation.

Rule of thumb: if you're about to say something in chat that is a **decision, a finding, a change, or a reversal**, the manifest gets the same content first (or at the latest, in the same turn). Chat is ephemeral; the manifest is the record.

When you can't tell whether something warrants a manifest update, err toward writing it down — a slightly over-documented manifest costs nothing; a silently-drifted one costs trust.

## Anti-patterns to avoid

- Writing a grand plan before any exploration. Plans written without grepping are fiction.
- Letting the manifest and the code diverge. If you updated code, update the manifest in the same turn.
- Mixing "the ask" and "the plan" in one section. Separate what the user wanted from what you intend to do.
- Dropping the fallback / rollback section because "we won't need it". Keep it — future-you will.
- Hiding surprises. If exploration invalidates a decision, say so with ⚠️ and update **Decisions** with the revised stance.
- Committing the manifest without checking gitignore.
- Narrating every step in chat while the manifest stays sparse. The chat is ephemeral; the manifest is the record.
- **Waiting to be told.** Never require the user to say "log this" / "note it down" / "update the task file". The manifest is your output as much as the code is. If the user has to prompt an update, the skill has failed — see **Proactive updating** above.
- **Batching updates.** Don't accumulate decisions across three turns and write them all at the end. Update in the same turn each decision is made; otherwise you forget nuance and miss reversals.
- **Leaving reversed decisions undocumented.** When a decision flips mid-session, the old line stays (struck through) and the new line goes in with `Superseded (YYYY-MM-DD)` or `Revised (YYYY-MM-DD)`. Future-you will want to know what almost got built.

## Templates

Copy from `~/skills/manifest/templates/` — but only when each is actually needed (see the lazy-creation rule above), not all upfront:

- `manifest.md` — the main manifest scaffold (Context, Decisions, Exploration Results, Plan, Open questions, Confirmed findings, Testing plan, Rollout plan, Review). Copied **at init** — lands at `tasks/<slug>/manifest.md`.
- `inspection.md` — for raw exploration probes. Copied **only when you start probing** — lands at `tasks/<slug>/artifacts/inspection.md` (creating `artifacts/` then).
- `notes.md` — free-form scratch. Copied **only when you need it** — lands at `tasks/<slug>/artifacts/notes.md`.

For the manifest, fill in the title and any context you already have from the user's ask, then keep the other sections as placeholders to populate as the work progresses.

## Example invocations

- "Let's add support for parquet in the pipeline" → create `tasks/add-parquet-support/manifest.md`, start at stage 1.
- "Refactor the auth middleware to use JWT" → create `tasks/refactor-auth-to-jwt/manifest.md`.
- "Migrate sector_exposure to a normalized table" → create `tasks/normalize-sector-exposure/manifest.md`.
- "Integrate with Acme Payments" → create `tasks/integrate-acme-payments/manifest.md`.

## Example

`examples/migrate-uploads-to-object-storage.md` is a comprehensive manifest to model yours on: a design-first migration showing a full Context paragraph, a numbered Decisions log (with dates), exploration findings with `file:line` cross-links, a Stack section, a per-layer Plan, testing + rollout plans, and the Review placeholder. Use it to calibrate altitude and how much to capture at each stage.

## Not for

- "Fix the typo on line 12" — too small.
- "Why is this function slow?" — it's a question, not a feature.
- "Rename `foo` to `bar` across the repo" — rename, no design surface.
- Multi-turn conversations where the user has already started implementing without a plan and just wants help finishing — if the manifest would be retrofit, ask first.
