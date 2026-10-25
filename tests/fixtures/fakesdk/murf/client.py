import typing


class Murf:
    def __init__(self, *, api_key: typing.Optional[str] = None, region: typing.Optional[str] = None):
        self.text_to_speech = None
