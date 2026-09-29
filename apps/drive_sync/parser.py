"""Parse product data from a Google Drive file name.

Convention (the folder name is the category):

    Nome - Cor - Tamanhos - Preço [- Atacado 6+ [- Caixa 24+]].ext
    Camiseta UV - Azul - P ao G - 49,90 - 44,90 - 42,90.jpg
    Vestido_Azul_P-GG_89,90.jpg          (underscore also accepted)

Only the name is mandatory. Colors may be comma-separated ("Azul, Preto").
"""
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

_PRICE_RE = re.compile(r"^(?:R\$)?\s*(\d{1,7}(?:[.,]\d{1,2})?)$", re.IGNORECASE)
_PRICE_WITH_DECIMALS_RE = re.compile(r"^(?:R\$)?\s*\d{1,7}[.,]\d{1,2}$", re.IGNORECASE)
_WINTER_HINTS = ("inverno", "frio", "blue")


@dataclass
class ParsedName:
    name: str
    color: str = ""
    size_range: str = ""
    prices: list = field(default_factory=list)

    @property
    def price(self):
        return self.prices[0] if self.prices else None

    @property
    def wholesale_price_6(self):
        return self.prices[1] if len(self.prices) > 1 else None

    @property
    def wholesale_price_24(self):
        return self.prices[2] if len(self.prices) > 2 else None


def _to_decimal(token):
    match = _PRICE_RE.match(token.strip())
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(",", ".")).quantize(Decimal("0.01"))
    except InvalidOperation:  # pragma: no cover - regex already guarantees digits
        return None


def parse_filename(filename):
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    stem = stem.strip()
    separator = " - " if " - " in stem else "_"
    parts = [p.strip() for p in stem.split(separator) if p.strip()]
    if not parts:
        return ParsedName(name="Produto")

    name, rest = parts[0], parts[1:]
    texts, prices = [], []
    for position, token in enumerate(rest, start=1):
        # A token is a price when it has decimals ("49,90") or when it comes
        # after name/color/size (position >= 3). This keeps "38" as a size.
        is_price = bool(_PRICE_WITH_DECIMALS_RE.match(token)) or (
            position >= 3 and _to_decimal(token) is not None
        )
        if is_price and _to_decimal(token) is not None:
            prices.append(_to_decimal(token))
        elif not prices:
            texts.append(token)

    return ParsedName(
        name=name,
        color=texts[0] if texts else "",
        size_range=texts[1] if len(texts) > 1 else "",
        prices=prices,
    )


def detect_line(*texts):
    """Blue Line (inverno) when any text hints winter, else Red Line (verão)."""
    joined = " ".join(t.lower() for t in texts if t)
    return "inverno" if any(h in joined for h in _WINTER_HINTS) else "verao"
