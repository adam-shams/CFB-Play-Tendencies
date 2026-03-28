"""
MCP-ready function for generating plain-English scouting summaries.
Supports Groq API (cloud, free tier) and Ollama (local) backends.
"""

import os

import requests as http_requests


# MCP-READY
def generate_scouting_summary(
    analysis: dict,
    backend: str = "groq",
    api_key: str | None = None,
    model: str | None = None,
    ollama_host: str = "http://localhost:11434",
) -> str:
    """Generates a 3-4 sentence scouting summary using an LLM.

    Supports two backends:
      - 'groq': Groq cloud API (free tier, uses open-source models like Llama 3).
                Requires a Groq API key via api_key param or GROQ_API_KEY env var.
      - 'ollama': Local Ollama instance. Requires Ollama running at ollama_host.

    Args:
        analysis: Dict with shape:
            {
                "team": str,
                "seasons": list[int],
                "sample_size": int,
                "run_pass_split": {
                    "run_pct": float, "pass_pct": float,
                    "avg_yards_run": float, "avg_yards_pass": float
                },
                "top_tendencies": list[dict],
                "field_zone_tendencies": list[dict],
            }
        backend: 'groq' or 'ollama'. Default 'groq'.
        api_key: API key for Groq. Falls back to GROQ_API_KEY env var / Streamlit secrets.
        model: Model name override. Defaults to 'llama-3.1-8b-instant' (Groq) or 'llama3.2' (Ollama).
        ollama_host: URL of the Ollama server. Default 'http://localhost:11434'.

    Returns:
        A 3-4 sentence scouting summary string.
        On error, returns a string starting with 'Error: '.
    """
    prompt = _build_prompt(analysis)
    system_msg = (
        "You are an expert college football analyst. "
        "Write concise, insightful scouting reports based on play-call data. "
        "Be specific about tendencies, avoid filler phrases, and focus on "
        "actionable observations a defensive coordinator would care about."
    )

    if backend == "ollama":
        return _call_ollama(system_msg, prompt, ollama_host, model or "llama3.2")
    else:
        return _call_groq(system_msg, prompt, api_key, model or "llama-3.1-8b-instant")


def _call_groq(system_msg: str, prompt: str, api_key: str | None, model: str) -> str:
    """Calls the Groq API via direct HTTP (no SDK dependency)."""
    key = api_key or os.environ.get("GROQ_API_KEY", "")
    if not key:
        # Try Streamlit secrets
        try:
            import streamlit as st
            key = st.secrets["GROQ_API_KEY"]
        except Exception:
            pass
    if not key:
        return "Error: No Groq API key. Set GROQ_API_KEY in secrets or environment."

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 400,
    }
    try:
        resp = http_requests.post(url, headers=headers, json=payload, timeout=30)
    except http_requests.Timeout:
        return "Error: Groq API request timed out."
    except http_requests.ConnectionError:
        return "Error: Cannot connect to Groq API."

    if not resp.ok:
        return f"Error: Groq API returned {resp.status_code} — {resp.text[:200]}"

    try:
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, ValueError):
        return "Error: Unexpected response format from Groq API."


def _call_ollama(system_msg: str, prompt: str, host: str, model: str) -> str:
    """Calls a local Ollama instance via HTTP."""
    url = f"{host.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    try:
        resp = http_requests.post(url, json=payload, timeout=60)
    except http_requests.Timeout:
        return "Error: Ollama request timed out."
    except http_requests.ConnectionError:
        return f"Error: Cannot connect to Ollama at {host}. Is `ollama serve` running?"

    if not resp.ok:
        return f"Error: Ollama returned {resp.status_code} — {resp.text[:200]}"

    try:
        data = resp.json()
        return data["message"]["content"].strip()
    except (KeyError, ValueError):
        return "Error: Unexpected response format from Ollama."


def _build_prompt(analysis: dict) -> str:
    """Formats an analysis dict into a structured prompt string."""
    team = analysis.get("team", "Unknown")
    seasons = analysis.get("seasons", [])
    sample = analysis.get("sample_size", 0)
    rps = analysis.get("run_pass_split", {})
    top_tend = analysis.get("top_tendencies", [])[:5]
    zones = analysis.get("field_zone_tendencies", [])

    season_str = ", ".join(str(s) for s in seasons)

    lines = [
        f"Team: {team} | Seasons: {season_str} | Sample: {sample} plays",
        "",
        "OVERALL RUN/PASS SPLIT:",
        f"  Run: {rps.get('run_pct', 0)}%  |  Pass: {rps.get('pass_pct', 0)}%",
        f"  Avg yards/run: {rps.get('avg_yards_run', 0)}  |  Avg yards/pass: {rps.get('avg_yards_pass', 0)}",
        "",
        "FIELD ZONE TENDENCIES:",
    ]
    for z in zones:
        if z.get("total", 0) > 0:
            lines.append(
                f"  {z['zone']}: {z['run_pct']}% run / {z['pass_pct']}% pass (n={z['total']})"
            )

    lines += ["", "TOP SITUATIONAL TENDENCIES:"]
    for t in top_tend:
        lines.append(
            f"  Down {t['down']}, {t['distance_bucket']}, {t['field_zone']}: "
            f"{t['play_type']} ({t['count']} times, {t['avg_yards']} avg yds)"
        )

    lines += [
        "",
        "Write a 3-4 sentence scouting report summarizing this team's play-calling tendencies. "
        "Highlight the most notable patterns, any situational tendencies, "
        "and one defensive suggestion based on the data.",
    ]

    return "\n".join(lines)
