import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import unicodedata
from difflib import SequenceMatcher

# =========================================================
# TENNIS IA v11.2
# ATP/WTA PATH FIX + BIG SERVER ENGINE
# =========================================================

st.set_page_config(
    page_title="Tennis IA v11.2",
    page_icon="🎾",
    layout="wide"
)

# =========================================================
# UTILIDADES
# =========================================================

def normalizar_texto(txt):
    if pd.isna(txt):
        return ""
    t = unicodedata.normalize("NFKD", str(txt))
    t = t.encode("ascii", "ignore").decode("ascii")
    t = t.replace("\xa0", " ")
    return t.strip()


def limpiar(txt):
    t = normalizar_texto(txt)
    t = re.sub(r"\[.*?\]|\(.*?\)", "", t)
    return re.sub(r"[^A-Z0-9]", "", t.upper())


def tokenizar_nombre(txt):
    t = normalizar_texto(txt)
    t = re.sub(r"\[.*?\]|\(.*?\)", "", t)
    return set(re.findall(r"[A-Z]+", t.upper()))


def similitud_nombre(a, b):
    a_clean = limpiar(a)
    b_clean = limpiar(b)

    if not a_clean or not b_clean:
        return 0.0

    if a_clean == b_clean:
        return 1.0

    if a_clean in b_clean or b_clean in a_clean:
        return 0.92

    ta = tokenizar_nombre(a)
    tb = tokenizar_nombre(b)

    token_score = 0
    if ta and tb:
        token_score = len(ta & tb) / len(ta | tb)

    seq_score = SequenceMatcher(None, a_clean, b_clean).ratio()

    return max(token_score, seq_score)


def buscar_columna(df, nombres_posibles):
    cols = list(df.columns)
    cols_clean = {limpiar(c): c for c in cols}

    for n in nombres_posibles:
        n_clean = limpiar(n)
        if n_clean in cols_clean:
            return cols_clean[n_clean]

    return None


def leer_porcentaje(valor, default):
    try:
        if pd.isna(valor):
            return default

        txt = str(valor).replace("%", "").replace(",", ".").strip()

        if txt == "":
            return default

        num = float(txt)

        if num > 1:
            num = num / 100

        return num

    except:
        return default


def leer_float(valor, default):
    try:
        if pd.isna(valor):
            return default

        txt = str(valor).replace(",", ".").strip()

        if txt == "":
            return default

        return float(txt)

    except:
        return default


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


def riesgo_partido(set3, std_games, p_fav):
    if set3 > 0.48 or std_games > 6.2 or p_fav < 0.55:
        return "🔴 Riesgo alto"
    elif set3 > 0.40 or std_games > 5.4 or p_fav < 0.62:
        return "🟡 Riesgo medio"
    else:
        return "🟢 Riesgo bajo"


def perfil_saque(ace):
    if ace >= 0.16:
        return "elite_server"
    elif ace >= 0.12:
        return "big_server"
    elif ace >= 0.08:
        return "good_server"
    else:
        return "normal"


def perfil_legible(profile):
    mapa = {
        "elite_server": "🚀 Elite server",
        "big_server": "🔥 Big server",
        "good_server": "✅ Buen sacador",
        "normal": "Normal"
    }
    return mapa.get(profile, "Normal")


# =========================================================
# BUSCAR STATS
# =========================================================

def buscar_stats(nombre_elo, stats_map):

    nid = limpiar(nombre_elo)

    if nid in stats_map:
        stats = stats_map[nid].copy()
        stats["match_type"] = "exacto"
        stats["match_score"] = 1.0
        return stats

    mejor_id = None
    mejor_score = 0

    for sid, data in stats_map.items():
        raw_stats_name = data.get("raw_name_stats", sid)

        score = max(
            similitud_nombre(nombre_elo, raw_stats_name),
            similitud_nombre(nid, sid)
        )

        if score > mejor_score:
            mejor_score = score
            mejor_id = sid

    if mejor_id and mejor_score >= 0.70:
        stats = stats_map[mejor_id].copy()
        stats["match_type"] = "aproximado"
        stats["match_score"] = mejor_score
        return stats

    return {
        "found_stats": False,
        "raw_name_stats": "NO ENCONTRADO",
        "clean_stats_id": "",
        "hold": 0.78,
        "ace": 0.05,
        "1in": 0.62,
        "1w": 0.70,
        "2w": 0.50,
        "serve_profile": "normal",
        "match_type": "default",
        "match_score": 0
    }


