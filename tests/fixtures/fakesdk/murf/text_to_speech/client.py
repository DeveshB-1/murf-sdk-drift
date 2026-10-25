import typing

OMIT = typing.cast(typing.Any, ...)


def jsonable_encoder(x):
    return x


class TextToSpeechClient:
    def __init__(self, *, client_wrapper):
        self._client_wrapper = client_wrapper

    def stream(self, *, text: str, voice_id: str, rate: typing.Optional[int] = OMIT, variation=OMIT,
               request_options=None):
        with self._client_wrapper.httpx_client.stream(
            "v1/speech/stream",
            method="POST",
            json={"text": text, "voiceId": voice_id, "rate": rate, "variation": variation},
            headers={"content-type": "application/json"},
            request_options=request_options,
        ) as r:
            yield r

    def get_voices(self, *, model=None, token=None):
        return self._client_wrapper.httpx_client.request(
            "v1/speech/voices", method="GET", params={"model": model}, headers={"token": token}
        )

    def delete_clone(self, voice_id: str):
        return self._client_wrapper.httpx_client.request(
            f"v1/speech/voices/cloned/{jsonable_encoder(voice_id)}", method="DELETE"
        )

    def legacy(self):
        return self._client_wrapper.httpx_client.request("v1/speech/legacy", method="GET")


class AsyncTextToSpeechClient:
    def __init__(self, *, client_wrapper):
        self._client_wrapper = client_wrapper

    async def stream(self, *, text: str, voice_id: str, rate=OMIT, variation=OMIT):
        async with self._client_wrapper.httpx_client.stream(
            "v1/speech/stream",
            method="POST",
            json={"text": text, "voiceId": voice_id, "rate": rate, "variation": variation},
        ) as r:
            yield r
