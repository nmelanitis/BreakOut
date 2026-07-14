# BreakOut

Before you opt-out, get a local copy of your likes.
Works with Spotify, more platforms to come.

BreakOut is a local web application for exporting Spotify libraries into portable JSON and
Excel-friendly CSV files. It runs only on `127.0.0.1` and opens a browser dashboard.

## Onboarding

The first time you open BreakOut, it asks for a Spotify Developer Client ID. This identifies
your personal BreakOut integration to Spotify; it is not a password or a Client Secret.

1. Open the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and sign in
   with the Spotify account you want to export.
2. Create an app. You can name it **BreakOut**.
3. In the app settings, add this Redirect URI exactly, then save:

   ```
   http://127.0.0.1:3000/auth/spotify/callback
   ```

4. Copy the app’s **Client ID** and paste it into the BreakOut setup screen.

Do not replace `127.0.0.1` with `localhost`. Your Spotify password is entered only on
Spotify’s website and is never shared with BreakOut. BreakOut stores the Client ID locally;
access tokens remain in memory only until BreakOut stops.

## Run

```sh
uv sync --all-groups
uv run breakout serve
```

Open `http://127.0.0.1:3000` if the browser does not open automatically.

## Desktop beta

BreakOut is designed to run locally: the desktop app starts a server bound only to
`127.0.0.1` and opens the dashboard in your browser. Prebuilt macOS, Windows, and Linux beta
downloads are produced by the GitHub Actions **Desktop Beta Build** workflow.

Each beta tester must create and use their **own Spotify developer app and Client ID**. Do not
share a Spotify Client ID or Client Secret with other users, and do not enter a Client Secret into
BreakOut. This avoids operating a shared Spotify beta app and keeps every user’s authorization
separate.

### macOS: allow BreakOut on first launch

The beta is downloaded from GitHub rather than the Mac App Store and is not yet notarized by
Apple. macOS may block it the first time you open it.

1. Extract `BreakOut-macOS.zip`, then try to open `BreakOut.app` once. If macOS refuses to open
   it, dismiss the warning.
2. Open **Apple menu → System Settings → Privacy & Security** and scroll to **Security**.
3. Click **Open Anyway** beside the BreakOut warning, then confirm **Open** and enter your Mac
   password if requested.

macOS remembers this choice for BreakOut, so subsequent launches work normally. Only approve the
app when you downloaded it from the official BreakOut GitHub release. Apple documents the same
process in its [macOS security guidance](https://support.apple.com/102445).

### Build a local executable from source
To build a local desktop executable from source:

```sh
uv sync --group desktop
uv run pyinstaller --noconfirm --clean breakout.spec
```

The desktop application is written to `dist/BreakOut.app` on macOS, `dist/BreakOut.exe` on
Windows, or `dist/BreakOut` on Linux. Run it directly; it launches the browser dashboard
automatically—no `serve` argument is needed.

Use **Quit BreakOut** in the dashboard when finished. Closing the browser alone leaves the local
application running, so you can return to it at `http://127.0.0.1:3000`.

## Spotify setup

Create a Spotify developer application, register this redirect URI exactly, then paste its
Client ID into the first-run BreakOut screen:

```
http://127.0.0.1:3000/auth/spotify/callback
```

BreakOut uses Spotify's browser authorization flow. Your Spotify password is entered only at
Spotify and is never seen or stored by BreakOut. BreakOut stores the non-secret Client ID locally;
access tokens live only in memory until the process exits.

## Output

Each export downloads a ZIP containing a normalized `archive.json`, its JSON Schema, one CSV
per collection, a manifest, and a short README. The portable archive is intentionally designed
for future destination-service import adapters; BreakOut does not yet import into another service.

## License

Copyright © 2026 BreakOut contributors. BreakOut is licensed under the
[Creative Commons Attribution-NonCommercial 4.0 International license](https://creativecommons.org/licenses/by-nc/4.0/)
(CC BY-NC 4.0). Reuse requires attribution and must be non-commercial.