# =========================================================
# RUTAS
# =========================================================

def rutas_archivos(circuito):
    circuito = circuito.lower()

    if circuito == "atp":
        return {
            "stats": "datos/atp/atp_completa.xlsx",
            "elo": "datos/atp/atp_elo.xlsx"
        }

    return {
        "stats": "datos/wta/wta_completa.xlsx",
        "elo": "datos/wta/wta_elo.xlsx"
    }


# =========================================================
# CARGA DATOS
# =========================================================

@st.cache_data
def cargar_datos(circuito):

    rutas = rutas_archivos(circuito)

    stats_path = rutas["stats"]
    elo_path = rutas["elo"]

    stats_map = {}
    players = {}

    if os.path.exists(stats_path):

        df_stats = pd.read_excel(stats_path)

        col_player = buscar_columna(df_stats, ["Player", "Jugador", "Name"])
        col_hold = buscar_columna(df_stats, ["Hld%", "Hold%", "Hold"])
        col_ace = buscar_columna(df_stats, ["Ace%", "Aces%", "Ace"])
        col_1in = buscar_columna(df_stats, ["1stIn", "1st In", "FirstIn"])
        col_1w = buscar_columna(df_stats, ["1st%", "1st Won", "FirstWon"])
        col_2w = buscar_columna(df_stats, ["2nd%", "2nd Won", "SecondWon"])

        if col_player is not None:

            for _, row in df_stats.iterrows():

                nombre = normalizar_texto(row.get(col_player, ""))
                nid = limpiar(nombre)

                if not nid:
                    continue

                hold = leer_porcentaje(row.get(col_hold, None), 0.78) if col_hold else 0.78
                ace = leer_porcentaje(row.get(col_ace, None), 0.05) if col_ace else 0.05
                first_in = leer_porcentaje(row.get(col_1in, None), 0.62) if col_1in else 0.62
                first_won = leer_porcentaje(row.get(col_1w, None), 0.70) if col_1w else 0.70
                second_won = leer_porcentaje(row.get(col_2w, None), 0.50) if col_2w else 0.50

                stats_map[nid] = {
                    "found_stats": True,
                    "raw_name_stats": nombre,
                    "clean_stats_id": nid,
                    "hold": np.clip(hold, 0.50, 0.95),
                    "ace": np.clip(ace, 0.00, 0.35),
                    "1in": np.clip(first_in, 0.35, 0.85),
                    "1w": np.clip(first_won, 0.40, 0.90),
                    "2w": np.clip(second_won, 0.25, 0.75),
                    "serve_profile": perfil_saque(ace)
                }

    if os.path.exists(elo_path):

        df_elo = pd.read_excel(elo_path)

        col_player = buscar_columna(df_elo, ["Player", "Jugador", "Name"])
        col_rank = buscar_columna(df_elo, ["ATP Rank", "WTA Rank", "ATPRank", "WTARank", "Rank"])
        col_elo = buscar_columna(df_elo, ["Elo"])
        col_helo = buscar_columna(df_elo, ["hElo", "HElo", "Hard Elo"])
        col_celo = buscar_columna(df_elo, ["cElo", "CElo", "Clay Elo"])
        col_gelo = buscar_columna(df_elo, ["gElo", "GElo", "Grass Elo"])

        if col_player is not None:

            for _, row in df_elo.iterrows():

                nombre = normalizar_texto(row.get(col_player, ""))
                nid = limpiar(nombre)

                if not nid:
                    continue

                rank = int(leer_float(row.get(col_rank, 999), 999)) if col_rank else 999

                elo_general = leer_float(row.get(col_elo, 1500), 1500) if col_elo else 1500
                h_elo = leer_float(row.get(col_helo, elo_general), elo_general) if col_helo else elo_general
                c_elo = leer_float(row.get(col_celo, elo_general), elo_general) if col_celo else elo_general
                g_elo = leer_float(row.get(col_gelo, elo_general), elo_general) if col_gelo else elo_general

                stats = buscar_stats(nombre, stats_map)

                players[nombre] = {
                    "Player": nombre,
                    "CleanID": nid,
                    "Rank": rank,
                    "Hard": h_elo,
                    "Clay": c_elo,
                    "Grass": g_elo,
                    "General": elo_general,
                    "Stats": stats
                }

    return players, stats_path, elo_path


# =========================================================
# HOLD CALIBRADO
# =========================================================

