import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import glob
import unicodedata
from difflib import SequenceMatcher

# =========================================================
# TENNIS IA v12
# PREDICTOR + HISTORICAL VALIDATOR
# =========================================================

st.set_page_config(
    page_title="Tennis IA v12",
    page_icon="🎾",
    layout="wide"
)

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


def tokens(txt):
    t = normalizar_texto(txt)
    t = re.sub(r"\[.*?\]|\(.*?\)", "", t)
    return re.findall(r"[A-Z]+", t.upper())


def similitud_nombre(a, b):
    ac = limpiar(a)
    bc = limpiar(b)

    if not ac or not bc:
        return 0.0

    if ac == bc:
        return 1.0

    ta = tokens(a)
    tb = tokens(b)

    sa = set(ta)
    sb = set(tb)

    token_score = 0
    if sa and sb:
        token_score = len(sa & sb) / len(sa | sb)

    # Caso histórico tipo "Tiafoe F." vs "Frances Tiafoe"
    if len(ta) >= 2 and len(tb) >= 2:
        surname_a = ta[0]
        initial_a = ta[1][0]

        for full_token in tb:
            if surname_a == full_token:
                for other in tb:
                    if other != surname_a and other.startswith(initial_a):
                        token_score = max(token_score, 0.94)

    if len(tb) >= 2 and len(ta) >= 2:
        surname_b = tb[0]
        initial_b = tb[1][0]

        for full_token in ta:
            if surname_b == full_token:
                for other in ta:
                    if other != surname_b and other.startswith(initial_b):
                        token_score = max(token_score, 0.94)

    seq_score = SequenceMatcher(None, ac, bc).ratio()

    return max(token_score, seq_score)


def buscar_columna(df, posibles):
    cols_clean = {limpiar(c): c for c in df.columns}

    for p in posibles:
        pc = limpiar(p)
        if pc in cols_clean:
            return cols_clean[pc]

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
# RUTAS
# =========================================================

def rutas(circuito):
    base = f"datos/{circuito.lower()}"

    return {
        "base": base,
        "elo": f"{base}/{circuito.lower()}_elo.xlsx",
        "serve": f"{base}/{circuito.lower()}_serve.xlsx",
        "return": f"{base}/{circuito.lower()}_return.xlsx",
        "break": f"{base}/{circuito.lower()}_break.xlsx",
        "historicos": f"{base}/historicos"
    }


# =========================================================
# DEFAULTS
# =========================================================

def stats_default_por_elo(elo_surface, rank=999, surface="Clay", circuito="ATP"):
    if elo_surface >= 1800:
        hold = 0.825
        ace = 0.075
        ret = 0.300
        brk = 0.300
    elif elo_surface >= 1700:
        hold = 0.810
        ace = 0.070
        ret = 0.285
        brk = 0.285
    elif elo_surface >= 1600:
        hold = 0.795
        ace = 0.065
        ret = 0.270
        brk = 0.270
    elif elo_surface >= 1500:
        hold = 0.780
        ace = 0.055
        ret = 0.250
        brk = 0.250
    else:
        hold = 0.760
        ace = 0.050
        ret = 0.225
        brk = 0.225

    if rank <= 50:
        hold += 0.006
        ret += 0.012
        brk += 0.012
    elif rank <= 100:
        hold += 0.003
        ret += 0.006
        brk += 0.006
    elif rank > 180:
        hold -= 0.006
        ret -= 0.006
        brk -= 0.006

    if surface == "Clay":
        hold -= 0.010
        ret += 0.025
        brk += 0.025
        ace -= 0.005
    elif surface == "Grass":
        hold += 0.012
        ret -= 0.012
        brk -= 0.012
        ace += 0.006

    if circuito == "WTA":
        hold -= 0.035
        ret += 0.030
        brk += 0.030
        ace -= 0.015

    ace = np.clip(ace, 0.035, 0.090)

    return {
        "found_stats": False,
        "raw_name_stats": "NO ENCONTRADO",
        "hold": np.clip(hold, 0.72, 0.84),
        "ace": ace,
        "df": 0.035,
        "1in": 0.62,
        "1w": 0.70,
        "2w": 0.50,
        "rpw": np.clip(ret, 0.18, 0.38),
        "break_pct": np.clip(brk, 0.15, 0.42),
        "bp_conv": 0.38,
        "bp_saved": 0.58,
        "serve_profile": perfil_saque(ace),
        "match_type": "default_elo"
    }


