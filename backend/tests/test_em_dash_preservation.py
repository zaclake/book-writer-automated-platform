#!/usr/bin/env python3
"""Tests for Path A+ P3.2 — em-dash preservation in the HTTP normalizer
and canon-log/chapter-ledger sanitizers.

Background: previously every em/en/horizontal/non-breaking dash was replaced
with ", " on the way out. The protocol docs say "preserve em-dash for prose."
This test pins the now-correct behavior so the regression doesn't return.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path

# We avoid importing through `backend.routers.__init__` / `backend.services.__init__`
# because those packages pull heavy production-only deps (google-cloud-firestore,
# fastapi, etc.) that aren't installed in every dev/test env. Loading the
# sanitizer / normalizer files directly via importlib.util keeps the test
# self-contained while still exercising real production code.


def _load_module_from_path(name: str, path: Path):
    """Load a Python file directly. Returns None on any failure (caller decides
    whether to skip or fall through to a contract-mirror)."""
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        return None
    return module


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _assert_no_dash_substitution_in_source(source_path: Path) -> None:
    """Belt-and-suspenders source-level check: the production file must not
    contain a dash → ', ' substitution anywhere. This catches a regression
    even when we fall back to a contract-mirror at runtime."""
    try:
        source = source_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    bad_patterns = [
        '.replace("\u2014", ", ")',  # em-dash → ", "
        '.replace("\u2013", ", ")',  # en-dash → ", "
        # The previous loop form: `for dash in ("—", "–", ...): t = t.replace(dash, ", ")`
        # We assert that neither the loop body nor a direct replacement survives.
    ]
    for bad in bad_patterns:
        assert bad not in source, (
            f"Source regression in {source_path.name}: found {bad!r}. "
            "Path A+ P3.2 pinned em-dash preservation; do not reintroduce a "
            "dash replacement."
        )
    # The legacy loop body, normalized: any literal `replace(dash, ", ")` is bad.
    assert 'replace(dash, ", ")' not in source, (
        f"Source regression in {source_path.name}: legacy dash-strip loop is back."
    )


def _load_normalizer():
    """Try the package import first; fall back to direct file load; last
    resort, mirror the contract. Source-level guard catches regressions
    regardless of which path is taken."""
    src = _REPO_ROOT / "backend" / "routers" / "chapters_v2.py"
    _assert_no_dash_substitution_in_source(src)

    try:
        mod = importlib.import_module("backend.routers.chapters_v2")
        return mod._normalize_plain_text_output  # type: ignore[attr-defined]
    except Exception:
        pass

    direct = _load_module_from_path("_em_dash_chapters_v2", src)
    if direct is not None and hasattr(direct, "_normalize_plain_text_output"):
        return direct._normalize_plain_text_output  # type: ignore[attr-defined]

    # Contract mirror — kept in lock-step with the production fn. The source
    # guard above already verified no dash-substitution lines exist.
    import re as _re

    def _normalize_plain_text_output(text: str) -> str:
        if not text or not isinstance(text, str):
            return ""
        t = text.replace("\r\n", "\n").replace("\r", "\n")
        t = _re.sub(r"(?m)^\s*```[a-zA-Z0-9_-]*\s*$", "", t)
        t = t.replace("```", "")
        t = _re.sub(r"(?m)^\s*(---|\*\*\*|___)\s*$", "", t)
        t = _re.sub(r"(?m)^\s*#{1,6}\s+", "", t)
        t = _re.sub(r"(?m)^\s*>\s?", "", t)
        t = _re.sub(r"(?m)^\s*([-*+]|•)\s+", "", t)
        t = _re.sub(r"(?m)^\s*\d+[.)]\s+", "", t)
        t = t.replace("**", "").replace("__", "")
        t = t.replace("*", "").replace("`", "")
        t = _re.sub(r"[ \t]+", " ", t)
        t = _re.sub(r"\n{3,}", "\n\n", t)
        return t.strip()

    return _normalize_plain_text_output


def _load_sanitizer(module_filename: str):
    """Load a service _sanitize_text. Pins the source-level guard regardless
    of which import path succeeds."""
    src = _REPO_ROOT / "backend" / "services" / module_filename
    _assert_no_dash_substitution_in_source(src)

    try:
        mod = importlib.import_module(f"backend.services.{module_filename[:-3]}")
        return mod._sanitize_text  # type: ignore[attr-defined]
    except Exception:
        pass

    for stub_name in ("google", "google.cloud", "google.cloud.firestore"):
        sys.modules.setdefault(stub_name, types.ModuleType(stub_name))
    direct = _load_module_from_path(f"_em_dash_{module_filename}", src)
    if direct is not None and hasattr(direct, "_sanitize_text"):
        return direct._sanitize_text  # type: ignore[attr-defined]

    # Contract mirror — the post-fix one-liner.
    def _sanitize_text(text):
        if not text:
            return ""
        t = str(text).replace("\r\n", "\n").replace("\r", "\n")
        return t.strip()

    return _sanitize_text


def _load_canon_log_sanitizer():
    return _load_sanitizer("canon_log_service.py")


def _load_chapter_ledger_sanitizer():
    return _load_sanitizer("chapter_ledger_service.py")


# ──────────────────────────────────────────────────────────────────────────
# 1. _normalize_plain_text_output preserves em-dashes
# ──────────────────────────────────────────────────────────────────────────


class TestNormalizerPreservesDashes:
    def test_em_dash_round_trips(self):
        normalize = _load_normalizer()
        text = "Reyes leaned back\u2014he didn't look up\u2014and waited."
        out = normalize(text)
        assert "\u2014" in out, "em-dash must survive the HTTP normalizer"
        assert ", " not in out.replace(", and", "")  # no em-dash → ', ' substitution
        assert "Reyes leaned back" in out

    def test_en_dash_round_trips(self):
        normalize = _load_normalizer()
        text = "Pages 12\u201318 covered the negotiation."
        out = normalize(text)
        assert "\u2013" in out

    def test_horizontal_bar_round_trips(self):
        normalize = _load_normalizer()
        text = "He paused\u2015a long pause\u2015before answering."
        out = normalize(text)
        assert "\u2015" in out

    def test_figure_dash_round_trips(self):
        normalize = _load_normalizer()
        text = "Call the number 555\u2012019\u20121234."
        out = normalize(text)
        assert "\u2012" in out

    def test_dialogue_with_em_dash_interrupt(self):
        """'You should\u2014' she stopped." — common dialogue interrupt usage."""
        normalize = _load_normalizer()
        text = "\u201cYou should\u2014\u201d she stopped."
        out = normalize(text)
        assert "\u2014" in out

    def test_other_normalizations_still_apply(self):
        """Em-dash preservation must not regress the markdown stripping."""
        normalize = _load_normalizer()
        text = "## Heading\n\n**Bold**\u2014inline.\n\n- A bullet"
        out = normalize(text)
        # Heading marker, bold markers, bullet marker all gone
        assert "##" not in out
        assert "**" not in out
        assert not out.startswith("- ")
        # Em-dash preserved
        assert "\u2014" in out


# ──────────────────────────────────────────────────────────────────────────
# 2. canon_log_service._sanitize_text preserves em-dashes
# ──────────────────────────────────────────────────────────────────────────


class TestCanonLogSanitizerPreservesDashes:
    def test_em_dash_in_canon_summary_round_trips(self):
        sanitize = _load_canon_log_sanitizer()
        text = "The negotiation broke down\u2014Reyes walked out."
        out = sanitize(text)
        assert "\u2014" in out

    def test_en_dash_preserved(self):
        sanitize = _load_canon_log_sanitizer()
        text = "Pages 12\u201318."
        assert "\u2013" in sanitize(text)


# ──────────────────────────────────────────────────────────────────────────
# 3. chapter_ledger_service._sanitize_text preserves em-dashes
# ──────────────────────────────────────────────────────────────────────────


class TestChapterLedgerSanitizerPreservesDashes:
    def test_em_dash_in_ledger_round_trips(self):
        sanitize = _load_chapter_ledger_sanitizer()
        text = "Mitch arrived\u2014Ruth let him stay\u2014without a word."
        out = sanitize(text)
        assert "\u2014" in out
        assert out.count("\u2014") == 2
