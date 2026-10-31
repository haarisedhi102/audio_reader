"""Pull a Substack post into a markdown source file.

    python scripts/fetch_substack.py https://author.substack.com/p/slug
    python scripts/fetch_substack.py https://substack.com/home/post/p-221926555

Uses Substack's own JSON API, so links, headings, and non-Latin text are exact.
"""
import json
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (reader-pipeline)"}
SKIP = {"script", "style", "svg", "figure", "noscript", "iframe", "picture"}
BLOCK = {"p", "blockquote", "div", "section", "article", "ul", "ol", "li",
         "h1", "h2", "h3", "h4", "h5", "h6"}
CTA = {"share", "subscribe now", "subscribe", "leave a comment", "read more",
       "listen", "preview", "discuss"}


class MD(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.out.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag in ("p", "blockquote", "div", "section", "article", "hr"):
            self.out.append("\n\n")
        elif tag == "li":
            self.out.append("\n- ")
        elif tag == "br":
            self.out.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if not self.skip and tag in BLOCK:
            self.out.append("\n\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(re.sub(r"[ \t\r\n]+", " ", data))


def _api_url(url):
    u = urlparse(url)
    host, path = u.netloc.lower(), u.path
    if not host:
        raise SystemExit(f"not a URL: {url}")
    if "/home/post/" in path:
        pid = path.rstrip("/").rsplit("/", 1)[-1]
        pid = pid[2:] if pid.startswith("p-") else pid
        return f"https://substack.com/api/v1/posts/by-id/{pid}"
    if "/p/" in path:
        slug = path.split("/p/", 1)[1].split("/")[0]
        return f"https://{host}/api/v1/posts/{slug}"
    raise SystemExit(f"not a Substack post URL: {url}")


def _filename(title):
    return re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_") or "substack_post"


def _clean(text):
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    lines = []
    for line in text.split("\n"):
        if line.strip().lower() in CTA:
            continue
        lines.append(line.rstrip())
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def pull(url, out_dir=ROOT):
    api = _api_url(url)
    req = urllib.request.Request(api, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.load(r)
    except Exception as e:
        raise SystemExit(f"substack fetch failed for {api}: {e}")

    # /posts/by-id/<id> wraps the post; /posts/<slug> returns it directly
    post = payload.get("post", payload) if isinstance(payload, dict) else payload
    if not isinstance(post, dict):
        raise SystemExit(f"unexpected response for {api}")

    title = (post.get("title") or "").strip() or "Untitled"
    bylines = post.get("publishedBylines") or []
    author = (bylines[0].get("name") if bylines else "") or ""
    date = (post.get("post_date") or "")[:10]

    html = post.get("body_html") or ""
    if not html:
        html = post.get("truncated_body_text") or ""
        if html:
            print("warning: full body unavailable, using the preview text", file=sys.stderr)
    parser = MD()
    parser.feed(html)
    body = _clean("".join(parser.out))
    if not body:
        raise SystemExit(f"no body text returned for {title!r} (paywalled?)")

    out = Path(out_dir) / (_filename(title) + ".md")
    header = f"# {title}\n\n"
    if author or date:
        header += "### " + ", ".join(x for x in (author, date) if x) + "\n\n"
    out.write_text(header + body + "\n", encoding="utf-8")

    return {"path": out, "title": title, "author": author, "date": date,
            "words": len(body.split())}


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    meta = pull(sys.argv[1])
    print(f"{meta['path']}")
    print(f"{meta['title']} — {meta['author']} ({meta['date']}) · {meta['words']} words")


if __name__ == "__main__":
    main()
