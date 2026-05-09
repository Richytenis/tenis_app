# =========================================================
# TENNIS IA v11.7
# PRO MATCH ENGINE + RETURN STRENGTH
# =========================================================

import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import unicodedata
from difflib import SequenceMatcher

# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="Tennis IA v11.7",
    page_icon="🎾",
    layout="wide"
)

# =========================================================
# CSS
# =========================================================

st.markdown("""
<style>

.metric-box {
    background: #1f2937;
    padding: 14px;
    border-radius: 12px;
    text-align: center;
    border: 1px solid #374151;
}

.metric-title {
    font-size: 0.9rem;
    color: #9ca3af;
}

.metric-value {
    font-size: 1.8rem;
    font-weight: bold;
    color: white;
}

.metric-sub {
    font-size: 0.8rem;
    color: #9ca3af;
}

</style>
""", unsafe_allow_html=True)

# =========================================================
# UTILS
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
        return 0

    if a_clean == b_clean:
        return 1.0

    ta = tokenizar_nombre(a)
    tb = tokenizar_nombre(b)

    token_score = 0

    if ta and tb:
        token_score = len(ta & tb) / len(ta | tb)

    seq_score = SequenceMatcher(None, a_clean, b_clean).ratio()

    return max(token_score, seq_score)


def buscar_columna(df, posibles):
    cols = list(df.columns)
    cols_clean = {limpiar(c): c for c in cols}

    for p in posibles:
        if limpiar(p) in cols_clean:
            return cols_clean[limpiar(p)]

    return None


def leer_porcentaje(v, default):
    try:
        if pd.isna(v):
            return default

        txt = str(v).replace("%", "").replace(",", ".").strip()

        if txt == "":
            return default

        num = float(txt)

        if num > 1:
            num /= 100

        return num

    except:
        return default


def leer_float(v, default):
    try:
        if pd.isna(v):
            return default

        txt = str(v).replace(",", ".").strip()

        if txt == "":
            return default

        return float(txt)

    except:
        return default


def elo_prob(e1, e2):
    return 1 / (1 + 10 ** ((e2 - e1) / 400))


def nivel(p):
    if p >= 0.72:
        return "🔥 Alta"

    elif p >= 0.60:
        return "✅ Media-alta"

    elif p >= 0.53:
        return "⚖️ Ajustada"

    return "⚠️ Baja"


def perfil_saque(ace):
    if ace >= 0.16:
        return "elite_server"

    elif ace >= 0.12:
        return "big_server"

    elif ace >= 0.08:
        return "good_server"

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
# DEFAULT STATS
# =========================================================

def stats_default_por_elo(elo_surface, rank=999):
    if elo_surface >= 1750:
        hold = 0.82
        ace = 0.075

    elif elo_surface >= 1650:
        hold = 0.80
        ace = 0.070

    elif elo_surface >= 1550:
        hold = 0.785
        ace = 0.060

    else:
        hold = 0.765
        ace = 0.050

    if rank <= 75:
        hold += 0.005

    elif rank > 150:
        hold -= 0.005

    return {
        "found_stats": False,
        "raw_name_stats": "NO ENCONTRADO",
        "hold": np.clip(hold, 0.74, 0.83),
        "ace": ace,
        "1in": 0.62,
        "1w": 0.70,
        "2w": 0.50,
        "serve_profile": perfil_saque(ace),
        "match_type": "default_elo"
    }


# =========================================================
# BUSCAR STATS
# =========================================================

def buscar_stats(nombre, stats_map):
    nid = limpiar(nombre)

    if nid in stats_map:
        return stats_map[nid]

    mejor = None
    mejor_score = 0

    for sid, data in stats_map.items():
        score = similitud_nombre(nombre, sid)

        if score > mejor_score:
            mejor_score = score
            mejor = data

    if mejor_score >= 0.72:
        return mejor

    return None


# =========================================================
# RUTAS
# =========================================================

def rutas(circuito):
    if circuito == "ATP":
        return {
            "stats": "datos/atp/atp_completa.xlsx",
            "elo": "datos/atp/atp_elo.xlsx"
        }

    return {
        "stats": "datos/wta/wta_completa.xlsx",
        "elo": "datos/wta/wta_elo.xlsx"
    }