# =========================================================
# CARGA PLAYER PROFILES
# =========================================================

def merge_stats(base, extra):
    out = base.copy()
    for k, v in extra.items():
        if v is not None:
            out[k] = v
    return out


def leer_archivo_stats(path, tipo):
    stats = {}

    if not os.path.exists(path):
        return stats

    df = pd.read_excel(path)

    col_player = buscar_columna(df, ["Player", "Name", "Jugador"])

    if col_player is None:
        return stats

    if tipo == "serve":
        col_ace = buscar_columna(df, ["Ace%", "Ace"])
        col_df = buscar_columna(df, ["DF%", "DF"])
        col_1in = buscar_columna(df, ["1stIn", "1st In"])
        col_1w = buscar_columna(df, ["1st%", "1st Won"])
        col_2w = buscar_columna(df, ["2nd%", "2nd Won"])
        col_hold = buscar_columna(df, ["Hld%", "Hold%", "Hold"])

        for _, row in df.iterrows():
            nombre = normalizar_texto(row.get(col_player, ""))
            nid = limpiar(nombre)

            if not nid:
                continue

            ace = leer_porcentaje(row.get(col_ace), 0.05)

            stats[nid] = {
                "found_stats": True,
                "raw_name_stats": nombre,
                "ace": ace,
                "df": leer_porcentaje(row.get(col_df), 0.035),
                "1in": leer_porcentaje(row.get(col_1in), 0.62),
                "1w": leer_porcentaje(row.get(col_1w), 0.70),
                "2w": leer_porcentaje(row.get(col_2w), 0.50),
                "hold": leer_porcentaje(row.get(col_hold), 0.78),
                "serve_profile": perfil_saque(ace),
                "match_type": "serve"
            }

    elif tipo == "return":
        col_rpw = buscar_columna(df, ["RPW", "RPW%", "Return Points Won", "ReturnPointsWon"])
        col_brk = buscar_columna(df, ["Brk%", "Break%", "Break"])
        col_v1 = buscar_columna(df, ["v1st%", "v1st", "vs1st"])
        col_v2 = buscar_columna(df, ["v2nd%", "v2nd", "vs2nd"])

        for _, row in df.iterrows():
            nombre = normalizar_texto(row.get(col_player, ""))
            nid = limpiar(nombre)

            if not nid:
                continue

            stats[nid] = {
                "found_return": True,
                "raw_name_return": nombre,
                "rpw": leer_porcentaje(row.get(col_rpw), None) if col_rpw else None,
                "break_pct": leer_porcentaje(row.get(col_brk), None) if col_brk else None,
                "v1st": leer_porcentaje(row.get(col_v1), None) if col_v1 else None,
                "v2nd": leer_porcentaje(row.get(col_v2), None) if col_v2 else None
            }

    elif tipo == "break":
        col_bpconv = buscar_columna(df, ["BPConv%", "BP Conv%", "Break Points Converted"])
        col_bpsaved = buscar_columna(df, ["BPSvd%", "BP Saved%", "Break Points Saved"])
        col_brkset = buscar_columna(df, ["Breaks/Set", "Brk/Set", "Breaks Set"])

        for _, row in df.iterrows():
            nombre = normalizar_texto(row.get(col_player, ""))
            nid = limpiar(nombre)

            if not nid:
                continue

            stats[nid] = {
                "found_break": True,
                "raw_name_break": nombre,
                "bp_conv": leer_porcentaje(row.get(col_bpconv), None) if col_bpconv else None,
                "bp_saved": leer_porcentaje(row.get(col_bpsaved), None) if col_bpsaved else None,
                "breaks_set": leer_float(row.get(col_brkset), None) if col_brkset else None
            }

    return stats


