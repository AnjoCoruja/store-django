"""Template filters to expand size ranges into selectable size lists."""
from django import template

register = template.Library()

_ORDER = ["PP", "P", "M", "G", "GG", "XG", "G1", "G2", "G3", "G4"]


@register.filter
def expand_sizes(size_range):
    """Expande um size_range (ex.: "P ao GG", "04 ao 16") numa lista de tamanhos."""
    if not size_range:
        return []
    s = str(size_range).strip()
    start = end = s
    for sep in (" ao ", " a ", "-", "–"):
        if sep in s:
            start, _, end = s.partition(sep)
            start, end = start.strip(), end.strip()
            break
    else:
        return [s]
    try:
        start_n, end_n = int(start), int(end)
        if start_n <= end_n and (end_n - start_n) <= 30:
            return [f"{n:02d}" for n in range(start_n, end_n + 1, 2)]
    except (ValueError, TypeError):
        pass
    def idx(x):
        try:
            return _ORDER.index(x.upper())
        except ValueError:
            return None
    i, j = idx(start), idx(end)
    if i is not None and j is not None and i <= j:
        return _ORDER[i:j + 1]
    return [start, end] if start != end else [start]
