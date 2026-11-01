"""Optional AI second opinion on the P&ID scan.

The rule-based scan always runs first. When AI review is switched on, the drawing pages, the
scope and the scan's BOM are sent to an AI provider, which finds the legend/key and lists what
the scope needs that the BOM lacks (and what the BOM has that the scope doesn't need). Its
findings become ordinary review questions, so nothing changes without the user's approval.

Providers are pluggable: add a class to ``PROVIDERS`` and pick it in the AI settings.
Settings live in ``ai_settings.json`` in the user's app-data folder (or ``AI_SETTINGS_FILE``).
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_PAGES = 12
MAX_PIXELS = 2600  # longest side of a rendered page


class AIError(Exception):
    pass


# ---------------------------------------------------------------- settings

DEFAULTS = {"enabled": False, "provider": "gemini", "api_key": "", "models": {}}


def settings_path() -> Path:
    env = os.environ.get("AI_SETTINGS_FILE")
    if env:
        return Path(env)
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "EngineeringApp" / "ai_settings.json"


def load_settings() -> dict:
    data = dict(DEFAULTS)
    try:
        data.update(json.loads(settings_path().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    if not data.get("api_key"):
        data["api_key"] = os.environ.get("GEMINI_API_KEY", "") if data.get("provider") == "gemini" else ""
    return data


def save_settings(settings: dict) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**DEFAULTS, **settings}, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


# ---------------------------------------------------------------- providers

class Provider:
    name = ""
    label = ""
    default_model = ""

    def __init__(self, api_key: str, model: str | None = None):
        self.api_key = api_key
        self.model = model or self.default_model

    def generate(self, prompt: str, images: list[bytes]) -> str:
        """Send the prompt and PNG page images; return the model's JSON text reply."""
        raise NotImplementedError


