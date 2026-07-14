# BreakOut desktop beta

BreakOut runs only on the computer where the user launches it. The packaged application starts a
local server at `http://127.0.0.1:3000` and opens the dashboard in the default browser. It does
not host a public service or include Spotify credentials.

## For beta testers

1. Download the ZIP for your operating system from the **Desktop Beta Build** workflow artifacts.
2. Extract it and run `BreakOut` (`BreakOut.exe` on Windows). macOS may ask you to confirm that
   you want to open an app downloaded from the internet.
3. The BreakOut setup page opens in your browser. Create your own Spotify developer app, add the
   displayed callback address, and paste only that app’s Client ID.
4. Connect Spotify and export your library. The browser downloads the resulting ZIP archive.

Every tester uses their own Spotify developer app. Never distribute a shared Client ID or a Client
Secret, and never enter a Client Secret into BreakOut.

## Building locally

Install the desktop build group and run PyInstaller from the repository root:

```sh
uv sync --group desktop
uv run pyinstaller --noconfirm --clean breakout.spec
```

The output is one executable in `dist/`. PyInstaller must build each operating system’s artifact
on that operating system; the GitHub workflow provides the macOS, Windows, and Linux build matrix.
