import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import unicodedata

# =========================================================
# TENNIS IA v10.3
# ATP REALISTIC ENGINE - CLAY FIX + UI FIX
# =========================================================

st.set_page_config(
    page_title="Tennis IA v10.3",
    page_icon="🎾",
    layout="wide"
)

# =========================================================
# UTILIDADES
# =========================================================

def limpiar(txt):
    if pd.isna(txt):
        return ""

    t = unicodedata.normalize("NFKD", str(txt))
    t = t.encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"\[.*?\]|\(.*?\)", "", t)

    return re.sub(r"[^A-Z0-9]", "", t.upper())


def elo_prob(e1, e2):
    return 1 / (1 + 10 ** ((e2 - e1) / 400))


# =========================================================
# CARGA DATOS
# =========================================================

@st.cache_data
def cargar_datos():

    stats_map = {}
    players = {}

    if os.path.exists("atp_completa.xlsx"):

        df_stats = pd.read_excel("atp_completa.xlsx")

        for _, row in df_stats.iterrows():

            nombre = str(row.get("Player", "")).strip()
            nid = limpiar(nombre)

            try:
                hold = float(str(row.get("Hld%", "78")).replace("%", "")) / 100
                ace = float(str(row.get("Ace%", "5")).replace("%", "")) / 100
                first_in = float(str(row.get("1stIn", "62")).replace("%", "")) / 100
                first_won = float(str(row.get("1st%", "70")).replace("%", "")) / 100
                second_won = float(str(row.get("2nd%", "50")).replace("%", "")) / 100

                stats_map[nid] = {
                    "hold": np.clip(hold, 0.50, 0.95),
                    "ace": ace,
                    "1in": first_in,
                    "1w": first_won,
                    "2w": second_won
                }

            except:
                pass

    if os.path.exists("atp_elo.xlsx"):

        df_elo = pd.read_excel("atp_elo.xlsx")
        df_elo.columns = [limpiar(c) for c in df_elo.columns]

        for _, row in df_elo.iterrows():

            nombre = str(row.get("PLAYER", "")).replace("\xa0", " ").strip()
            nid = limpiar(nombre)

            try:
                rank = int(float(row.get("ATPRANK", 999)))
            except:
                rank = 999

            try:
                elo_general = float(row.get("ELO", 1500))
            except:
                elo_general = 1500

            try:
                h_elo = float(row.get("HELO", elo_general))
            except:
                h_elo = elo_general

            try:
                c_elo = float(row.get("CELO", elo_general))
            except:
                c_elo = elo_general

            try:
                g_elo = float(row.get("GELO", elo_general))
            except:
                g_elo = elo_general

            players[nombre] = {
                "Player": nombre,
                "Rank": rank,
                "Hard": h_elo,
                "Clay": c_elo,
                "Grass": g_elo,
                "General": elo_general,
                "Stats": stats_map.get(nid, {})
            }

    return players


# =========================================================
# HOLD CALIBRADO
# =========================================================

def calc_hold(stats, elo_diff, surface):

    base_hold = stats.get("hold", 0.78)

    surface_adj = {
        "Hard": -0.010,
        "Clay": -0.085,
        "Grass": +0.010
    }

    elo_adj = np.clip(
        elo_diff / 2200,
        -0.07,
        0.07
    )

    ace_bonus = stats.get("ace", 0.05) * 0.025

    first_bonus = (
        stats.get("1in", 0.62) * 0.005 +
        stats.get("1w", 0.70) * 0.010 +
        stats.get("2w", 0.50) * 0.005
    )

    hold = (
        base_hold
        + surface_adj[surface]
        + elo_adj
        + ace_bonus
        + first_bonus
    )

    return np.clip(hold, 0.50, 0.88)


# =========================================================
# SIMULAR SET
# =========================================================

def sim_set(hold1, hold2, surface):

    g1 = 0
    g2 = 0

    server = random.choice([1, 2])

    while True:

        if surface == "Clay":
            noise_scale = 0.065
            late_pressure = -0.055
        elif surface == "Hard":
            noise_scale = 0.040
            late_pressure = -0.025
        else:
            noise_scale = 0.030
            late_pressure = -0.015

        pressure = 0

        if g1 >= 4 and g2 >= 4:
            pressure = late_pressure

        current_hold1 = np.clip(
            np.random.normal(hold1, noise_scale) + pressure,
            0.38,
            0.92
        )

        current_hold2 = np.clip(
            np.random.normal(hold2, noise_scale) + pressure,
            0.38,
            0.92
        )

        if server == 1:
            if random.random() < current_hold1:
                g1 += 1
            else:
                g2 += 1
        else:
            if random.random() < current_hold2:
                g2 += 1
            else:
                g1 += 1

        server = 1 if server == 2 else 2

        if g1 >= 6 and g1 - g2 >= 2:
            return g1, g2

        if g2 >= 6 and g2 - g1 >= 2:
            return g1, g2

        if g1 == 6 and g2 == 6:

            if surface == "Clay":
                p_tb = 0.45 + ((hold1 - hold2) * 1.1)
            else:
                p_tb = hold1 / (hold1 + hold2)

            p_tb = np.clip(p_tb, 0.32, 0.68)

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

        score = f"{s1}-{s2}"

        results["scores"][score] = results["scores"].get(score, 0) + 1

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
    st.error("No se encontraron archivos ATP. Coloca atp_elo.xlsx y atp_completa.xlsx en la misma carpeta que este script.")
    st.stop()

