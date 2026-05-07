import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import unicodedata

# =========================================================
# TENNIS IA v10.7
# ATP REALISTIC ENGINE - CLAY DURATION FIX
# =========================================================

st.set_page_config(
    page_title="Tennis IA v10.7",
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


def nivel_prob(p):
    if p >= 0.70:
        return "🔥 Alta"
    elif p >= 0.58:
        return "✅ Media-alta"
    elif p >= 0.52:
        return "⚖️ Ajustada"
    else:
        return "⚠️ Baja"


def cuota_justa(p):
    if p <= 0:
        return "-"
    return f"{1 / p:.2f}"


def riesgo_partido(set3, std_games, p_fav):
    if set3 > 0.48 or std_games > 6.2 or p_fav < 0.55:
        return "🔴 Riesgo alto"
    elif set3 > 0.40 or std_games > 5.4 or p_fav < 0.62:
        return "🟡 Riesgo medio"
    else:
        return "🟢 Riesgo bajo"


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

            nid = limpiar(nombre)

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
        "Clay": -0.098,
        "Grass": +0.010
    }

    elo_adj = np.clip(
        elo_diff / 3800,
        -0.042,
        0.042
    )

    ace_bonus = stats.get("ace", 0.05) * 0.014

    first_bonus = (
        stats.get("1in", 0.62) * 0.003 +
        stats.get("1w", 0.70) * 0.005 +
        stats.get("2w", 0.50) * 0.003
    )

    hold = (
        base_hold
        + surface_adj[surface]
        + elo_adj
        + ace_bonus
        + first_bonus
    )

    return np.clip(hold, 0.48, 0.86)


# =========================================================
# SIMULAR SET
# =========================================================

