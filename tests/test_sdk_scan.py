import shutil

from murf_drift import sdk_scan


def test_scan_reads_wire_names_from_request_calls(fake_sdk):
    s = sdk_scan.scan(fake_sdk)
    stream = s.calls[("POST", "/v1/speech/stream")]
    assert stream.body == {"text", "voiceId", "rate", "variation"}
    assert stream.headers == set()  # content-type is ignored
    voices = s.calls[("GET", "/v1/speech/voices")]
    assert voices.query == {"model"} and voices.headers == {"token"}


def test_sync_and_async_clients_merge_and_fstring_paths_normalize(fake_sdk):
    s = sdk_scan.scan(fake_sdk)
    assert ("DELETE", "/v1/speech/voices/cloned/{}") in s.calls
    assert len([k for k in s.calls if k[1] == "/v1/speech/stream"]) == 1


def test_core_plumbing_is_skipped(fake_sdk):
    assert ("GET", "/v1/internal/ping") not in sdk_scan.scan(fake_sdk).calls


def test_models_use_alias_and_skip_classvars(fake_sdk):
    m = sdk_scan.scan(fake_sdk).models
    assert set(m["WordTimestamp"].fields) == {"word", "endMs"}
    assert set(m["SendText"].fields) == {"text", "voice_config"}


def test_websocket_import_detected(fake_sdk, tmp_path):
    root = tmp_path / "murf"
    shutil.copytree(fake_sdk, root)
    assert sdk_scan.scan(root).has_ws_client is False
    (root / "ws.py").write_text("import websockets\n")
    assert sdk_scan.scan(root).has_ws_client is True
