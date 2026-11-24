"""Keep videos.json up to date with every video on the channel.

Runs on GitHub Actions (see .github/workflows/update-videos.yml).
Uses only the Python standard library and YouTube's public pages: no API key.

YouTube's feed only lists the newest 15 uploads, so this script never
replaces the list. It adds new uploads, refreshes titles and view counts for
the ones in the feed, keeps older videos it already knows about, and drops a
video only once YouTube says it no longer exists (deleted or made private).
"""
import json
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

CHANNEL_ID = "UC7rae0Ql4UFfZxnmQ95juEg"  # KrazyAnimationsDojo
FEED = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
OUT = Path(__file__).resolve().parents[2] / "videos.json"
UA = {"User-Agent": "Mozilla/5.0 (site-updater)"}

NS = {
    "a": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def clean_title(title: str) -> str:
    """Drop #hashtags and tidy spaces."""
    title = re.sub(r"\s*#\S+", "", title)
    return re.sub(r"\s{2,}", " ", title).strip()


def fetch_feed() -> list:
    req = urllib.request.Request(FEED, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        root = ET.fromstring(resp.read())
    videos = []
    for entry in root.findall("a:entry", NS):
        link = entry.find("a:link", NS)
        href = link.get("href", "") if link is not None else ""
        stats = entry.find("media:group/media:community/media:statistics", NS)
        videos.append({
            "id": entry.findtext("yt:videoId", namespaces=NS),
            "title": clean_title(entry.findtext("a:title", "", NS)),
            "published": entry.findtext("a:published", "", NS),
            "views": int(stats.get("views", 0)) if stats is not None else None,
            "short": "/shorts/" in href,
        })
    return videos


def still_exists(video_id: str) -> bool:
    """Ask YouTube's oEmbed endpoint whether a video is still public.

    Returns True when unsure (network trouble), so a hiccup never wipes videos.
    """
    url = ("https://www.youtube.com/oembed?format=json&url="
           f"https://www.youtube.com/watch?v={video_id}")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20):
            return True
    except urllib.error.HTTPError as e:
        return e.code not in (400, 401, 403, 404)
    except Exception:
        return True


def main() -> None:
    old = {}
    if OUT.exists():
        old = json.loads(OUT.read_text(encoding="utf-8"))
    known = {v["id"]: v for v in old.get("videos", [])}

    feed = fetch_feed()
    feed_ids = {v["id"] for v in feed}

    merged = dict(known)
    for v in feed:
        merged[v["id"]] = {**known.get(v["id"], {}), **v}

    # Videos the feed no longer lists: keep them unless they're gone from YouTube.
    for vid in list(merged):
        if vid not in feed_ids and not still_exists(vid):
            print(f"Removing {vid}: no longer on YouTube")
            del merged[vid]

    videos = sorted(merged.values(), key=lambda v: v.get("published", ""), reverse=True)

    # Only rewrite the file when something actually changed,
    # so the workflow doesn't make a commit every run just for a timestamp.
    if old.get("videos") == videos:
        print("No changes.")
        return

    data = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "videos": videos,
    }
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(videos)} videos to {OUT.name}")


if __name__ == "__main__":
    main()
