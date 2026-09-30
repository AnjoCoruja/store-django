"""Interpreta o nome das fotos do Google Drive.

Padrão esperado do nome do arquivo (separado por vírgulas):

    Nome, Cor, Tamanhos, Preço[, Atacado 6+][, Caixa 24+].jpg

Exemplos:
    "Jaqueta Puffer Feminina, Preto/Vinho, P ao GG, 189.90.jpg"
    "Camiseta UV Manga Longa, Branco / Azul, P-M-G-GG, R$ 59,90, 49,90, 44,90.png"

- Várias cores: separe por "/" ou " e " (ex.: "Preto/Azul").
- Tamanhos: "P ao GG", "04 ao 16", "P/M/G" ou um tamanho único.
- Preços: aceita "59.90", "59,90" e "R$ 59,90".
"""
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


def parse_filename(filename: str) -> ParsedProduct:
    base = _EXT_RE.sub("", (filename or "").strip())
    tokens = [t.strip() for t in base.split(",")]
    name = tokens[0] if tokens else ""
    color = _normalize_colors(tokens[1]) if len(tokens) > 1 else ""
    sizes = tokens[2].strip() if len(tokens) > 2 else ""
    rest = ",".join(tokens[3:]) if len(tokens) > 3 else ""
    # Remonta "59,90" que o split por vírgula quebrou: junta de volta sem espaço.
    rest = re.sub(r"(\d),(\d{1,2})(?!\d)", r"\1.\2", ",".join(base.split(",")[3:])) if rest else ""
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
