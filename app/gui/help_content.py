"""User-facing setup and workflow guidance."""

PROVIDER_HELP = {
    "gemini": ("Google AI Studio", "https://aistudio.google.com/apikey", "https://ai.google.dev/gemini-api/docs/models"),
    "openai": ("OpenAI Platform API keys", "https://platform.openai.com/api-keys", "https://platform.openai.com/docs/models"),
    "anthropic": ("Anthropic Console API keys", "https://console.anthropic.com/settings/keys", "https://docs.anthropic.com/en/docs/about-claude/models/overview"),
    "xai": ("xAI Console API keys", "https://console.x.ai/", "https://docs.x.ai/docs/models"),
    "groq": ("Groq Console API keys", "https://console.groq.com/keys", "https://console.groq.com/docs/vision"),
    "mistral": ("Mistral AI Console API keys", "https://console.mistral.ai/api-keys/", "https://docs.mistral.ai/getting-started/models"),
    "openrouter": ("OpenRouter API keys", "https://openrouter.ai/settings/keys", "https://openrouter.ai/models"),
    "together": ("Together AI API keys", "https://api.together.ai/settings/api-keys", "https://api.together.ai/models"),
    "openai_compatible": ("your chosen service's developer console", "", ""),
}


def provider_guidance(name: str, provider_class: type) -> str:
    location, url, models_url = PROVIDER_HELP[name]
    key = f"API key: Create a key in {location}" + (f":\n{url}" if url else ".")
    default = provider_class.default_model
    model = (f"Model: Leave blank to use {default}, or enter a supported vision model ID."
             if default else
             "Model: Enter a vision-capable model ID from your provider's model catalog.")
    if models_url:
        model += f"\nModel catalog: {models_url}"
    endpoint = ("Base URL: Enter your provider's HTTPS API base URL, typically ending in /v1. "
                "It must support OpenAI-compatible chat completions with image input."
                if name == "openai_compatible" else
                "Base URL: Already configured for this provider; leave this field disabled.")
    billing = ("\nChatGPT subscriptions are separate from OpenAI API access and billing."
               if name == "openai" else "")
    return f"{key}\n\n{model}\n\n{endpoint}{billing}"


HELP_SECTIONS = {
    "Welcome": (
        "Welcome to Engineering App.\n\n"

        "Engineering App assists with reviewing P&IDs, generating BOMs, "
        "tracking jobs, reviewing drawing issues, drafting scopes of work, "
        "and managing project documentation.\n\n"

        "To begin:\n\n"

        "1. Open AI Settings and configure a preferred AI provider.\n"
        "2. Create a new job from the dashboard.\n"
        "3. Add a P&ID PDF and optional scope documentation.\n"
        "4. Run the scan and review the generated results.\n"
        "5. Verify all BOM entries, quantities, scope items and warnings before use.\n\n"

        "Engineering App is an engineering review tool. AI-generated content, "
        "scope recommendations and BOM information must always be reviewed and "
        "verified against the project drawings, specifications and site requirements.\n\n"

        "Use the Getting Started guide for detailed workflow instructions."
    ),
    "Getting started": (
        "1. Select Start a New Job, enter a job number and add a P&ID PDF. "
        "Add a scope file when one is available.\n\n"
        "2. Run the scan. If no scope is supplied, review and approve the proposed "
        "scope before it is saved; check each item against the drawing. Every "
        "scan requires AI review, and a missing scope is drafted into work phases "
        "with drawing-page/BOM references. AI-generated text is still a draft "
        "and must be checked and approved.\n\n"
        "3. Open the BOM review. Resolve questions and use Show on drawing to see "
        "the referenced page or highlighted location. Page-only issues open the "
        "whole page when precise coordinates are unavailable.\n\n"
        "Drag the review note by its heading to move it, or use Show / hide note. "
        "Drag the drawing itself to pan.\n\n"
        "Use Mark item location to select a drawing page and click the component. "
        "Save and re-export the BOM to retain the user-marked location. A printed BOM "
        "row or nearby scope reference is not automatically a component location.\n\n"
        "Example: a question about a flange may show its BOM row and matching scope "
        "wording. A terminology match alone does not confirm the item is in scope.\n\n"
        "Matching demo and new-work tag labels are comparison prompts, not proof "
        "of a replacement or exact component location. Printed BOM scans use the "
        "table as a master list and do not automatically compare those tags. "
        "Check each work area and verify connections, ancillary materials and "
        "quantities against the full drawings and specifications.\n\n"
        "Review quantities, descriptions, scope and all warnings before procurement."
    ),
    "AI setup": (
        "AI review is required for every scan. Before scanning, open AI settings "
        "and choose a primary provider. If that provider is not configured or fails, "
        "the bundled local Ollama fallback is used. Ollama starts automatically and "
        "downloads its vision model on first launch; allow several GB of disk space.\n\n"
        "Example: choose ChatGPT (OpenAI API), create an API key on the OpenAI "
        "Platform, paste it into API key, and leave the model blank to use the "
        "displayed default. A ChatGPT subscription is separate from API billing.\n\n"
        "For an OpenAI-compatible service, obtain its HTTPS API base URL and a "
        "model ID supporting image input from that service's documentation.\n\n"
        "Providers can charge for API use. Drawing pages, scope and BOM data are "
        "sent to the selected provider if it works; otherwise the local Ollama model "
        "is used. If no scope is supplied, "
        "extracted drawing text, BOM rows and a review index may also "
        "be sent to draft a phased scope with source references. AI suggestions are "
        "unverified and need review. Keys are stored in local settings, not encrypted."
    ),
    "Troubleshooting": (
        "BOM needs review: open View drawing issues or the BOM review and read each "
        "question. Rescan older jobs to collect drawing locations.\n\n"
        "Image-only sheets: OCR is local and can misread complex drawings. Check "
        "the extracted rows and revision notes against the original. Source-code "
        "installations require Tesseract with English data on PATH.\n\n"
        "AI error: check the API key, billing, model ID, image support and provider "
        "access. A web chat login is not necessarily an API key. Check the service's "
        "documentation if a model or endpoint changes.\n\n"
        "When a scan fails, save the offered debug report or use Open debug reports "
        "on the dashboard. New reports are saved in an error folder beside the jobs folder; "
        "older reports remain in its diagnostics subfolder. Reports include the job number, app version, failure stage "
        "and diagnostic codes, but not drawing contents, API keys or error messages. "
        "Review the report before sharing it.\n\n"
        "Missing or uncertain quantities remain blank or flagged for review; do not "
        "assume a quantity or that a matched material is in scope. If a cloud AI "
        "provider fails, the app uses local Ollama. Check the selected provider's "
        "API key, billing, model ID and image support if you want to use it instead. "
        "If Ollama returns an empty answer, the app retries and may take longer; "
        "a successful result still needs review."
    ),
}
