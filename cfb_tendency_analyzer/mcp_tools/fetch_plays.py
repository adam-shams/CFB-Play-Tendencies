"""
MCP-ready functions for fetching CFB play data from the CFBD API with local caching.
"""

import json
import os
from datetime import datetime, timezone

import requests

from utils.constants import CACHE_DIR, CFBD_BASE_URL, P5_CONFERENCES
from utils.helpers import slugify, normalize_play


def _get_cache_path(team: str, year: int) -> str:
    """Returns the absolute path to the cache file for a given team+year.

    Args:
        team: Team name string.
        year: Season year as integer.

    Returns:
        Absolute path string to the JSON cache file.
    """
    slug = slugify(team)
    return os.path.join(CACHE_DIR, f"{slug}_{year}.json")


def _load_from_cache(cache_path: str) -> list[dict] | None:
    """Loads plays from cache file if it exists and is valid JSON.

    Args:
        cache_path: Absolute path to the cache file.

    Returns:
        List of play dicts if cache hit, None otherwise.
    """
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("plays", [])
    except (json.JSONDecodeError, KeyError):
        return None


def _save_to_cache(cache_path: str, team: str, year: int, plays: list[dict]) -> None:
    """Saves play list to a JSON cache file.

    Args:
        cache_path: Absolute path to the cache file.
        team: Team name string.
        year: Season year as integer.
        plays: List of play dicts to cache.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    payload = {
        "team": team,
        "year": year,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "play_count": len(plays),
        "plays": plays,
    }
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _fetch_week(
    team: str, year: int, week: int, season_type: str, api_token: str
) -> tuple[list[dict], str]:
    """Fetches plays for one team+year+week+seasonType from the CFBD API.

    Args:
        team: Team name string.
        year: Season year as integer.
        week: Week number (1-based).
        season_type: 'regular' or 'postseason'.
        api_token: Bearer token for the CFBD API.

    Returns:
        Tuple of (plays list, error string). On success error is ''.
    """
    url = f"{CFBD_BASE_URL}/plays"
    headers = {"Authorization": f"Bearer {api_token}"}
    params = {"team": team, "year": year, "week": week, "seasonType": season_type}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
    except requests.Timeout:
        return [], "Request timed out after 30s. Check network connection."
    except requests.ConnectionError:
        return [], "Cannot connect to CFBD API. Check network connection."

    if resp.status_code == 401:
        return [], "API authentication failed. Check your Bearer token."
    if resp.status_code == 429:
        return [], "Rate limit exceeded (1,000 calls/month). Use cached data."
    if resp.status_code >= 500:
        return [], f"CFBD API server error ({resp.status_code}). Try again later."
    if not resp.ok:
        # 400 with empty week is expected — just return empty
        return [], ""

    try:
        plays = resp.json()
    except ValueError:
        return [], "Unexpected API response format. Could not parse plays."

    if not isinstance(plays, list):
        return [], "Unexpected API response format. Could not parse plays."

    return plays, ""


def _fetch_season(
    team: str, year: int, season_type: str, api_token: str,
    max_weeks: int = 16,
) -> tuple[list[dict], str]:
    """Fetches all plays for a team+year+seasonType by iterating over weeks.

    The CFBD /plays endpoint requires a week parameter, so we iterate weeks
    1 through max_weeks and stop early after 3 consecutive empty responses.

    Args:
        team: Team name string.
        year: Season year as integer.
        season_type: 'regular' or 'postseason'.
        api_token: Bearer token for the CFBD API.
        max_weeks: Maximum weeks to iterate. Default 16 for regular, use 5 for postseason.

    Returns:
        Tuple of (plays list, error string). On success error is ''.
    """
    all_plays: list[dict] = []
    consecutive_empty = 0
    for week in range(1, max_weeks + 1):
        week_plays, err = _fetch_week(team, year, week, season_type, api_token)
        if err:
            # Auth or rate-limit errors are fatal
            if "authentication" in err.lower() or "rate limit" in err.lower():
                return [], err
            # Other errors (server, parse) — skip this week
            continue
        if week_plays:
            all_plays.extend(week_plays)
            consecutive_empty = 0
        else:
            consecutive_empty += 1
            if consecutive_empty >= 3:
                break  # no more weeks this season
    return all_plays, ""


# MCP-READY
def get_plays(team: str, seasons: list[int], api_token: str) -> list[dict]:
    """Fetches all plays for a team across one or more seasons.

    Checks the local cache first (cache/{slug}_{year}.json). On a cache miss,
    fetches regular season and postseason plays from the CFBD /plays endpoint,
    merges them by unique play id, saves to cache, and returns the result.

    Args:
        team: Offensive team name (must match CFBD team name exactly, e.g. 'Alabama').
        seasons: List of season years, e.g. [2022, 2023].
        api_token: Bearer token for the CFBD API.

    Returns:
        List of play dicts. Each play contains at minimum:
            id, play_type, yards_gained, down, distance, yards_to_goal,
            period, offense, defense, offense_score, defense_score.
        On error, returns [{"error": "<human-readable message>"}].
    """
    all_plays: list[dict] = []
    for year in seasons:
        cache_path = _get_cache_path(team, year)
        cached = _load_from_cache(cache_path)
        if cached is not None:
            all_plays.extend(cached)
            continue

        # Cache miss — fetch all weeks from API
        regular_plays, err = _fetch_season(team, year, "regular", api_token, max_weeks=16)
        if err:
            return [{"error": err}]

        post_plays, err = _fetch_season(team, year, "postseason", api_token, max_weeks=5)
        if err:
            return [{"error": err}]

        # Merge, deduplicate on play id, and normalize to snake_case
        seen: set = set()
        merged: list[dict] = []
        for play in regular_plays + post_plays:
            pid = play.get("id")
            if pid not in seen:
                seen.add(pid)
                merged.append(normalize_play(play))

        _save_to_cache(cache_path, team, year, merged)
        all_plays.extend(merged)

    return all_plays


# MCP-READY
def get_p5_teams(api_token: str) -> list[dict]:
    """Fetches all Power 5 teams from the CFBD /teams endpoint.

    Queries each P5 conference (ACC, B12, B1G, SEC, PAC) and merges results.

    Args:
        api_token: Bearer token for the CFBD API.

    Returns:
        List of dicts with shape {"school": str, "conference": str, "abbreviation": str}.
        On error, returns [{"error": "<human-readable message>"}].
    """
    url = f"{CFBD_BASE_URL}/teams"
    headers = {"Authorization": f"Bearer {api_token}"}
    teams: list[dict] = []
    seen_schools: set[str] = set()

    for conf in P5_CONFERENCES:
        params = {"conference": conf}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
        except requests.Timeout:
            return [{"error": "Request timed out fetching teams."}]
        except requests.ConnectionError:
            return [{"error": "Cannot connect to CFBD API."}]

        if resp.status_code == 401:
            return [{"error": "API authentication failed. Check your Bearer token."}]
        if not resp.ok:
            continue  # skip failed conferences, don't abort entirely

        try:
            conf_teams = resp.json()
        except ValueError:
            continue

        for t in conf_teams:
            school = t.get("school", "")
            if school and school not in seen_schools:
                seen_schools.add(school)
                teams.append(
                    {
                        "school": school,
                        "conference": t.get("conference", conf),
                        "abbreviation": t.get("abbreviation", ""),
                    }
                )

    teams.sort(key=lambda t: t["school"])
    return teams


# MCP-READY
def clear_cache(team: str, year: int) -> dict:
    """Deletes the local cache file for a given team+year.

    Args:
        team: Team name string.
        year: Season year as integer.

    Returns:
        {"deleted": bool, "path": str}
    """
    cache_path = _get_cache_path(team, year)
    if os.path.exists(cache_path):
        os.remove(cache_path)
        return {"deleted": True, "path": cache_path}
    return {"deleted": False, "path": cache_path}
