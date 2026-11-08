import os
import tkinter as tk

import pytest

from app.services import ai_review


def test_provider_help_covers_every_provider():
    from app.gui.help_content import PROVIDER_HELP, provider_guidance

    assert set(PROVIDER_HELP) == set(ai_review.PROVIDERS)
    for name, cls in ai_review.PROVIDERS.items():
        text = provider_guidance(name, cls)
        assert "API key:" in text and "Model:" in text and "Base URL:" in text
        if name != "openai_compatible":
            assert all(url.startswith("https://") for url in PROVIDER_HELP[name][1:])


def test_provider_settings_keep_keys_separate(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_SETTINGS_FILE", str(tmp_path / "settings.json"))
    ai_review.save_settings({"enabled": True, "provider": "openai", "api_key": "openai-key",
                             "api_keys": {"openai": "openai-key", "anthropic": "anthropic-key"}})
    settings = ai_review.load_settings()
    assert ai_review.get_provider(settings).api_key == "openai-key"
    settings.update(provider="anthropic", api_key="anthropic-key")
    assert ai_review.get_provider(settings).api_key == "anthropic-key"


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="Tk requires a display")
def test_chatgpt_label_preserves_existing_openai_settings(tmp_path, monkeypatch):
    from app.gui.job_manager_gui import AISettingsWindow

    monkeypatch.setenv("AI_SETTINGS_FILE", str(tmp_path / "settings.json"))
    ai_review.save_settings({"enabled": True, "provider": "openai", "api_key": "existing-key",
                             "api_keys": {"openai": "existing-key"},
                             "models": {"openai": "vision-model"}})
    root = tk.Tk()
    root.withdraw()
    try:
        window = AISettingsWindow(root)
        assert window.provider.get() == "ChatGPT (OpenAI API)"
        assert window.labels[window.provider.get()] == "openai"
        assert window.key.get() == "existing-key" and window.model.get() == "vision-model"
        window.save()
        settings = ai_review.load_settings()
        assert settings["provider"] == "openai" and settings["api_key"] == "existing-key"
    finally:
        root.destroy()


@pytest.mark.parametrize("provider,expected_url", [
    (ai_review.OpenAIProvider("test"), "https://api.openai.com/v1/chat/completions"),
    (ai_review.OpenAICompatibleProvider("test", "vision-model", "https://example.test/v1"),
     "https://example.test/v1/chat/completions"),
])
def test_openai_protocol_includes_images(monkeypatch, provider, expected_url):
    def request(url, body, headers):
        assert url == expected_url and headers["Authorization"] == "Bearer test"
        assert body["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
        return {"choices": [{"message": {"content": '{"ok": true}'}}]}
    monkeypatch.setattr(ai_review, "_json_request", request)
    assert provider.generate("prompt", [b"image"]) == '{"ok": true}'


def test_ai_scope_draft_requests_text_only_grounded_output():
    class FakeProvider:
        name = "gemini"
        model = "test-model"

        def generate(self, prompt, images):
            assert images == []
            assert "BOM rows are a material reference list" in prompt
            assert "AI-BOM-12" in prompt and "EXTRACTIVE REVIEW INDEX" in prompt
            return ('{"sections":[{"title":"Phase 1","tasks":[{"text":"Install item",'
                    '"sources":["P3","BOM-12"],"verify":true}]}]}')

    draft = ai_review.draft_scope_with_ai("P3: Install item.", "AI-BOM-12 | 12 | valve",
                                          review_index="- Candidate task (verify).",
                                          provider=FakeProvider())
    assert draft["provider"] == "gemini" and draft["model"] == "test-model"
    assert draft["sections"][0]["tasks"][0]["sources"] == ["P3", "BOM-12"]


def test_anthropic_protocol_includes_images(monkeypatch):
    def request(url, body, headers):
        assert url == "https://api.anthropic.com/v1/messages" and headers["x-api-key"] == "test"
        assert body["messages"][0]["content"][1]["source"]["media_type"] == "image/png"
        return {"content": [{"type": "text", "text": '{"ok": true}'}]}
    monkeypatch.setattr(ai_review, "_json_request", request)
    assert ai_review.AnthropicProvider("test").generate("prompt", [b"image"]) == '{"ok": true}'


def test_custom_provider_rejects_insecure_url():
    with pytest.raises(ai_review.AIError, match="HTTPS"):
        ai_review.OpenAICompatibleProvider("test", "vision", "http://example.test/v1").generate("prompt", [])


def test_custom_provider_requires_model_and_url():
    with pytest.raises(ai_review.AIError, match="model and HTTPS"):
        ai_review.OpenAICompatibleProvider("test").generate("prompt", [])


@pytest.mark.parametrize("name,endpoint", [
    ("xai", "https://api.x.ai/v1/chat/completions"),
    ("groq", "https://api.groq.com/openai/v1/chat/completions"),
    ("mistral", "https://api.mistral.ai/v1/chat/completions"),
    ("openrouter", "https://openrouter.ai/api/v1/chat/completions"),
    ("together", "https://api.together.xyz/v1/chat/completions"),
])
def test_named_vision_provider(name, endpoint, monkeypatch):
    def request(url, body, headers):
        assert url == endpoint
        assert body["model"] == "vision-model"
        assert body["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")
        return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    monkeypatch.setattr(ai_review, "_json_request", request)
    provider = ai_review.get_provider({"provider": name, "api_keys": {name: "key"},
                                       "models": {name: "vision-model"}})
    assert provider.generate("prompt", [b"image"]) == '{"ok": true}'
    with pytest.raises(ai_review.AIError, match="vision-capable model"):
        ai_review.PROVIDERS[name]("key").generate("prompt", [])


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="Tk requires a display")
def test_settings_named_providers_keep_separate_fields(tmp_path, monkeypatch):
    from app.gui.job_manager_gui import AISettingsWindow

    monkeypatch.setenv("AI_SETTINGS_FILE", str(tmp_path / "settings.json"))
    root = tk.Tk()
    root.withdraw()
    try:
        window = AISettingsWindow(root)
        assert {"xAI Grok", "Groq", "Mistral AI", "OpenRouter", "Together AI"} <= set(window.labels)
        window.key.insert(0, "gemini-key")
        window.provider.set("Groq")
        window._change_provider()
        assert "Groq Console" in window.guidance.cget("text")
        assert "vision-capable model" in window.guidance.cget("text")
        assert str(window.key_link.cget("state")) == "normal"
        assert window.key.get() == ""
        assert str(window.base_url.cget("state")) == "disabled"
        window.key.insert(0, "groq-key")
        window.model.insert(0, "vision-model")
        window.enabled.set(True)
        window.save()
        settings = ai_review.load_settings()
        assert settings["api_keys"]["gemini"] == "gemini-key"
        assert settings["api_keys"]["groq"] == "groq-key"
        assert settings["models"]["groq"] == "vision-model"
    finally:
        root.destroy()


@pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="Tk requires a display")
def test_help_window_has_navigable_examples():
    from app.gui.job_manager_gui import HelpWindow

    root = tk.Tk()
    root.withdraw()
    try:
        window = HelpWindow(root, "AI setup")
        assert [window.tabs.tab(tab, "text") for tab in window.tabs.tabs()] == [
            "Getting started", "AI setup", "Troubleshooting"]
        assert window.tabs.tab(window.tabs.select(), "text") == "AI setup"
    finally:
        root.destroy()
