import hashlib
import math
import re
from collections import Counter
from typing import Any


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
MAX_SPARSE_INDEX = 2**31 - 1


def sparse_text_values(text: str) -> dict[str, list[float] | list[int]]:
    tokens = [token.lower() for token in TOKEN_PATTERN.findall(text)]
    counts = Counter(tokens)
    if not counts:
        return {"indices": [], "values": []}

    weighted: dict[int, float] = {}
    for token, count in counts.items():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % MAX_SPARSE_INDEX
        weighted[index] = weighted.get(index, 0.0) + 1.0 + math.log(count)

    items = sorted(weighted.items())
    return {
        "indices": [index for index, _ in items],
        "values": [value for _, value in items],
    }


def scale_dense_vector(vector: list[float], alpha: float) -> list[float]:
    return [value * alpha for value in vector]


def scale_sparse_values(
    sparse_values: dict[str, Any],
    alpha: float,
) -> dict[str, list[float] | list[int]]:
    values = sparse_values.get("values") or []
    return {
        "indices": list(sparse_values.get("indices") or []),
        "values": [float(value) * (1.0 - alpha) for value in values],
    }
