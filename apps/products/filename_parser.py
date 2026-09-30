"""Interpreta o nome das fotos do Google Drive.

Aceita dois padrões. 1) Hífens (o usado nas fotos da loja):

    jaqueta-bomber-capuz-removivel-p-m-g-gg-preto-cinza.claro-165.00.jpg

2) Vírgulas:

    Nome, Cor, Tamanhos, Preço[, Atacado 6+][, Caixa 24+].jpg

Exemplos:
    "Jaqueta Puffer Feminina, Preto/Vinho, P ao GG, 189.90.jpg"
    "Camiseta UV Manga Longa, Branco / Azul, P-M-G-GG, R$ 59,90, 49,90, 44,90.png"

- Várias cores: separe por "/" ou " e " (ex.: "Preto/Azul").
- Tamanhos: "P ao GG", "04 ao 16", "P/M/G" ou um tamanho único.
- Preços: aceita "59.90", "59,90" e "R$ 59,90".
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_PRICE_RE = re.compile(r"\d+(?:[.,]\d{1,2})?")
_EXT_RE = re.compile(r"\.(jpe?g|png|webp|gif|heic)$", re.IGNORECASE)


@dataclass
class ParsedProduct:
    name: str
    color: str = ""
    size_range: str = ""
    price: Decimal | None = None
    wholesale_price_6: Decimal | None = None
    wholesale_price_24: Decimal | None = None

    @property
    def is_valid(self) -> bool:
        return bool(self.name) and self.price is not None


def normalize(text: str) -> str:
    """Minúsculas e sem acentos (para comparar nomes de pastas)."""
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower().strip()


def detect_season(folder_name: str) -> str | None:
    """Retorna 'verao', 'inverno' ou None a partir do nome da pasta."""
    n = normalize(folder_name)
    if "inverno" in n or "frio" in n:
        return "inverno"
    if "verao" in n or "calor" in n:
        return "verao"
    return None


def _to_decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, AttributeError):
        return None


def _normalize_colors(raw: str) -> str:
    parts = re.split(r"\s*/\s*|\s+e\s+|\s*\|\s*", raw.strip())
    return ", ".join(p.strip() for p in parts if p.strip())


# ---------------------------------------------------------------------------
# Padrão com hífens (usado nas fotos da loja), ex.:
#   "jaqueta-bomber-faixa-refletiva-p-m-g-gg-preto-cinza.claro-165.00.jpg"
#   "camiseta-uv-infantil-azul-amarelo-tamanho-04-ao-16-30.00.jpg"
# Regras: o último número é o preço; o bloco de tamanhos é a última sequência de
# tamanhos (P, M, G, GG, G1..G5, 1..18, "p-ao-gg"); as cores ficam depois dos
# tamanhos (ou antes, quando os tamanhos estão no fim); o resto é o nome.
# ---------------------------------------------------------------------------
_LETTER_SIZES = ["PP", "P", "M", "G", "GG", "XG", "XGG", "G1", "G2", "G3", "G4", "G5", "EG", "EGG"]
_FILLERS = {"tamanho", "tamanhos", "tam", "somente", "so", "apenas", "na", "nas", "cor", "cores", "e"}
_RANGE_WORDS = {"ao", "a", "ate"}

_COLOR_WORDS = {
    "preto": "Preto", "preta": "Preto", "branco": "Branco", "branca": "Branco",
    "off": "Off White", "offwhite": "Off White", "cinza": "Cinza", "azul": "Azul",
    "marinho": "Marinho", "azulmarinho": "Azul Marinho", "azulbebe": "Azul Bebê",
    "azulroyal": "Azul Royal", "rosa": "Rosa", "rose": "Rosê", "vermelho": "Vermelho",
    "vermelha": "Vermelho", "vermelo": "Vermelho", "vinho": "Vinho", "verde": "Verde",
    "verdelimao": "Verde Limão", "amarelo": "Amarelo", "amarela": "Amarelo",
    "amarelinho": "Amarelinho", "bege": "Bege", "nude": "Nude", "marrom": "Marrom",
    "caramelo": "Caramelo", "mostarda": "Mostarda", "kaki": "Cáqui", "caqui": "Cáqui",
    "creme": "Creme", "prata": "Prata", "dourado": "Dourado", "roxo": "Roxo",
    "lilas": "Lilás", "laranja": "Laranja", "camuflada": "Camuflada",
    "camufrada": "Camuflada", "chumbo": "Chumbo", "grafite": "Grafite", "bordo": "Bordô",
    "claro": "Claro", "escuro": "Escuro", "bebe": "Bebê", "royal": "Royal",
}


def _is_size(tok: str) -> bool:
    t = tok.upper()
    if t in _LETTER_SIZES:
        return True
    return t.isdigit() and 1 <= int(t) <= 18


def _is_color(tok: str) -> bool:
    parts = [p for p in normalize(tok).split(".") if p]
    return bool(parts) and all(p in _COLOR_WORDS for p in parts)


def _format_color(tok: str) -> str:
    parts = [p for p in normalize(tok).split(".") if p]
    return " ".join(_COLOR_WORDS.get(p, p.capitalize()) for p in parts)


def _format_sizes(tokens: list[str]) -> str:
    toks = [t for t in tokens if t]
    low = [normalize(t) for t in toks]
    if any(t in _RANGE_WORDS for t in low):
        sizes = [t for t in toks if normalize(t) not in _RANGE_WORDS]
        if len(sizes) >= 2:
            first, last = sizes[0].upper(), sizes[-1].upper()
            if first.isdigit() and last.isdigit():
                first, last = f"{int(first):02d}", f"{int(last):02d}"
            return f"{first} ao {last}"
    out, seen = [], set()
    for t in toks:
        u = t.upper()
        if normalize(t) in _RANGE_WORDS or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return ", ".join(out)


def _colors_from(tokens: list[str]) -> str:
    out = []
    for t in tokens:
        if not t or normalize(t) in _FILLERS:
            continue
        c = _format_color(t) if _is_color(t) else t.replace(".", " ").strip().capitalize()
        if c and c not in out:
            out.append(c)
    return ", ".join(out)


def _format_name(tokens: list[str]) -> str:
    while tokens and normalize(tokens[-1]) in _FILLERS:
        tokens = tokens[:-1]
    name = " ".join(t for t in tokens if t).strip()
    return name[:1].upper() + name[1:]


def parse_hyphen_filename(base: str) -> ParsedProduct:
    tokens = [t.strip() for t in re.split(r"[-,_]+", base) if t.strip()]
    if not tokens:
        return ParsedProduct(name="")
    price = None
    if re.fullmatch(r"\d+(?:[.,]\d{1,2})?", tokens[-1]):
        price = _to_decimal(tokens[-1])
        tokens = tokens[:-1]

    # bloco de tamanhos: última sequência de tamanhos (aceita "ao" no meio)
    end = start = None
    i = len(tokens) - 1
    while i >= 0:
        if _is_size(tokens[i]):
            end = i
            start = i
            j = i - 1
            while j >= 0 and (_is_size(tokens[j]) or normalize(tokens[j]) in _RANGE_WORDS):
                if _is_size(tokens[j]):
                    start = j
                j -= 1
            # um número solto no meio do nome (ex.: "UV-50") não é bloco de tamanhos
            if start == end and tokens[end].isdigit():
                end = start = None
                i -= 1
                continue
            break
        i -= 1

    if start is None:
        # sem tamanhos: cores são a sequência final de cores conhecidas
        k = len(tokens)
        while k > 0 and (_is_color(tokens[k - 1]) or normalize(tokens[k - 1]) in _FILLERS):
            k -= 1
        return ParsedProduct(name=_format_name(tokens[:k]), color=_colors_from(tokens[k:]), price=price)

    sizes = _format_sizes(tokens[start:end + 1])
    after = tokens[end + 1:]
    before = tokens[:start]
    if [t for t in after if normalize(t) not in _FILLERS]:
        color = _colors_from(after)
        name_tokens = before
    else:
        # cores antes dos tamanhos (ex.: camiseta-uv-azul-branco-tamanho-p-ao-gg)
        k = len(before)
        while k > 0 and (_is_color(before[k - 1]) or normalize(before[k - 1]) in _FILLERS):
            k -= 1
        color = _colors_from(before[k:])
        name_tokens = before[:k]
    return ParsedProduct(name=_format_name(name_tokens), color=color, size_range=sizes, price=price)


def parse_filename(filename: str) -> ParsedProduct:
    """Aceita os dois padrões: vírgula + espaço ("Nome, Cor, Tamanhos, Preço")
    ou hífens ("nome-do-produto-p-m-g-gg-preto-azul-150.00")."""
    base = _EXT_RE.sub("", (filename or "").strip())
    if base.count(", ") >= 3:
        return _parse_comma_filename(base)
    return parse_hyphen_filename(base)


def _parse_comma_filename(base: str) -> ParsedProduct:
    tokens = [t.strip() for t in base.split(",")]
    name = tokens[0] if tokens else ""
    color = _normalize_colors(tokens[1]) if len(tokens) > 1 else ""
    sizes = tokens[2].strip() if len(tokens) > 2 else ""
    rest = ",".join(base.split(",")[3:])
    rest = re.sub(r"(\d),(\d{1,2})(?!\d)", r"\1.\2", rest)
    prices = [_to_decimal(m) for m in _PRICE_RE.findall(rest)]
    prices = [p for p in prices if p is not None]
    return ParsedProduct(
        name=name,
        color=color,
        size_range=sizes,
        price=prices[0] if prices else None,
        wholesale_price_6=prices[1] if len(prices) > 1 else None,
        wholesale_price_24=prices[2] if len(prices) > 2 else None,
    )
