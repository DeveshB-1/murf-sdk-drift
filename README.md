# murf-sdk-drift

Checks whether the Murf Python SDK (`pip install murf`) still covers what Murf's own API docs say the API can do.

It reads 3 public things and compares them:

1. Murf's OpenAPI spec (`murf.ai/api/docs/openapi.json`), for REST endpoints, body fields, query params and headers.
2. Murf's AsyncAPI spec (`murf.ai/api/docs/asyncapi.json`), for WebSocket messages on `/stream-input` (Falcon TTS) and `/v1/transcription/stream-input` (Speech to Text).
3. Every ```python block on every docs page listed in `murf.ai/api/docs/llms.txt` (optional, `--docs`).

The SDK is parsed with `ast` and never imported or executed, so it needs no API key and makes no API calls. Fern writes every request as a string path plus a dict of wire names (`json={"voiceId": voice_id, ...}`), so the scanner reads exactly what goes on the wire.

## Why this matters to Murf

Murf ships API changes fast. Falcon 2, word timestamps, `volumeOffset`, pronunciation dictionaries on streaming, Falcon 2.1 and Speech to Text all landed between June and October 2026. The latest SDK on PyPI is 2.3.0, from 2026-03-05, and the `murf-python-sdk` repo hasn't had a push since that date.

So a developer who copies the Python example from the volume offset docs gets this, before any request is sent:

```
$ python -c "from murf import Murf; Murf(api_key='x').text_to_speech.stream(text='hi', voice_id='Matthew', volume_offset=25)"
TypeError: TextToSpeechClient.stream() got an unexpected keyword argument 'volume_offset'
```

murf-sdk-drift finds that class of bug from the specs alone, exits 1, and can run nightly in CI next to the Fern generation step.

## Quickstart

```bash
uv venv && uv pip install -e . murf          # murf is the SDK under test
.venv/bin/murf-drift                          # live specs vs installed SDK
.venv/bin/murf-drift --docs                   # also check every Python example in the docs
.venv/bin/murf-drift --sdk ../murf-python-sdk/src/murf --format markdown   # a source checkout, issue-ready table
```

Options:

| Flag | Default | |
|---|---|---|
| `--openapi` | live Murf spec | URL or file |
| `--asyncapi` | live Murf spec | URL or file, `''` skips WebSocket checks |
| `--sdk` | installed `murf` package | path to a `murf/` package dir |
| `--docs [LLMS_TXT]` | off | walk the docs index and check Python examples |
| `--format` | `text` | `text`, `json`, `markdown` |
| `--fail-on` | `error` | `error`, `warn`, `never` |

Exit codes: 0 clean, 1 drift at or above `--fail-on`, 2 bad input.

## What it reports

| Kind | Severity | Meaning |
|---|---|---|
| `missing-operation` | error | endpoint in the spec, no SDK method calls it |
| `missing-field` | error | body field, query param or header in the spec the SDK can't send |
| `ws-missing-channel` / `ws-missing-message` / `ws-missing-field` | error | WebSocket channel, message or field (nested too) with no SDK type |
| `docs-unknown-kwarg` / `docs-unknown-method` | error | a docs example that raises before sending anything |
| `stale-field` / `stale-operation` / `ws-stale-field` | warn | the SDK sends something the spec doesn't list |
| `ws-no-client` | warn | the SDK has WebSocket types but nothing that connects |
| `spec-mixed-casing` | info | one object in the spec mixes camelCase and snake_case |

Fern's `request_options` (`additional_headers`, `additional_body_parameters`) can paper over a missing field, so an error here means "no typed parameter", and a workaround might exist. The docs-example error is different: that one fails as written.

## Demo: live run, 2026-10-25

`murf` 2.3.0 from PyPI against the live specs and all 62 docs pages:

```
$ murf-drift --docs
murf-drift: SDK 2.3.0 vs https://murf.ai/api/docs/openapi.json
            and https://murf.ai/api/docs/asyncapi.json

ERROR (20)
  [missing-field] POST /v1/speech/stream: body field `volumeOffset` is in the spec, SDK never sends it
  [missing-field] POST /v1/speech/stream: header `token` is in the spec, SDK never sends it
  [missing-field] POST /v1/speech/generate: header `token` is in the spec, SDK never sends it
  [missing-operation] POST /v1/speech/voices/create: in the spec, no SDK method calls it
  [missing-operation] GET /v1/speech/voice-clone-creation-status/{requestId}: in the spec, no SDK method calls it
  [missing-operation] GET /v1/speech/voices/cloned: in the spec, no SDK method calls it
  [missing-operation] DELETE /v1/speech/voices/cloned/{voiceId}: in the spec, no SDK method calls it
  [missing-field] POST /v1/voice-changer/convert: header `token` is in the spec, SDK never sends it
  [missing-field] POST /v1/text/translate: header `token` is in the spec, SDK never sends it
  [ws-missing-field] WS /stream-input audioOutput: field `trace_id` is in the spec, missing from SDK model AudioOutput
  [ws-missing-message] WS /stream-input timestampOutput: message type is in the spec, SDK has no model for it
  [ws-missing-field] WS /stream-input finalOutput: field `trace_id` is in the spec, missing from SDK model FinalOutput
  [ws-missing-message] WS /stream-input warningOutput: message type is in the spec, SDK has no model for it
  [ws-missing-message] WS /stream-input errorOutput: message type is in the spec, SDK has no model for it
  [ws-missing-field] WS /stream-input setVoiceConfigurationOrInitializeContext.voice_config: field `volumeOffset` is in the spec, missing from SDK model SetVoiceConfigurationOrInitializeContextVoiceConfig
  [ws-missing-field] WS /stream-input sendText.voice_config: field `volumeOffset` is in the spec, missing from SDK model SendTextVoiceConfig
  [ws-missing-field] WS /stream-input setAdvancedSettings: field `add_word_timestamps` is in the spec, missing from SDK model SetAdvancedSettings
  [ws-missing-field] WS /stream-input setAdvancedSettings: field `predictive_chunking` is in the spec, missing from SDK model SetAdvancedSettings
  [ws-missing-channel] /v1/transcription/stream-input: no SDK types for any message on this channel (Partial, Final, QuotaWarning, Error, setAudioConfiguration, Audio, Finalize, CloseStream, KeepAlive)
  [docs-unknown-kwarg] https://murf.ai/api/docs/text-to-speech/speech-customization.md: `text_to_speech.stream(volume_offset=...)` raises TypeError: the SDK has no `volume_offset` parameter

