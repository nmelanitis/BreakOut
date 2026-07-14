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
