from .utils import safe_score

WEIGHTS = {
    "content": 0.20,
    "schema": 0.15,
    "eeat": 0.20,
    "technical": 0.15,
    "entity": 0.15,
    "ai_visibility": 0.15,
}


def compute_composite(
    content: float,
    schema: float,
    eeat: float,
    technical: float,
    entity: float = 0.0,
    ai_visibility: float = 0.0,
) -> float:
    composite = (
        content * WEIGHTS["content"]
        + schema * WEIGHTS["schema"]
        + eeat * WEIGHTS["eeat"]
        + technical * WEIGHTS["technical"]
        + entity * WEIGHTS["entity"]
        + ai_visibility * WEIGHTS["ai_visibility"]
    )
    return safe_score(composite)


def compute_static_composite(
    content: float,
    schema: float,
    eeat: float,
    technical: float,
) -> float:
    """Compute composite using only static pillars (for competitor scoring)."""
    total_weight = (
        WEIGHTS["content"] + WEIGHTS["schema"] + WEIGHTS["eeat"] + WEIGHTS["technical"]
    )
    composite = (
        content * WEIGHTS["content"]
        + schema * WEIGHTS["schema"]
        + eeat * WEIGHTS["eeat"]
        + technical * WEIGHTS["technical"]
    ) / total_weight * 100  # Normalize to 0-100 scale
    return safe_score(composite / 100 * 100)
