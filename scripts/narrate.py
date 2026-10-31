"""Written text -> spoken text. Deterministic; no dictionaries, no accent stripping."""
import os
import re

DROPPED = []

# Both engines (Fish, Eleven) read Arabic and accented Latin natively.
KEEP_ARABIC = True





SCRUB_RULES = [
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), ""),          # images
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),      # links -> label
    (re.compile(r"https?://\S+"), ""),                  # bare urls
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), ""),   # emails
    (re.compile(r"\[\d+\]"), ""),                       # footnote markers
    (re.compile(r"[*_`#]+"), ""),                       # markdown emphasis
    (re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]"), ""),
]



def scrub(t):
    """Remove things a TTS engine should never try to pronounce."""
    for rx, rep in SCRUB_RULES:
        t = rx.sub(rep, t)

    return re.sub(r"\s{2,}", " ", t)


ARABIC_RANGES = ((0x0600, 0x06FF), (0x0750, 0x077F),
                 (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))
LATIN_EXT = ((0x00C0, 0x024F), (0x1E00, 0x1EFF), (0x0300, 0x036F))


def _is_arabic(ch):
    return any(lo <= ord(ch) <= hi for lo, hi in ARABIC_RANGES)


def _is_latin_ext(ch):
    """Accented Latin (Jāvīdnāma) and combining marks, which TTS reads natively."""
    return any(lo <= ord(ch) <= hi for lo, hi in LATIN_EXT)


KEEP_PUNCT = set("“”‘’–—…")
NON_ASCII_RUN = re.compile(r"[^\x00-\x7f]+")


def _filter_run(m):
    keep, drop = [], []
    for ch in m.group(0):
        if (ch in KEEP_PUNCT or _is_latin_ext(ch)
                or (KEEP_ARABIC and _is_arabic(ch))):
            keep.append(ch)
        else:
            drop.append(ch)
    if "".join(drop).strip():
        DROPPED.append("".join(drop).strip())
    return "".join(keep)


def prepare(t):
    t = scrub(t)
    t = NON_ASCII_RUN.sub(_filter_run, t)
    return re.sub(r"\s{2,}", " ", t)


def report_dropped(stream=None):
    """Warn about script the voice cannot speak instead of leaving a silent gap."""
    import sys
    if not DROPPED:
        return
    stream = stream or sys.stderr
    sample = ", ".join(repr(s) for s in DROPPED[:5])
    more = f" (+{len(DROPPED) - 5} more)" if len(DROPPED) > 5 else ""
    print(f"WARNING: dropped {len(DROPPED)} unsupported span(s): {sample}{more}",
          file=stream)
