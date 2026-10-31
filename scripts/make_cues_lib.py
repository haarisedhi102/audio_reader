"""Load the cue timeline written by generate_audio.main().

The stitcher records t0/t1 from the actual audio arrays it concatenates, so
there is no second timeline to keep in sync here.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIO = ROOT / "audio"


def build(tag: str) -> list:
    path = AUDIO / f"{tag}.cues.json"
    if not path.exists():
        raise FileNotFoundError(
            f"no cue manifest at {path} — run the synthesis step first")
    return json.loads(path.read_text(encoding="utf-8"))
