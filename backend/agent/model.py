import os

from strands.models.openai import OpenAIModel

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class AgentConfigError(RuntimeError):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise AgentConfigError(
            f"Missing required environment variable {name}. "
            "Set it in the .env file (see .env.example)."
        )
    return value


def build_model() -> OpenAIModel:
    api_key = _require_env("OPENROUTER_API_KEY")
    model_id = _require_env("OPENROUTER_MODEL")
    return OpenAIModel(
        client_args={
            "api_key": api_key,
            "base_url": OPENROUTER_BASE_URL,
            "timeout": 90.0,
            "max_retries": 2,
        },
        model_id=model_id,
    )