# =========================================================
# LOAD
# =========================================================

@st.cache_data
def cargar_datos(circuito):
    r = rutas(circuito)

    stats_map = {}
    players = {}

    # =====================================================
    # STATS
    # =====================================================

    if os.path.exists(r["stats"]):
        df = pd.read_excel(r["stats"])

        col_player = buscar_columna(df, ["Player"])
        col_hold = buscar_columna(df, ["Hld%"])
        col_ace = buscar_columna(df, ["Ace%"])
        col_1in = buscar_columna(df, ["1stIn"])
        col_1w = buscar_columna(df, ["1st%"])
        col_2w = buscar_columna(df, ["2nd%"])

        for _, row in df.iterrows():
            nombre = normalizar_texto(row.get(col_player, ""))
            nid = limpiar(nombre)

            if not nid:
                continue

            ace = leer_porcentaje(row.get(col_ace), 0.05)

            stats_map[nid] = {
                "found_stats": True,
                "raw_name_stats": nombre,
                "hold": leer_porcentaje(row.get(col_hold), 0.78),
                "ace": ace,
                "1in": leer_porcentaje(row.get(col_1in), 0.62),
                "1w": leer_porcentaje(row.get(col_1w), 0.70),
                "2w": leer_porcentaje(row.get(col_2w), 0.50),
                "serve_profile": perfil_saque(ace),
                "match_type": "exacto"
            }

    # =====================================================
    # ELO
    # =====================================================

    if os.path.exists(r["elo"]):
        df = pd.read_excel(r["elo"])

        col_player = buscar_columna(df, ["Player"])
        col_rank = buscar_columna(df, ["ATP Rank", "WTA Rank", "Rank"])
        col_elo = buscar_columna(df, ["Elo"])
        col_hard = buscar_columna(df, ["hElo"])
        col_clay = buscar_columna(df, ["cElo"])
        col_grass = buscar_columna(df, ["gElo"])

        for _, row in df.iterrows():
            nombre = normalizar_texto(row.get(col_player, ""))

            if nombre == "":
                continue

            rank = int(leer_float(row.get(col_rank), 999))
            elo_general = leer_float(row.get(col_elo), 1500)

            hard = leer_float(row.get(col_hard), elo_general)
            clay = leer_float(row.get(col_clay), elo_general)
            grass = leer_float(row.get(col_grass), elo_general)

            stats = buscar_stats(nombre, stats_map)

            if stats is None:
                stats = stats_default_por_elo(clay, rank)

            players[nombre] = {
                "Player": nombre,
                "Rank": rank,
                "Hard": hard,
                "Clay": clay,
                "Grass": grass,
                "Stats": stats
            }

    return players


# =========================================================
# HOLD ENGINE
# =========================================================