class GeminiProvider(Provider):
    name = "gemini"
    label = "Google Gemini (free tier available)"
    default_model = "gemini-2.5-flash"
    url = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def generate(self, prompt: str, images: list[bytes]) -> str:
        parts = [{"text": prompt}]
        parts += [{"inline_data": {"mime_type": "image/png", "data": base64.b64encode(i).decode()}}
                  for i in images]
        body = json.dumps({"contents": [{"parts": parts}],
                           "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1}}
                          ).encode()
        req = urllib.request.Request(self.url.format(model=self.model), data=body, method="POST",
                                     headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key})
        last = ""
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=240) as resp:
                    payload = json.loads(resp.read())
                break
            except urllib.error.HTTPError as exc:
                last = _http_message(exc)
                if exc.code in (429, 500, 503) and attempt < 2:
                    time.sleep(5 * (attempt + 1))
                    continue
                raise AIError(last) from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                raise AIError(f"Could not reach Gemini: {getattr(exc, 'reason', exc)}") from None
        try:
            return "".join(p.get("text", "") for p in payload["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            raise AIError("Gemini returned no answer (the drawing may have been blocked).") from None


def _http_message(exc: urllib.error.HTTPError) -> str:
    try:
        detail = json.loads(exc.read()).get("error", {}).get("message", "")
    except Exception:
        detail = ""
    hints = {400: "The key or request was rejected", 403: "The API key isn't allowed to use this model",
             429: "Free-tier limit reached - try again later", 404: "Model not found"}
    return f"{hints.get(exc.code, 'AI service error')} ({exc.code}). {detail[:160]}".strip()


PROVIDERS: dict[str, type[Provider]] = {GeminiProvider.name: GeminiProvider}


def get_provider(settings: dict | None = None) -> Provider:
    s = settings or load_settings()
    cls = PROVIDERS.get(s.get("provider"))
    if not cls:
        raise AIError(f"Unknown AI provider '{s.get('provider')}'.")
    if not s.get("api_key"):
        raise AIError("No API key set. Add one in AI settings.")
    return cls(s["api_key"], (s.get("models") or {}).get(cls.name))


def is_enabled() -> bool:
    s = load_settings()
    return bool(s.get("enabled") and s.get("api_key"))


# ---------------------------------------------------------------- review

def render_pages(pdf_path: str, limit: int = MAX_PAGES) -> list[bytes]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_path)
    out = []
    try:
        for i in range(min(len(pdf), limit)):
            page = pdf[i]
            w, h = page.get_size()
            image = page.render(scale=min(3.0, MAX_PIXELS / max(w, h))).to_pil().convert("RGB")
            buf = io.BytesIO()
            image.save(buf, "PNG", optimize=True)
            out.append(buf.getvalue())
    finally:
        pdf.close()
    return out


PROMPT = """You are a piping/instrumentation estimator checking a bill of materials (BOM).
The attached images are the pages of a P&ID drawing, in order (page 1 first). Colours: green or
highlighted = new work, red = demolition, blue clouds = future work, grey = existing. Black bold =
in scope.

SCOPE OF WORK:
{scope}

BOM PRODUCED BY AN AUTOMATIC SCAN (tag | description | qty):
{bom}

Tasks:
1. Find the legend / instrument key and use it to identify symbols and tags.
2. Decide what the scope of work actually requires to be purchased. Items only used as a location or
   reference (e.g. "at tank 1") are NOT needed. Existing or demolished items are NOT needed.
3. List items the scope requires that are missing from the BOM (including quantity differences).
4. List BOM items the scope does not require.
Only report what you can see on the drawing or read in the scope. Do not invent tags.

Reply with JSON only:
{{"key_page": <page number or null>,
 "summary": "<one or two plain sentences>",
 "missing": [{{"tag": "<tag or empty>", "description": "<item>", "quantity": <number>, "page": <number or null>, "reason": "<why>"}}],
 "not_needed": [{{"tag": "<tag as in BOM>", "reason": "<why>"}}]}}"""


def _bom_text(materials: list[dict]) -> str:
    rows = [f"{m.get('tag_id', '-')} | {m.get('description', '')} | {m.get('quantity', '')}" for m in materials]
    return "\n".join(rows) or "(empty)"


def parse_reply(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        data = json.loads(text)
    except ValueError:
        raise AIError("The AI's answer couldn't be read.") from None
    if not isinstance(data, dict):
        raise AIError("The AI's answer couldn't be read.")
    return data


def build_flags(reply: dict, materials: list[dict]) -> list[dict]:
    """Turn the AI's findings into review flags (nothing is applied automatically)."""
    flags: list[dict] = []
    have = {str(m.get("tag_id", "")).upper() for m in materials}
    missing = []
    for i, it in enumerate(reply.get("missing") or []):
        if not isinstance(it, dict) or not (it.get("description") or it.get("tag")):
            continue
        tag = str(it.get("tag") or "").strip().upper()
        if tag and tag in have:
            continue
        page = it.get("page") if isinstance(it.get("page"), int) else None
        qty = it.get("quantity")
        missing.append({
            "tag": tag or f"AI-{i + 1}", "description": str(it.get("description") or tag)[:80],
            "type": "ai_suggested", "quantity": qty if isinstance(qty, (int, float)) and qty > 0 else 1,
            "location": f"p{page}" if page else "", "pages": [page] if page else [],
            "locations": [], "reason": str(it.get("reason") or "")[:200]})
    if missing:
        flags.append({"type": "ai_missing_items", "severity": "review", "items": missing,
                      "message": f"AI review suggests {len(missing)} item(s) the scope needs that are not on the BOM."})

    by_tag = {str(m.get("tag_id", "")).upper(): m for m in materials if m.get("tag_id", "-") != "-"}
    extras = []
    for it in reply.get("not_needed") or []:
        tag = str((it or {}).get("tag") or "").strip().upper() if isinstance(it, dict) else ""
        m = by_tag.get(tag)
        if m:
            extras.append({"tag": tag, "description": m.get("description", ""), "type": m.get("type", ""),
                           "quantity": m.get("quantity", 1), "location": m.get("location", ""),
                           "pages": [], "locations": m.get("locations", []),
                           "reason": str(it.get("reason") or "")[:200]})
    if extras:
        flags.append({"type": "ai_not_needed", "severity": "review", "items": extras,
                      "message": f"AI review suggests {len(extras)} BOM item(s) the scope does not need."})
    return flags


def review_with_ai(pid_path: str, scope_text: str, materials: list[dict],
                   provider: Provider | None = None) -> dict:
    """Returns {"flags": [...], "summary": str, "key_page": int|None, "provider": str, "model": str}."""
    provider = provider or get_provider()
    images = render_pages(pid_path)
    if not images:
        raise AIError("The drawing has no pages to review.")
    prompt = PROMPT.format(scope=scope_text[:12000], bom=_bom_text(materials))
    reply = parse_reply(provider.generate(prompt, images))
    key_page = reply.get("key_page")
    return {"flags": build_flags(reply, materials), "summary": str(reply.get("summary") or "")[:400],
            "key_page": key_page if isinstance(key_page, int) else None,
            "provider": provider.name, "model": provider.model}
