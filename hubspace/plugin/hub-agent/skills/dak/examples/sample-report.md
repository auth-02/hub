# Sample Report

This is an example artifact you can publish to verify the skill end to end.

```bash
# frozen snapshot link
python3 scripts/dak.py examples/sample-report.md

# stable live link you can re-publish
python3 scripts/dak.py examples/sample-report.md --mode live --slug sample
```

## What to expect

- Markdown is rendered to a clean, readable HTML page.
- The command prints a single URL to stdout — that's the shareable link.
- Snapshot links never change; live links update when you re-run with the same `--slug`.

> Tip: run with `--dry-run` first to see the exact deploy command and predicted URL
> without publishing anything.
