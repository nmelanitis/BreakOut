from breakout import cli


def test_serve_subcommand_starts_dashboard(monkeypatch) -> None:
    started = []
    monkeypatch.setattr(cli, "serve", lambda: started.append(True))

    cli.main(["serve"])

    assert started == [True]