def calc_hold(stats, elo_diff, surface, circuito):

    base_hold = stats.get("hold", 0.78)
    ace = stats.get("ace", 0.05)
    profile = stats.get("serve_profile", "normal")

    if circuito == "ATP":
        surface_adj = {
            "Hard": -0.010,
            "Clay": -0.102,
            "Grass": +0.015
        }
    else:
        surface_adj = {
            "Hard": -0.015,
            "Clay": -0.085,
            "Grass": +0.010
        }

    elo_adj = np.clip(
        elo_diff / 3900,
        -0.040,
        0.040
    )

    serve_bonus = 0

    if profile == "good_server":
        serve_bonus += 0.012
    elif profile == "big_server":
        serve_bonus += 0.026
    elif profile == "elite_server":
        serve_bonus += 0.040

    ace_bonus = ace * 0.015

    first_bonus = (
        stats.get("1in", 0.62) * 0.003 +
        stats.get("1w", 0.70) * 0.005 +
        stats.get("2w", 0.50) * 0.003
    )

    hold = (
        base_hold
        + surface_adj[surface]
        + elo_adj
        + serve_bonus
        + ace_bonus
        + first_bonus
    )

    return np.clip(hold, 0.48, 0.89)


# =========================================================
# SIMULAR SET
# =========================================================

def sim_set(hold1, hold2, surface, match_shift, p1_big, p2_big):

    g1 = 0
    g2 = 0
    server = random.choice([1, 2])
    had_tiebreak = False

    big_server_match = p1_big or p2_big
    double_big_server = p1_big and p2_big

    if surface == "Clay":

        noise_scale = 0.066
        late_pressure = -0.082
        set_flow_scale = 0.028

        if big_server_match:
            late_pressure += 0.020

        if double_big_server:
            late_pressure += 0.025

    elif surface == "Hard":

        noise_scale = 0.038
        late_pressure = -0.030
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
            0.93
        )

        current_hold2 = np.clip(
            np.random.normal(hold2 - set_shift, noise_scale) + pressure,
            0.32,
            0.93
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
                p_tb = 0.45 + ((hold1 - hold2) * 0.90)
            else:
                p_tb = hold1 / (hold1 + hold2)

            if big_server_match:
                p_tb += 0.04

            if double_big_server:
                p_tb += 0.05

            p_tb += set_shift
            p_tb = np.clip(p_tb, 0.30, 0.70)

            if random.random() < p_tb:
                return 7, 6, had_tiebreak
            else:
                return 6, 7, had_tiebreak


# =========================================================
# SIMULAR PARTIDO
# =========================================================

def sim_match(d1, d2, surface, circuito, best_of=3, n=10000):

    e1 = d1[surface]
    e2 = d2[surface]

    elo_diff = e1 - e2

    stats1 = d1["Stats"]
    stats2 = d2["Stats"]

    hold1 = calc_hold(stats1, elo_diff, surface, circuito)
    hold2 = calc_hold(stats2, -elo_diff, surface, circuito)

    p1_profile = stats1.get("serve_profile", "normal")
    p2_profile = stats2.get("serve_profile", "normal")

    p1_big = p1_profile in ["big_server", "elite_server"]
    p2_big = p2_profile in ["big_server", "elite_server"]

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
        "tiebreak_match": 0,
        "games": []
    }

    if surface == "Clay":
        match_flow_scale = 0.068
    elif surface == "Hard":
        match_flow_scale = 0.034
    else:
        match_flow_scale = 0.024

    if p1_big or p2_big:
        match_flow_scale += 0.010

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
                match_shift,
                p1_big,
                p2_big
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

        if tiebreak_seen:
            results["tiebreak_match"] += 1

        results["games"].append(total_games)

    return results, hold1, hold2, p1_profile, p2_profile


# =========================================================
# UI
# =========================================================

with st.sidebar:

    st.header("🎾 Tennis IA v11.2")
    st.caption("ATP/WTA + rutas datos/")

    if st.button("🧹 Limpiar caché y recargar datos"):
        st.cache_data.clear()
        st.success("Caché limpiada. Vuelve a analizar.")

    circuito = st.radio(
        "Circuito",
        ["ATP", "WTA"]
    )

db, stats_path, elo_path = cargar_datos(circuito)

if not db:
    st.error(
        f"No se encontraron datos para {circuito}. Revisa estas rutas:\n\n"
        f"{stats_path}\n\n"
        f"{elo_path}"
    )
    st.stop()

