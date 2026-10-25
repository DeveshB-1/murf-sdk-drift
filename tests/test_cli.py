import json

from murf_drift import cli


def _args(fix, fake_sdk, *extra):
    return ["--openapi", str(fix / "openapi.json"), "--asyncapi", str(fix / "asyncapi.json"),
            "--sdk", str(fake_sdk), *extra]


def test_exit_1_on_errors_by_default(fix, fake_sdk, capsys):
    assert cli.main(_args(fix, fake_sdk)) == 1
    out = capsys.readouterr().out
    assert "7 error(s), 4 warning(s), 1 info" in out


def test_fail_on_never_exits_0(fix, fake_sdk):
    assert cli.main(_args(fix, fake_sdk, "--fail-on", "never")) == 0


def test_json_output_is_machine_readable(fix, fake_sdk, capsys):
    cli.main(_args(fix, fake_sdk, "--format", "json"))
    data = json.loads(capsys.readouterr().out)
    assert data["meta"]["ws_channels"] == 2
    assert {"severity", "kind", "where", "detail"} == set(data["findings"][0])


def test_skip_websocket_checks(fix, fake_sdk, capsys):
    cli.main(_args(fix, fake_sdk, "--asyncapi", "", "--format", "json"))
    kinds = {f["kind"] for f in json.loads(capsys.readouterr().out)["findings"]}
    assert not any(k.startswith("ws-") for k in kinds)


def test_markdown_table(fix, fake_sdk, capsys):
    cli.main(_args(fix, fake_sdk, "--format", "markdown"))
    out = capsys.readouterr().out
    assert out.startswith("### SDK drift") and "| error | missing-operation |" in out


def test_bad_sdk_path_is_usage_error(fix, tmp_path):
    assert cli.main(_args(fix, tmp_path / "nope")) == 2
