"""Guard the UI layering (z-index) contract — AGENTS.md › "UI layering".

Hub has two front-ends (the SPA `ui/src/hub.css` and the standalone doc page
`ui/public/chrome.css`). A popup/toast that picks a bare z-index number instead
of a layer token renders *behind* the open trace/graph/palette — the recurring
"it opened on the home page" bug. These tests assert every *summoned* surface
(modal, name input, composer, help) uses `var(--z-transient)` and every
notification uses `var(--z-toast)`, and that both stylesheets define the scale,
so the regression can't silently return with the next feature.
"""
import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

_UI = Path(__file__).resolve().parent.parent / "hubspace" / "ui"
_HUB_CSS = (_UI / "src" / "hub.css").read_text(encoding="utf-8")
_CHROME_CSS = (_UI / "public" / "chrome.css").read_text(encoding="utf-8")

# The ordered scale both stylesheets must declare.
_TOKENS = ("--z-sticky", "--z-chrome", "--z-overlay",
           "--z-palette", "--z-transient", "--z-toast")


def _decl(css: str, selector: str) -> str:
    """The declaration block for an exact top-level selector (first match)."""
    # Match `<selector>{ ... }` where selector is the whole rule head.
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return m.group(1) if m else ""


class TestLayeringTokensDefined(unittest.TestCase):
    def test_both_frontends_define_the_full_scale(self):
        for name, css in (("hub.css", _HUB_CSS), ("chrome.css", _CHROME_CSS)):
            for tok in _TOKENS:
                self.assertIn(tok + ":", css, f"{name} missing {tok}")

    def test_transient_is_above_overlay_and_palette(self):
        # Read the numeric values from hub.css :root and assert the ordering
        # that makes summoned surfaces + toasts sit on top.
        def val(tok):
            m = re.search(re.escape(tok) + r":\s*(\d+)", _HUB_CSS)
            return int(m.group(1))
        self.assertLess(val("--z-overlay"), val("--z-palette"))
        self.assertLess(val("--z-palette"), val("--z-transient"))
        self.assertLess(val("--z-transient"), val("--z-toast"))


class TestSummonedSurfacesUseTokens(unittest.TestCase):
    def test_spa_notifications_use_z_toast(self):
        self.assertIn("var(--z-toast)", _decl(_HUB_CSS, ".toast"))

    def test_spa_modal_and_composer_use_z_transient(self):
        for sel in (".modal", ".composer", ".pal-help"):
            self.assertIn("var(--z-transient)", _decl(_HUB_CSS, sel),
                          f"{sel} must layer on --z-transient")

    def test_doc_page_notifications_use_z_toast(self):
        self.assertIn("var(--z-toast)", _decl(_CHROME_CSS, ".doc-toast"))

    def test_doc_page_summoned_surfaces_use_z_transient(self):
        for sel in (".doc-pub-namebox", ".hub-composer"):
            self.assertIn("var(--z-transient)", _decl(_CHROME_CSS, sel),
                          f"{sel} must layer on --z-transient")


class TestNoBareHighZIndex(unittest.TestCase):
    """No selector may hard-code a bare z-index >= the overlay layer (90): that
    is exactly how a popup used to leapfrog the scale and then get occluded.
    High layers must go through the tokens (var(--z-…) or calc on one)."""

    def _offenders(self, css: str):
        bad = []
        for m in re.finditer(r"z-index:\s*([^;]+);", css):
            expr = m.group(1).strip()
            if "var(" in expr:
                continue
            num = re.fullmatch(r"(\d+)", expr)
            if num and int(num.group(1)) >= 90:
                bad.append(expr)
        return bad

    def test_hub_css_has_no_bare_high_z(self):
        self.assertEqual(self._offenders(_HUB_CSS), [])

    def test_chrome_css_has_no_bare_high_z(self):
        self.assertEqual(self._offenders(_CHROME_CSS), [])


if __name__ == "__main__":
    unittest.main()
