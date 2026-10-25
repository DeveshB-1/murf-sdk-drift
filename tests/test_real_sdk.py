"""Runs against the real `murf` wheel when it is installed. Offline: no spec download, no API key."""

import inspect

import pytest

from murf_drift import docs_check, sdk_scan

murf = pytest.importorskip("murf")


def test_scanner_agrees_with_the_real_signature():
    root, version = sdk_scan.locate_installed("murf")
    surface = sdk_scan.scan(root, version)
    stream = surface.calls[("POST", "/v1/speech/stream")]
    assert {"text", "voiceId", "pronunciationDictionary"} <= stream.body
    real = set(inspect.signature(murf.Murf(api_key="x").text_to_speech.stream).parameters)
    ast_view = docs_check.sdk_signatures(root)[("text_to_speech", "stream")].params
    assert ast_view == real


def test_volume_offset_example_fails_on_installed_sdk_if_unsupported():
    """The docs example passes volume_offset=25. On murf<=2.3.0 that is a TypeError before any request."""
    root, _ = sdk_scan.locate_installed("murf")
    accepts = "volume_offset" in docs_check.sdk_signatures(root)[("text_to_speech", "stream")].params
    client = murf.Murf(api_key="x")
    if accepts:
        pytest.skip("installed SDK already accepts volume_offset")
    with pytest.raises(TypeError, match="volume_offset"):
        client.text_to_speech.stream(text="hi", voice_id="Matthew", volume_offset=25)
