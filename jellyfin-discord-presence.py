#!/usr/bin/env python3
"""Jellyfin -> Discord Rich Presence over the local IPC socket.

Discord only accepts presence from a client logged into your account on the same
machine, so this runs next to a Discord desktop client (headless is fine, see
docs/headless-discord.md). Jellyfin is only the data source.

Usage: ./jellyfin-discord-presence.py [--once]
       --once prints the payload it would send and exits (no Discord needed).
"""
import json
import os
import urllib.parse
import sys
import time
import urllib.request

from pypresence import ActivityType, Presence

JF = os.environ.get("JF_URL", "").rstrip("/")
KEY = os.environ.get("JF_KEY", "")
USER = os.environ.get("JF_USER", "").lower()  # empty = any user
CLIENT = os.environ.get("DISCORD_CLIENT_ID", "")
ASSET = os.environ.get("DISCORD_ASSET", "jellyfin")
POLL = int(os.environ.get("POLL", "15"))
ART_CACHE = os.environ.get(
    "ART_CACHE", os.path.expanduser("~/.cache/jellyfin-presence-artwork.json")
)
_art_mem = {}

for _name, _value in (("JF_URL", JF), ("JF_KEY", KEY), ("DISCORD_CLIENT_ID", CLIENT)):
    if not _value:
        sys.exit(f"missing env {_name} (see .env.example)")


def get_sessions():
    req = urllib.request.Request(
        f"{JF}/Sessions?ActiveWithinSeconds=300",
        headers={"Authorization": f'MediaBrowser Token="{KEY}"'},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def now_playing(data):
    """Session of our user with something playing. Prefers a non-paused one."""
    playing = paused = None
    for s in data:
        if not s.get("NowPlayingItem"):
            continue
        if USER and s.get("UserName", "").lower() != USER:
            continue
        if s.get("PlayState", {}).get("IsPaused"):
            paused = paused or s
        else:
            playing = playing or s
    return playing or paused


def _http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "jellyfin-discord-presence/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def _wikipedia_poster(name, year):
    for title in (f"{name} ({year} film)" if year else "", f"{name} (film)", name):
        if not title:
            continue
        try:
            d = _http_json(
                "https://en.wikipedia.org/api/rest_v1/page/summary/"
                + urllib.parse.quote(title.replace(" ", "_"))
            )
        except Exception:
            continue
        thumb = (d.get("thumbnail") or {}).get("source")
        if thumb and "film" in (d.get("description") or "").lower():
            return thumb.split("?")[0]
    return ""


def _tvmaze_poster(series):
    try:
        d = _http_json("https://api.tvmaze.com/singlesearch/shows?q=" + urllib.parse.quote(series))
        return ((d.get("image") or {}).get("original") or "").split("?")[0]
    except Exception:
        return ""


def artwork(item):
    """Public poster URL: TVMaze for series, Wikipedia for movies.

    Discord's image proxy fetches the image from its own servers, so a poster served by
    your Jellyfin (LAN/Tailscale address) never loads. Falls back to the app asset.
    """
    episode = item.get("Type") == "Episode"
    title = (item.get("SeriesName") if episode else item.get("Name")) or ""
    year = None if episode else item.get("ProductionYear")
    key = f"{'tv' if episode else 'movie'}|{title}|{year}".lower()
    if key in _art_mem:
        return _art_mem[key]
    try:
        with open(ART_CACHE) as f:
            cache = json.load(f)
    except Exception:
        cache = {}
    url = cache.get(key)
    if url is None:
        # ponytail: single search hit per title; unknown releases fall back to the logo
        url = _tvmaze_poster(title) if episode else _wikipedia_poster(title, year)
        if url:
            cache[key] = url
            try:
                os.makedirs(os.path.dirname(ART_CACHE), exist_ok=True)
                with open(ART_CACHE, "w") as f:
                    json.dump(cache, f)
            except Exception:
                pass
    _art_mem[key] = url
    return url or ASSET


def payload(session):
    item = session["NowPlayingItem"]
    ps = session.get("PlayState", {})
    pos = ps.get("PositionTicks", 0) / 1e7
    runtime = item.get("RunTimeTicks", 0) / 1e7

    if item.get("Type") == "Episode":
        details = item.get("SeriesName") or item.get("Name") or "Jellyfin"
        state = "S%02dE%02d · %s" % (
            item.get("ParentIndexNumber") or 0,
            item.get("IndexNumber") or 0,
            item.get("Name") or "",
        )
    else:
        details = item.get("Name") or "Jellyfin"
        year = item.get("ProductionYear")
        state = str(year) if year else "Movie"

    out = {
        "details": details[:128],
        "state": state[:128],
        "large_image": artwork(item),
        "large_text": details[:128],
        "activity_type": ActivityType.WATCHING,
    }
    if not ps.get("IsPaused"):
        start = int(time.time() - pos)
        out["start"] = start
        if runtime > pos:
            out["end"] = int(start + runtime)
    else:
        out["state"] = (out["state"] + " (paused)")[:128]
    return out


def main():
    once = "--once" in sys.argv
    rpc = None
    while True:
        try:
            session = now_playing(get_sessions())
            pl = payload(session) if session else None
            if once:
                print(json.dumps(pl, ensure_ascii=False, indent=2) if pl else "nothing playing")
                return
            if rpc is None:
                rpc = Presence(CLIENT)
                rpc.connect()
                print("connected to Discord", flush=True)
            if pl:
                rpc.update(**pl)
            else:
                rpc.clear()
        except Exception as e:  # Discord closed, network down, ... just retry
            print(f"{time.strftime('%H:%M:%S')} {type(e).__name__}: {e}", flush=True)
            try:
                rpc and rpc.close()
            except Exception:
                pass
            rpc = None
            if once:
                raise
            time.sleep(5)
            continue
        time.sleep(POLL)


if __name__ == "__main__":
    main()
