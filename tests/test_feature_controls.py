from app.services import ai_review
from app.gui import feature_controls


def test_fallback_setting_defaults_on_for_existing_users(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_SETTINGS_FILE", str(tmp_path / "settings.json"))
    ai_review.save_settings({"provider": "gemini", "api_key": "key"})
    assert ai_review.load_settings().get("ollama_fallback_enabled", True) is True


def test_disabled_fallback_provider_does_not_send_to_ollama(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_SETTINGS_FILE", str(tmp_path / "settings.json"))
    ai_review.save_settings({"provider": "gemini", "api_key": "key",
                             "ollama_fallback_enabled": False})
    feature_controls.install()
    provider = ai_review.OllamaProvider()
    monkeypatch.setattr(provider, "model", "unused")
    monkeypatch.setattr("app.services.ollama_runtime.chat",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Ollama must not run")))
    try:
        provider.generate("private prompt", [b"private image"])
    except ai_review.AIError as exc:
        assert "disabled" in str(exc)
    else:
        raise AssertionError("disabled fallback should fail instead of using Ollama")
