from murf_drift import diff, sdk_scan, spec


def _findings(fix, fake_sdk):
    s = sdk_scan.scan(fake_sdk)
    out = diff.diff_rest(spec.rest_operations(spec.load(str(fix / "openapi.json"))), s)
    channels, r = spec.ws_channels(spec.load(str(fix / "asyncapi.json")))
    return out + diff.diff_ws(channels, r, s)


def test_exact_findings_for_fixture(fix, fake_sdk):
    got = {(f.severity, f.kind, f.where, f.detail.split("`")[1] if "`" in f.detail else "") for f in _findings(fix, fake_sdk)}
    assert got == {
        ("error", "missing-field", "POST /v1/speech/stream", "volumeOffset"),
        ("error", "missing-field", "POST /v1/speech/stream", "token"),
        ("warn", "stale-field", "POST /v1/speech/stream", "variation"),
        ("error", "missing-operation", "POST /v1/speech/voices/create", ""),
        ("warn", "stale-operation", "GET /v1/speech/legacy", ""),
        ("error", "ws-missing-message", "WS /stream-input errorOutput", ""),
        ("error", "ws-missing-field", "WS /stream-input sendText", "context_id"),
        ("error", "ws-missing-field", "WS /stream-input sendText.voice_config", "volumeOffset"),
        ("warn", "ws-stale-field", "WS /stream-input sendText.voice_config", "variation"),
        ("info", "spec-mixed-casing", "WS /stream-input sendText.voice_config", ""),
        ("error", "ws-missing-channel", "/v1/transcription/stream-input", ""),
        ("warn", "ws-no-client", "SDK", ""),
    }


def test_aliased_fields_and_matching_ops_produce_nothing(fix, fake_sdk):
    wheres = {f.where for f in _findings(fix, fake_sdk)}
    assert "WS /stream-input wordTimestamp" not in wheres
    assert "GET /v1/speech/voices" not in wheres
    assert "DELETE /v1/speech/voices/cloned/{voiceId}" not in wheres


def test_mixed_casing_split():
    assert diff.mixed_casing(["voice_id", "volumeOffset", "rate"]) == (["voice_id"], ["volumeOffset"])
    assert diff.mixed_casing(["voiceId", "sampleRate"]) == ([], ["sampleRate", "voiceId"])


def test_worst():
    assert diff.worst([]) is None
    assert diff.worst([diff.Finding("info", "k", "w", "d"), diff.Finding("warn", "k", "w", "d")]) == "warn"
