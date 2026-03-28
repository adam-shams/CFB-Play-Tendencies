"""Shared utility functions for the CFB Tendency Analyzer."""

import re
import pandas as pd
from utils.constants import RUN_PLAY_TYPES, PASS_PLAY_TYPES, FIELD_ZONES, DISTANCE_BUCKETS


def classify_play(play_type: str) -> str:
    """Returns 'run', 'pass', or 'other' for a given CFBD play_type string.

    Args:
        play_type: The play_type string from the CFBD API response.

    Returns:
        'run', 'pass', or 'other'.
    """
    # Exact match first
    if play_type in RUN_PLAY_TYPES:
        return "run"
    if play_type in PASS_PLAY_TYPES:
        return "pass"
    # Case-insensitive fallback
    lower = play_type.lower()
    for rpt in RUN_PLAY_TYPES:
        if rpt.lower() == lower:
            return "run"
    for ppt in PASS_PLAY_TYPES:
        if ppt.lower() == lower:
            return "pass"
    return "other"


def get_field_zone(yards_to_goal: int) -> str:
    """Returns the field zone label for a given yards_to_goal value.

    Args:
        yards_to_goal: Yards remaining to the opponent's goal line (0-99).

    Returns:
        A zone label from FIELD_ZONES keys, or 'Midfield' as default.
    """
    for zone_label, (low, high) in FIELD_ZONES.items():
        if low <= yards_to_goal <= high:
            return zone_label
    return "Midfield"


def get_distance_bucket(distance: int) -> str:
    """Returns the distance bucket label for a given yards-to-first-down value.

    Args:
        distance: Yards needed for a first down.

    Returns:
        A bucket label from DISTANCE_BUCKETS keys, or 'Long (8+)' as default.
    """
    for bucket_label, (low, high) in DISTANCE_BUCKETS.items():
        if low <= distance <= high:
            return bucket_label
    return "Long (8+)"


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Returns numerator / denominator, or default if denominator is zero.

    Args:
        numerator: The dividend.
        denominator: The divisor.
        default: Value to return when denominator is zero.

    Returns:
        Division result or default.
    """
    if denominator == 0:
        return default
    return numerator / denominator


def plays_to_dataframe(plays: list[dict]) -> pd.DataFrame:
    """Converts a list of play dicts to a pandas DataFrame for CSV export.

    Args:
        plays: List of play dicts as returned by mcp_tools functions.

    Returns:
        A pandas DataFrame with one row per play.
    """
    if not plays:
        return pd.DataFrame()
    return pd.DataFrame(plays)


# Map from CFBD camelCase API keys to snake_case used internally.
_FIELD_MAP = {
    "playType": "play_type",
    "yardsGained": "yards_gained",
    "yardsToGoal": "yards_to_goal",
    "offenseScore": "offense_score",
    "defenseScore": "defense_score",
    "offenseConference": "offense_conference",
    "defenseConference": "defense_conference",
    "offenseTimeouts": "offense_timeouts",
    "defenseTimeouts": "defense_timeouts",
    "gameId": "game_id",
    "driveId": "drive_id",
    "driveNumber": "drive_number",
    "playNumber": "play_number",
    "playText": "play_text",
}


def normalize_play(play: dict) -> dict:
    """Converts a CFBD API play dict from camelCase to snake_case keys.

    Keys not in the mapping are kept as-is. The 'clock' nested dict is
    flattened to 'clock_minutes' and 'clock_seconds'.

    Args:
        play: Raw play dict from the CFBD API.

    Returns:
        A new dict with snake_case keys.
    """
    out: dict = {}
    for k, v in play.items():
        if k == "clock" and isinstance(v, dict):
            out["clock_minutes"] = v.get("minutes")
            out["clock_seconds"] = v.get("seconds")
        elif k in _FIELD_MAP:
            out[_FIELD_MAP[k]] = v
        else:
            out[k] = v
    return out


def slugify(text: str) -> str:
    """Converts a team name to a filesystem-safe slug.

    Args:
        text: Team name string.

    Returns:
        Lowercase alphanumeric slug with underscores.
    """
    slug = text.lower().replace(" ", "_")
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    return slug