def buscar_stats(nombre, stats_map):
    nid = limpiar(nombre)

    if nid in stats_map:
        return stats_map[nid]

    mejor = None
    mejor_score = 0

    for sid, data in stats_map.items():
        score = max(
            similitud_nombre(nombre, sid),
            similitud_nombre(nombre, data.get("raw_name_stats", sid))
        )

        if score > mejor_score:
            mejor_score = score
            mejor = data

    if mejor is not None and mejor_score >= 0.72:
        out = mejor.copy()
        out["match_type"] = "aproximado"
        return out

    return None


@st.cache_data
def cargar_datos(circuito):
    r = rutas(circuito)

    serve_map = leer_archivo_stats(r["serve"], "serve")
    return_map = leer_archivo_stats(r["return"], "return")
    break_map = leer_archivo_stats(r["break"], "break")

    stats_map = {}

    all_ids = set(serve_map.keys()) | set(return_map.keys()) | set(break_map.keys())

    for nid in all_ids:
        base = {
            "found_stats": False,
            "raw_name_stats": "NO ENCONTRADO",
            "hold": 0.78,
            "ace": 0.05,
            "df": 0.035,
            "1in": 0.62,
            "1w": 0.70,
            "2w": 0.50,
            "rpw": None,
            "break_pct": None,
            "bp_conv": None,
            "bp_saved": None,
            "serve_profile": "normal",
            "match_type": "stats"
        }

        if nid in serve_map:
            base = merge_stats(base, serve_map[nid])

        if nid in return_map:
            base = merge_stats(base, return_map[nid])

        if nid in break_map:
            base = merge_stats(base, break_map[nid])

        if base.get("serve_profile", "normal") == "normal":
            base["serve_profile"] = perfil_saque(base.get("ace", 0.05))

        stats_map[nid] = base

    players = {}

    if not os.path.exists(r["elo"]):
        return players

    df = pd.read_excel(r["elo"])

    col_player = buscar_columna(df, ["Player", "Name", "Jugador"])
    col_rank = buscar_columna(df, ["ATP Rank", "WTA Rank", "Rank"])
    col_elo = buscar_columna(df, ["Elo"])
    col_hard = buscar_columna(df, ["hElo", "Hard Elo"])
    col_clay = buscar_columna(df, ["cElo", "Clay Elo"])
    col_grass = buscar_columna(df, ["gElo", "Grass Elo"])

    if col_player is None:
        return players

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
            stats = stats_default_por_elo(clay, rank, "Clay", circuito)

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
# ENGINES
# =========================================================

def calc_hold(stats, elo_diff, surface, circuito):
    base = stats.get("hold", 0.78)
    ace = stats.get("ace", 0.05)
    profile = stats.get("serve_profile", "normal")

    if circuito == "ATP":
        surface_adj = {
            "Hard": -0.005,
            "Clay": -0.105,
            "Grass": +0.015
        }
    else:
        surface_adj = {
            "Hard": -0.015,
            "Clay": -0.085,
            "Grass": +0.010
        }

    elo_adj = np.clip(elo_diff / 3900, -0.040, 0.040)

    serve_bonus = 0

    if profile == "good_server":
        serve_bonus += 0.006
    elif profile == "big_server":
        serve_bonus += 0.012
    elif profile == "elite_server":
        serve_bonus += 0.018

    bp_saved = stats.get("bp_saved", None)
    clutch_bonus = 0

    if bp_saved is not None:
        clutch_bonus = np.clip((bp_saved - 0.58) * 0.05, -0.010, 0.012)

    hold = (
        base
        + surface_adj[surface]
        + elo_adj
        + serve_bonus
        + ace * 0.01
        + clutch_bonus
    )

    return np.clip(hold, 0.46, 0.84)