def calc_hold(stats, elo_diff, surface, circuito):
    base = stats["hold"]
    ace = stats["ace"]
    profile = stats["serve_profile"]

    if circuito == "ATP":
        surface_adj = {
            "Hard": -0.010,
            "Clay": -0.105,
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
        serve_bonus += 0.006

    elif profile == "big_server":
        serve_bonus += 0.012

    elif profile == "elite_server":
        serve_bonus += 0.018

    hold = (
        base
        + surface_adj[surface]
        + elo_adj
        + serve_bonus
        + ace * 0.01
    )

    return np.clip(hold, 0.48, 0.84)


# =========================================================
# RETURN ENGINE
# =========================================================

def calc_return_strength(stats, elo_surface, surface):
    hold = stats.get("hold", 0.78)

    # Cuanto menor hold propio, normalmente más perfil de restador / jugador de fondo.
    base_return = 1.0 - hold

    elo_bonus = (elo_surface - 1500) / 4200

    surface_bonus = 0

    if surface == "Clay":
        surface_bonus = 0.020

    elif surface == "Grass":
        surface_bonus = -0.010

    ret = base_return + elo_bonus + surface_bonus

    return np.clip(ret, 0.12, 0.38)


def aplicar_return_pressure(hold1, hold2, ret1, ret2, surface):
    if surface == "Clay":
        pressure_weight = 0.16

    elif surface == "Hard":
        pressure_weight = 0.12

    else:
        pressure_weight = 0.09

    hold1_adj = hold1 - (ret2 * pressure_weight)
    hold2_adj = hold2 - (ret1 * pressure_weight)

    return (
        np.clip(hold1_adj, 0.46, 0.84),
        np.clip(hold2_adj, 0.46, 0.84)
    )


# =========================================================
# SET SIM
# =========================================================

def sim_set(hold1, hold2, surface, shift, p1_big, p2_big):
    g1 = 0
    g2 = 0

    tb = False

    server = random.choice([1, 2])

    if surface == "Clay":
        noise = 0.066
        pressure = -0.082

    elif surface == "Hard":
        noise = 0.038
        pressure = -0.030

    else:
        noise = 0.028
        pressure = -0.018

    while True:
        extra = 0

        if g1 >= 4 and g2 >= 4:
            extra = pressure

        h1 = np.clip(
            np.random.normal(hold1 + shift, noise) + extra,
            0.32,
            0.93
        )

        h2 = np.clip(
            np.random.normal(hold2 - shift, noise) + extra,
            0.32,
            0.93
        )

        if server == 1:
            if random.random() < h1:
                g1 += 1
            else:
                g2 += 1

        else:
            if random.random() < h2:
                g2 += 1
            else:
                g1 += 1

        server = 1 if server == 2 else 2

        if g1 >= 6 and g1 - g2 >= 2:
            return g1, g2, tb

        if g2 >= 6 and g2 - g1 >= 2:
            return g1, g2, tb

        if g1 == 6 and g2 == 6:
            tb = True

            p_tb = hold1 / (hold1 + hold2)

            if p1_big or p2_big:
                p_tb += 0.06

            p_tb = np.clip(p_tb, 0.32, 0.72)

            if random.random() < p_tb:
                return 7, 6, tb

            return 6, 7, tb


# =========================================================
# MATCH VOLATILITY
# =========================================================

def calcular_match_volatility(e1, e2, surface):
    elo_gap = abs(e1 - e2)

    base_vol = 0.040

    if elo_gap > 300:
        base_vol += 0.018

    elif elo_gap > 200:
        base_vol += 0.010

    elif elo_gap > 120:
        base_vol += 0.005

    if surface == "Clay":
        base_vol += 0.008

    elif surface == "Grass":
        base_vol -= 0.004

    return base_vol


# =========================================================
# MATCH SIM
# =========================================================

def sim_match(d1, d2, surface, circuito, best_of=3, n=10000):
    e1 = d1[surface]
    e2 = d2[surface]

    elo_diff = e1 - e2

    s1 = d1["Stats"]
    s2 = d2["Stats"]

    raw_hold1 = calc_hold(s1, elo_diff, surface, circuito)
    raw_hold2 = calc_hold(s2, -elo_diff, surface, circuito)

    ret1 = calc_return_strength(s1, e1, surface)
    ret2 = calc_return_strength(s2, e2, surface)

    hold1, hold2 = aplicar_return_pressure(
        raw_hold1,
        raw_hold2,
        ret1,
        ret2,
        surface
    )

    p1_profile = s1["serve_profile"]
    p2_profile = s2["serve_profile"]

    p1_big = p1_profile in ["big_server", "elite_server"]
    p2_big = p2_profile in ["big_server", "elite_server"]

    sets_to_win = 3 if best_of == 5 else 2

    res = {
        "p1": 0,
        "p2": 0,
        "set3": 0,
        "tb": 0,
        "games": [],
        "p1_fs": 0,
        "p2_fs": 0
    }

    match_volatility = calcular_match_volatility(e1, e2, surface)

    if p1_big or p2_big:
        match_volatility += 0.006

    for _ in range(n):
        sets1 = 0
        sets2 = 0

        games = 0

        tb_seen = False

        shift = np.random.normal(0, match_volatility)

        first_set_done = False

        while sets1 < sets_to_win and sets2 < sets_to_win:
            g1, g2, tb = sim_set(
                hold1,
                hold2,
                surface,
                shift,
                p1_big,
                p2_big
            )

            games += g1 + g2

            if tb:
                tb_seen = True

            if not first_set_done:
                if g1 > g2:
                    res["p1_fs"] += 1
                else:
                    res["p2_fs"] += 1

                first_set_done = True

            if g1 > g2:
                sets1 += 1
            else:
                sets2 += 1

        if sets1 > sets2:
            res["p1"] += 1
        else:
            res["p2"] += 1

        if sets1 == 2 and sets2 == 1:
            res["set3"] += 1

        if sets2 == 2 and sets1 == 1:
            res["set3"] += 1

        if tb_seen:
            res["tb"] += 1

        res["games"].append(games)

    return (
        res,
        hold1,
        hold2,
        raw_hold1,
        raw_hold2,
        ret1,
        ret2,
        p1_profile,
        p2_profile,
        match_volatility
    )


# =========================================================
# UI
# =========================================================

with st.sidebar:
    st.header("🎾 Tennis IA v11.7")
    st.caption("Return Strength Engine")

    circuito = st.radio(
        "Circuito",
        ["ATP", "WTA"]
    )

db = cargar_datos(circuito)

players = sorted(db.keys())

with st.sidebar:
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
    p1_name = st.selectbox("Jugador 1", players)

with c2:
    p2_name = st.selectbox(
        "Jugador 2",
        players,
        index=min(1, len(players)-1)
    )

# =========================================================
# RUN
# =========================================================

if st.button("🚀 ANALIZAR PARTIDO", use_container_width=True):
    d1 = db[p1_name]
    d2 = db[p2_name]

    best_of = 5 if "5" in format_match else 3

    with st.spinner(f"Simulando {sims:,} partidos..."):
        (
            res,
            hold1,
            hold2,
            raw_hold1,
            raw_hold2,
            ret1,
            ret2,
            p1_profile,
            p2_profile,
            match_volatility
        ) = sim_match(
            d1,
            d2,
            surface,
            circuito,
            best_of,
            sims
        )

    p1 = res["p1"] / sims
    p2 = res["p2"] / sims

    p1_fs = res["p1_fs"] / sims
    p2_fs = res["p2_fs"] / sims

    set3 = res["set3"] / sims
    tb = res["tb"] / sims

    games = res["games"]

    avg_games = np.mean(games)
    med_games = np.median(games)

    over18 = sum(x > 18.5 for x in games) / sims
    over20 = sum(x > 20.5 for x in games) / sims
    over21 = sum(x > 21.5 for x in games) / sims
    over22 = sum(x > 22.5 for x in games) / sims

    under22 = 1 - over22

    elo_ref = elo_prob(
        d1[surface],
        d2[surface]
    )

    risk = "🟢 Riesgo bajo"

    if max(p1, p2) < 0.56:
        risk = "🔴 Riesgo alto"

    elif max(p1, p2) < 0.63:
        risk = "🟡 Riesgo medio"

    # =====================================================
    # MAIN
    # =====================================================

    st.divider()

    st.subheader("🏆 Ganador del Partido")

    r1, r2 = st.columns(2)

    with r1:
        st.metric(
            d1["Player"],
            f"{p1:.1%}",
            nivel(p1)
        )

        st.caption(
            f"Rank #{d1['Rank']} · Elo {surface}: {d1[surface]:.0f}"
        )

    with r2:
        st.metric(
            d2["Player"],
            f"{p2:.1%}",
            nivel(p2)
        )

        st.caption(
            f"Rank #{d2['Rank']} · Elo {surface}: {d2[surface]:.0f}"
        )

    st.caption(
        f"Referencia Elo puro: {elo_ref:.1%} / {1-elo_ref:.1%} · {risk}"
    )

    # =====================================================
    # FIRST SET
    # =====================================================

    st.divider()

    st.subheader("🎾 Primer Set")

    fs1, fs2 = st.columns(2)

    with fs1:
        st.metric(
            f"{d1['Player']} gana",
            f"{p1_fs:.1%}",
            nivel(p1_fs)
        )

    with fs2:
        st.metric(
            f"{d2['Player']} gana",
            f"{p2_fs:.1%}",
            nivel(p2_fs)
        )

    # =====================================================
    # MARKETS
    # =====================================================

    st.divider()

    st.subheader("📊 Mercados")

    m1, m2, m3, m4 = st.columns(4)

    with m1:
        st.metric("Over 18.5", f"{over18:.1%}", nivel(over18))

    with m2:
        st.metric("Over 20.5", f"{over20:.1%}", nivel(over20))

    with m3:
        st.metric("Over 22.5", f"{over22:.1%}", nivel(over22))

    with m4:
        st.metric("Under 22.5", f"{under22:.1%}", nivel(under22))

    # =====================================================
    # EXTRA
    # =====================================================

    e1, e2, e3 = st.columns(3)

    with e1:
        st.metric("3 sets", f"{set3:.1%}", nivel(set3))

    with e2:
        st.metric("Tie-break", f"{tb:.1%}", nivel(tb))

    with e3:
        st.metric("Media games", f"{avg_games:.1f}")

    st.caption(f"Mediana games: {med_games:.0f}")

    # =====================================================
    # HOLD / RETURN
    # =====================================================

    st.divider()

    st.subheader("🎾 Hold / Return Engine")

    h1, h2 = st.columns(2)

    with h1:
        st.metric(
            d1["Player"],
            f"{hold1:.1%}",
            f"Raw hold {raw_hold1:.1%}"
        )

        st.caption(
            f"{perfil_legible(p1_profile)} · Return strength {ret1:.1%}"
        )

    with h2:
        st.metric(
            d2["Player"],
            f"{hold2:.1%}",
            f"Raw hold {raw_hold2:.1%}"
        )

        st.caption(
            f"{perfil_legible(p2_profile)} · Return strength {ret2:.1%}"
        )

    # =====================================================
    # DATA
    # =====================================================

    st.divider()

    st.subheader("🔎 Diagnóstico")

    dcol1, dcol2 = st.columns(2)

    with dcol1:
        st.write("Stats:", "✅" if d1["Stats"]["found_stats"] else "❌")
        st.write("Ace%:", f"{d1['Stats']['ace']:.1%}")
        st.write("Hold%:", f"{d1['Stats']['hold']:.1%}")
        st.write("Tipo:", d1["Stats"]["match_type"])

    with dcol2:
        st.write("Stats:", "✅" if d2["Stats"]["found_stats"] else "❌")
        st.write("Ace%:", f"{d2['Stats']['ace']:.1%}")
        st.write("Hold%:", f"{d2['Stats']['hold']:.1%}")
        st.write("Tipo:", d2["Stats"]["match_type"])

    # =====================================================
    # PROFILE
    # =====================================================

    st.divider()

    st.subheader("🧠 Perfil del Partido")

    tags = []

    if p1_profile in ["big_server", "elite_server"]:
        tags.append(f"🚀 {d1['Player']} gran sacador")

    if p2_profile in ["big_server", "elite_server"]:
        tags.append(f"🚀 {d2['Player']} gran sacador")

    if set3 > 0.45:
        tags.append("⚠️ Partido volátil")

    if tb > 0.32:
        tags.append("🎯 Tie-break probable")

    if avg_games > 24:
        tags.append("📈 Partido largo")

    if avg_games < 21:
        tags.append("📉 Partido corto")

    if max(p1, p2) < 0.55:
        tags.append("⚠️ Favorito débil")

    if match_volatility > 0.06:
        tags.append("🌪️ Alta volatilidad por diferencia Elo/superficie")

    if abs(ret1 - ret2) > 0.05:
        mejor_restador = d1["Player"] if ret1 > ret2 else d2["Player"]
        tags.append(f"🧱 Mejor restador: {mejor_restador}")

    if tags:
        st.info(" · ".join(tags))

    # =====================================================
    # SIGNAL
    # =====================================================

    st.divider()

    st.subheader("🎯 Señal principal del modelo")

    markets = {
        "ML favorito": max(p1, p2),
        "Over 18.5": over18,
        "Over 20.5": over20,
        "Over 22.5": over22,
        "Under 22.5": under22,
        "Tie-break": tb
    }

    best_market = max(markets.items(), key=lambda x: x[1])

    st.success(
        f"{best_market[0]} → {best_market[1]:.1%}"
    )

    st.divider()

    st.caption(
        f"Tennis IA v11.7 · Return Strength Engine · {sims:,} simulaciones Monte Carlo"
    )