WARN (7)
  [stale-field] POST /v1/speech/stream: SDK sends body field `variation`, spec does not list it
  [stale-field] POST /v1/voice-changer/convert: SDK sends body field `pronunciation_dictionary`, spec does not list it
  [ws-stale-field] WS /stream-input setVoiceConfigurationOrInitializeContext.voice_config: SDK model SetVoiceConfigurationOrInitializeContextVoiceConfig has `multi_native_locale`, spec does not list it
  [ws-stale-field] WS /stream-input setVoiceConfigurationOrInitializeContext.voice_config: SDK model SetVoiceConfigurationOrInitializeContextVoiceConfig has `variation`, spec does not list it
  [ws-stale-field] WS /stream-input sendText.voice_config: SDK model SendTextVoiceConfig has `multi_native_locale`, spec does not list it
  [ws-stale-field] WS /stream-input sendText.voice_config: SDK model SendTextVoiceConfig has `variation`, spec does not list it
  [ws-no-client] SDK: SDK ships WebSocket message types but no connect helper, so callers hand-build URLs and query params (/stream-input: channel_type, format, model, sample_rate; /v1/transcription/stream-input: alpha, bvc, commit_mode, keywords, language, text_formatting)

INFO (2)
  [spec-mixed-casing] WS /stream-input setVoiceConfigurationOrInitializeContext.voice_config: spec mixes camelCase (volumeOffset) with snake_case (pronunciation_dictionary, voice_id...) in one object
  [spec-mixed-casing] WS /stream-input sendText.voice_config: spec mixes camelCase (volumeOffset) with snake_case (pronunciation_dictionary, voice_id...) in one object

docs: 62 pages, 102 python blocks, 86 SDK calls checked
20 error(s), 7 warning(s), 2 info
```

In plain terms:

- **Instant Voice Cloning** (4 endpoints) has no SDK methods.
- **Speech to Text** (launched 2026-10-22) has no SDK types at all.
- **`volumeOffset`** is in the spec for HTTP streaming and WebSocket, missing from the SDK, and the docs' own Python example for it fails.
- **WebSocket** responses: `timestampOutput`, `warningOutput` and `errorOutput` frames have no SDK model, so `ReceiveMessage` can't type a word timestamp or an error.
- `volumeOffset` is the only camelCase key inside the snake_case WebSocket `voice_config`. The docs say to send it that way, so it's probably intended, but it's an easy one to get wrong in a hand-written client.

Of 86 SDK calls in the docs, 85 match the installed SDK.

## Tests

```
$ .venv/bin/python -m pytest -q
..........................                                               [100%]
26 passed in 0.37s
```

The fixture tests use a small fake Fern-style SDK (`tests/fixtures/fakesdk`) and trimmed specs, so they're deterministic and offline. `tests/test_real_sdk.py` runs against the real `murf` wheel when it's installed: it checks that the AST view of `text_to_speech.stream` matches `inspect.signature` of the imported client, and reproduces the `volume_offset` TypeError (skipped once a fixed SDK is installed).

## Running it in CI

```yaml
# .github/workflows/sdk-drift.yml
on:
  schedule: [{cron: "30 3 * * *"}]
  workflow_dispatch:
jobs:
  drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv venv && uv pip install -e . murf
      - run: .venv/bin/murf-drift --docs --format markdown >> "$GITHUB_STEP_SUMMARY"
```

## Limits

- Field checks are by name. Types, enums and required-ness aren't compared yet.
- SDK messages are matched to spec messages by normalized name (`sendText` to `SendText`). A renamed type shows up as one missing and one unmatched.
- The docs check reads `client.<resource>.<method>(...)` and `Murf(...)` calls. Code that aliases the client through another variable chain, or builds kwargs with `**opts`, isn't checked.
- The findings above are from the public specs and the public SDK. Nothing here called Murf's API.

## Layout

```
murf_drift/spec.py        OpenAPI + AsyncAPI loading, $ref / allOf / nullable resolution
murf_drift/sdk_scan.py    AST scan of the SDK: request calls, pydantic models, websocket imports
murf_drift/diff.py        the comparison and findings
murf_drift/docs_check.py  docs Python examples vs SDK signatures
murf_drift/cli.py         CLI, text / json / markdown output, exit codes
```