def calc_return_strength(stats, elo_surface, surface):
    if stats.get("rpw", None) is not None:
        ret = stats["rpw"]
    elif stats.get("break_pct", None) is not None:
        ret = stats["break_pct"]
    else:
        hold = stats.get("hold", 0.78)
        ret = 1.0 - hold + ((elo_surface - 1500) / 4200)

    if stats.get("break_pct", None) is not None:
        ret = (ret * 0.65) + (stats["break_pct"] * 0.35)

    if stats.get("bp_conv", None) is not None:
        ret += np.clip((stats["bp_conv"] - 0.38) * 0.05, -0.010, 0.012)

    if surface == "Clay":
        ret += 0.020
    elif surface == "Grass":
        ret -= 0.010

    return np.clip(ret, 0.12, 0.40)


def aplicar_return_pressure(hold1, hold2, ret1, ret2, surface):
    if surface == "Clay":
        weight = 0.19
    elif surface == "Hard":
        weight = 0.10
    else:
        weight = 0.09

    h1 = hold1 - (ret2 * weight)
    h2 = hold2 - (ret1 * weight)

    return np.clip(h1, 0.44, 0.84), np.clip(h2, 0.44, 0.84)


def calcular_match_volatility(e1, e2, surface):
    elo_gap = abs(e1 - e2)

    vol = 0.040

    if elo_gap > 300:
        vol += 0.018
    elif elo_gap > 200:
        vol += 0.010
    elif elo_gap > 120:
        vol += 0.005

    if surface == "Clay":
        vol += 0.010
    elif surface == "Grass":
        vol -= 0.004

    return vol


def sim_set(hold1, hold2, surface, shift, p1_big, p2_big):
    g1 = 0
    g2 = 0
    tb = False
    server = random.choice([1, 2])

    if surface == "Clay":
        noise = 0.068
        pressure = -0.085
    elif surface == "Hard":
        noise = 0.038
        pressure = -0.030
    else:
        noise = 0.028
        pressure = -0.018

    while True:
        extra = pressure if g1 >= 4 and g2 >= 4 else 0

        h1 = np.clip(np.random.normal(hold1 + shift, noise) + extra, 0.30, 0.93)
        h2 = np.clip(np.random.normal(hold2 - shift, noise) + extra, 0.30, 0.93)

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

            if surface == "Hard":
                p_tb += 0.03

            p_tb = np.clip(p_tb, 0.32, 0.72)

            if random.random() < p_tb:
                return 7, 6, tb

            return 6, 7, tb


def sim_match(d1, d2, surface, circuito, best_of=3, n=5000):
    e1 = d1[surface]
    e2 = d2[surface]

    elo_diff = e1 - e2

    s1 = d1["Stats"]
    s2 = d2["Stats"]

    raw_hold1 = calc_hold(s1, elo_diff, surface, circuito)
    raw_hold2 = calc_hold(s2, -elo_diff, surface, circuito)

    ret1 = calc_return_strength(s1, e1, surface)
    ret2 = calc_return_strength(s2, e2, surface)

    hold1, hold2 = aplicar_return_pressure(raw_hold1, raw_hold2, ret1, ret2, surface)

    p1_profile = s1.get("serve_profile", "normal")
    p2_profile = s2.get("serve_profile", "normal")

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

    vol = calcular_match_volatility(e1, e2, surface)

    if p1_big or p2_big:
        vol += 0.006

    for _ in range(n):
        sets1 = 0
        sets2 = 0
        games = 0
        tb_seen = False
        first_done = False

        shift = np.random.normal(0, vol)

        while sets1 < sets_to_win and sets2 < sets_to_win:
            g1, g2, tb = sim_set(hold1, hold2, surface, shift, p1_big, p2_big)

            games += g1 + g2

            if tb:
                tb_seen = True

            if not first_done:
                if g1 > g2:
                    res["p1_fs"] += 1
                else:
                    res["p2_fs"] += 1
                first_done = True

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

    return {
        "p1": res["p1"] / n,
        "p2": res["p2"] / n,
        "p1_fs": res["p1_fs"] / n,
        "p2_fs": res["p2_fs"] / n,
        "set3": res["set3"] / n,
        "tb": res["tb"] / n,
        "games": res["games"],
        "hold1": hold1,
        "hold2": hold2,
        "raw_hold1": raw_hold1,
        "raw_hold2": raw_hold2,
        "ret1": ret1,
        "ret2": ret2,
        "p1_profile": p1_profile,
        "p2_profile": p2_profile,
        "vol": vol
    }


