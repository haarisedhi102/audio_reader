#!/usr/bin/env python3
"""Stage the library for static hosting, then sync it to S3-compatible storage.

    ./reader publish --stage-only     # transcode into .publish/, no network
    ./reader publish --dry-run        # show what rclone would send
    ./reader publish                  # transcode + upload

Sources in library/ and audio/ are never modified: the staging tree is a copy at
64 kbps with the MP4 index moved to the front, so a seek does not stall and the
files are a third of the size.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "library"
STAGE = ROOT / ".publish"


def load_env() -> None:
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()  # before the constants below, and before rclone is spawned

BITRATE = os.environ.get("PUBLISH_BITRATE", "64k")
REMOTE = os.environ.get("PUBLISH_REMOTE", "r2")
BUCKET = os.environ.get("PUBLISH_BUCKET", "")
PREFIX = os.environ.get("PUBLISH_PREFIX", "library")


def encoder() -> str:
    return "aac_at" if sys.platform == "darwin" else "aac"


def encode(src: Path, dst: Path) -> bool:
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
             "-c:a", encoder(), "-b:a", BITRATE, "-ac", "1", "-ar", "44100",
             "-movflags", "+faststart", str(tmp)],
            check=True,
        )
        tmp.replace(dst)
    finally:
        tmp.unlink(missing_ok=True)
    return True


def stage(force: bool) -> None:
    if force and STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(exist_ok=True)

    index = LIB / "index.json"
    if not index.exists():
        sys.exit("library/index.json missing — run: ./reader add <file>")

    shutil.copy2(index, STAGE / "index.json")

    books = [b for b in LIB.iterdir() if b.is_dir()]
    total_in = total_out = 0
    encoded = 0
    for book in sorted(books):
        out = STAGE / book.name
        out.mkdir(parents=True, exist_ok=True)
        for f in sorted(book.iterdir()):
            if f.name.endswith(".json"):
                shutil.copy2(f, out / f.name)
            elif f.suffix == ".m4a":
                src = f.resolve()
                if not src.exists():
                    sys.exit(f"broken audio link: {f}")
                total_in += src.stat().st_size
                if encode(src, out / f.name):
                    encoded += 1
                total_out += (out / f.name).stat().st_size
                print(f"  {book.name}/{f.name}  "
                      f"{src.stat().st_size/1e6:6.1f} MB → "
                      f"{(out / f.name).stat().st_size/1e6:5.1f} MB")

    if total_in:
        print(f"\nstaged {len(books)} book(s): "
              f"{total_in/1e6:.0f} MB → {total_out/1e6:.0f} MB "
              f"({total_out/total_in:.0%}), {encoded} file(s) encoded")
    print(f"staging tree: {STAGE.relative_to(ROOT)}/")


def sync(dry: bool, reupload: bool = False) -> None:
    if not BUCKET:
        sys.exit("PUBLISH_BUCKET is not set — see docs/hosting.md")
    if not shutil.which("rclone"):
        sys.exit("rclone not found — brew install rclone, then see docs/hosting.md")

    dest = f"{REMOTE}:{BUCKET}/{PREFIX}"
    common = ["rclone", "sync", str(STAGE) + "/", dest]
    if dry:
        common.append("--dry-run")
    if reupload:
        # headers are only written on upload; unchanged objects are skipped otherwise
        common.append("--ignore-times")

    print(f"\n→ {dest}")
    # R2 infers .m4a as audio/mp4a-latm, which WKWebView is inconsistent about
    subprocess.run(common + [
        "--include", "*.m4a",
        "--header-upload", "Content-Type: audio/mp4",
        "--header-upload", "Cache-Control: public, max-age=86400",
    ], check=True)
    subprocess.run(common + [
        "--include", "*.json", "--exclude", "index.json",
        "--header-upload", "Content-Type: application/json",
        "--header-upload", "Cache-Control: public, max-age=86400",
    ], check=True)
    subprocess.run(common + [
        "--include", "index.json",
        "--header-upload", "Content-Type: application/json",
        "--header-upload", "Cache-Control: no-cache",
    ], check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="transcode, then show what would upload")
    ap.add_argument("--stage-only", action="store_true", help="transcode only, no upload")
    ap.add_argument("--force", action="store_true", help="re-encode even if the staged file is newer")
    ap.add_argument("--reupload", action="store_true",
                    help="upload every object again, to rewrite headers")
    args = ap.parse_args()

    stage(args.force)
    if args.stage_only:
        return
    sync(args.dry_run, args.reupload)


if __name__ == "__main__":
    main()
