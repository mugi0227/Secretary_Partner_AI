import pytest
from pydantic import BaseModel

from app.core.exceptions import LLMValidationError
from app.services.llm_utils import generate_validated_json


class ParsedOutput(BaseModel):
    title: str


def test_generate_validated_json_retries_until_output_validates() -> None:
    outputs = iter(["not json", '{"title": "ok"}'])

    result = generate_validated_json(lambda: next(outputs), ParsedOutput, label="task parser")

    assert result == ParsedOutput(title="ok")


def test_generate_validated_json_uses_fallback_after_failures() -> None:
    result = generate_validated_json(
        lambda: None,
        ParsedOutput,
        max_attempts=2,
        fallback=ParsedOutput(title="fallback"),
        label="task parser",
    )

    assert result == ParsedOutput(title="fallback")


def test_generate_validated_json_raises_with_attempt_count() -> None:
    with pytest.raises(LLMValidationError) as exc_info:
        generate_validated_json(
            lambda: "{",
            ParsedOutput,
            max_attempts=2,
            label="task parser",
        )

    assert exc_info.value.raw_output == "{"
    assert exc_info.value.attempts == 2
