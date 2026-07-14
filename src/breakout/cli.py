"""Local-only command line launcher."""

from __future__ import annotations

import argparse
import threading
import webbrowser
from collections.abc import Sequence

import uvicorn

from breakout.app import HOST, PORT, create_app


def serve() -> None:
    """Start the local dashboard and open it in the default browser."""
    url = f"http://{HOST}:{PORT}"
    print(f"BreakOut is running at {url}")
    threading.Timer(0.75, lambda: webbrowser.open(url)).start()
    uvicorn.run(create_app(), host=HOST, port=PORT, log_level="info")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="breakout", description="Run the BreakOut local dashboard."
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("serve", help="Start the local dashboard at http://127.0.0.1:3000")
    arguments = parser.parse_args(argv)
    if arguments.command == "serve":
        serve()
