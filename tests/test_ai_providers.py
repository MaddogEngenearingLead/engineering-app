import pytest

from app.services import ai_review


def test_provider_settings_keep_keys_separate(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_SETTINGS_FILE", str(tmp_path / "settings.json"))
    ai_review.save_settings({"enabled": True, "provider": "openai", "api_key": "openai-key",
                             "api_keys": {"openai": "openai-key", "anthropic": "anthropic-key"}})
    settings = ai_review.load_settings()
    assert ai_review.get_provider(settings).api_key == "openai-key"
    settings.update(provider="anthropic", api_key="anthropic-key")
    assert ai_review.get_provider(settings).api_key == "anthropic-key"


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
