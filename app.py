import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import unicodedata

# =========================================================
# TENNIS IA v10.1
# MODELO CALIBRADO ATP REAL
# =========================================================

st.set_page_config(
    page_title="Tennis IA v10.1",
    page_icon="🎾",
    layout="wide"
)

# =========================================================
# CSS
# =========================================================

st.markdown("""
<style>

.metric-card {
    background: #1e1e2e;
    border-radius: 12px;
    padding: 18px;
    border: 1px solid #313244;
    text-align: center;
}

.metric-label {
    color: #a6adc8;
    font-size: 0.85rem;
    margin-bottom: 6px;
}

.metric-value {
    color: #cdd6f4;
    font-size: 1.8rem;
    font-weight: bold;
}

.metric-sub {
    color: #6c7086;
    font-size: 0.75rem;
    margin-top: 4px;
}

</style>
""", unsafe_allow_html=True)

# =========================================================
# UTILIDADES
# =========================================================

def limpiar(txt):

    if pd.isna(txt):
        return ""

    t = unicodedata.normalize('NFKD', str(txt))
    t = t.encode('ascii', 'ignore').decode('ascii')
    t = re.sub(r'\[.*?\]|\(.*?\)', '', t)

    return re.sub(r'[^A-Z0-9]', '', t.upper())


def elo_prob(e1, e2):

    return 1 / (1 + 10 ** ((e2 - e1) / 400))


# =========================================================
# CARGA DATOS
# =========================================================

@st.cache_data
def cargar_datos():

    stats_map = {}
    players = {}

    # =====================================================
    # STATS ATP
    # =====================================================

    if os.path.exists("atp_completa.xlsx"):

        df_stats = pd.read_excel("atp_completa.xlsx")

        for _, row in df_stats.iterrows():

            nombre = str(row.get("Player", "")).strip()
            nid = limpiar(nombre)

            try:

                hold = float(str(row.get("Hld%", "80")).replace('%', '')) / 100
                ace = float(str(row.get("Ace%", "7")).replace('%', '')) / 100
                first_in = float(str(row.get("1stIn", "62")).replace('%', '')) / 100
                first_won = float(str(row.get("1st%", "72")).replace('%', '')) / 100
                second_won = float(str(row.get("2nd%", "50")).replace('%', '')) / 100

                stats_map[nid] = {

                    "hold": np.clip(hold, 0.55, 0.95),
                    "ace": ace,
                    "1in": first_in,
                    "1w": first_won,
                    "2w": second_won
                }

            except:
                pass

    # =====================================================
    # ELO ATP
    # =====================================================

    if os.path.exists("atp_elo.xlsx"):

        df_elo = pd.read_excel("atp_elo.xlsx")

        df_elo.columns = [limpiar(c) for c in df_elo.columns]

        for _, row in df_elo.iterrows():

            nombre = str(row.get("PLAYER", "")).replace('\xa0', ' ').strip()

            nid = limpiar(nombre)

            try:
                rank = int(float(row.get("ATPRANK", 999)))
            except:
                rank = 999

            players[nombre] = {

                "Player": nombre,

                "Rank": rank,

                "Hard": float(row.get("HELO", row.get("ELO", 1500))),
                "Clay": float(row.get("CELO", row.get("ELO", 1500))),
                "Grass": float(row.get("GELO", row.get("ELO", 1500))),
                "General": float(row.get("ELO", 1500)),

                "Stats": stats_map.get(nid, {})
            }

    return players


# =========================================================
# HOLD CALIBRADO
# =========================================================