with st.sidebar:

    st.header("🎾 Tennis IA v10.3")

    st.caption("Motor ATP realista calibrado")

    players = sorted(db.keys())

    surface = st.selectbox(
        "Superficie",
        ["Hard", "Clay", "Grass"]
    )

    format_match = st.radio(
        "Formato",
        [
            "ATP Tour (3 sets)",
            "Grand Slam (5 sets)"
        ]
    )

    sims = st.select_slider(
        "Simulaciones",
        [5000, 10000, 20000],
        value=10000
    )


# =========================================================
# SELECCIÓN JUGADORES
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
        index=min(1, len(players) - 1)
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

    with st.spinner(f"Simulando {sims:,} partidos..."):

        res, hold1, hold2 = sim_match(
            d1,
            d2,
            surface,
            best_of,
            sims
        )

    p1 = res["p1"] / sims
    p2 = res["p2"] / sims

    games = res["games"]

    avg_games = np.mean(games)
    med_games = np.median(games)
    std_games = np.std(games)

    over_18 = sum(x > 18.5 for x in games) / sims
    over_19 = sum(x > 19.5 for x in games) / sims
    over_20 = sum(x > 20.5 for x in games) / sims
    over_21 = sum(x > 21.5 for x in games) / sims

    st.divider()

    st.subheader("🏆 Probabilidad de Victoria")

    cc1, cc2 = st.columns(2)

    with cc1:
        st.metric(
            d1["Player"],
            f"{p1:.1%}",
            f"Rank #{d1['Rank']} · Elo {surface}: {d1[surface]:.0f}"
        )

    with cc2:
        st.metric(
            d2["Player"],
            f"{p2:.1%}",
            f"Rank #{d2['Rank']} · Elo {surface}: {d2[surface]:.0f}"
        )

    st.caption(
        f"Referencia Elo puro: {elo_prob(d1[surface], d2[surface]):.1%} / {1 - elo_prob(d1[surface], d2[surface]):.1%}"
    )

    st.divider()

    st.subheader("🎾 Hold Probability")

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

    st.divider()

    st.subheader("📋 Marcadores más probables")

    scores_sorted = sorted(
        res["scores"].items(),
        key=lambda x: -x[1]
    )

    cols = st.columns(
        min(4, len(scores_sorted))
    )

    for i, (score, count) in enumerate(scores_sorted[:4]):
        with cols[i]:
            st.metric(
                score,
                f"{count / sims:.1%}"
            )

    st.divider()

    st.subheader("📊 Games")

    g1, g2, g3, g4, g5, g6 = st.columns(6)

    with g1:
        st.metric(
            "Media Games",
            f"{avg_games:.1f}"
        )

    with g2:
        st.metric(
            "Mediana",
            f"{med_games:.0f}"
        )

    with g3:
        st.metric(
            "Over 18.5",
            f"{over_18:.1%}"
        )

    with g4:
        st.metric(
            "Over 19.5",
            f"{over_19:.1%}"
        )

    with g5:
        st.metric(
            "Over 20.5",
            f"{over_20:.1%}"
        )

    with g6:
        st.metric(
            "Over 21.5",
            f"{over_21:.1%}"
        )

    st.divider()

    st.subheader("🎾 Sets")

    s1, s2 = st.columns(2)

    with s1:
        st.metric(
            "3 Sets",
            f"{res['set3'] / sims:.1%}"
        )

    with s2:
        if best_of == 5:
            st.metric(
                "5 Sets",
                f"{res['set5'] / sims:.1%}"
            )
        else:
            st.metric(
                "Dispersión games",
                f"{std_games:.1f}"
            )

    st.divider()

    if surface == "Clay" and avg_games > 24:
        st.warning(
            "📈 Sigue saliendo largo para clay. Si al probar más partidos ocurre mucho, bajaremos otro punto el hold en tierra."
        )
    elif avg_games < 21:
        st.success(
            "📉 Partido esperado corto con bastantes breaks."
        )
    elif avg_games > 24:
        st.warning(
            "📈 Partido largo esperado con muchos holds."
        )
    else:
        st.info(
            "⚖️ Partido equilibrado en duración."
        )

    st.divider()

    st.caption(
        f"Tennis IA v10.3 · Elo superficie + Hold dinámico · Clay calibrado · {sims:,} simulaciones Monte Carlo"
    )