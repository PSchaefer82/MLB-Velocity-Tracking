# ==========================================
# MLB PITCHING ANALYTICS
# Streamlit Application
# ==========================================

import os
import sqlite3
from datetime import datetime, timedelta

import pandas as pd
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import streamlit as st

from pybaseball import (
    statcast_pitcher,
    playerid_lookup
)


# ==========================================
# PAGE CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="MLB Pitching Analytics",
    page_icon="⚾",
    layout="wide"
)

st.title("MLB Pitching Analytics")

st.caption(
    "Pitch-level Statcast analysis across seasons, "
    "games, and innings."
)

st.divider()


# ==========================================
# DATABASE CONFIGURATION
# ==========================================

DATA_DIR = "data"

os.makedirs(
    DATA_DIR,
    exist_ok=True
)

DB_PATH = os.path.join(
    DATA_DIR,
    "pitching_statcast.sqlite"
)

REFRESH_OVERLAP_DAYS = 3


# ==========================================
# DATABASE COLUMNS
# ==========================================

DATABASE_COLUMNS = [

    "pitcher_id",
    "game_pk",
    "game_date",
    "at_bat_number",
    "pitch_number",
    "pitch_type",
    "pitch_name",
    "release_speed",
    "release_spin_rate",
    "pfx_x",
    "pfx_z",
    "plate_x",
    "plate_z",
    "balls",
    "strikes",
    "description",
    "events",
    "inning",
    "inning_topbot",
    "batter",
    "stand",
    "home_team",
    "away_team",
    "release_extension",
    "effective_speed",
    "estimated_woba_using_speedangle"
]


# ==========================================
# INITIALIZE DATABASE
# ==========================================

