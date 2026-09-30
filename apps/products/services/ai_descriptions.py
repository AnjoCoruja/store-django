"""Descrições automáticas de produtos com LangChain + Google Gemini.

O modelo recebe a foto do produto e os dados extraídos do nome do arquivo
(nome, cor, tamanhos, preço) e devolve uma descrição de vitrine em português.
"""
from __future__ import annotations

import base64
import logging

from django.conf import settings

logger = logging.getLogger("apps.products")

SYSTEM_PROMPT = (
    "Você é redator de e-commerce de moda da loja Red Blue Line (Brás, São Paulo), "
    "que vende no atacado e varejo. Escreva em português do Brasil."
)

USER_PROMPT = """Crie a descrição de vitrine deste produto a partir da foto e dos dados abaixo.

Produto: {name}
Linha: {season}
Categoria: {category}
Cores: {color}
Tamanhos: {sizes}

Regras:
- 2 a 4 frases, no máximo 450 caracteres.
- Descreva o que aparece na foto (modelagem, tecido aparente, detalhes, caimento).
- Destaque o benefício para a estação ({season}).
- Não invente preço, composição exata do tecido nem promoções.
- Responda só com o texto da descrição, sem título e sem markdown."""


class GeminiNotConfigured(RuntimeError):
    pass


def build_llm():
    api_key = settings.GEMINI_API_KEY
    if not api_key or "API AQUI" in api_key:
        raise GeminiNotConfigured("Configure GEMINI_API_KEY no .env.")
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL,
        google_api_key=api_key,
        temperature=0.6,
    )


class ProductDescriber:
    def __init__(self, llm=None):
        self.llm = llm or build_llm()

    def describe(self, *, image_bytes: bytes, mime_type: str, name: str, season: str,
                 category: str, color: str, sizes: str) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        b64 = base64.b64encode(image_bytes).decode()
        message = HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": USER_PROMPT.format(
                        name=name,
                        season="Verão / Calor" if season == "verao" else "Inverno / Frio",
                        category=category or "-",
                        color=color or "-",
                        sizes=sizes or "-",
                    ),
                },
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
            ]
        )
        result = self.llm.invoke([SystemMessage(content=SYSTEM_PROMPT), message])
        text = result.content
        if isinstance(text, list):  # alguns modelos devolvem blocos
            text = " ".join(
                b.get("text", "") if isinstance(b, dict) else str(b) for b in text
            )
        return str(text).strip()[:1000]
