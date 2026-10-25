import typing

import pydantic
import typing_extensions

from ..core.unchecked_base_model import UncheckedBaseModel, FieldMetadata, IS_PYDANTIC_V2


class SendTextVoiceConfig(UncheckedBaseModel):
    voice_id: typing.Optional[str] = pydantic.Field(default=None)
    variation: typing.Optional[int] = None


class SendText(UncheckedBaseModel):
    text: str = pydantic.Field()
    voice_config: typing.Optional[SendTextVoiceConfig] = None

    if IS_PYDANTIC_V2:
        model_config: typing.ClassVar[dict] = {}


class WordTimestamp(UncheckedBaseModel):
    word: str
    end_ms: typing_extensions.Annotated[typing.Optional[int], FieldMetadata(alias="endMs")] = None
