#!/usr/bin/env python3
"""
MiniMax Anthropic API probe script.

Tests whether MiniMax Anthropic Messages API is reachable and returns valid JSON.
Does NOT fetch URLs, write to DB, or create InsightCards.
Does NOT print API keys.
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load .env
load_dotenv()

from app.llm.factory import create_llm_client
from app.llm.config_loader import get_active_profile

# Simple test prompts
SYSTEM_PROMPT = "You are a JSON test assistant. Only output JSON, nothing else."

USER_PROMPT = """Please return the following JSON and nothing else:
{"ok": true, "message": "hello"}"""


def main():
    print("=" * 50)
    print("MiniMax Anthropic API Probe")
    print("=" * 50)

    # Show active profile (without API key)
    profile_name = os.getenv("LLM_PROFILE", "unknown")
    print(f"[OK] LLM_PROFILE={profile_name}")

    try:
        active_profile = get_active_profile()
        print(f"[OK] provider={active_profile.get('provider')}")
        print(f"[OK] protocol={active_profile.get('protocol')}")
        print(f"[OK] model={active_profile.get('model')}")
        print(f"[OK] base_url={active_profile.get('base_url')}")
        print(f"[OK] endpoint={active_profile.get('endpoint')}")
        auth_type = active_profile.get("auth_type", "bearer")
        print(f"[OK] auth_type={auth_type}")
        api_key_env = active_profile.get("api_key_env", "")
        print(f"[OK] api_key_env={api_key_env}")
        api_key = os.getenv(api_key_env, "")
        print(f"[OK] MINIMAX_API_KEY configured: {'yes' if api_key else 'NO'}")
    except Exception as e:
        print(f"[FAIL] Failed to load profile: {e}")
        return 1

    # Create client
    print("\nCreating LLM client...")
    try:
        client = create_llm_client()
        print(f"[OK] Client created: {client.__class__.__name__}")
    except Exception as e:
        print(f"[FAIL] Failed to create client: {e}")
        return 1

    # Call API
    print("\nCalling MiniMax API...")
    try:
        result = client.generate_json(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=USER_PROMPT,
        )
        print(f"[OK] API call succeeded")
        print(f"[OK] model_name={result.get('model_name', 'NOT PRESENT')}")

        if "ok" in result:
            print(f"[OK] Response 'ok'={result['ok']}")
        if "message" in result:
            print(f"[OK] Response 'message'={result['message']}")

        import json
        print(f"\n[OK] parsed JSON: {json.dumps(result, ensure_ascii=False)}")
        return 0

    except Exception as e:
        print(f"[FAIL] API call failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
