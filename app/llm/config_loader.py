"""LLM configuration loader."""
import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
PROFILES_FILE = CONFIG_DIR / "llm_profiles.yaml"
PROFILES_EXAMPLE_FILE = CONFIG_DIR / "llm_profiles.example.yaml"

# Environment variable pattern: ${VAR_NAME}
ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _substitute_env_vars(value: Any) -> Any:
    """Recursively substitute ${ENV_NAME} patterns with environment variable values."""
    if isinstance(value, str):
        def replacer(m):
            var_name = m.group(1)
            env_val = os.getenv(var_name, "")
            return env_val

        return ENV_VAR_PATTERN.sub(replacer, value)
    elif isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]
    return value


def _load_yaml_file(filepath: Path) -> dict[str, Any]:
    """Load YAML file and return as dict."""
    if not filepath.exists():
        return {}
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_llm_profiles() -> dict[str, Any]:
    """
    Load LLM profiles from YAML config.

    Priority:
    1. config/llm_profiles.yaml (user config, gitignored)
    2. config/llm_profiles.example.yaml (example config)
    """
    # Try user config first, then example
    profiles_data = _load_yaml_file(PROFILES_FILE)
    if not profiles_data:
        profiles_data = _load_yaml_file(PROFILES_EXAMPLE_FILE)

    if not profiles_data:
        raise FileNotFoundError(
            f"No LLM profiles config found. "
            f"Create {PROFILES_FILE} or {PROFILES_EXAMPLE_FILE}"
        )

    return profiles_data


def get_active_profile() -> dict[str, Any]:
    """
    Load and return the active LLM profile based on LLM_PROFILE env var.
    """
    profiles_data = load_llm_profiles()
    profile_name = os.getenv("LLM_PROFILE", profiles_data.get("default_profile", ""))

    if not profile_name:
        raise ValueError("LLM_PROFILE environment variable is not set")

    profiles = profiles_data.get("profiles", {})
    if profile_name not in profiles:
        raise ValueError(f"LLM profile not found: {profile_name}")

    profile = profiles[profile_name]

    # Substitute environment variables in string values
    profile = _substitute_env_vars(profile)

    # Load API key from environment variable specified by api_key_env
    api_key_env = profile.get("api_key_env", "")
    if api_key_env:
        api_key = os.getenv(api_key_env, "")
        if not api_key or api_key == "replace-me":
            raise ValueError(
                f"{api_key_env} is not configured. "
                f"Please set your API key in the .env file."
            )
        profile["api_key"] = api_key
    else:
        profile["api_key"] = ""

    return profile


def validate_profile(profile: dict[str, Any]) -> None:
    """Validate that a profile has all required fields."""
    required = ["provider", "protocol", "base_url", "model", "api_key"]
    for field in required:
        if field not in profile or not profile[field]:
            raise ValueError(f"LLM profile missing required field: {field}")

    if profile["protocol"] == "anthropic_messages":
        if "max_tokens" not in profile:
            raise ValueError(
                "Anthropic Messages API requires 'max_tokens' field, "
                "not 'max_completion_tokens'"
            )
    elif profile["protocol"] == "openai_chat_completions":
        if "max_completion_tokens" not in profile and "max_tokens" not in profile:
            raise ValueError(
                "OpenAI Chat Completions requires 'max_completion_tokens' field"
            )