# =========================================================
# HISTÓRICOS
# =========================================================

def encontrar_jugador(nombre_hist, db):
    if nombre_hist in db:
        return nombre_hist

    mejor = None
    score_best = 0

    for nombre in db.keys():
        score = similitud_nombre(nombre_hist, nombre)

        if score > score_best:
            score_best = score
            mejor = nombre

    if mejor is not None and score_best >= 0.70:
        return mejor

    return None


def total_games_row(row):
    total = 0

    for i in range(1, 6):
        w = row.get(f"W{i}", np.nan)
        l = row.get(f"L{i}", np.nan)

        if not pd.isna(w) and not pd.isna(l):
            total += int(w) + int(l)

    return total


def hay_tiebreak_row(row):
    for i in range(1, 6):
        w = row.get(f"W{i}", np.nan)
        l = row.get(f"L{i}", np.nan)

        if not pd.isna(w) and not pd.isna(l):
            if (int(w) == 7 and int(l) == 6) or (int(w) == 6 and int(l) == 7):
                return True

    return False


def cargar_historicos(circuito):
    r = rutas(circuito)
    folder = r["historicos"]

    files = sorted(glob.glob(os.path.join(folder, "*.xlsx")))

    dfs = []

    for f in files:
        try:
            df = pd.read_excel(f)
            df["SourceFile"] = os.path.basename(f)
            dfs.append(df)
        except:
            pass

    if not dfs:
        return pd.DataFrame()

    return pd.concat(dfs, ignore_index=True)


def validar_historico(db, hist_df, circuito, surface_filter, max_matches, sims_bt):
    rows = []

    df = hist_df.copy()

    if surface_filter != "Todas":
        df = df[df["Surface"].astype(str) == surface_filter]

    df = df[df["Comment"].astype(str).str.contains("Completed", na=False)]

    if max_matches:
        df = df.tail(max_matches)

    progress = st.progress(0)
    total = len(df)

    for idx, (_, row) in enumerate(df.iterrows()):
        winner_hist = normalizar_texto(row.get("Winner", ""))
        loser_hist = normalizar_texto(row.get("Loser", ""))

        surface = str(row.get("Surface", "Hard"))
        best_of = int(leer_float(row.get("Best of", 3), 3))

        p_win_key = encontrar_jugador(winner_hist, db)
        p_los_key = encontrar_jugador(loser_hist, db)

        if p_win_key is None or p_los_key is None:
            continue

        d_win = db[p_win_key]
        d_los = db[p_los_key]

        # Simulamos en orden Winner vs Loser.
        sim = sim_match(d_win, d_los, surface, circuito, best_of, sims_bt)

        p_model_winner = sim["p1"]
        fav_model_is_winner = p_model_winner >= 0.50

        games_real = total_games_row(row)
        set3_real = int(row.get("Wsets", 0)) == 2 and int(row.get("Lsets", 0)) == 1
        tb_real = hay_tiebreak_row(row)

        over18_real = games_real > 18.5
        over20_real = games_real > 20.5
        over22_real = games_real > 22.5

        games_model = sim["games"]

        over18_model = sum(x > 18.5 for x in games_model) / sims_bt
        over20_model = sum(x > 20.5 for x in games_model) / sims_bt
        over22_model = sum(x > 22.5 for x in games_model) / sims_bt

        rows.append({
            "Date": row.get("Date", ""),
            "Tournament": row.get("Tournament", ""),
            "Surface": surface,
            "WinnerHist": winner_hist,
            "LoserHist": loser_hist,
            "WinnerMatched": p_win_key,
            "LoserMatched": p_los_key,
            "ModelWinnerProb": p_model_winner,
            "ModelFavWasWinner": fav_model_is_winner,
            "RealGames": games_real,
            "ModelAvgGames": np.mean(games_model),
            "Real3Sets": set3_real,
            "Model3Sets": sim["set3"],
            "RealTB": tb_real,
            "ModelTB": sim["tb"],
            "RealOver18": over18_real,
            "ModelOver18": over18_model,
            "RealOver20": over20_real,
            "ModelOver20": over20_model,
            "RealOver22": over22_real,
            "ModelOver22": over22_model,
            "WinnerStats": d_win["Stats"]["match_type"],
            "LoserStats": d_los["Stats"]["match_type"]
        })

        if total > 0:
            progress.progress(min((idx + 1) / total, 1.0))

    progress.empty()

    return pd.DataFrame(rows)


