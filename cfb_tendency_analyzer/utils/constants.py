"""Shared constants for the CFB Tendency Analyzer."""

import os

# /tmp/cfb_cache works on macOS, Linux, and Streamlit Cloud
CACHE_DIR = "/tmp/cfb_cache"

P5_CONFERENCES = ["ACC", "B12", "B1G", "SEC", "PAC"]

SEASONS = list(range(2021, 2026))  # 2021–2025

# Score differential buckets: offense_score - defense_score
# Values are inclusive (min, max)
SCORE_BUCKETS: dict[str, tuple[int, int]] = {
    "Blowout Loss (< -21)":        (-999, -22),
    "Large Deficit (-21 to -14)":  (-21,  -14),
    "Down 1-2 Scores (-13 to -7)": (-13,   -7),
    "Close Behind (-6 to -1)":     ( -6,   -1),
    "Tied (0)":                    (  0,    0),
    "Close Ahead (1 to 6)":        (  1,    6),
    "Up 1-2 Scores (7 to 13)":     (  7,   13),
    "Large Lead (14 to 21)":       ( 14,   21),
    "Blowout Lead (> 21)":         ( 22,  999),
}

# Field zone buckets based on yards_to_goal
# yards_to_goal: 99 = own 1-yard line, 1 = opponent 1-yard line
FIELD_ZONES: dict[str, tuple[int, int]] = {
    "Own Red Zone (backed up)": (76, 99),
    "Own Territory":            (51, 75),
    "Midfield":                 (40, 50),
    "Opponent Territory":       (21, 39),
    "Opponent Red Zone":        ( 0, 20),
}

# Distance-to-first-down buckets
DISTANCE_BUCKETS: dict[str, tuple[int, int]] = {
    "Short (1-3)":  (1,   3),
    "Medium (4-7)": (4,   7),
    "Long (8+)":    (8, 999),
}

# Play type classification sets (case-sensitive — match CFBD API strings)
RUN_PLAY_TYPES: set[str] = {
    "Rush",
    "Rushing Touchdown",
    "QB Sneak",
    "Quarterback Sneak",
    "Quarterback Keeper",
    "Keeper",
    "End Around",
    "Reverse",
    "Option Run",
    "Zone Read",
    "Scramble",
}

PASS_PLAY_TYPES: set[str] = {
    "Pass",
    "Pass Reception",
    "Pass Completion",
    "Passing Touchdown",
    "Pass Incompletion",
    "Incomplete Pass",
    "Pass Interception",
    "Pass Interception Return",
    "Interception",
    "Sack",
    "Pass Touchdown",
}

# CFBD API base URL
CFBD_BASE_URL = "https://api.collegefootballdata.com"
