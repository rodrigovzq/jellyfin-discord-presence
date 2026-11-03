# Running Discord headless on a Linux server

Rich Presence only works through a Discord client logged into **your** account on the
**same machine** as the script, because it writes to a local IPC socket
(`$XDG_RUNTIME_DIR/discord-ipc-0`). There is no API to set a human user's activity from
a remote server, and using a user token against the gateway is a self-bot (bannable).

So if the machine showing the presence is a headless box (NAS, LXC, VPS), it needs a
Discord desktop client running on a virtual display. This was tested on Debian 12,
x86_64, no GPU, systemd as PID 1.

> Cost: ~500 MB RAM (Discord + Xvfb). Don't try it with less than ~1.5 GB free.
> The account session is stored on that machine. Accept that before starting.

## 1. Dependencies

```bash
apt-get update -qq
apt-get install -y xvfb x11vnc ffmpeg xdotool libgbm1 libnss3 libasound2 libxss1 libxtst6 \
  libatspi2.0-0 libayatana-appindicator3-1 libdrm2 libxcomposite1 libxdamage1 libxrandr2 \
  libcups2 libpango-1.0-0 libcairo2 libnspr4 libgtk-3-0 libnotify4
```

## 2. Install the Discord core

The `.deb`/`.tar.gz` from discord.com is a ~2 MB stub that downloads the real client.
Without a TTY it opens a zenity dialog and hangs forever at "Installing 0%". Call the
bootstrap directly:

```bash
mkdir -p ~/.config/discord /run/user/$(id -u) && chmod 700 /run/user/$(id -u)
/usr/share/discord/updater_bootstrap --no-zenity ~/.config/discord stable https://updates.discord.com/
```

It ends with `Install Complete` and leaves the client in
`~/.config/discord/app-<version>/Discord`. That path changes on every update, so never
hardcode it in a unit — resolve it at start:

```bash
ls -d ~/.config/discord/app-*/Discord | sort -V | tail -1
```

## 3. Run it

```bash
export DISPLAY=:99 XDG_RUNTIME_DIR=/run/user/$(id -u)
Xvfb :99 -screen 0 1280x800x24 -nolisten tcp &
"$(ls -d ~/.config/discord/app-*/Discord | sort -V | tail -1)" \
  --no-sandbox --disable-dev-shm-usage --disable-gpu &
```

Healthy signs: several `app-*/Discord` processes, a window
(`xwininfo -root -tree | grep -i discord`), and the socket
`$XDG_RUNTIME_DIR/discord-ipc-0`. Grab a screenshot without VNC:

```bash
ffmpeg -loglevel error -f x11grab -video_size 1280x800 -i :99 -frames:v 1 -y /tmp/screen.png
```

Two units work well, both `Restart=always`:

- `discord-xvfb.service` — `Xvfb :99 -screen 0 1280x800x24 -nolisten tcp`
- `discord-headless.service` — the `Discord` binary, with
  `Environment=DISPLAY=:99` and `Environment=XDG_RUNTIME_DIR=/run/user/<uid>`

## 4. Log in once (over VNC)

```bash
x11vnc -storepasswd /root/.vnc/passwd
x11vnc -display :99 -rfbauth /root/.vnc/passwd -forever -shared -rfbport 5900
```

- Bind VNC to a private interface (VPN/Tailscale/LAN), never `0.0.0.0`: the login screen
  exposes your account.
- Connect with any VNC client and use **"Log in with QR code"** from the Discord mobile
  app — no password typed into a remote screen.
- Stop the VNC service once you are in; it is not needed afterwards.

## Gotchas

- **Electron needs `HOME`.** Run the client with `HOME=<the user that owns
  ~/.config/discord>`. Without it, Electron starts on the login screen even though the
  token is on disk, and every RPC call fails with `User logged out`.
- **Killing/restarting Discord can log you out.** Check the screen before assuming the
  script is broken.
- **The `app-<version>` directory changes on upgrades** — resolve it dynamically.
- **Session loss is silent**: the script logs `DiscordError: Error Code: 1000 Message:
  User logged out`. Re-run steps 3-4.