# =========================================================
# UI
# =========================================================

with st.sidebar:
    st.header("🎾 Tennis IA v12")
    st.caption("Predictor + Historical Validator")

    if st.button("🧹 Limpiar caché"):
        st.cache_data.clear()
        st.success("Caché limpiada")

    circuito = st.radio("Circuito", ["ATP", "WTA"])
    modo = st.radio("Modo", ["Predictor", "Validador histórico"])

db = cargar_datos(circuito)

if not db:
    st.error("No se encontraron jugadores. Revisa carpetas y archivos.")
    st.stop()

# =========================================================
# MODO PREDICTOR
# =========================================================

if modo == "Predictor":
    with st.sidebar:
        players = sorted(db.keys())

        surface = st.selectbox("Superficie", ["Hard", "Clay", "Grass"])

        format_match = st.radio(
            "Formato",
            ["ATP Tour (3 sets)", "Grand Slam (5 sets)"]
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

    if st.button("🚀 ANALIZAR PARTIDO", use_container_width=True):
        d1 = db[p1_name]
        d2 = db[p2_name]

        best_of = 5 if "5" in format_match else 3

        with st.spinner(f"Simulando {sims:,} partidos..."):
            sim = sim_match(d1, d2, surface, circuito, best_of, sims)

        p1 = sim["p1"]
        p2 = sim["p2"]

        games = sim["games"]

        avg_games = np.mean(games)
        med_games = np.median(games)

        over18 = sum(x > 18.5 for x in games) / sims
        over20 = sum(x > 20.5 for x in games) / sims
        over22 = sum(x > 22.5 for x in games) / sims
        under22 = 1 - over22

        elo_ref = elo_prob(d1[surface], d2[surface])

        risk = "🟢 Riesgo bajo"
        if max(p1, p2) < 0.56:
            risk = "🔴 Riesgo alto"
        elif max(p1, p2) < 0.63:
            risk = "🟡 Riesgo medio"

        st.divider()
        st.subheader("🏆 Ganador del Partido")

        r1, r2 = st.columns(2)

        with r1:
            st.metric(d1["Player"], f"{p1:.1%}", nivel(p1))
            st.caption(f"Rank #{d1['Rank']} · Elo {surface}: {d1[surface]:.0f}")

        with r2:
            st.metric(d2["Player"], f"{p2:.1%}", nivel(p2))
            st.caption(f"Rank #{d2['Rank']} · Elo {surface}: {d2[surface]:.0f}")

        st.caption(f"Referencia Elo puro: {elo_ref:.1%} / {1-elo_ref:.1%} · {risk}")

        st.divider()
        st.subheader("🎾 Primer Set")

        fs1, fs2 = st.columns(2)

        with fs1:
            st.metric(f"{d1['Player']} gana", f"{sim['p1_fs']:.1%}", nivel(sim["p1_fs"]))

        with fs2:
            st.metric(f"{d2['Player']} gana", f"{sim['p2_fs']:.1%}", nivel(sim["p2_fs"]))

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

        e1, e2, e3 = st.columns(3)

        with e1:
            st.metric("3 sets", f"{sim['set3']:.1%}", nivel(sim["set3"]))

        with e2:
            st.metric("Tie-break", f"{sim['tb']:.1%}", nivel(sim["tb"]))

        with e3:
            st.metric("Media games", f"{avg_games:.1f}")

        st.caption(f"Mediana games: {med_games:.0f}")

        st.divider()
        st.subheader("🎾 Hold / Return Engine")

        h1, h2 = st.columns(2)

        with h1:
            st.metric(d1["Player"], f"{sim['hold1']:.1%}", f"Raw hold {sim['raw_hold1']:.1%}")
            st.caption(f"{perfil_legible(sim['p1_profile'])} · Return strength {sim['ret1']:.1%}")

        with h2:
            st.metric(d2["Player"], f"{sim['hold2']:.1%}", f"Raw hold {sim['raw_hold2']:.1%}")
            st.caption(f"{perfil_legible(sim['p2_profile'])} · Return strength {sim['ret2']:.1%}")

        st.divider()
        st.subheader("🔎 Diagnóstico")

        dcol1, dcol2 = st.columns(2)

        with dcol1:
            st.write("Stats:", "✅" if d1["Stats"]["found_stats"] else "❌")
            st.write("Ace%:", f"{d1['Stats']['ace']:.1%}")
            st.write("Hold%:", f"{d1['Stats']['hold']:.1%}")
            st.write("RPW:", "N/A" if d1["Stats"].get("rpw") is None else f"{d1['Stats']['rpw']:.1%}")
            st.write("Break%:", "N/A" if d1["Stats"].get("break_pct") is None else f"{d1['Stats']['break_pct']:.1%}")
            st.write("Tipo:", d1["Stats"]["match_type"])

        with dcol2:
            st.write("Stats:", "✅" if d2["Stats"]["found_stats"] else "❌")
            st.write("Ace%:", f"{d2['Stats']['ace']:.1%}")
            st.write("Hold%:", f"{d2['Stats']['hold']:.1%}")
            st.write("RPW:", "N/A" if d2["Stats"].get("rpw") is None else f"{d2['Stats']['rpw']:.1%}")
            st.write("Break%:", "N/A" if d2["Stats"].get("break_pct") is None else f"{d2['Stats']['break_pct']:.1%}")
            st.write("Tipo:", d2["Stats"]["match_type"])

        st.divider()
        st.subheader("🧠 Perfil del Partido")

        tags = []

        if sim["p1_profile"] in ["big_server", "elite_server"]:
            tags.append(f"🚀 {d1['Player']} gran sacador")

        if sim["p2_profile"] in ["big_server", "elite_server"]:
            tags.append(f"🚀 {d2['Player']} gran sacador")

        if sim["set3"] > 0.45:
            tags.append("⚠️ Partido volátil")

        if sim["tb"] > 0.32:
            tags.append("🎯 Tie-break probable")

        if avg_games > 24:
            tags.append("📈 Partido largo")

        if avg_games < 21:
            tags.append("📉 Partido corto")

        if max(p1, p2) < 0.55:
            tags.append("⚠️ Favorito débil")

        if sim["vol"] > 0.06:
            tags.append("🌪️ Alta volatilidad por diferencia Elo/superficie")

        if abs(sim["ret1"] - sim["ret2"]) > 0.05:
            mejor_restador = d1["Player"] if sim["ret1"] > sim["ret2"] else d2["Player"]
            tags.append(f"🧱 Mejor restador: {mejor_restador}")

        if tags:
            st.info(" · ".join(tags))
        else:
            st.info("Sin perfil extremo detectado.")

        st.divider()
        st.subheader("🎯 Señal principal del modelo")

        markets = {
            "ML favorito": max(p1, p2),
            "Over 18.5": over18,
            "Over 20.5": over20,
            "Over 22.5": over22,
            "Under 22.5": under22,
            "Tie-break": sim["tb"]
        }

        best_market = max(markets.items(), key=lambda x: x[1])

        st.success(f"{best_market[0]} → {best_market[1]:.1%}")

        st.divider()
        st.caption(f"Tennis IA v12 · Predictor · {sims:,} simulaciones Monte Carlo")


# =========================================================
# MODO VALIDADOR HISTÓRICO
# =========================================================

else:
    st.subheader("📚 Validador histórico")

    hist_df = cargar_historicos(circuito)

    if hist_df.empty:
        st.error("No se encontraron históricos. Revisa datos/atp/historicos o datos/wta/historicos.")
        st.stop()

    with st.sidebar:
        surface_filter = st.selectbox("Superficie histórica", ["Todas", "Hard", "Clay", "Grass"])
        max_matches = st.number_input("Máx partidos a validar", min_value=10, max_value=5000, value=100, step=50)
        sims_bt = st.select_slider("Simulaciones por partido", [300, 500, 1000, 2000], value=500)

    st.info(
        f"Históricos cargados: {len(hist_df):,} partidos. "
        f"Para empezar, prueba con 100-300 partidos y 500 simulaciones."
    )

    if st.button("🚀 EJECUTAR VALIDACIÓN", use_container_width=True):
        with st.spinner("Validando partidos históricos..."):
            val = validar_historico(
                db,
                hist_df,
                circuito,
                surface_filter,
                int(max_matches),
                int(sims_bt)
            )

        if val.empty:
            st.error("No se pudieron emparejar partidos históricos con la base de jugadores.")
            st.stop()

        ml_acc = val["ModelFavWasWinner"].mean()

        over18_acc = ((val["ModelOver18"] >= 0.50) == val["RealOver18"]).mean()
        over20_acc = ((val["ModelOver20"] >= 0.50) == val["RealOver20"]).mean()
        over22_acc = ((val["ModelOver22"] >= 0.50) == val["RealOver22"]).mean()

        set3_acc = ((val["Model3Sets"] >= 0.50) == val["Real3Sets"]).mean()
        tb_acc = ((val["ModelTB"] >= 0.50) == val["RealTB"]).mean()

        games_error = np.mean(np.abs(val["ModelAvgGames"] - val["RealGames"]))

        st.divider()
        st.subheader("📊 Resumen validación")

        a1, a2, a3, a4 = st.columns(4)

        with a1:
            st.metric("ML accuracy", f"{ml_acc:.1%}")

        with a2:
            st.metric("Over 20.5 accuracy", f"{over20_acc:.1%}")

        with a3:
            st.metric("3 sets accuracy", f"{set3_acc:.1%}")

        with a4:
            st.metric("Error medio games", f"{games_error:.2f}")

        b1, b2, b3 = st.columns(3)

        with b1:
            st.metric("Over 18.5 accuracy", f"{over18_acc:.1%}")

        with b2:
            st.metric("Over 22.5 accuracy", f"{over22_acc:.1%}")

        with b3:
            st.metric("Tie-break accuracy", f"{tb_acc:.1%}")

        st.divider()
        st.subheader("📈 Calibración ML por tramos")

        val["ProbBin"] = pd.cut(
            val["ModelWinnerProb"],
            bins=[0, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00],
            labels=["0-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]
        )

        calib = val.groupby("ProbBin", observed=True).agg(
            Partidos=("ModelWinnerProb", "count"),
            ProbMedia=("ModelWinnerProb", "mean"),
            RealWinRate=("ModelFavWasWinner", "mean")
        ).reset_index()

        st.dataframe(calib, use_container_width=True)

        st.divider()
        st.subheader("🧾 Detalle partidos validados")

        st.dataframe(val, use_container_width=True)

        st.download_button(
            "⬇️ Descargar validación CSV",
            data=val.to_csv(index=False).encode("utf-8"),
            file_name="validacion_tennis_ia_v12.csv",
            mime="text/csv"
        )

        st.divider()
        st.caption(f"Tennis IA v12 · Validador histórico · {len(val):,} partidos validados")