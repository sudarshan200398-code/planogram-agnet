"""Gemini LLM client using google-genai."""
from __future__ import annotations

import os

from ..settings import Settings, load_settings


class GeminiClient:
    """Client for Google Gemini models using the google-genai SDK.

    Reads GEMINI_API_KEY from environment variables and lazily imports
    google-genai inside the class so test suites do not require the package.
    """

    def __init__(self, settings: Settings | None = None, api_key: str | None = None) -> None:
        if settings is None:
            settings = load_settings()
        self.settings = settings
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")

    def generate(self, system: str, user: str) -> str:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ImportError(
                "The google-genai package is required to use GeminiClient. "
                "Install it with 'pip install google-genai'."
            ) from exc

        client = genai.Client(api_key=self.api_key)
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.0,
            max_output_tokens=self.settings.max_tokens,
            response_mime_type="application/json",
        )
        response = client.models.generate_content(
            model=self.settings.model_name,
            contents=user,
            config=config,
        )
        return response.text or ""
