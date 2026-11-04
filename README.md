# jellyfin-discord-presence

Show what you are watching on [Jellyfin](https://jellyfin.org/) as a Discord Rich
Presence card: poster, title, live progress bar and pause state.

```
Watching Jellyfin
  The Bear
  S03E05 · Children
  ──────────────●──────────── 21:04 / 28:31
```

One Python file, no dependencies beyond `pypresence`.

## How it works (and why it runs where it runs)

Discord only accepts presence from a Discord client logged into **your** account on the
**same machine**, through a local socket (`$XDG_RUNTIME_DIR/discord-ipc-0`). A remote
server (TV, phone, NAS) cannot set a human's activity, and a user token against the
gateway is a self-bot (bannable). So the script sits next to a Discord client — your
desktop, or a headless client on a server — and reads Jellyfin's sessions over the API.

Because it reads the server's sessions, it doesn't matter where playback happens: the
Jellyfin web UI, an Android TV client, Infuse, the mobile app. If the session exists,
the card appears.

The poster is resolved from a public source (TVMaze for series, Wikipedia for movies)
because Discord loads Rich Presence images through its own proxy, which cannot reach a
private Jellyfin.

## Requirements

- Python 3.8+ and `pip install pypresence`
- A Discord client running and logged in on the same machine
- Jellyfin reachable over HTTP(S) and an API key

## Install

### 1. Create the Discord application

1. <https://discord.com/developers/applications> → **New Application** → name it
   `Jellyfin` (this text is what appears in the card: "Watching Jellyfin").
2. **General Information** → copy the **Application ID**.
3. **Rich Presence → Art Assets** → upload the logo with the key `jellyfin`
   (the key must match `DISCORD_ASSET`). Without an asset the card has no image.

### 2. Jellyfin API key

Dashboard → **API Keys** → **+** → any name. The key only needs to read sessions.

### 3. Install the script

```bash
sudo install -m 755 jellyfin-discord-presence.py /usr/local/bin/
pip install pypresence
```

### 4. Configure

```bash
sudo install -m 600 .env.example /etc/jellyfin-presence.env
sudo nano /etc/jellyfin-presence.env
```

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `JF_URL` | yes | — | Jellyfin base URL, e.g. `http://127.0.0.1:8096` |
| `JF_KEY` | yes | — | API key from step 2 |
| `JF_USER` | no | *(any)* | Only show this Jellyfin username's playback |
| `DISCORD_CLIENT_ID` | yes | — | Application ID from step 1 |
| `DISCORD_ASSET` | no | `jellyfin` | Fallback image when no poster is found |
| `POLL` | no | `15` | Seconds between polls |
| `ART_CACHE` | no | `~/.cache/jellyfin-presence-artwork.json` | Where resolved poster URLs are cached |

### 5. Test before installing the service

```bash
set -a; . /etc/jellyfin-presence.env; set +a
XDG_RUNTIME_DIR=/run/user/$(id -u) jellyfin-discord-presence.py --once
```

`--once` prints the payload it would send (or `nothing playing`) without touching
Discord. If that works but nothing shows up on your profile, the problem is the Discord
connection, not Jellyfin.

Start a video and run it without `--once` — the card should appear within one poll.

### 6. Run it as a service

```bash
sudo install -m 644 jellyfin-discord-presence.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now jellyfin-discord-presence
journalctl -u jellyfin-discord-presence -f
```

Edit the unit first if needed: `ExecStart` path, `EnvironmentFile`, `User`, and
`XDG_RUNTIME_DIR` (must be the runtime dir of the user running Discord — `/run/user/1000`
for the first user, `/run/user/0` for root).

No desktop session on that machine? See [docs/headless-discord.md](docs/headless-discord.md)
for running the Discord client on a virtual display (~500 MB RAM).

## Troubleshooting

| Symptom | Cause |
|---|---|
| `ConnectionRefusedError` | Discord isn't running, or `XDG_RUNTIME_DIR` points to another user's runtime dir |
| `User logged out` (error 1000) | Discord lost the session — check the client's screen and log in again |
| `missing env JF_URL` | The service can't read the env file (`EnvironmentFile` path/permissions) |
| `AttributeError: 'int' object has no attribute 'value'` | An old edit passed `activity_type=3`; the enum is required (already handled here) |
| Card shows "Playing" instead of "Watching" | Same as above — the enum sets the label |
| Progress bar jumps or restarts | Jellyfin reports positions in 10-second granularity to clients |
| Card without poster | No match on TVMaze/Wikipedia for that title; the app logo is used instead |
| Service restart-loops with `status=203/EXEC` | The script isn't executable: `chmod 755` |
| Card hidden in your profile | While Spotify is playing, Discord shows only the Spotify card |

Useful checks:

```bash
journalctl -u jellyfin-discord-presence -n 20 --no-pager -o cat
ls -l /run/user/$(id -u)/discord-ipc-0     # no socket = Discord isn't up
curl -H 'Authorization: MediaBrowser Token="'"$JF_KEY"'"' "$JF_URL/Sessions"
```

## Limitations

- One card per Discord app; if you run this next to another presence, Discord shows the
  most recent one.
- The poster is not the file from your library: Discord's image proxy fetches the URL
  from **its** servers, so an image served by a private Jellyfin (LAN/Tailscale) never
  loads. Posters are resolved from public sources instead — TVMaze for series, Wikipedia
  for movies — and cached. Titles that don't match fall back to the app logo.
- No playback controls and no "Listening to Spotify"-style section: those are exclusive to
  Discord's official partner integrations.

## License

MIT
