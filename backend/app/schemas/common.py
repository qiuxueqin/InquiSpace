from pydantic import BaseModel, ConfigDict, Field, JsonValue
from pydantic.alias_generators import to_camel


class APIModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class Envelope[T](APIModel):
    data: T
    request_id: str


class ErrorDetail(APIModel):
    code: str
    message: str
    details: dict[str, JsonValue] = Field(default_factory=dict)
    retryable: bool = False


class ErrorEnvelope(APIModel):
    error: ErrorDetail
    request_id: str