with st.sidebar:

    st.caption(f"Stats: {stats_path}")
    st.caption(f"Elo: {elo_path}")

    players = sorted(db.keys())

    surface = st.selectbox(
        "Superficie",
        ["Hard", "Clay", "Grass"]
    )

    format_match = st.radio(
        "Formato",
        [
            "Tour (3 sets)",
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
    p1_name = st.selectbox("Jugador 1", players)

with c2:
    p2_name = st.selectbox(
        "Jugador 2",
        players,
        index=min(1, len(players)-1)
    )


if st.button(
    "🚀 ANALIZAR PARTIDO",
    use_container_width=True
):

    d1 = db[p1_name]
    d2 = db[p2_name]

    best_of = 5 if "5" in format_match else 3

    with st.spinner(f"Simulando {sims:,} partidos..."):

        res, hold1, hold2, p1_profile, p2_profile = sim_match(
            d1,
            d2,
            surface,
            circuito,
            best_of,
            sims
        )

    p1 = res["p1"] / sims
    p2 = res["p2"] / sims

    p1_first = res["p1_first_set"] / sims
    p2_first = res["p2_first_set"] / sims

    p1_2_0 = res["p1_2_0"] / sims
    p2_2_0 = res["p2_2_0"] / sims

    p1_any = res["p1_any_set"] / sims
    p2_any = res["p2_any_set"] / sims

    both_win_set = res["both_win_set"] / sims
    set3 = res["set3"] / sims
    tb_match = res["tiebreak_match"] / sims

    first_set_over_95 = res["first_set_over_9_5"] / sims

    games = res["games"]

    avg_games = np.mean(games)
    med_games = np.median(games)
    std_games = np.std(games)

    over_18 = sum(x > 18.5 for x in games) / sims
    over_20 = sum(x > 20.5 for x in games) / sims
    over_21 = sum(x > 21.5 for x in games) / sims

    elo_p1 = elo_prob(d1[surface], d2[surface])
    elo_p2 = 1 - elo_p1

    fav_name = d1["Player"] if p1 > p2 else d2["Player"]
    fav_prob = max(p1, p2)

    risk = riesgo_partido(set3, std_games, fav_prob)

    profile_tags = []

    if p1_profile in ["big_server", "elite_server"]:
        profile_tags.append(f"🚀 {d1['Player']} {perfil_legible(p1_profile)}")

    if p2_profile in ["big_server", "elite_server"]:
        profile_tags.append(f"🚀 {d2['Player']} {perfil_legible(p2_profile)}")

    if tb_match > 0.35:
        profile_tags.append("🎯 Tie-break probable")

    if set3 > 0.45:
        profile_tags.append("⚠️ Partido volátil")

    if avg_games > 24:
        profile_tags.append("📈 Partido largo")

    if avg_games < 21:
        profile_tags.append("📉 Partido corto")

    if fav_prob < 0.55:
        profile_tags.append("⚠️ Favorito débil")

    markets = {
        "ML favorito": fav_prob,
        "Over 18.5": over_18,
        "Over 20.5": over_20,
        "Ambos ganan set": both_win_set,
        "Tie-break": tb_match,
        "1er set over 9.5": first_set_over_95
    }

    best_market = max(markets.items(), key=lambda x: x[1])

    st.divider()

    st.subheader("🏆 Ganador del Partido")

    cc1, cc2 = st.columns(2)

    with cc1:
        st.metric(
            d1["Player"],
            f"{p1:.1%}",
            f"{nivel_prob(p1)}"
        )
        st.caption(
            f"Rank #{d1['Rank']} · Elo {surface}: {d1[surface]:.0f}"
        )

    with cc2:
        st.metric(
            d2["Player"],
            f"{p2:.1%}",
            f"{nivel_prob(p2)}"
        )
        st.caption(
            f"Rank #{d2['Rank']} · Elo {surface}: {d2[surface]:.0f}"
        )

    st.caption(
        f"Referencia Elo puro: {elo_p1:.1%} / {elo_p2:.1%} · {risk}"
    )

    st.divider()

    st.subheader("🎾 Primer Set")

    fs1, fs2, fs3 = st.columns(3)

    with fs1:
        st.metric(
            f"{d1['Player']} gana",
            f"{p1_first:.1%}",
            nivel_prob(p1_first)
        )

    with fs2:
        st.metric(
            f"{d2['Player']} gana",
            f"{p2_first:.1%}",
            nivel_prob(p2_first)
        )

    with fs3:
        st.metric(
            "Over 9.5 games",
            f"{first_set_over_95:.1%}",
            nivel_prob(first_set_over_95)
        )

    st.divider()

    st.subheader("📌 Mercados de Sets")

    s1, s2, s3, s4 = st.columns(4)

    with s1:
        st.metric(
            f"{d1['Player']} 2-0",
            f"{p1_2_0:.1%}",
            nivel_prob(p1_2_0)
        )

    with s2:
        st.metric(
            f"{d2['Player']} 2-0",
            f"{p2_2_0:.1%}",
            nivel_prob(p2_2_0)
        )

    with s3:
        st.metric(
            f"{d1['Player']} gana set",
            f"{p1_any:.1%}",
            nivel_prob(p1_any)
        )

    with s4:
        st.metric(
            f"{d2['Player']} gana set",
            f"{p2_any:.1%}",
            nivel_prob(p2_any)
        )

    ex1, ex2, ex3 = st.columns(3)

    with ex1:
        st.metric(
            "Ambos ganan set",
            f"{both_win_set:.1%}",
            nivel_prob(both_win_set)
        )

    with ex2:
        st.metric(
            "Partido a 3 sets",
            f"{set3:.1%}",
            nivel_prob(set3)
        )

    with ex3:
        st.metric(
            "Tie-break partido",
            f"{tb_match:.1%}",
            nivel_prob(tb_match)
        )

    st.divider()

    st.subheader("📊 Games")

    g1, g2, g3, g4 = st.columns(4)

    with g1:
        st.metric("Media games", f"{avg_games:.1f}")
        st.caption(f"Mediana {med_games:.0f} · σ {std_games:.1f}")

    with g2:
        st.metric("Over 18.5", f"{over_18:.1%}", nivel_prob(over_18))

    with g3:
        st.metric("Over 20.5", f"{over_20:.1%}", nivel_prob(over_20))

    with g4:
        st.metric("Over 21.5", f"{over_21:.1%}", nivel_prob(over_21))

    st.divider()

    st.subheader("🎾 Hold Probability")

    h1, h2 = st.columns(2)

    with h1:
        st.metric(d1["Player"], f"{hold1:.1%}")
        st.caption(perfil_legible(p1_profile))

    with h2:
        st.metric(d2["Player"], f"{hold2:.1%}")
        st.caption(perfil_legible(p2_profile))

    st.divider()

    st.subheader("🔎 Diagnóstico de datos")

    dcol1, dcol2 = st.columns(2)

    with dcol1:
        st.markdown(f"**{d1['Player']}**")
        st.write("Stats encontradas:", "✅ Sí" if d1["Stats"].get("found_stats", False) else "❌ No")
        st.write("Tipo cruce:", d1["Stats"].get("match_type", "N/A"))
        st.write("Score cruce:", f"{d1['Stats'].get('match_score', 0):.2f}")
        st.write("Nombre stats:", d1["Stats"].get("raw_name_stats", "N/A"))
        st.write("Ace% leído:", f"{d1['Stats'].get('ace', 0):.1%}")
        st.write("Hld% leído:", f"{d1['Stats'].get('hold', 0):.1%}")
        st.write("CleanID:", d1.get("CleanID", ""))

    with dcol2:
        st.markdown(f"**{d2['Player']}**")
        st.write("Stats encontradas:", "✅ Sí" if d2["Stats"].get("found_stats", False) else "❌ No")
        st.write("Tipo cruce:", d2["Stats"].get("match_type", "N/A"))
        st.write("Score cruce:", f"{d2['Stats'].get('match_score', 0):.2f}")
        st.write("Nombre stats:", d2["Stats"].get("raw_name_stats", "N/A"))
        st.write("Ace% leído:", f"{d2['Stats'].get('ace', 0):.1%}")
        st.write("Hld% leído:", f"{d2['Stats'].get('hold', 0):.1%}")
        st.write("CleanID:", d2.get("CleanID", ""))

    st.divider()

    st.subheader("🧠 Perfil del Partido")

    if profile_tags:
        st.info(" · ".join(profile_tags))
    else:
        st.info("Sin perfil extremo detectado.")

    st.divider()

    st.subheader("🎯 Señal principal del modelo")

    st.success(
        f"{best_market[0]} → {best_market[1]:.1%}"
    )

    st.divider()

    st.caption(
        f"Tennis IA v11.2 · ATP/WTA rutas datos/ · Big Server Engine · {sims:,} simulaciones Monte Carlo"
    )