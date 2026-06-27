from app.ai_governance.services.nlp.nlp_loader import get_sm

KNOWN_AI_TOOLS = [
    "chatgpt",
    "openai",
    "gpt-4",
    "gpt-3",
    "claude",
    "anthropic",
    "gemini",
    "bard",
    "copilot",
    "github copilot",
    "midjourney",
    "stable diffusion",
    "dall-e",
    "cohere",
    "llama",
    "mistral",
    "hugging face",
    "perplexity",
    "notion ai",
    "grammarly",
    "jasper",
    "character.ai",
    "replicate",
    "together ai",
    "groq",
]


def scan_text_for_shadow_ai(text: str) -> list[dict]:
    if not text or not text.strip():
        return []

    nlp = get_sm()
    doc = nlp(text.lower())
    detected: list[dict] = []
    seen: set[str] = set()
    for tool in KNOWN_AI_TOOLS:
        if tool in doc.text and tool not in seen:
            seen.add(tool)
            detected.append(
                {
                    "detected_name": tool,
                    "detection_method": "questionnaire",
                    "confidence": "medium",
                }
            )
    return detected
