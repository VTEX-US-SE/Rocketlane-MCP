#!/usr/bin/env python3
"""
Presentation-artifact renderer for the SE Co-pilot.

Assembles a SELF-CONTAINED HTML artifact from a digest dict:
  static shell (templates/presentation_v1.html)  — zero numbers
  + data-island (the digest JSON, verbatim)       — the only place numbers live
  + inline JS renderer (in the template)           — renders DOM from the JSON

Number fidelity is guaranteed by a checksum: build_artifact() computes an FNV-1a
hash over the exact embedded JSON string; the template's JS recomputes it over the
data-island's textContent and refuses to render (red banner) on mismatch. The model's
only job is to paste the returned `html` verbatim into an artifact — it can corrupt
the blob only DETECTABLY, never silently. No external requests (strict-CSP safe).
"""
from __future__ import annotations

import json
from pathlib import Path

TEMPLATE_VERSION = "v2"
_TEMPLATE = Path(__file__).resolve().parent / "templates" / "presentation_v2.html"

# VTEX brand mark — OFFICIAL logo (from the demo artifact, corrected viewBox 255 120 220 85):
# pink "V" glyph + white "TEX" wordmark. Paths carry classes .glyph/.word that the template
# CSS colours (--pink / --paper). Inline SVG, self-contained.
VTEX_LOGO_SVG = (
    '<svg class="vtex-mark" viewBox="255 120 220 85" aria-label="VTEX">'
    '<path class="glyph" d="M342.54,124.13h-67a6.89,6.89,0,0,0-6.09,10.12l6.7,12.69H264a4.47,4.47,0,0,0-4,6.56l21.56,40.81a4.47,4.47,0,0,0,7.9,0l5.85-11,7.35,13.91a6.9,6.9,0,0,0,12.19,0L348.47,134A6.71,6.71,0,0,0,342.54,124.13Zm-30.1,27L298,178.4a3,3,0,0,1-4,1.24,2.89,2.89,0,0,1-1.23-1.24l-14.35-27.14a3,3,0,0,1,2.62-4.37h28.91a2.89,2.89,0,0,1,2.56,4.25Z"/>'
    '<path class="word" d="M413.83,153.46H406.5v25.12a.87.87,0,0,1-.86.87H400a.86.86,0,0,1-.86-.87V153.46h-7.38a.83.83,0,0,1-.86-.8v-4.47a.83.83,0,0,1,.84-.82h22.11a.88.88,0,0,1,.91.82v4.45A.88.88,0,0,1,413.83,153.46Z"/>'
    '<path class="word" d="M437.37,179.27a57.6,57.6,0,0,1-8.72.56c-5.57,0-10.48-1.43-10.48-9.28V156.21c0-7.85,5-9.23,10.53-9.23a55.51,55.51,0,0,1,8.67.56c.6.08.86.3.86.86v4a.86.86,0,0,1-.86.86h-9.1c-2,0-2.77.69-2.77,2.94v3.93H437a.85.85,0,0,1,.86.86v4.1a.87.87,0,0,1-.86.87H425.5v4.57c0,2.24.74,2.94,2.77,2.94h9.1a.86.86,0,0,1,.86.86v4C438.23,178.92,438,179.18,437.37,179.27Z"/>'
    '<path class="word" d="M469.93,179.44h-6.86a1.16,1.16,0,0,1-1.13-.65L456,169.35l-5.4,9.23c-.3.52-.6.87-1.07.87h-6.39a.57.57,0,0,1-.64-.56.68.68,0,0,1,.08-.31L451.93,163l-9.45-14.8a.79.79,0,0,1-.08-.26.62.62,0,0,1,.65-.56H450c.48,0,.82.43,1.08.82l5.52,8.72,5.34-8.72a1.41,1.41,0,0,1,1.08-.82h6.39a.61.61,0,0,1,.64.56.79.79,0,0,1-.08.26l-9.4,14.89,9.8,15.5a1,1,0,0,1,.13.44C470.49,179.27,470.27,179.44,469.93,179.44Z"/>'
    '<path class="word" d="M380.54,147.46a.67.67,0,0,0-.66.54l-6.26,23.18c-.09.48-.22.65-.6.65s-.52-.18-.61-.65L366.14,148a.67.67,0,0,0-.65-.54h-6.17a.67.67,0,0,0-.67.67.77.77,0,0,0,0,.15s7.65,26.59,7.74,26.85a6.5,6.5,0,0,0,6.65,4.69,6.69,6.69,0,0,0,6.65-4.68c.12-.36,7.61-26.86,7.61-26.86a.67.67,0,0,0-.51-.8l-.14,0Z"/>'
    '</svg>'
)


def _canonical(obj) -> str:
    """Deterministic JSON: sorted keys, compact, real UTF-8 (not ASCII \\uXXXX-escaped).

    ensure_ascii=False on purpose (fixed 2026-07-15): when an LLM has to paste this
    string verbatim into an artifact (Desktop model, or any manual re-transcription),
    it reliably "auto-corrects" \\u00fc back to the literal ü — a 6-char escape sequence
    is much easier to silently normalize than a single real character. That flipped the
    checksum on every real digest with an accented name (Müller, Bürklin, ...) even
    though the underlying data was byte-for-byte semantically identical — a false
    positive on the integrity check, not real corruption. Real unicode chars are what
    LLMs reproduce most faithfully, so keep them as-is.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _harden(s: str) -> str:
    """Make the JSON safe to embed inside <script>: escape only `<` (as \\u003c) so a
    literal "</script" sequence in the data can never close the tag early. That's the
    one byte sequence that's structurally unsafe here; `&` and `>` need no escaping
    inside script-tag text content (HTML doesn't parse entities there), and each extra
    escape is one more thing a transcribing LLM could silently "fix" back to the literal
    character, breaking the checksum without changing the data (see _canonical above)."""
    return s.replace("<", "\\u003c")


def _fnv1a_hex(s: str) -> str:
    """FNV-1a 32-bit over UTF-8 bytes -> 8-char hex. MUST match the template's JS impl
    (TextEncoder + Math.imul). `s` may now contain real UTF-8 multi-byte chars, encoded
    to bytes here the same way TextEncoder does in the browser."""
    h = 0x811C9DC5
    for b in s.encode("utf-8"):
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return format(h, "08x")


def build_artifact(view: str, digest: dict, prov: dict, generated_ts: str) -> str:
    """view: 'exec'|'region'|'se'. digest: analyze.*_digest output. prov: {source,as_of,universe}.
    generated_ts: ISO string (passed in — no wall-clock here, keeps it testable)."""
    if view not in ("exec", "region", "se"):
        raise ValueError(f"unknown view: {view}")
    payload = {
        "view": view,
        "template_version": TEMPLATE_VERSION,
        "generated_ts": generated_ts,
        "prov": prov,
        "digest": digest,
    }
    data_str = _harden(_canonical(payload))
    checksum = _fnv1a_hex(data_str)
    html = _TEMPLATE.read_text(encoding="utf-8")
    html = (html
            .replace("__DATA__", data_str)
            .replace("__CHECKSUM__", checksum)
            .replace("__TEMPLATE_VERSION__", TEMPLATE_VERSION)
            .replace("__VIEW__", view)
            .replace("__VTEX_LOGO__", VTEX_LOGO_SVG))
    return html