def calc_hold(stats, elo_diff, surface):

    # =====================================================
    # HOLD BASE REAL
    # =====================================================

    base_hold = stats.get("hold", 0.78)

    # =====================================================
    # AJUSTE SUPERFICIE
    # =====================================================

    surface_adj = {
        "Hard": 0.00,
        "Clay": -0.045,
        "Grass": +0.025
    }

    # =====================================================
    # AJUSTE ELO
    # =====================================================

    elo_adj = np.clip(
        elo_diff / 2500,
        -0.06,
        0.06
    )

    # =====================================================
    # AJUSTE DEFENSIVO
    # MEJORES JUGADORES ROMPEN MÁS
    # =====================================================

    defensive_adj = np.clip(
        (-elo_diff) / 5000,
        -0.03,
        0.03
    )

    # =====================================================
    # AJUSTE SERVICIO
    # =====================================================

    ace_bonus = stats.get("ace", 0.05) * 0.05

    first_bonus = (
        stats.get("1in", 0.62) * 0.02 +
        stats.get("1w", 0.72) * 0.03 +
        stats.get("2w", 0.50) * 0.02
    )

    # =====================================================
    # HOLD FINAL
    # =====================================================

    hold = (
        base_hold
        + surface_adj[surface]
        + elo_adj
        + defensive_adj
        + ace_bonus
        + first_bonus
    )

    return np.clip(hold, 0.58, 0.92)


# =========================================================
# SIMULAR SET
# =========================================================

def sim_set(hold1, hold2, surface):

    g1 = 0
    g2 = 0

    server = random.choice([1, 2])

    while True:

        # =================================================
        # GAME
        # =================================================

        if server == 1:

            if random.random() < hold1:
                g1 += 1
            else:
                g2 += 1

        else:

            if random.random() < hold2:
                g2 += 1
            else:
                g1 += 1

        server = 1 if server == 2 else 2

        # =================================================
        # SET NORMAL
        # =================================================

        if g1 >= 6 and (g1 - g2) >= 2:
            return g1, g2

        if g2 >= 6 and (g2 - g1) >= 2:
            return g1, g2

        # =================================================
        # TIEBREAK
        # =================================================

        if g1 == 6 and g2 == 6:

            if surface == "Clay":

                p_tb = 0.46 + ((hold1 - hold2) * 1.2)

            else:

                p_tb = hold1 / (hold1 + hold2)

            p_tb = np.clip(p_tb, 0.30, 0.70)

            if random.random() < p_tb:
                return 7, 6
            else:
                return 6, 7


# =========================================================
# SIMULAR PARTIDO
# =========================================================

def sim_match(d1, d2, surface, best_of=3, n=10000):

    e1 = d1[surface]
    e2 = d2[surface]

    elo_diff = e1 - e2

    hold1 = calc_hold(
        d1["Stats"],
        elo_diff,
        surface
    )

    hold2 = calc_hold(
        d2["Stats"],
        -elo_diff,
        surface
    )

    sets_to_win = 3 if best_of == 5 else 2

    results = {

        "p1": 0,
        "p2": 0,

        "set3": 0,
        "set5": 0,

        "scores": {},

        "games": []
    }

    for _ in range(n):

        s1 = 0
        s2 = 0

        total_games = 0

        sets_played = 0

        while s1 < sets_to_win and s2 < sets_to_win:

            g1, g2 = sim_set(
                hold1,
                hold2,
                surface
            )

            total_games += g1 + g2

            if g1 > g2:
                s1 += 1
            else:
                s2 += 1

            sets_played += 1

        # =================================================
        # RESULTADO
        # =================================================

        score = f"{s1}-{s2}"

        results["scores"][score] = (
            results["scores"].get(score, 0) + 1
        )

        if s1 > s2:
            results["p1"] += 1
        else:
            results["p2"] += 1

        if sets_played >= 3:
            results["set3"] += 1

        if sets_played >= 5:
            results["set5"] += 1

        results["games"].append(total_games)

    return results, hold1, hold2


# =========================================================
# UI
# =========================================================

db = cargar_datos()

if not db:

    st.error("No se encontraron archivos ATP.")

    st.stop()

# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.header("🎾 Tennis IA v10.1")

    st.caption(
        "Modelo calibrado ATP real"
    )

    players = sorted(db.keys())

    surface = st.selectbox(
        "Superficie",
        ["Hard", "Clay", "Grass"]
    )

    format_match = st.radio(
        "Formato",
        ["ATP Tour (3 sets)", "Grand Slam (5 sets)"]
    )

    sims = st.select_slider(
        "Simulaciones",
        [5000, 10000, 20000],
        value=10000
    )

