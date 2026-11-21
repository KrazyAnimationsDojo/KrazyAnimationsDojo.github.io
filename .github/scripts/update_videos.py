"""Fetch the channel's YouTube feed and write videos.json for the website.

Runs on GitHub Actions (see .github/workflows/update-videos.yml).
Uses only the Python standard library and YouTube's public RSS feed: no API key.
"""
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

CHANNEL_ID = "UC7rae0Ql4UFfZxnmQ95juEg"  # KrazyAnimationsDojo
FEED = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
OUT = Path(__file__).resolve().parents[2] / "videos.json"

NS = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def clean_title(title: str) -> str:
    """Drop #hashtags and tidy spaces."""
    title = re.sub(r"\s*#\S+", "", title)
    return re.sub(r"\s{2,}", " ", title).strip()


def main() -> None:
    req = urllib.request.Request(FEED, headers={"User-Agent": "Mozilla/5.0 (site-updater)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        root = ET.fromstring(resp.read())

    videos = []
    for entry in root.findall("a:entry", NS):
        vid = entry.findtext("yt:videoId", namespaces=NS)
        link = entry.find("a:link", NS)
        href = link.get("href", "") if link is not None else ""
        stats = entry.find("media:group/media:community/media:statistics", NS)
        videos.append({
            "id": vid,
            "title": clean_title(entry.findtext("a:title", "", NS)),
            "published": entry.findtext("a:published", "", NS),
            "views": int(stats.get("views", 0)) if stats is not None else None,
            "short": "/shorts/" in href,
        })

    data = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "videos": videos,
    }

    # Only rewrite the file when the video list actually changed,
    # so the workflow doesn't make a commit every run just for a timestamp.
    if OUT.exists():
        old = json.loads(OUT.read_text(encoding="utf-8"))
        if old.get("videos") == videos:
            print("No changes.")
            return

    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(videos)} videos to {OUT.name}")


if __name__ == "__main__":
    main()