def sim_set(hold1, hold2, surface, match_shift):

    g1 = 0
    g2 = 0
    server = random.choice([1, 2])
    had_tiebreak = False

    if surface == "Clay":
        noise_scale = 0.066
        late_pressure = -0.082
        set_flow_scale = 0.028
    elif surface == "Hard":
        noise_scale = 0.038
        late_pressure = -0.032
        set_flow_scale = 0.018
    else:
        noise_scale = 0.028
        late_pressure = -0.018
        set_flow_scale = 0.014

    set_shift = np.random.normal(match_shift, set_flow_scale)

    while True:

        pressure = 0

        if g1 >= 4 and g2 >= 4:
            pressure = late_pressure

        current_hold1 = np.clip(
            np.random.normal(hold1 + set_shift, noise_scale) + pressure,
            0.32,
            0.91
        )

        current_hold2 = np.clip(
            np.random.normal(hold2 - set_shift, noise_scale) + pressure,
            0.32,
            0.91
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
            return g1, g2, had_tiebreak

        if g2 >= 6 and g2 - g1 >= 2:
            return g1, g2, had_tiebreak

        if g1 == 6 and g2 == 6:

            had_tiebreak = True

            if surface == "Clay":
                p_tb = 0.45 + ((hold1 - hold2) * 0.90) + set_shift
            else:
                p_tb = hold1 / (hold1 + hold2) + set_shift

            p_tb = np.clip(p_tb, 0.30, 0.70)

            if random.random() < p_tb:
                return 7, 6, had_tiebreak
            else:
                return 6, 7, had_tiebreak


# =========================================================
# SIMULAR PARTIDO
# =========================================================

def sim_match(d1, d2, surface, best_of=3, n=10000):

    e1 = d1[surface]
    e2 = d2[surface]

    elo_diff = e1 - e2

    hold1 = calc_hold(d1["Stats"], elo_diff, surface)
    hold2 = calc_hold(d2["Stats"], -elo_diff, surface)

    sets_to_win = 3 if best_of == 5 else 2

    results = {
        "p1": 0,
        "p2": 0,

        "p1_first_set": 0,
        "p2_first_set": 0,

        "first_set_over_9_5": 0,

        "p1_2_0": 0,
        "p2_2_0": 0,

        "p1_any_set": 0,
        "p2_any_set": 0,

        "both_win_set": 0,

        "set3": 0,
        "set5": 0,

        "tiebreak_match": 0,

        "games": []
    }

    if surface == "Clay":
        match_flow_scale = 0.068
    elif surface == "Hard":
        match_flow_scale = 0.034
    else:
        match_flow_scale = 0.024

    for _ in range(n):

        s1 = 0
        s2 = 0
        total_games = 0
        sets_played = 0
        first_set_done = False
        tiebreak_seen = False

        match_shift = np.random.normal(0, match_flow_scale)

        while s1 < sets_to_win and s2 < sets_to_win:

            g1, g2, tb = sim_set(
                hold1,
                hold2,
                surface,
                match_shift
            )

            if tb:
                tiebreak_seen = True

            set_games = g1 + g2
            total_games += set_games

            if not first_set_done:
                if set_games > 9.5:
                    results["first_set_over_9_5"] += 1

                if g1 > g2:
                    results["p1_first_set"] += 1
                else:
                    results["p2_first_set"] += 1

                first_set_done = True

            if g1 > g2:
                s1 += 1
            else:
                s2 += 1

            sets_played += 1

        if s1 > s2:
            results["p1"] += 1
        else:
            results["p2"] += 1

        if s1 >= 1:
            results["p1_any_set"] += 1

        if s2 >= 1:
            results["p2_any_set"] += 1

        if s1 >= 1 and s2 >= 1:
            results["both_win_set"] += 1

        if best_of == 3:
            if s1 == 2 and s2 == 0:
                results["p1_2_0"] += 1
            if s2 == 2 and s1 == 0:
                results["p2_2_0"] += 1

        if sets_played >= 3:
            results["set3"] += 1

        if sets_played >= 5:
            results["set5"] += 1

        if tiebreak_seen:
            results["tiebreak_match"] += 1

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

    st.header("🎾 Tennis IA v10.7")
    st.caption("Motor ATP realista · Clay duration fix")

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

    elo_p1 = elo_prob(d1[surface], d2[surface])
    elo_p2 = 1 - elo_p1

    games = res["games"]

    avg_games = np.mean(games)
    med_games = np.median(games)
    std_games = np.std(games)

    over_18 = sum(x > 18.5 for x in games) / sims
    over_19 = sum(x > 19.5 for x in games) / sims
    over_20 = sum(x > 20.5 for x in games) / sims
    over_21 = sum(x > 21.5 for x in games) / sims

    p1_first = res["p1_first_set"] / sims
    p2_first = res["p2_first_set"] / sims

    first_over_95 = res["first_set_over_9_5"] / sims

    p1_2_0 = res["p1_2_0"] / sims
    p2_2_0 = res["p2_2_0"] / sims

    p1_any = res["p1_any_set"] / sims
    p2_any = res["p2_any_set"] / sims

    both_win_set = res["both_win_set"] / sims
    set3 = res["set3"] / sims
    tb_match = res["tiebreak_match"] / sims

    fav_name = d1["Player"] if p1 > p2 else d2["Player"]
    fav_prob = max(p1, p2)

    risk = riesgo_partido(set3, std_games, fav_prob)

    st.divider()

    st.subheader("🏆 Ganador del Partido")

    cc1, cc2 = st.columns(2)

    with cc1:
        st.metric(
            d1["Player"],
            f"{p1:.1%}",
            f"{nivel_prob(p1)} · Cuota justa {cuota_justa(p1)}"
        )
        st.caption(f"Rank #{d1['Rank']} · Elo {surface}: {d1[surface]:.0f}")

    with cc2:
        st.metric(
            d2["Player"],
            f"{p2:.1%}",
            f"{nivel_prob(p2)} · Cuota justa {cuota_justa(p2)}"
        )
        st.caption(f"Rank #{d2['Rank']} · Elo {surface}: {d2[surface]:.0f}")

    st.caption(
        f"Referencia Elo puro: {elo_p1:.1%} / {elo_p2:.1%} · {risk}"
    )

    st.divider()

    st.subheader("🎾 Ganador del 1er Set")

    fs1, fs2, fs3 = st.columns(3)

    with fs1:
        st.metric(
            f"{d1['Player']} gana 1er set",
            f"{p1_first:.1%}",
            f"{nivel_prob(p1_first)} · CJ {cuota_justa(p1_first)}"
        )

    with fs2:
        st.metric(
            f"{d2['Player']} gana 1er set",
            f"{p2_first:.1%}",
            f"{nivel_prob(p2_first)} · CJ {cuota_justa(p2_first)}"
        )

    with fs3:
        st.metric(
            "Over 9.5 games 1er set",
            f"{first_over_95:.1%}",
            f"{nivel_prob(first_over_95)} · CJ {cuota_justa(first_over_95)}"
        )

    st.divider()

    st.subheader("📌 Mercados de Sets")

    s1, s2, s3, s4 = st.columns(4)

    with s1:
        st.metric(
            f"{d1['Player']} gana 2-0",
            f"{p1_2_0:.1%}",
            f"{nivel_prob(p1_2_0)} · CJ {cuota_justa(p1_2_0)}"
        )

    with s2:
        st.metric(
            f"{d2['Player']} gana 2-0",
            f"{p2_2_0:.1%}",
            f"{nivel_prob(p2_2_0)} · CJ {cuota_justa(p2_2_0)}"
        )

    with s3:
        st.metric(
            f"{d1['Player']} gana al menos 1 set",
            f"{p1_any:.1%}",
            f"{nivel_prob(p1_any)} · CJ {cuota_justa(p1_any)}"
        )

    with s4:
        st.metric(
            f"{d2['Player']} gana al menos 1 set",
            f"{p2_any:.1%}",
            f"{nivel_prob(p2_any)} · CJ {cuota_justa(p2_any)}"
        )

    s5, s6, s7 = st.columns(3)

    with s5:
        st.metric(
            "Ambos ganan set",
            f"{both_win_set:.1%}",
            f"{nivel_prob(both_win_set)} · CJ {cuota_justa(both_win_set)}"
        )

    with s6:
        st.metric(
            "Partido a 3 sets",
            f"{set3:.1%}",
            f"{nivel_prob(set3)} · CJ {cuota_justa(set3)}"
        )

    with s7:
        st.metric(
            "Tie-break en el partido",
            f"{tb_match:.1%}",
            f"{nivel_prob(tb_match)} · CJ {cuota_justa(tb_match)}"
        )

    st.divider()

    st.subheader("📊 Mercados de Games")

    g1, g2, g3, g4, g5 = st.columns(5)

    with g1:
        st.metric("Media games", f"{avg_games:.1f}")
        st.caption(f"Mediana: {med_games:.0f} · σ: {std_games:.1f}")

    with g2:
        st.metric("Over 18.5", f"{over_18:.1%}", f"{nivel_prob(over_18)} · CJ {cuota_justa(over_18)}")
        st.metric("Under 18.5", f"{1-over_18:.1%}", f"{nivel_prob(1-over_18)} · CJ {cuota_justa(1-over_18)}")

    with g3:
        st.metric("Over 19.5", f"{over_19:.1%}", f"{nivel_prob(over_19)} · CJ {cuota_justa(over_19)}")
        st.metric("Under 19.5", f"{1-over_19:.1%}", f"{nivel_prob(1-over_19)} · CJ {cuota_justa(1-over_19)}")

    with g4:
        st.metric("Over 20.5", f"{over_20:.1%}", f"{nivel_prob(over_20)} · CJ {cuota_justa(over_20)}")
        st.metric("Under 20.5", f"{1-over_20:.1%}", f"{nivel_prob(1-over_20)} · CJ {cuota_justa(1-over_20)}")

    with g5:
        st.metric("Over 21.5", f"{over_21:.1%}", f"{nivel_prob(over_21)} · CJ {cuota_justa(over_21)}")
        st.metric("Under 21.5", f"{1-over_21:.1%}", f"{nivel_prob(1-over_21)} · CJ {cuota_justa(1-over_21)}")

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

    st.subheader("🧠 Lectura rápida")

    mejor_1set = d1["Player"] if p1_first > p2_first else d2["Player"]
    prob_1set = max(p1_first, p2_first)

    if avg_games < 21:
        lectura_games = "partido más bien corto"
    elif avg_games > 23.5:
        lectura_games = "partido con tendencia larga"
    else:
        lectura_games = "partido de duración media"

    if tb_match < 0.22:
        lectura_tb = "tie-break poco probable"
    elif tb_match > 0.35:
        lectura_tb = "riesgo alto de tie-break"
    else:
        lectura_tb = "tie-break posible pero no dominante"

    if fav_prob < 0.55:
        alerta_fav = "⚠️ favorito débil / underdog vivo"
    elif fav_prob < 0.62:
        alerta_fav = "🟡 favorito moderado"
    else:
        alerta_fav = "🟢 favorito sólido"

    st.info(
        f"Favorito: **{fav_name} ({fav_prob:.1%})** · "
        f"{alerta_fav} · "
        f"Mejor 1er set: **{mejor_1set} ({prob_1set:.1%})** · "
        f"Games: **{lectura_games}** · "
        f"3 sets: **{set3:.1%}** · "
        f"{lectura_tb} · "
        f"{risk}"
    )

    st.divider()

    st.caption(
        f"Tennis IA v10.7 · Elo superficie + Hold dinámico · Clay duration fix · {sims:,} simulaciones Monte Carlo"
    )