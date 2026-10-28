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
    "OPENAI_API_KEY": ("openai", "https://api.openai.com/v1/chat/completions", "gpt-4.1-mini"),
    "OPENROUTER_API_KEY": ("openai", "https://openrouter.ai/api/v1/chat/completions", "openai/gpt-4.1-mini"),
    "DEEPSEEK_API_KEY": ("openai", "https://api.deepseek.com/chat/completions", "deepseek-chat"),
    "GROQ_API_KEY": ("openai", "https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile"),
    "ANTHROPIC_API_KEY": ("anthropic", "https://api.anthropic.com/v1/messages", "claude-sonnet-4-5"),
    "GEMINI_API_KEY": ("gemini", "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", "gemini-2.5-flash"),
    "GOOGLE_API_KEY": ("gemini", "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", "gemini-2.5-flash"),
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
        os.environ.setdefault(k, v)

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
    (kind, url, default_model), key = provider()
    if kind is None:
        raise RuntimeError("no LLM key found in .env")
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

REPAIR_SYSTEM = """You repair OCR and PDF-extraction artefacts in a text.

Rules:
- Do NOT rewrite, summarise, modernise or reorder. Preserve the author's wording,
  punctuation, spelling variants and paragraph breaks.
- Fix only mechanical damage: words split by stray spaces ("urkish" -> "Turkish",
  "men il ta" -> "menzil taşı"), missing letters, hyphenation joined wrongly,
  duplicated or missing spaces, stray glyphs, mangled proper nouns.
- Keep non-English terms (Turkish, Arabic transliterations) exactly as they are,
  including diacritics; do not translate them.
- If a passage is already clean, return it unchanged.
- Never invent sentences that are not in the input.
- Never guess proper nouns you cannot see. If a name is too damaged to recover
  with confidence, leave it exactly as it is rather than inventing a plausible one.
- Do not "improve" style, spelling variants or punctuation the author chose.

Return JSON: {"text": "<repaired text>", "changes": [{"before": "...", "after": "...", "why": "..."}]}"""

def repair_block(block: str) -> tuple[str, list]:
    out = _json(chat(REPAIR_SYSTEM, block))
    return out.get("text", block), out.get("changes", [])

def repair(md: str, max_block: int = 3500, verbose: bool = True) -> tuple[str, list]:
    """Repair paragraph by paragraph; reject any block that changed too much."""
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

    out_blocks, all_changes = [], []
    for i, b in enumerate(blocks):
        try:
            new, changes = repair_block(b)
        except Exception as e:
            if verbose:
                print(f"      llm skip block {i}: {type(e).__name__}: {e}")
            out_blocks.append(b)
            continue
        safe, accepted = safe_apply(b, new)
        out_blocks.append(safe)
        all_changes.extend(accepted)
        if accepted and verbose:
            for ch in accepted[:3]:
                print(f"        fix: {ch.get('before','')[:40]!r} -> {ch.get('after','')[:40]!r}")
    return "\n\n".join(out_blocks), all_changes

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

LEX_SYSTEM = """You prepare foreign terms for an English text-to-speech engine.

Given a list of terms (Turkish, Ottoman, Arabic transliterations, names), return
an English respelling for each that an English phonemizer will pronounce
approximately correctly. Rules:
- Use plain ASCII letters only, no hyphens or diacritics.
- Respell for sound, e.g. "Okmeydanı" -> "Okmaydunu", "Şeyh" -> "Shaykh".
- Turkish vowels: ı -> u/i, ö -> u, ü -> oo, ş -> sh, ç -> ch, ğ -> silent.
- Keep it one token (no spaces) so the phonemizer treats it as one word.
- If the term is already English-friendly, return it unchanged.

Return JSON: {"terms": [{"term": "...", "say": "..."}]}"""

def respell_terms(terms: list[str]) -> dict:
    if not available() or not terms:
        return {}
    try:
        out = _json(chat(LEX_SYSTEM, json.dumps({"terms": terms}, ensure_ascii=False)))
    except Exception:
        return {}
    result = {}
    for item in out.get("terms", []):
        t, s = item.get("term", ""), item.get("say", "")
        if not t or not s:
            continue
        if re.fullmatch(r"[A-Za-z' ]{2,40}", s) and t not in result:
            result[t] = s
    return result

