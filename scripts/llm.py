"""
Minimal LLM client for the reader pipeline.

Reads .env from the project root. Speaks OpenAI-compatible, Anthropic and
Gemini APIs over httpx, so no SDKs are needed. Used for the two jobs where a
model genuinely beats heuristics:

  repair(md)   — fix OCR/extraction artefacts without rewriting the prose
  metadata(md) — title, author, and which sections are apparatus not content
"""
import json, os, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT = 120

PROVIDERS = {
    "CMD_API_KEY": ("openai", None, "gpt-5.6-sol"),  # base URL comes from FOOD_BASE_URL
}

def load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ[k] = v

def provider():
    load_env()
    for key, cfg in PROVIDERS.items():
        if os.environ.get(key):
            kind, url, model = cfg
            if url is None:
                base = os.environ.get("FOOD_BASE_URL", "https://api.commandcode.ai/provider/v1").rstrip("/")
                url = f"{base}/chat/completions"
            return (kind, url, model), os.environ[key]
    return None, None

def available() -> bool:
    p, _ = provider()
    return p is not None

def chat(system: str, user: str, json_mode: bool = True) -> str:
    import httpx
    p, key = provider()
    if p is None:
        raise RuntimeError("no LLM key found in .env")
    kind, url, default_model = p
    model = os.environ.get("LLM_MODEL", default_model)

    if kind == "openai":
        body = {"model": model, "temperature": 0,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        r = httpx.post(url, json=body, timeout=TIMEOUT,
                       headers={"Authorization": f"Bearer {key}"})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    if kind == "anthropic":
        r = httpx.post(url, timeout=TIMEOUT,
                       headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                       json={"model": model, "max_tokens": 4096, "temperature": 0,
                             "system": system,
                             "messages": [{"role": "user", "content": user}]})
        r.raise_for_status()
        return r.json()["content"][0]["text"]

    if kind == "gemini":
        r = httpx.post(url.format(model=model), timeout=TIMEOUT,
                       params={"key": key},
                       json={"systemInstruction": {"parts": [{"text": system}]},
                             "contents": [{"role": "user", "parts": [{"text": user}]}],
                             "generationConfig": {"temperature": 0}})
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]

    raise RuntimeError(f"unsupported provider {kind}")

def _json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"no JSON in response: {text[:200]}")
    return json.loads(m.group(0))

META_SYSTEM = """Extract bibliographic metadata from the start of a document.
Return JSON: {"title": str, "author": str, "apparatus_sections": [str]}
apparatus_sections = headings whose content should NOT be narrated (references,
bibliography, appendices of forms, acknowledgements, table of contents, figure
lists). Use [] if none. Keep the title exactly as printed."""

def metadata(md: str) -> dict:
    if not available():
        return {}
    try:
        return _json(chat(META_SYSTEM, md[:3000]))
    except Exception:
        return {}

SPEAK_SYSTEM = """You prepare a written article for being read aloud by a text-to-speech voice.

You do NOT rewrite. You return a list of literal find-and-replace pairs. Every
"from" must appear verbatim in the input. Nothing else about the text may change.

Allowed rules (use the exact label):
- drop_artifact   page numbers, running heads, footnote markers, "[illegible]",
                  "OCR", bracketed printer marks — set "to" to ""
- join_hyphen     a word broken across a line break: "arch-\nery" -> "archery"


Forbidden: changing word choice, grammar, sentence order, paragraph breaks; removing
sentences; translating; summarising; "fixing" the author's spelling; adding words that
are not an expansion of a symbol or abbreviation.

Prefer fewer, safer edits. If a symbol is ambiguous, leave it alone.
Return JSON: {"replacements": [{"from": "...", "to": "...", "rule": "..."}]}"""

RULES = {  "drop_artifact", "join_hyphen",}

# abbreviations that are only unambiguous in front of a number ("p. 12", not "1,200 p.")
NUMERIC_FOLLOW = {"p.", "pp.", "no.", "fig.", "figs."}

def _apply_swap(text: str, src: str, dst: str) -> str:
    if src.lower().rstrip(".") + "." in NUMERIC_FOLLOW:
        pat = re.compile(r"(?<![\w,])" + re.escape(src) + r"(?=\s*\d)")
        return pat.sub(dst, text)
    return text.replace(src, dst)

def speakable(md: str, max_block: int = 6000, verbose: bool = True) -> tuple[str, list]:
    """Make text listenable without letting a model touch the prose.

    The model may only propose literal string swaps; each is applied only if the
    source string exists verbatim and the edit is inside the allowed rule set.
    """
    if not available():
        return md, []
    paras = md.split("\n\n")
    blocks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 > max_block and cur:
            blocks.append(cur); cur = p
        else:
            cur = (cur + "\n\n" + p).strip() if cur else p
    if cur:
        blocks.append(cur)

    out_blocks, applied = [], []
    for i, b in enumerate(blocks):
        try:
            out = _json(chat(SPEAK_SYSTEM, b))
        except Exception as e:
            if verbose:
                print(f"      speak skip block {i}: {type(e).__name__}")
            out_blocks.append(b)
            continue
        new = b
        block_applied = []
        for r in out.get("replacements") or []:
            if not isinstance(r, dict):
                continue
            src, dst, rule = r.get("from", ""), r.get("to", ""), r.get("rule", "")
            if rule not in RULES or not src or src == dst or len(src) > 300:
                continue
            if src not in new:
                continue
            if rule == "drop_artifact" and (dst.strip() or len(src) <= 3 or new.count(src) != 1):
                continue
            if rule == "join_hyphen" and re.sub(r"-\s*", "", src) != dst:
                continue
            prev = new
            new = _apply_swap(new, src, dst)
            if new != prev:
                block_applied.append({"rule": rule, "from": src, "to": dst})
        out_blocks.append(new)
        applied.extend(block_applied)
        if verbose and block_applied:
            for a in block_applied[-3:]:
                print(f"        {a['rule']:<14} {a['from'][:30]!r} -> {a['to'][:30]!r}")
    return "\n\n".join(out_blocks), applied
