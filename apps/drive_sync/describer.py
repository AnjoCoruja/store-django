"""AI caption generator for synced products.

Uses any OpenAI-compatible chat-completions endpoint (AI_API_BASE / AI_API_KEY /
AI_MODEL). The photo is sent so the model can describe the piece. When AI is
not configured or fails, a deterministic template caption is used, so the
sync never blocks on the AI provider.
"""
import base64
import json
import logging
import urllib.request

from django.conf import settings

logger = logging.getLogger("apps.drive_sync")

PROMPT = (
    "Você é redator de uma loja de roupas online. Escreva uma legenda de venda "
    "em português do Brasil, com no máximo 400 caracteres, sem emojis e sem "
    "inventar dados técnicos. Destaque o visual da peça na foto. Dados: {data}"
)


def template_description(parsed, category_name):
    parts = [f"{parsed.name} da categoria {category_name}."]
    if parsed.color:
        parts.append(f"Cor: {parsed.color}.")
    if parsed.size_range:
        parts.append(f"Tamanhos: {parsed.size_range}.")
    if parsed.wholesale_price_6:
        parts.append(f"Atacado a partir de 6 peças: R$ {parsed.wholesale_price_6}.")
    if parsed.wholesale_price_24:
        parts.append(f"Caixa com 24+ peças: R$ {parsed.wholesale_price_24}.")
    return " ".join(parts)


def generate_description(parsed, category_name, image_bytes, mime_type):
    fallback = template_description(parsed, category_name)
    if not (settings.AI_API_KEY and settings.AI_MODEL):
        return fallback

    data = {
        "nome": parsed.name,
        "categoria": category_name,
        "cor": parsed.color,
        "tamanhos": parsed.size_range,
    }
    image_b64 = base64.b64encode(image_bytes).decode()
    body = {
        "model": settings.AI_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT.format(data=json.dumps(data, ensure_ascii=False))},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}},
                ],
            }
        ],
    }
    request = urllib.request.Request(
        settings.AI_API_BASE.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {settings.AI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
        text = payload["choices"][0]["message"]["content"].strip()
        return text or fallback
    except Exception as exc:  # network, quota, bad payload: never break the sync
        logger.warning("Falha ao gerar legenda com IA (%s); usando modelo padrão.", exc)
        return fallback
