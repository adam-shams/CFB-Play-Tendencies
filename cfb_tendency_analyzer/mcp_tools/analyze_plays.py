"""
MCP-ready functions for aggregating and analyzing CFB play data.
All functions accept list[dict] and return plain dicts or list[dict].
"""

from collections import defaultdict

from utils.helpers import classify_play, get_field_zone, get_distance_bucket, safe_divide


# MCP-READY
def get_run_pass_split(plays: list[dict]) -> dict:
    """Computes the overall run/pass split for a list of plays.

    Args:
        plays: List of play dicts (post-filter).

    Returns:
        {
            "run_pct": float,       # 0.0–100.0
            "pass_pct": float,
            "other_pct": float,
            "sample_size": int,     # total plays (run + pass + other)
            "run_count": int,
            "pass_count": int,
            "other_count": int,
            "avg_yards_run": float,
            "avg_yards_pass": float,
        }
    """
    run_yards: list[float] = []
    pass_yards: list[float] = []
    other_count = 0

    for play in plays:
        pt = play.get("play_type", "")
        yg = float(play.get("yards_gained", 0) or 0)
        cat = classify_play(pt)
        if cat == "run":
            run_yards.append(yg)
        elif cat == "pass":
            pass_yards.append(yg)
        else:
            other_count += 1

    total = len(run_yards) + len(pass_yards) + other_count
    return {
        "run_pct": round(safe_divide(len(run_yards) * 100, total), 1),
        "pass_pct": round(safe_divide(len(pass_yards) * 100, total), 1),
        "other_pct": round(safe_divide(other_count * 100, total), 1),
        "sample_size": total,
        "run_count": len(run_yards),
        "pass_count": len(pass_yards),
        "other_count": other_count,
        "avg_yards_run": round(safe_divide(sum(run_yards), len(run_yards)), 1),
        "avg_yards_pass": round(safe_divide(sum(pass_yards), len(pass_yards)), 1),
    }


# MCP-READY
def get_play_type_breakdown(plays: list[dict]) -> list[dict]:
    """Returns frequency and average yards for each unique play type.

    Args:
        plays: List of play dicts (post-filter).

    Returns:
        List of dicts sorted by count descending:
        [{"play_type": str, "count": int, "pct": float, "avg_yards": float}, ...]
    """
    counts: dict[str, int] = defaultdict(int)
    yards_sum: dict[str, float] = defaultdict(float)

    for play in plays:
        pt = play.get("play_type", "Unknown")
        yg = float(play.get("yards_gained", 0) or 0)
        counts[pt] += 1
        yards_sum[pt] += yg

    total = sum(counts.values())
    result = []
    for pt, count in sorted(counts.items(), key=lambda x: -x[1]):
        result.append(
            {
                "play_type": pt,
                "count": count,
                "pct": round(safe_divide(count * 100, total), 1),
                "avg_yards": round(safe_divide(yards_sum[pt], count), 1),
            }
        )
    return result


# MCP-READY
def get_field_zone_tendencies(plays: list[dict]) -> list[dict]:
    """Returns run/pass split broken down by field zone.

    Field zones are derived from the yards_to_goal field.

    Args:
        plays: List of play dicts (post-filter).

    Returns:
        List of dicts in field zone order (own red zone → opponent red zone):
        [{"zone": str, "run_pct": float, "pass_pct": float,
          "run_count": int, "pass_count": int, "total": int}, ...]
    """
    from utils.constants import FIELD_ZONES

    zone_runs: dict[str, int] = defaultdict(int)
    zone_passes: dict[str, int] = defaultdict(int)
    zone_totals: dict[str, int] = defaultdict(int)

    for play in plays:
        ytg = play.get("yards_to_goal")
        if ytg is None:
            continue
        zone = get_field_zone(int(ytg))
        cat = classify_play(play.get("play_type", ""))
        if cat == "run":
            zone_runs[zone] += 1
        elif cat == "pass":
            zone_passes[zone] += 1
        zone_totals[zone] += 1 if cat in ("run", "pass") else 0

    result = []
    for zone in FIELD_ZONES:
        total = zone_totals[zone]
        result.append(
            {
                "zone": zone,
                "run_count": zone_runs[zone],
                "pass_count": zone_passes[zone],
                "total": total,
                "run_pct": round(safe_divide(zone_runs[zone] * 100, total), 1),
                "pass_pct": round(safe_divide(zone_passes[zone] * 100, total), 1),
            }
        )
    return result


# MCP-READY
def get_top_tendencies(plays: list[dict], top_n: int = 10) -> list[dict]:
    """Returns the most frequent situational play-call tendencies.

    A tendency is a unique combination of (down, distance_bucket, field_zone, play_type).

    Args:
        plays: List of play dicts (post-filter).
        top_n: Number of top tendencies to return. Default 10.

    Returns:
        List of dicts sorted by count descending (up to top_n entries):
        [{
            "down": int,
            "distance_bucket": str,
            "field_zone": str,
            "play_type": str,
            "count": int,
            "pct": float,
            "avg_yards": float,
        }, ...]
    """
    combo_counts: dict[tuple, int] = defaultdict(int)
    combo_yards: dict[tuple, float] = defaultdict(float)

    for play in plays:
        down = play.get("down")
        distance = play.get("distance")
        ytg = play.get("yards_to_goal")
        pt = play.get("play_type", "Unknown")
        yg = float(play.get("yards_gained", 0) or 0)

        if down is None or distance is None or ytg is None:
            continue

        key = (
            int(down),
            get_distance_bucket(int(distance)),
            get_field_zone(int(ytg)),
            pt,
        )
        combo_counts[key] += 1
        combo_yards[key] += yg

    total = sum(combo_counts.values())
    sorted_combos = sorted(combo_counts.items(), key=lambda x: -x[1])[:top_n]

    result = []
    for (down, dist_bucket, zone, pt), count in sorted_combos:
        result.append(
            {
                "down": down,
                "distance_bucket": dist_bucket,
                "field_zone": zone,
                "play_type": pt,
                "count": count,
                "pct": round(safe_divide(count * 100, total), 1),
                "avg_yards": round(safe_divide(combo_yards[(down, dist_bucket, zone, pt)], count), 1),
            }
        )
    return result