# =========================================================
# JUGADORES
# =========================================================

c1, c2 = st.columns(2)

with c1:

    p1_name = st.selectbox(
        "Jugador 1",
        players
    )

with c2:

    p2_name = st.selectbox(
        "Jugador 2",
        players,
        index=min(1, len(players)-1)
    )

# =========================================================
# ANALIZAR
# =========================================================

if st.button(
    "🚀 ANALIZAR PARTIDO",
    use_container_width=True
):

    d1 = db[p1_name]
    d2 = db[p2_name]

    best_of = 5 if "5" in format_match else 3

    with st.spinner(
        f"Simulando {sims:,} partidos..."
    ):

        res, hold1, hold2 = sim_match(
            d1,
            d2,
            surface,
            best_of,
            sims
        )

    p1 = res["p1"] / sims
    p2 = res["p2"] / sims

    avg_games = np.mean(res["games"])

    # =====================================================
    # PROBABILIDADES
    # =====================================================

    st.divider()

    st.subheader(
        "🏆 Probabilidad de Victoria"
    )

    cc1, cc2 = st.columns(2)

    with cc1:

        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{d1['Player']}</div>
            <div class="metric-value">{p1:.1%}</div>
            <div class="metric-sub">
                Rank #{d1['Rank']}
                · Elo {surface}: {d1[surface]:.0f}
            </div>
        </div>
        """, unsafe_allow_html=True)

    with cc2:

        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{d2['Player']}</div>
            <div class="metric-value">{p2:.1%}</div>
            <div class="metric-sub">
                Rank #{d2['Rank']}
                · Elo {surface}: {d2[surface]:.0f}
            </div>
        </div>
        """, unsafe_allow_html=True)

    # =====================================================
    # HOLD
    # =====================================================

    st.divider()

    st.subheader(
        "🎾 Hold Probability"
    )

    h1, h2 = st.columns(2)

    with h1:

        st.metric(
            d1["Player"],
            f"{hold1:.1%}"
        )

    with h2:

        st.metric(
            d2["Player"],
            f"{hold2:.1%}"
        )

    # =====================================================
    # MARCADORES
    # =====================================================

    st.divider()

    st.subheader(
        "📋 Marcadores más probables"
    )

    scores_sorted = sorted(
        res["scores"].items(),
        key=lambda x: -x[1]
    )

    cols = st.columns(
        min(4, len(scores_sorted))
    )

    for i, (score, count) in enumerate(scores_sorted[:4]):

        with cols[i]:

            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{score}</div>
                <div class="metric-value">
                    {count/sims:.1%}
                </div>
            </div>
            """, unsafe_allow_html=True)

    # =====================================================
    # GAMES
    # =====================================================

    st.divider()

    st.subheader(
        "📊 Games"
    )

    g1, g2, g3, g4 = st.columns(4)

    with g1:

        st.metric(
            "Media Games",
            f"{avg_games:.1f}"
        )

    with g2:

        st.metric(
            "Over 18.5",
            f"{sum(x > 18.5 for x in res['games']) / sims:.1%}"
        )

    with g3:

        st.metric(
            "Over 20.5",
            f"{sum(x > 20.5 for x in res['games']) / sims:.1%}"
        )

    with g4:

        st.metric(
            "3 Sets",
            f"{res['set3']/sims:.1%}"
        )

    # =====================================================
    # INSIGHTS
    # =====================================================

    st.divider()

    if avg_games < 21:

        st.success(
            "📉 Partido esperado corto "
            "con bastantes breaks."
        )

    elif avg_games > 24:

        st.warning(
            "📈 Partido largo esperado "
            "con muchos holds."
        )

    else:

        st.info(
            "⚖️ Partido equilibrado "
            "en duración."
        )

    # =====================================================
    # INFO FINAL
    # =====================================================

    st.divider()

    st.caption(
        f"""
        Tennis IA v10.1
        · Elo superficie + Hold calibrado ATP
        · {sims:,} simulaciones Monte Carlo
        """
    )