SPEAK_SYSTEM = """You prepare a written article for being read aloud by a text-to-speech voice.

You do NOT rewrite. You return a list of literal find-and-replace pairs. Every
"from" must appear verbatim in the input. Nothing else about the text may change.

Allowed rules (use the exact label):
- expand_abbrev   "Dr." -> "Doctor", "e.g." -> "for example", "etc." -> "etcetera",
                  "cf." -> "compare", "c." -> "circa", "d." -> "died", "b." -> "born",
                  "fig." -> "figure", "p." -> "page", "pp." -> "pages", "no." -> "number"
- speak_symbol    "&" -> "and", "%" -> "percent", "§" -> "section", "→" -> "to",
                  "≈" -> "about", "×" -> "by", "=" -> "equals", "1/2" -> "one half"
- drop_artifact   page numbers, running heads, footnote markers, "[illegible]",
                  "OCR", bracketed printer marks — set "to" to ""
- join_hyphen     a word broken across a line break: "arch-\nery" -> "archery"
- normalize_quote curly quotes/dashes -> straight equivalents (same characters otherwise)
- respell_term    a foreign term the voice will mangle: "Okçular Tekkesi" -> "Okchular Tekkessey"

Forbidden: changing word choice, grammar, sentence order, paragraph breaks; removing
sentences; translating; summarising; "fixing" the author's spelling; adding words that
are not an expansion of a symbol or abbreviation.

Prefer fewer, safer edits. If a symbol is ambiguous, leave it alone.
Return JSON: {"replacements": [{"from": "...", "to": "...", "rule": "..."}]}"""

RULES = {"expand_abbrev", "speak_symbol", "drop_artifact", "join_hyphen",
         "normalize_quote", "respell_term"}

# abbreviations that are only unambiguous in front of a number ("p. 12", not "1,200 p.")
NUMERIC_FOLLOW = {"p.", "pp.", "no.", "fig.", "figs."}

def _apply_swap(text: str, src: str, dst: str) -> str:
    if src.lower().rstrip(".") + "." in NUMERIC_FOLLOW:
        pat = re.compile(r"(?<![\d,])" + re.escape(src) + r"(?=\s*\d)")
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
        for r in out.get("replacements", []):
            src, dst, rule = r.get("from", ""), r.get("to", ""), r.get("rule", "")
            if rule not in RULES or not src or src == dst:
                continue
            if src not in new or len(src) > 300:
                continue
            if rule in ("expand_abbrev", "speak_symbol") and len(src) > 24:
                continue
            if rule == "drop_artifact" and len(src) > 120:
                continue
            new = _apply_swap(new, src, dst)
            applied.append({"rule": rule, "from": src, "to": dst})
        out_blocks.append(new)
        if verbose and applied:
            for a in applied[-3:]:
                print(f"        {a['rule']:<14} {a['from'][:30]!r} -> {a['to'][:30]!r}")
    return "\n\n".join(out_blocks), applied

def _lev(a: str, b: str) -> int:
    if a == b:
        return 0
    if abs(len(a) - len(b)) > 3:
        return 99
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]

def safe_apply(original: str, repaired: str) -> tuple[str, list]:
    """Apply only character-level repairs from the model's rewrite.

    Word swaps, insertions and deletions are rejected: a language model asked to
    clean OCR will happily 'improve' prose, and this pipeline must not do that.
    """
    import difflib
    a = original.split()
    b = repaired.split()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    out, accepted = [], []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.extend(a[i1:i2])
            continue
        if tag == "replace" and (i2 - i1) == (j2 - j1):
            for x, y in zip(a[i1:i2], b[j1:j2]):
                d = _lev(x, y)
                ok = d <= 2 and not (x.isalpha() and y.isalpha() and x[0].lower() != y[0].lower())
                if not ok and re.fullmatch(r"[\w’'\-]+", x) and re.fullmatch(r"[\w’'\-]+", y):
                    # allow restoring diacritics / case on the same base word
                    base_x = re.sub(r"[^\w]", "", x).lower()
                    base_y = re.sub(r"[^\w]", "", y).lower()
                    ok = base_x == base_y
                if ok:
                    out.append(y)
                    accepted.append({"before": x, "after": y})
                else:
                    out.append(x)
            continue
        if tag == "replace" and (i2 - i1) > (j2 - j1):
            # joined split word: "men il ta" -> "menzil"
            joined = "".join(a[i1:i2])
            if len(b[j1:j2]) == 1 and _lev(joined, b[j1]) <= 3:
                out.append(b[j1]); accepted.append({"before": " ".join(a[i1:i2]), "after": b[j1]})
            else:
                out.extend(a[i1:i2])
            continue
        # insertions/deletions of whole words: keep the original
        out.extend(a[i1:i2])
    return " ".join(out), accepted
