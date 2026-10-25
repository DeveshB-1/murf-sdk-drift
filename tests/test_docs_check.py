from murf_drift import docs_check


def test_signatures_cover_resources_and_constructor(fake_sdk):
    sigs = docs_check.sdk_signatures(fake_sdk)
    assert "volume_offset" not in sigs[("text_to_speech", "stream")].params
    assert {"text", "voice_id", "rate"} <= sigs[("text_to_speech", "stream")].params
    assert sigs[("", "Murf")].params == {"api_key", "region"}
    # async client methods are not double counted under another resource
    assert all(not r.startswith("Async") for r, _ in sigs)


def test_unknown_kwarg_is_reported(fake_sdk):
    src = '''
from murf import Murf
client = Murf(region="GLOBAL")
audio = client.text_to_speech.stream(text="hi", voice_id="Matthew", volume_offset=25)
'''
    findings, n = docs_check.check_source(src, "page.md", docs_check.sdk_signatures(fake_sdk))
    assert n == 2
    assert [(f.kind, f.detail.split("`")[1]) for f in findings] == [("docs-unknown-kwarg", "text_to_speech.stream(volume_offset=...)")]


def test_unknown_method_and_bad_constructor(fake_sdk):
    src = 'c = Murf(apikey="x")\nc.text_to_speech.clone_voice(name="a")\n'
    kinds = sorted(f.kind for f in docs_check.check_source(src, "p", docs_check.sdk_signatures(fake_sdk))[0])
    assert kinds == ["docs-unknown-kwarg", "docs-unknown-method"]


def test_non_sdk_calls_and_broken_snippets_are_ignored(fake_sdk):
    sigs = docs_check.sdk_signatures(fake_sdk)
    assert docs_check.check_source('f.write(b"x")\nws.send(json.dumps({}))', "p", sigs) == ([], 0)
    assert docs_check.check_source("client.text_to_speech.stream(\n  ...", "p", sigs) == ([], 0)


def test_check_docs_walks_index_with_injected_fetch(fake_sdk):
    pages = {
        "IDX": "- [A](https://murf.ai/api/docs/a.md)\n- [B](https://murf.ai/api/docs/b.md)\n- [A](https://murf.ai/api/docs/a.md)",
        "https://murf.ai/api/docs/a.md": "text\n```python\nclient.text_to_speech.stream(text='x', voice_id='y', volume_offset=1)\n```\n"
                                         "```python title=\"again\"\nclient.text_to_speech.stream(text='x', voice_id='y', volume_offset=1)\n```\n",
        "https://murf.ai/api/docs/b.md": "```javascript\nclient.textToSpeech.stream({volumeOffset: 1})\n```\n",
    }
    findings, stats = docs_check.check_docs(fake_sdk, "IDX", fetch=pages.__getitem__)
    assert stats == {"pages": 2, "python_blocks": 2, "sdk_calls_checked": 2, "fetch_errors": 0}
    assert len(findings) == 1  # duplicate tab snippet collapses to one row
