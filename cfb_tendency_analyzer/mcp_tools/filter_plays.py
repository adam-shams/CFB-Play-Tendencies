"""
MCP-ready functions for filtering CFB play data by situational criteria.
"""

from utils.constants import SCORE_BUCKETS


def _score_diff(play: dict) -> int:
    """Returns offense_score - defense_score for a play dict."""
    return int(play.get("offense_score", 0)) - int(play.get("defense_score", 0))


# MCP-READY
def filter_plays(
    plays: list[dict],
    down: int | None = None,
    distance_min: int = 1,
    distance_max: int = 30,
    yard_line_min: int = 0,
    yard_line_max: int = 99,
    score_bucket: str | None = None,
    quarters: list[int] | None = None,
) -> list[dict]:
    """Applies situational filters to a list of play dicts.

    All filters are combined with AND logic. Any parameter set to its default
    value (None / full range) is treated as 'no filter applied'.

    Args:
        plays: Raw list of play dicts as returned by get_plays().
        down: Filter to a specific down (1-4). None = all downs.
        distance_min: Minimum yards to first down (inclusive). Default 1.
        distance_max: Maximum yards to first down (inclusive). Default 30.
        yard_line_min: Minimum yards_to_goal (inclusive). Default 0.
        yard_line_max: Maximum yards_to_goal (inclusive). Default 99.
        score_bucket: One of the SCORE_BUCKETS keys. None = all situations.
        quarters: List of period numbers to include (1-4). None = all quarters.

    Returns:
        Filtered list of play dicts. Empty list if no plays match.
    """
    result: list[dict] = []

    # Resolve score bucket range once
    score_range: tuple[int, int] | None = None
    if score_bucket and score_bucket in SCORE_BUCKETS:
        score_range = SCORE_BUCKETS[score_bucket]

    for play in plays:
        # Skip plays with error markers
        if "error" in play:
            continue

        # Down filter
        if down is not None:
            play_down = play.get("down")
            if play_down is None or int(play_down) != down:
                continue

        # Distance filter
        distance = play.get("distance")
        if distance is not None:
            d = int(distance)
            if not (distance_min <= d <= distance_max):
                continue

        # Yard line filter (yards_to_goal)
        ytg = play.get("yards_to_goal")
        if ytg is not None:
            y = int(ytg)
            if not (yard_line_min <= y <= yard_line_max):
                continue

        # Score bucket filter
        if score_range is not None:
            diff = _score_diff(play)
            low, high = score_range
            if not (low <= diff <= high):
                continue

        # Quarter / period filter
        if quarters is not None and len(quarters) > 0:
            period = play.get("period")
            if period is None or int(period) not in quarters:
                continue

        result.append(play)

    return result
