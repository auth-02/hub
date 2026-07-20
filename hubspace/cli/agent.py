"""`hub agent` — manage a persistent launchd agent that runs hub (macOS).

This is the single, reusable implementation of launchd plist generation +
management, shared by BOTH distributions:

* the package's `scripts/setup-launchd.sh` (dev/dogfood, runs `uv run --project`)
* the plugin's `scripts/daemon.sh` (runs the vendored wheel via `uv tool run`)

Only the *launcher prefix* differs between them — passed via ``--exec``. Everything
else (plist XML, KeepAlive vs StartInterval, WorkingDirectory, launchctl
bootstrap/bootout/print) lives here so both inherit every fix.

Two agent shapes:
  --serve                KeepAlive agent running ``<exec> serve --port <port>``
  --rebuild-interval N   StartInterval agent running ``<exec>`` every N seconds
                         (one-shot rebuild; HUB_SERVER_PORT is set for links)
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape as _xml


def _default_exec() -> list[str]:
    """How to launch hub persistently when the caller doesn't say.

    Prefer a resolved ``hub`` on PATH; otherwise the current interpreter running
    the package module. Both are stable across reboots (unlike an ephemeral
    ``uvx`` env), so callers using an ephemeral env MUST pass ``--exec``.
    """
    hub = shutil.which("hub")
    if hub:
        return [hub]
    return [sys.executable, "-m", "hubspace.cli.hub"]


def _plist_path(label: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def _render_plist(
    label: str,
    program_args: list[str],
    workdir: str,
    *,
    keepalive: bool,
    interval: int | None,
    env: dict[str, str],
) -> str:
    args_xml = "\n".join(f"    <string>{_xml(a)}</string>" for a in program_args)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
        '<plist version="1.0">',
        "<dict>",
        f"  <key>Label</key><string>{_xml(label)}</string>",
        "  <key>ProgramArguments</key>",
        "  <array>",
        args_xml,
        "  </array>",
        f"  <key>WorkingDirectory</key><string>{_xml(workdir)}</string>",
        "  <key>RunAtLoad</key><true/>",
    ]
    if env:
        parts.append("  <key>EnvironmentVariables</key>")
        parts.append("  <dict>")
        for k, v in env.items():
            parts.append(f"    <key>{_xml(k)}</key><string>{_xml(v)}</string>")
        parts.append("  </dict>")
    if keepalive:
        parts.append("  <key>KeepAlive</key><true/>")
    if interval is not None:
        parts.append(f"  <key>StartInterval</key><integer>{int(interval)}</integer>")
    parts.append("</dict>")
    parts.append("</plist>")
    return "\n".join(parts) + "\n"


def _gui() -> str:
    return f"gui/{os.getuid()}"


def _require_macos() -> None:
    if sys.platform != "darwin":
        print("hub agent: persistent agents use macOS launchd only.", file=sys.stderr)
        sys.exit(1)


def install(args) -> None:
    _require_macos()
    exec_tokens = shlex.split(args.exec_prefix) if args.exec_prefix else _default_exec()
    workdir = args.root or os.getcwd()
    port = args.port

    if args.rebuild_interval is not None:
        program_args = exec_tokens
        env = {"HUB_SERVER_PORT": str(port)}
        keepalive, interval = False, args.rebuild_interval
    else:  # default: KeepAlive serve agent
        program_args = [*exec_tokens, "serve", "--port", str(port)]
        env = {}
        keepalive, interval = True, None

    plist = _plist_path(args.label)
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(
        _render_plist(args.label, program_args, workdir,
                      keepalive=keepalive, interval=interval, env=env),
        encoding="utf-8",
    )
    label_ref = f"{_gui()}/{args.label}"
    subprocess.run(["launchctl", "bootout", label_ref],
                   capture_output=True, check=False)
    r = subprocess.run(["launchctl", "bootstrap", _gui(), str(plist)],
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        print(f"hub agent: launchctl bootstrap failed: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    kind = "rebuild" if interval is not None else "serve"
    print(f"hub agent '{args.label}' installed ({kind}) at "
          f"http://localhost:{port} — serving {workdir}")


def uninstall(args) -> None:
    _require_macos()
    subprocess.run(["launchctl", "bootout", f"{_gui()}/{args.label}"],
                   capture_output=True, check=False)
    plist = _plist_path(args.label)
    plist.unlink(missing_ok=True)
    print(f"hub agent '{args.label}' stopped and removed.")


def status(args) -> None:
    _require_macos()
    r = subprocess.run(["launchctl", "print", f"{_gui()}/{args.label}"],
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        print(f"hub agent '{args.label}' is not installed.")
        return
    for line in r.stdout.splitlines():
        s = line.strip()
        if s.startswith("state =") or s.startswith("pid ="):
            print(f"  {s}")


def run(args) -> None:
    {"install": install, "uninstall": uninstall, "status": status}[args.action](args)
