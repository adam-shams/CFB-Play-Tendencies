"""
CFB Play-Call Tendency Analyzer — Streamlit UI.
All logic lives in mcp_tools/; this file is display-only.
"""

import sys
import os

# Ensure project root is on sys.path when running from any directory
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from mcp_tools.fetch_plays import get_plays, get_p5_teams, clear_cache
from mcp_tools.filter_plays import filter_plays
from mcp_tools.analyze_plays import (
    get_run_pass_split,
    get_play_type_breakdown,
    get_field_zone_tendencies,
    get_top_tendencies,
)
from mcp_tools.summarize import generate_scouting_summary
from utils.constants import SEASONS, SCORE_BUCKETS
from utils.helpers import plays_to_dataframe

st.set_page_config(
    page_title="CFB Tendency Analyzer",
    page_icon="🏈",
    layout="wide",
)


# ── Session state defaults ────────────────────────────────────────────────────

def _init_state() -> None:
    defaults = {
        "p5_teams": None,
        "raw_plays": None,
        "filtered_plays": None,
        "analysis": None,
        "summary": None,
        "last_team": None,
        "last_seasons": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar():
    """Renders sidebar controls and returns user selections."""
    st.sidebar.title("🏈 CFB Tendency Analyzer")

    # CFBD API token — auto-fill from Streamlit secrets if available
    default_cfb_token = st.secrets.get("CFB_API_TOKEN", "") if hasattr(st, "secrets") else ""
    api_token = st.sidebar.text_input(
        "CFBD API Token",
        value=default_cfb_token,
        type="password",
        help="Free token from collegefootballdata.com/key",
    )

    # Load P5 teams on first valid token entry
    if api_token and st.session_state.p5_teams is None:
        with st.spinner("Loading teams..."):
            teams_result = get_p5_teams(api_token)
        if teams_result and "error" in teams_result[0]:
            st.sidebar.error(teams_result[0]["error"])
        else:
            st.session_state.p5_teams = teams_result

    team_names = (
        [t["school"] for t in st.session_state.p5_teams]
        if st.session_state.p5_teams
        else []
    )

    st.sidebar.divider()
    st.sidebar.subheader("Team & Season")

    selected_team = st.sidebar.selectbox(
        "Team",
        options=team_names if team_names else ["— enter API token first —"],
        disabled=not team_names,
    )

    selected_seasons = st.sidebar.multiselect(
        "Seasons",
        options=SEASONS,
        default=SEASONS,
        format_func=str,
    )

    st.sidebar.divider()
    st.sidebar.subheader("Situational Filters")

    down_option = st.sidebar.selectbox(
        "Down",
        options=["All", 1, 2, 3, 4],
        format_func=lambda x: f"Down {x}" if x != "All" else "All Downs",
    )
    selected_down = None if down_option == "All" else int(down_option)

    col1, col2 = st.sidebar.columns(2)
    dist_min = col1.number_input("Dist min", min_value=1, max_value=30, value=1)
    dist_max = col2.number_input("Dist max", min_value=1, max_value=30, value=30)

    col3, col4 = st.sidebar.columns(2)
    ytg_min = col3.number_input("YTG min", min_value=0, max_value=99, value=0, help="Yards to Goal")
    ytg_max = col4.number_input("YTG max", min_value=0, max_value=99, value=99, help="Yards to Goal")

    score_options = ["All Situations"] + list(SCORE_BUCKETS.keys())
    score_bucket_label = st.sidebar.selectbox("Score Situation", options=score_options)
    selected_score_bucket = None if score_bucket_label == "All Situations" else score_bucket_label

    quarter_options = st.sidebar.multiselect(
        "Quarters",
        options=[1, 2, 3, 4],
        default=[1, 2, 3, 4],
        format_func=lambda x: f"Q{x}",
    )
    selected_quarters = quarter_options if len(quarter_options) < 4 else None

    st.sidebar.divider()
    analyze_clicked = st.sidebar.button("🔍 Analyze", use_container_width=True, type="primary")

    # LLM settings (collapsed by default)
    with st.sidebar.expander("⚙️ AI Summary Settings"):
        llm_backend = st.selectbox("Backend", options=["Groq (cloud, free)", "Ollama (local)"])
        llm_backend_key = "groq" if "Groq" in llm_backend else "ollama"
        if llm_backend_key == "groq":
            default_groq_key = st.secrets.get("GROQ_API_KEY", "") if hasattr(st, "secrets") else ""
            groq_key = st.text_input("Groq API Key", value=default_groq_key, type="password", help="Free key from console.groq.com")
            llm_model = st.text_input("Model", value="llama-3.1-8b-instant")
            ollama_host = ""
        else:
            groq_key = ""
            ollama_host = st.text_input("Ollama URL", value="http://localhost:11434")
            llm_model = st.text_input("Model", value="llama3.2")

    # Cache management
    with st.sidebar.expander("🗑️ Cache"):
        if st.button("Clear cache for selected team/seasons"):
            if selected_team and selected_seasons and team_names:
                for yr in selected_seasons:
                    result = clear_cache(selected_team, yr)
                    if result["deleted"]:
                        st.success(f"Cleared {yr}")
                st.session_state.raw_plays = None
                st.session_state.analysis = None
                st.session_state.summary = None

    return (
        api_token,
        selected_team,
        selected_seasons,
        selected_down,
        int(dist_min),
        int(dist_max),
        int(ytg_min),
        int(ytg_max),
        selected_score_bucket,
        selected_quarters,
        analyze_clicked,
        llm_backend_key,
        groq_key,
        ollama_host,
        llm_model,
        bool(team_names),
    )


# ── Main panel ────────────────────────────────────────────────────────────────

def render_results(
    team: str,
    seasons: list[int],
    filtered: list[dict],
    rps: dict,
    breakdown: list[dict],
    zones: list[dict],
    top_tend: list[dict],
) -> None:
    """Renders analysis results to the main panel."""

    season_str = " · ".join(str(s) for s in seasons)
    st.title(f"📊 {team}  —  {season_str}")

    n = rps.get("sample_size", 0)
    if n == 0:
        st.warning("No plays match the current filters. Adjust your selections and try again.")
        return

    # ── Run/Pass metrics ──────────────────────────────────────────────────────
    st.subheader("Run / Pass Split")
    if n < 20:
        st.warning(f"⚠️ Small sample warning: only {n} plays match these filters.")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Sample Size", n)
    c2.metric("Run %", f"{rps['run_pct']}%", f"{rps['run_count']} plays")
    c3.metric("Pass %", f"{rps['pass_pct']}%", f"{rps['pass_count']} plays")
    c4.metric("Avg Yds / Run", rps["avg_yards_run"])
    c5.metric("Avg Yds / Pass", rps["avg_yards_pass"])

    st.divider()

    # ── Play type bar chart ───────────────────────────────────────────────────
    st.subheader("Play Type Breakdown")
    if breakdown:
        df_bt = pd.DataFrame(breakdown)
        # Show top 15 by count to keep chart readable
        df_bt = df_bt.head(15)
        fig_bt = px.bar(
            df_bt,
            x="count",
            y="play_type",
            orientation="h",
            color="pct",
            color_continuous_scale="Blues",
            text="pct",
            labels={"count": "Count", "play_type": "Play Type", "pct": "% of plays"},
            title="Play Type Frequency",
        )
        fig_bt.update_traces(texttemplate="%{text}%", textposition="outside")
        fig_bt.update_layout(yaxis={"categoryorder": "total ascending"}, coloraxis_showscale=False)
        st.plotly_chart(fig_bt, use_container_width=True)

    st.divider()

    # ── Field zone chart ──────────────────────────────────────────────────────
    st.subheader("Field Zone Tendencies")
    if zones:
        df_zones = pd.DataFrame(zones)
        df_zones = df_zones[df_zones["total"] > 0]
        if not df_zones.empty:
            fig_z = go.Figure()
            fig_z.add_trace(
                go.Bar(
                    name="Run %",
                    y=df_zones["zone"],
                    x=df_zones["run_pct"],
                    orientation="h",
                    marker_color="#2166ac",
                    text=df_zones["run_pct"].apply(lambda v: f"{v}%"),
                    textposition="inside",
                )
            )
            fig_z.add_trace(
                go.Bar(
                    name="Pass %",
                    y=df_zones["zone"],
                    x=df_zones["pass_pct"],
                    orientation="h",
                    marker_color="#d6604d",
                    text=df_zones["pass_pct"].apply(lambda v: f"{v}%"),
                    textposition="inside",
                )
            )
            fig_z.update_layout(
                barmode="group",
                title="Run vs Pass % by Field Zone",
                xaxis_title="Percentage",
                yaxis_title="",
                legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
            )
            st.plotly_chart(fig_z, use_container_width=True)

    st.divider()

    # ── Top tendencies table ──────────────────────────────────────────────────
    st.subheader("Top Situational Tendencies")
    if top_tend:
        df_tend = pd.DataFrame(top_tend)
        df_tend.rename(
            columns={
                "down": "Down",
                "distance_bucket": "Distance",
                "field_zone": "Field Zone",
                "play_type": "Play Type",
                "count": "Count",
                "pct": "% of Plays",
                "avg_yards": "Avg Yards",
            },
            inplace=True,
        )
        st.dataframe(df_tend, use_container_width=True, hide_index=True)

    st.divider()

    # ── Download CSV ──────────────────────────────────────────────────────────
    df_dl = plays_to_dataframe(filtered)
    if not df_dl.empty:
        csv = df_dl.to_csv(index=False)
        st.download_button(
            label="⬇️ Download Filtered Plays as CSV",
            data=csv,
            file_name=f"{team.replace(' ', '_')}_{season_str.replace(' · ', '_')}_plays.csv",
            mime="text/csv",
        )


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    _init_state()

    (
        api_token,
        team,
        seasons,
        down,
        dist_min,
        dist_max,
        ytg_min,
        ytg_max,
        score_bucket,
        quarters,
        analyze_clicked,
        llm_backend,
        groq_key,
        ollama_host,
        llm_model,
        teams_loaded,
    ) = render_sidebar()

    # Landing state
    if not api_token:
        st.info("Enter your CFBD API token in the sidebar to get started.")
        st.markdown(
            "Get a free token at [collegefootballdata.com/key](https://collegefootballdata.com/key)."
        )
        return

    if not teams_loaded:
        return

    if not seasons:
        st.warning("Select at least one season.")
        return

    # Fetch plays when Analyze is clicked
    if analyze_clicked:
        st.session_state.summary = None  # reset summary on new fetch
        with st.spinner(f"Fetching plays for {team} ({', '.join(str(s) for s in seasons)})..."):
            plays = get_plays(team, seasons, api_token)

        if plays and "error" in plays[0]:
            st.error(plays[0]["error"])
            return

        st.session_state.raw_plays = plays
        st.session_state.last_team = team
        st.session_state.last_seasons = seasons

    # Work with cached raw plays
    raw = st.session_state.raw_plays
    if raw is None:
        st.info("Select a team and seasons, then click **Analyze**.")
        return

    # Apply filters
    filtered = filter_plays(
        raw,
        down=down,
        distance_min=dist_min,
        distance_max=dist_max,
        yard_line_min=ytg_min,
        yard_line_max=ytg_max,
        score_bucket=score_bucket,
        quarters=quarters,
    )

    # Compute analysis
    rps = get_run_pass_split(filtered)
    breakdown = get_play_type_breakdown(filtered)
    zones = get_field_zone_tendencies(filtered)
    top_tend = get_top_tendencies(filtered, top_n=10)

    display_team = st.session_state.last_team or team
    display_seasons = st.session_state.last_seasons or seasons

    render_results(display_team, display_seasons, filtered, rps, breakdown, zones, top_tend)

    # Scouting summary section
    st.divider()
    st.subheader("🤖 AI Scouting Summary")
    backend_label = f"Groq ({llm_model})" if llm_backend == "groq" else f"Ollama ({llm_model}) at {ollama_host}"
    st.caption(f"Powered by {backend_label}")

    if st.session_state.summary:
        st.info(st.session_state.summary)
    else:
        if st.button("Generate Scouting Summary", disabled=(rps.get("sample_size", 0) == 0)):
            analysis_input = {
                "team": display_team,
                "seasons": display_seasons,
                "sample_size": rps.get("sample_size", 0),
                "run_pass_split": rps,
                "top_tendencies": top_tend,
                "field_zone_tendencies": zones,
            }
            with st.spinner("Generating scouting summary..."):
                summary = generate_scouting_summary(
                    analysis_input,
                    backend=llm_backend,
                    api_key=groq_key,
                    model=llm_model,
                    ollama_host=ollama_host,
                )
            st.session_state.summary = summary
            if summary.startswith("Error:"):
                st.error(summary)
            else:
                st.info(summary)


if __name__ == "__main__":
    main()