def initialize_database():

    conn = sqlite3.connect(DB_PATH)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pitcher_data (
            pitcher_id INTEGER,
            game_pk INTEGER,
            game_date TEXT,
            at_bat_number INTEGER,
            pitch_number INTEGER,
            pitch_type TEXT,
            pitch_name TEXT,
            release_speed REAL,
            release_spin_rate REAL,
            pfx_x REAL,
            pfx_z REAL,
            plate_x REAL,
            plate_z REAL,
            balls INTEGER,
            strikes INTEGER,
            description TEXT,
            events TEXT,
            inning INTEGER,
            inning_topbot TEXT,
            batter INTEGER,
            stand TEXT,
            home_team TEXT,
            away_team TEXT,
            release_extension REAL,
            effective_speed REAL,
            estimated_woba_using_speedangle REAL
        )
    """)

    conn.commit()
    conn.close()


initialize_database()


# ==========================================
# PLAYER LOOKUP
# ==========================================

@st.cache_data(show_spinner=False)
def lookup_statcast_id(
    first_name,
    last_name
):

    lookup = playerid_lookup(
        last_name,
        first_name
    )

    if lookup.empty:

        raise ValueError(
            f"No MLB player found for "
            f"{first_name} {last_name}."
        )

    if "mlb_played_last" in lookup.columns:

        lookup = lookup.sort_values(
            "mlb_played_last",
            ascending=False
        )

    return int(
        lookup.iloc[0]["key_mlbam"]
    )


# ==========================================
# DATABASE HELPERS
# ==========================================

def get_latest_database_date(
    player_id,
    season
):

    conn = sqlite3.connect(DB_PATH)

    result = conn.execute(
        """
        SELECT MAX(game_date)
        FROM pitcher_data
        WHERE pitcher_id = ?
        AND game_date BETWEEN ? AND ?
        """,
        (
            player_id,
            f"{season}-01-01",
            f"{season}-12-31"
        )
    ).fetchone()[0]

    conn.close()

    return result


def save_statcast_data(
    df,
    player_id,
    start_date,
    end_date
):

    if df.empty:
        return

    df = df.copy()

    df["pitcher_id"] = player_id

    df["game_date"] = pd.to_datetime(
        df["game_date"]
    ).dt.strftime("%Y-%m-%d")

    available_columns = [
        column
        for column in DATABASE_COLUMNS
        if column in df.columns
    ]

    save_df = df[
        available_columns
    ].copy()

    conn = sqlite3.connect(DB_PATH)

    # Replace the overlap period rather
    # than blindly appending duplicate pitches.
    conn.execute(
        """
        DELETE FROM pitcher_data
        WHERE pitcher_id = ?
        AND game_date BETWEEN ? AND ?
        """,
        (
            player_id,
            start_date,
            end_date
        )
    )

    save_df.to_sql(
        "pitcher_data",
        conn,
        if_exists="append",
        index=False
    )

    conn.commit()
    conn.close()


# ==========================================
# STATCAST UPDATE
# ==========================================

def update_pitcher_database(
    player_id,
    season,
    force_refresh=False
):

    season_start = f"{season}-03-01"

    # Don't request future dates for an
    # earlier season.
    current_year = datetime.now().year

    if season < current_year:

        end_date = f"{season}-11-15"

    else:

        end_date = (
            datetime.now()
            .strftime("%Y-%m-%d")
        )

    latest_date = get_latest_database_date(
        player_id,
        season
    )

    if (
        force_refresh
        or latest_date is None
    ):

        update_start = season_start

    else:

        latest_date = pd.to_datetime(
            latest_date
        )

        update_start = (
            latest_date
            - timedelta(
                days=REFRESH_OVERLAP_DAYS
            )
        ).strftime("%Y-%m-%d")

    with st.spinner(
        "Checking Baseball Savant "
        "for Statcast data..."
    ):

        new_data = statcast_pitcher(
            update_start,
            end_date,
            player_id
        )

    if not new_data.empty:

        save_statcast_data(
            new_data,
            player_id,
            update_start,
            end_date
        )

    return len(new_data)


# ==========================================
# LOAD DATABASE DATA
# ==========================================

def load_pitcher_data(
    player_id,
    season
):

    conn = sqlite3.connect(DB_PATH)

    df = pd.read_sql_query(
        """
        SELECT *
        FROM pitcher_data
        WHERE pitcher_id = ?
        AND game_date BETWEEN ? AND ?
        ORDER BY
            game_date,
            game_pk,
            at_bat_number,
            pitch_number
        """,
        conn,
        params=(
            player_id,
            f"{season}-01-01",
            f"{season}-12-31"
        )
    )

    conn.close()

    if not df.empty:

        df["game_date"] = pd.to_datetime(
            df["game_date"]
        )

    return df


# ==========================================
# SIDEBAR
# ==========================================

st.sidebar.title(
    "Analysis Controls"
)

st.sidebar.subheader(
    "Pitcher"
)

first_name = st.sidebar.text_input(
    "First Name",
    value=""
)

last_name = st.sidebar.text_input(
    "Last Name",
    value=""
)

season = st.sidebar.selectbox(
    "Season",
    options=[
        2026,
        2025,
        2024,
        2023,
        2022
    ]
)
st.sidebar.divider()

st.sidebar.subheader(
    "Analysis"
)
analysis_mode = st.sidebar.radio(
    "View",
    [
        "Season Trends",
        "Game Analysis"
    ]
)


# ==========================================
# LOAD BUTTON
# ==========================================

load_player = st.sidebar.button(
    "Load Pitcher",
    type="primary",
    use_container_width=True
)


# ==========================================
# SESSION STATE
# ==========================================

if "pitcher_df" not in st.session_state:

    st.session_state.pitcher_df = None

if "player_id" not in st.session_state:

    st.session_state.player_id = None

if "loaded_name" not in st.session_state:

    st.session_state.loaded_name = None

if "loaded_season" not in st.session_state:

    st.session_state.loaded_season = None


# ==========================================
# LOAD PLAYER DATA
# ==========================================

if load_player:

    try:

        player_id = lookup_statcast_id(
            first_name.strip(),
            last_name.strip()
        )

        update_pitcher_database(
            player_id,
            season
        )

        pitcher_df = load_pitcher_data(
            player_id,
            season
        )

        if pitcher_df.empty:

            st.warning(
                "No Statcast pitching data "
                "was found for this selection."
            )

        else:

            st.session_state.pitcher_df = (
                pitcher_df
            )

            st.session_state.player_id = (
                player_id
            )

            st.session_state.loaded_name = (
                f"{first_name.strip()} "
                f"{last_name.strip()}"
            )

            st.session_state.loaded_season = (
                season
            )

    except Exception as error:

        st.error(
            f"Unable to load pitcher: {error}"
        )


# ==========================================
# MAIN APPLICATION
# ==========================================

pitcher_df = (
    st.session_state.pitcher_df
)

if pitcher_df is None:

    st.info(
        "Select a pitcher and season, "
        "then choose **Load Pitcher**."
    )

    st.stop()


player_name = (
    st.session_state.loaded_name
)

loaded_season = (
    st.session_state.loaded_season
)


# ==========================================
# PLAYER HEADER
# ==========================================

st.header(player_name)

latest_data_date = (
    pitcher_df["game_date"]
    .max()
)

latest_data_display = (
    latest_data_date
    .strftime("%B %d, %Y")
)

st.caption(
    f"{loaded_season} Statcast data "
    f"• Data through {latest_data_display}"
)


# ==========================================
# PITCH TYPES
# ==========================================

pitch_options = (
    pitcher_df[
        ["pitch_type", "pitch_name"]
    ]
    .dropna()
    .drop_duplicates()
    .sort_values("pitch_name")
)

pitch_dictionary = dict(
    zip(
        pitch_options["pitch_name"],
        pitch_options["pitch_type"]
    )
)

pitch_name = st.sidebar.selectbox(
    "Pitch Type",
    options=list(
        pitch_dictionary.keys()
    )
)

pitch_type = (
    pitch_dictionary[pitch_name]
)


# ==========================================
# FILTER SELECTED PITCH
# ==========================================

selected_pitch_df = pitcher_df[
    pitcher_df["pitch_type"]
    == pitch_type
].copy()


# ==========================================
# SUMMARY METRICS
# ==========================================

metric1, metric2, metric3, metric4 = (
    st.columns(4)
)

metric1.metric(
    "Pitches",
    f"{len(selected_pitch_df):,}"
)

metric2.metric(
    "Average Velocity",
    (
        f"{selected_pitch_df['release_speed'].mean():.1f} mph"
    )
)

metric3.metric(
    "Maximum Velocity",
    (
        f"{selected_pitch_df['release_speed'].max():.1f} mph"
    )
)

metric4.metric(
    "Games",
    selected_pitch_df[
        "game_pk"
    ].nunique()
)

st.divider()


# ==========================================
# SEASON TRENDS
# ==========================================

if analysis_mode == "Season Trends":

    st.subheader(
        f"{pitch_name} — Average Velocity by Game"
    )

    st.caption(
        "Each point represents the average velocity "
        "of the selected pitch type in one game."
    )

    # --------------------------------------
    # CREATE GAME-BY-GAME SUMMARY
    # --------------------------------------

    season_summary = (
        selected_pitch_df
        .groupby(
            ["game_pk", "game_date"]
        )
        .agg(
            average_velocity=(
                "release_speed",
                "mean"
            ),
            maximum_velocity=(
                "release_speed",
                "max"
            ),
            pitches=(
                "release_speed",
                "count"
            )
        )
        .reset_index()
        .sort_values("game_date")
    )

    # --------------------------------------
    # CHECK FOR DATA
    # --------------------------------------

    if season_summary.empty:

        st.warning(
            "No data available for "
            "this pitch type."
        )

    else:

        # ----------------------------------
        # DATE DISPLAY FOR HOVER
        # ----------------------------------

        season_summary[
            "date_display"
        ] = (
            season_summary[
                "game_date"
            ]
            .dt.strftime("%b %d, %Y")
        )

        # ----------------------------------
        # BUILD INTERACTIVE CHART
        # ----------------------------------

        season_fig = go.Figure()

        season_fig.add_trace(

            go.Scatter(

                x=season_summary[
                    "game_date"
                ],

                y=season_summary[
                    "average_velocity"
                ],

                mode="lines+markers",

                name="Average Velocity",

                customdata=season_summary[
                    [
                        "date_display",
                        "maximum_velocity",
                        "pitches"
                    ]
                ],

                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Average: %{y:.1f} mph<br>"
                    "Maximum: %{customdata[1]:.1f} mph<br>"
                    "Pitches: %{customdata[2]:.0f}"
                    "<extra></extra>"
                ),

                marker=dict(
                    size=8
                ),

                line=dict(
                    width=2
                )
            )
        )

        # ----------------------------------
        # CHART LAYOUT
        # ----------------------------------

        season_fig.update_layout(

            xaxis_title="Game Date",

            yaxis_title="Average Velocity (mph)",

            hovermode="closest",

            height=500,

            margin=dict(
                l=20,
                r=20,
                t=20,
                b=20
            ),

            showlegend=False
        )

        # ----------------------------------
        # DISPLAY CHART
        # ----------------------------------

        st.plotly_chart(
            season_fig,
            use_container_width=True
        )

        # ----------------------------------
        # GAME DATA TABLE
        # ----------------------------------

        with st.expander(
            "View Game Data"
        ):

            display_season = (
                season_summary[
                    [
                        "game_date",
                        "average_velocity",
                        "maximum_velocity",
                        "pitches"
                    ]
                ]
                .copy()
            )

            display_season[
                "game_date"
            ] = (
                display_season[
                    "game_date"
                ]
                .dt.strftime("%b %d, %Y")
            )

            display_season = (
                display_season.rename(
                    columns={
                        "game_date":
                            "Game Date",
                        "average_velocity":
                            "Average Velocity",
                        "maximum_velocity":
                            "Maximum Velocity",
                        "pitches":
                            "Pitches"
                    }
                )
            )

            st.dataframe(
                display_season,
                use_container_width=True,
                hide_index=True
            )

# ==========================================
# GAME ANALYSIS
# ==========================================

elif analysis_mode == "Game Analysis":

    st.subheader("Individual Game Analysis")

    # --------------------------------------
    # BUILD GAME LIST
    # --------------------------------------

    games = (
        pitcher_df[
            [
                "game_pk",
                "game_date",
                "away_team",
                "home_team"
            ]
        ]
        .drop_duplicates()
        .sort_values(
            "game_date",
            ascending=False
        )
    )

    if games.empty:

        st.warning(
            "No games are available "
            "for this pitcher."
        )

        st.stop()

    # --------------------------------------
    # CREATE READABLE GAME LABELS
    # --------------------------------------

    games["game_label"] = (
        games["game_date"]
        .dt.strftime("%b %d, %Y")
        + " — "
        + games["away_team"]
        + " @ "
        + games["home_team"]
    )

    game_dictionary = dict(
        zip(
            games["game_label"],
            games["game_pk"]
        )
    )

    selected_game_label = st.selectbox(
        "Game",
        options=list(
            game_dictionary.keys()
        )
    )

    selected_game_pk = (
        game_dictionary[
            selected_game_label
        ]
    )

    # --------------------------------------
    # FILTER SELECTED GAME
    # --------------------------------------

    game_df = pitcher_df[
        pitcher_df["game_pk"]
        == selected_game_pk
    ].copy()
    
    # --------------------------------------
    # OVERALL PITCH NUMBER FOR GAME
    # --------------------------------------

    game_df = (
        game_df
        .sort_values(
            [
                "inning",
                "at_bat_number",
                "pitch_number"
            ]
        )
        .reset_index(drop=True)
    )

    game_df[
        "game_pitch_number"
    ] = range(
        1,
        len(game_df) + 1
    )
    
    # --------------------------------------
    # FILTER SELECTED PITCH TYPE
    # --------------------------------------

    game_pitch_df = game_df[
        game_df["pitch_type"]
        == pitch_type
    ].copy()

    # --------------------------------------
    # AVAILABLE INNINGS
    # --------------------------------------

    available_innings = sorted(
        game_pitch_df[
            "inning"
        ]
        .dropna()
        .astype(int)
        .unique()
        .tolist()
    )

    inning_options = (
        ["All Innings"]
        + available_innings
    )

    selected_inning = st.selectbox(
        "Inning",
        options=inning_options
    )

    # --------------------------------------
    # APPLY INNING FILTER
    # --------------------------------------

    if selected_inning != "All Innings":

        game_pitch_df = game_pitch_df[
            game_pitch_df["inning"]
            == selected_inning
        ].copy()

    # --------------------------------------
    # SORT PITCHES CHRONOLOGICALLY
    # --------------------------------------

    game_pitch_df = (
        game_pitch_df
        .sort_values(
            [
                "inning",
                "at_bat_number",
                "pitch_number"
            ]
        )
        .reset_index(drop=True)
    )

    # --------------------------------------
    # CHECK FOR DATA
    # --------------------------------------

    if game_pitch_df.empty:

        st.warning(
            f"No {pitch_name} pitches "
            f"were found for this selection."
        )

        st.stop()

    # --------------------------------------
    # CREATE PITCH SEQUENCE
    # --------------------------------------

    game_pitch_df[
        "pitch_sequence"
    ] = range(
        1,
        len(game_pitch_df) + 1
    )

    # --------------------------------------
    # ROLLING VELOCITY
    # --------------------------------------

    ROLLING_WINDOW = 5

    game_pitch_df[
        "rolling_velocity"
    ] = (
        game_pitch_df[
            "release_speed"
        ]
        .rolling(
            window=ROLLING_WINDOW,
            min_periods=1
        )
        .mean()
    )

    # --------------------------------------
    # VELOCITY VALUES
    # --------------------------------------

    velocities = (
        game_pitch_df[
            "release_speed"
        ]
        .dropna()
    )

    pitch_count = len(
        velocities
    )

    average_velocity = (
        velocities.mean()
    )

    maximum_velocity = (
        velocities.max()
    )

    latest_velocity = (
        velocities.iloc[-1]
    )

    first_10_average = (
        velocities
        .head(10)
        .mean()
    )

    last_10_average = (
        velocities
        .tail(10)
        .mean()
    )

    velocity_change = (
        last_10_average
        - first_10_average
    )

    # ======================================
    # GAME SUMMARY
    # ======================================

    st.markdown(
        f"### {selected_game_label}"
    )

    if selected_inning == "All Innings":

        inning_display = "All Innings"

    else:

        inning_display = (
            f"Inning {selected_inning}"
        )


    st.caption(
        f"{pitch_name} • "
        f"{inning_display}"
    )

    # --------------------------------------
    # TOP METRICS
    # --------------------------------------

    metric1, metric2, metric3, metric4 = (
        st.columns(4)
    )

    metric1.metric(
        "Pitches",
        pitch_count
    )

    metric2.metric(
        "Average Velocity",
        f"{average_velocity:.1f} mph"
    )

    metric3.metric(
        "Maximum Velocity",
        f"{maximum_velocity:.1f} mph"
    )

    metric4.metric(
        "Latest Velocity",
        f"{latest_velocity:.1f} mph"
    )

    # --------------------------------------
    # TREND METRICS
    # --------------------------------------

    trend1, trend2, trend3 = (
        st.columns(3)
    )

    trend1.metric(
        "First 10 Avg",
        f"{first_10_average:.1f} mph"
    )

    trend2.metric(
        "Last 10 Avg",
        f"{last_10_average:.1f} mph"
    )

    trend3.metric(
        "Velocity Change",
        f"{velocity_change:+.1f} mph",
        delta=f"{velocity_change:+.1f} mph"
    )

    st.divider()

        # ======================================
    # INTERACTIVE PITCH-BY-PITCH VELOCITY
    # ======================================

    st.subheader(
        "Pitch-by-Pitch Velocity"
    )

    # --------------------------------------
    # CREATE HOVER INFORMATION
    # --------------------------------------

    game_pitch_df[
        "count"
    ] = (
        game_pitch_df["balls"]
        .fillna(0)
        .astype(int)
        .astype(str)
        + "-"
        + game_pitch_df["strikes"]
        .fillna(0)
        .astype(int)
        .astype(str)
    )

    game_pitch_df[
        "spin_display"
    ] = (
        game_pitch_df[
            "release_spin_rate"
        ]
        .round(0)
        .fillna(0)
    )

    game_pitch_df[
    "result_display"
] = (
    game_pitch_df[
        "description"
    ]
    .fillna("Unknown")
    .str.replace(
        "_",
        " ",
        regex=False
    )
    .str.title()
)


    # --------------------------------------
    # BUILD PLOTLY FIGURE
    # --------------------------------------

    fig = go.Figure()


    # --------------------------------------
    # INDIVIDUAL PITCHES
    # --------------------------------------

    fig.add_trace(

        go.Scatter(

            x=game_pitch_df[
                "pitch_sequence"
            ],

            y=game_pitch_df[
                "release_speed"
            ],

            mode="markers",

            name="Individual Pitch",

            customdata=game_pitch_df[
                [
                    "game_pitch_number",
                    "inning",
                    "count",
                    "spin_display",
                    "result_display"
                ]
            ],

            hovertemplate=(
                "<b>Game Pitch #%{customdata[0]}</b><br>"
                f"{pitch_name} #%{{x}}<br>"
                "Velocity: %{y:.1f} mph<br>"
                "Inning: %{customdata[1]}<br>"
                "Count: %{customdata[2]}<br>"
                "Spin: %{customdata[3]:.0f} rpm<br>"
                "Result: %{customdata[4]}"
                "<extra></extra>"
            ),

            marker=dict(
                size=9
            )
        )
    )


    # --------------------------------------
    # ROLLING AVERAGE
    # --------------------------------------

    fig.add_trace(

        go.Scatter(

            x=game_pitch_df[
                "pitch_sequence"
            ],

            y=game_pitch_df[
                "rolling_velocity"
            ],

            mode="lines",

            name=(
                f"{ROLLING_WINDOW}-Pitch "
                "Rolling Average"
            ),

            hovertemplate=(
                "Pitch %{x}<br>"
                "Rolling Avg: %{y:.1f} mph"
                "<extra></extra>"
            ),

            line=dict(
                width=3
            )
        )
    )


    # --------------------------------------
    # CHART LAYOUT
    # --------------------------------------

    fig.update_layout(

        xaxis_title=(
            f"{pitch_name} Pitch Sequence"
        ),

        yaxis_title="Velocity (mph)",

        hovermode="closest",

        height=520,

        margin=dict(
            l=20,
            r=20,
            t=30,
            b=20
        ),

        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0
        )
    )


    fig.update_xaxes(
        dtick=1
    )


    st.plotly_chart(
        fig,
        use_container_width=True
    )

    # ======================================
    # INNING SUMMARY
    # ======================================

    st.subheader(
        "Velocity by Inning"
    )

    # Use the whole selected game for
    # inning summary rather than only
    # the currently selected inning.

    full_game_pitch_df = game_df[
        game_df["pitch_type"]
        == pitch_type
    ].copy()

    inning_summary = (
        full_game_pitch_df
        .groupby("inning")
        .agg(
            average_velocity=(
                "release_speed",
                "mean"
            ),
            maximum_velocity=(
                "release_speed",
                "max"
            ),
            minimum_velocity=(
                "release_speed",
                "min"
            ),
            pitches=(
                "release_speed",
                "count"
            )
        )
        .reset_index()
        .sort_values("inning")
    )

    if not inning_summary.empty:

        fig2, ax2 = plt.subplots(
            figsize=(10, 4)
        )

        ax2.plot(
            inning_summary["inning"],
            inning_summary[
                "average_velocity"
            ],
            marker="o"
        )

        ax2.set_xlabel(
            "Inning"
        )

        ax2.set_ylabel(
            "Average Velocity (mph)"
        )

        ax2.set_xticks(
            inning_summary[
                "inning"
            ]
        )

        ax2.grid(
            alpha=0.25
        )

        plt.tight_layout()

        st.pyplot(fig2)

    # ======================================
    # PITCH DATA TABLE
    # ======================================

    with st.expander(
        "View Pitch-by-Pitch Data"
    ):

        display_columns = [
            "pitch_sequence",
            "inning",
            "balls",
            "strikes",
            "pitch_name",
            "release_speed",
            "release_spin_rate",
            "result_display"
        ]

        available_display_columns = [
            column
            for column in display_columns
            if column in game_pitch_df.columns
        ]

        display_df = game_pitch_df[
            available_display_columns
        ].copy()

        display_df = display_df.rename(
            columns={
                "pitch_sequence":
                    "Pitch",
                "inning":
                    "Inning",
                "balls":
                    "Balls",
                "strikes":
                    "Strikes",
                "pitch_name":
                    "Pitch Type",
                "release_speed":
                    "Velocity",
                "release_spin_rate":
                    "Spin Rate",
                "result_display":
                    "Result"
            }
        )

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True
        )