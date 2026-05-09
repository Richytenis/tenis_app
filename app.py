
import streamlit as st
import pandas as pd
import numpy as np
import random, re, os, glob, unicodedata
from difflib import SequenceMatcher

st.set_page_config(page_title="Tennis IA v17.1", page_icon="🎾", layout="wide")

# =========================================================
# TENNIS IA v15
# Stable core + Hard Compression + Smart Tie-break + Analyzer
# =========================================================

def normalizar_texto(x):
    if pd.isna(x): return ""
    t = unicodedata.normalize("NFKD", str(x)).encode("ascii", "ignore").decode("ascii")
    return t.replace("\xa0", " ").strip()

def limpiar(x):
    t = re.sub(r"\[.*?\]|\(.*?\)", "", normalizar_texto(x))
    return re.sub(r"[^A-Z0-9]", "", t.upper())

def tokens(x):
    t = re.sub(r"\[.*?\]|\(.*?\)", "", normalizar_texto(x))
    return re.findall(r"[A-Z]+", t.upper())

def similitud_nombre(a, b):
    ac, bc = limpiar(a), limpiar(b)
    if not ac or not bc: return 0.0
    if ac == bc: return 1.0
    ta, tb = tokens(a), tokens(b)
    sa, sb = set(ta), set(tb)
    score = len(sa & sb) / len(sa | sb) if sa and sb else 0.0

    # "Tiafoe F." vs "Frances Tiafoe"
    if len(ta) >= 2 and len(tb) >= 2:
        surname, initial = ta[0], ta[1][0]
        if surname in tb and any(x != surname and x.startswith(initial) for x in tb):
            score = max(score, 0.94)
    if len(tb) >= 2 and len(ta) >= 2:
        surname, initial = tb[0], tb[1][0]
        if surname in ta and any(x != surname and x.startswith(initial) for x in ta):
            score = max(score, 0.94)

    return max(score, SequenceMatcher(None, ac, bc).ratio())

def buscar_columna(df, posibles):
    cols = {limpiar(c): c for c in df.columns}
    for p in posibles:
        if limpiar(p) in cols:
            return cols[limpiar(p)]
    return None

def leer_float(v, default):
    try:
        if pd.isna(v): return default
        s = str(v).replace(",", ".").replace("%", "").strip()
        if s == "": return default
        return float(s)
    except:
        return default

def leer_porcentaje(v, default):
    n = leer_float(v, default)
    if n is None: return None
    if n > 1: n /= 100
    return n

def elo_prob(e1, e2):
    return 1 / (1 + 10 ** ((e2 - e1) / 400))

def nivel(p):
    if p >= 0.72: return "🔥 Alta"
    if p >= 0.60: return "✅ Media-alta"
    if p >= 0.53: return "⚖️ Ajustada"
    return "⚠️ Baja"

def perfil_saque(ace):
    if ace >= 0.16: return "elite_server"
    if ace >= 0.12: return "big_server"
    if ace >= 0.08: return "good_server"
    return "normal"

def perfil_legible(p):
    return {
        "elite_server": "🚀 Elite server",
        "big_server": "🔥 Big server",
        "good_server": "✅ Buen sacador",
        "normal": "Normal"
    }.get(p, "Normal")

def calibrar_probabilidad(p, surface):
    if p >= 0.50:
        fav, sign = p, 1
    else:
        fav, sign = 1 - p, -1

    if fav < 0.58: shrink = 0.02
    elif fav < 0.65: shrink = 0.05
    elif fav < 0.72: shrink = 0.08
    elif fav < 0.80: shrink = 0.12
    else: shrink = 0.16

    if surface == "Clay": shrink += 0.02
    elif surface == "Hard": shrink += 0.01

    cal = 0.50 + (fav - 0.50) * (1 - shrink)
    cal = np.clip(cal, 0.50, 0.88)
    return cal if sign == 1 else 1 - cal

def edge_calibracion(raw, cal):
    d = abs(raw - cal)
    if d < 0.025: return "🟢 estable"
    if d < 0.055: return "🟡 algo inflada"
    return "🔴 muy inflada"

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

def ruta_stats_superficie(circuito, tipo, surface):
    """
    v15 Surface Adaptive:
    Intenta leer primero:
      datos/atp/atp_serve_hard.xlsx
      datos/atp/atp_return_clay.xlsx
      datos/atp/atp_break_grass.xlsx
    Si no existe, usa el archivo general:
      datos/atp/atp_serve.xlsx
    """
    base = f"datos/{circuito.lower()}"
    surf = str(surface).lower()
    specific = f"{base}/{circuito.lower()}_{tipo}_{surf}.xlsx"
    general = f"{base}/{circuito.lower()}_{tipo}.xlsx"
    return specific if os.path.exists(specific) else general

def merge_surface_stats(general_stats, surface_stats):
    """
    Combina general + superficie.
    La superficie pisa al general cuando trae dato.
    """
    out = general_stats.copy()
    for k, v in surface_stats.items():
        if v is not None:
            out[k] = v
    return out

def stats_filename_label(circuito, tipo, surface):
    path = ruta_stats_superficie(circuito, tipo, surface)
    return os.path.basename(path) if path else "N/A"

def stats_default_por_elo(elo_surface, rank=999, surface="Clay", circuito="ATP"):
    if elo_surface >= 1800: hold, ace, ret, brk = 0.825, 0.075, 0.300, 0.300
    elif elo_surface >= 1700: hold, ace, ret, brk = 0.810, 0.070, 0.285, 0.285
    elif elo_surface >= 1600: hold, ace, ret, brk = 0.795, 0.065, 0.270, 0.270
    elif elo_surface >= 1500: hold, ace, ret, brk = 0.780, 0.055, 0.250, 0.250
    else: hold, ace, ret, brk = 0.760, 0.050, 0.225, 0.225

    if rank <= 50: hold += 0.006; ret += 0.012; brk += 0.012
    elif rank <= 100: hold += 0.003; ret += 0.006; brk += 0.006
    elif rank > 180: hold -= 0.006; ret -= 0.006; brk -= 0.006

    if surface == "Clay": hold -= 0.010; ret += 0.025; brk += 0.025; ace -= 0.005
    elif surface == "Grass": hold += 0.012; ret -= 0.012; brk -= 0.012; ace += 0.006

    if circuito == "WTA": hold -= 0.035; ret += 0.030; brk += 0.030; ace -= 0.015

    ace = np.clip(ace, 0.035, 0.090)
    return {
        "found_stats": False, "raw_name_stats": "NO ENCONTRADO",
        "hold": np.clip(hold, 0.72, 0.84), "ace": ace, "df": 0.035,
        "1in": 0.62, "1w": 0.70, "2w": 0.50,
        "rpw": np.clip(ret, 0.18, 0.38),
        "break_pct": np.clip(brk, 0.15, 0.42),
        "bp_conv": 0.38, "bp_saved": 0.58,
        "serve_profile": perfil_saque(ace), "match_type": "default_elo"
    }

def merge_stats(base, extra):
    out = base.copy()
    for k, v in extra.items():
        if v is not None:
            out[k] = v
    return out

def leer_archivo_stats(path, tipo):
    stats = {}
    if not os.path.exists(path): return stats

    df = pd.read_excel(path)
    col_player = buscar_columna(df, ["Player", "Name", "Jugador"])
    if col_player is None: return stats

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
            if not nid: continue
            ace = leer_porcentaje(row.get(col_ace), 0.05)
            stats[nid] = {
                "found_stats": True, "raw_name_stats": nombre,
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
            if not nid: continue
            stats[nid] = {
                "found_return": True, "raw_name_return": nombre,
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
            if not nid: continue
            stats[nid] = {
                "found_break": True, "raw_name_break": nombre,
                "bp_conv": leer_porcentaje(row.get(col_bpconv), None) if col_bpconv else None,
                "bp_saved": leer_porcentaje(row.get(col_bpsaved), None) if col_bpsaved else None,
                "breaks_set": leer_float(row.get(col_brkset), None) if col_brkset else None
            }

    return stats

def buscar_stats(nombre, stats_map):
    nid = limpiar(nombre)
    if nid in stats_map: return stats_map[nid]
    mejor, best = None, 0
    for sid, data in stats_map.items():
        score = max(similitud_nombre(nombre, sid), similitud_nombre(nombre, data.get("raw_name_stats", sid)))
        if score > best:
            best, mejor = score, data
    if mejor is not None and best >= 0.72:
        out = mejor.copy()
        out["match_type"] = "aproximado"
        return out
    return None

@st.cache_data
def cargar_datos(circuito):
    r = rutas(circuito)
    fatigue_map = crear_fatigue_map(circuito)

    # =========================
    # Mapas generales
    # =========================
    serve_general = leer_archivo_stats(r["serve"], "serve")
    return_general = leer_archivo_stats(r["return"], "return")
    break_general = leer_archivo_stats(r["break"], "break")

    def construir_stats_map(serve_map, return_map, break_map):
        stats_map = {}
        all_ids = set(serve_map) | set(return_map) | set(break_map)

        for nid in all_ids:
            base = {
                "found_stats": False, "raw_name_stats": "NO ENCONTRADO",
                "hold": 0.78, "ace": 0.05, "df": 0.035,
                "1in": 0.62, "1w": 0.70, "2w": 0.50,
                "rpw": None, "break_pct": None, "bp_conv": None, "bp_saved": None,
                "serve_profile": "normal", "match_type": "stats"
            }
            if nid in serve_map:
                base = merge_stats(base, serve_map[nid])
            if nid in return_map:
                base = merge_stats(base, return_map[nid])
            if nid in break_map:
                base = merge_stats(base, break_map[nid])
            base["serve_profile"] = perfil_saque(base.get("ace", 0.05))
            stats_map[nid] = base

        return stats_map

    stats_general_map = construir_stats_map(serve_general, return_general, break_general)

    # =========================
    # Mapas por superficie
    # =========================
    stats_surface_maps = {}

    for surface in ["Hard", "Clay", "Grass"]:
        serve_surface = leer_archivo_stats(ruta_stats_superficie(circuito, "serve", surface), "serve")
        return_surface = leer_archivo_stats(ruta_stats_superficie(circuito, "return", surface), "return")
        break_surface = leer_archivo_stats(ruta_stats_superficie(circuito, "break", surface), "break")

        surface_map_raw = construir_stats_map(serve_surface, return_surface, break_surface)

        # Combina cada jugador con general + superficie
        combined = {}
        all_ids = set(stats_general_map) | set(surface_map_raw)

        for nid in all_ids:
            if nid in stats_general_map and nid in surface_map_raw:
                combined[nid] = merge_surface_stats(stats_general_map[nid], surface_map_raw[nid])
                combined[nid]["match_type"] = f"surface_{surface.lower()}"
            elif nid in surface_map_raw:
                combined[nid] = surface_map_raw[nid]
                combined[nid]["match_type"] = f"surface_{surface.lower()}"
            else:
                combined[nid] = stats_general_map[nid].copy()
                combined[nid]["match_type"] = "general_fallback"

            combined[nid]["serve_profile"] = perfil_saque(combined[nid].get("ace", 0.05))

        stats_surface_maps[surface] = combined

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

        stats_general = buscar_stats(nombre, stats_general_map)
        if stats_general is None:
            stats_general = stats_default_por_elo(clay, rank, "Clay", circuito)

        stats_by_surface = {}
        for surface, elo_surface in [("Hard", hard), ("Clay", clay), ("Grass", grass)]:
            s = buscar_stats(nombre, stats_surface_maps.get(surface, {}))
            if s is None:
                s = stats_default_por_elo(elo_surface, rank, surface, circuito)
            stats_by_surface[surface] = s

        players[nombre] = {
            "Player": nombre,
            "Rank": rank,
            "Hard": hard,
            "Clay": clay,
            "Grass": grass,
            "Stats": stats_general,
            "StatsBySurface": stats_by_surface,
            "Fatigue": buscar_fatigue(nombre, fatigue_map)
        }

    return players

def get_stats_surface(player_data, surface):
    return player_data.get("StatsBySurface", {}).get(surface, player_data.get("Stats", {}))


def calc_hold(stats, elo_diff, surface, circuito):
    base = stats.get("hold", 0.78)
    ace = stats.get("ace", 0.05)
    profile = stats.get("serve_profile", "normal")
    surface_adj = {"Hard": -0.005, "Clay": -0.105, "Grass": 0.015} if circuito == "ATP" else {"Hard": -0.010, "Clay": -0.085, "Grass": 0.010}
    elo_adj = np.clip(elo_diff / 3900, -0.040, 0.040)

    serve_bonus = 0
    if profile == "good_server": serve_bonus = 0.006
    elif profile == "big_server": serve_bonus = 0.012
    elif profile == "elite_server": serve_bonus = 0.018

    bp_saved = stats.get("bp_saved")
    clutch_bonus = np.clip((bp_saved - 0.58) * 0.05, -0.010, 0.012) if bp_saved is not None else 0
    hold = base + surface_adj[surface] + elo_adj + serve_bonus + ace * 0.01 + clutch_bonus
    return np.clip(hold, 0.46, 0.84)

def calc_return_strength(stats, elo_surface, surface):
    if stats.get("rpw") is not None:
        ret = stats["rpw"]
    elif stats.get("break_pct") is not None:
        ret = stats["break_pct"]
    else:
        ret = 1.0 - stats.get("hold", 0.78) + ((elo_surface - 1500) / 4200)

    if stats.get("break_pct") is not None:
        ret = (ret * 0.65) + (stats["break_pct"] * 0.35)

    if stats.get("bp_conv") is not None:
        ret += np.clip((stats["bp_conv"] - 0.38) * 0.05, -0.010, 0.012)

    if surface == "Clay": ret += 0.020
    elif surface == "Grass": ret -= 0.010
    return np.clip(ret, 0.12, 0.40)

def aplicar_return_pressure(h1, h2, r1, r2, surface):
    weight = 0.19 if surface == "Clay" else 0.10 if surface == "Hard" else 0.09
    return np.clip(h1 - r2 * weight, 0.44, 0.84), np.clip(h2 - r1 * weight, 0.44, 0.84)

def calcular_match_volatility(e1, e2, surface, fav_raw_est=None):
    gap = abs(e1 - e2)
    vol = 0.040
    if gap > 300: vol += 0.018
    elif gap > 200: vol += 0.010
    elif gap > 120: vol += 0.005
    if surface == "Clay": vol += 0.010
    elif surface == "Grass": vol -= 0.004

    # v14: Hard Compression
    if surface == "Hard" and fav_raw_est is not None:
        if fav_raw_est >= 0.72: vol -= 0.010
        elif fav_raw_est >= 0.66: vol -= 0.006

    return float(np.clip(vol, 0.020, 0.075))

def hard_compression(surface, fav, h1, h2):
    noise_mult, pressure_add, shift_mult = 1.0, 0.0, 1.0
    if surface == "Hard" and fav >= 0.72:
        noise_mult, pressure_add, shift_mult = 0.88, 0.008, 0.86
    elif surface == "Hard" and fav >= 0.66:
        noise_mult, pressure_add, shift_mult = 0.93, 0.004, 0.92

    if surface == "Hard" and h1 > 0.76 and h2 > 0.76:
        noise_mult = min(1.0, noise_mult + 0.05)
        shift_mult = min(1.0, shift_mult + 0.05)

    return noise_mult, pressure_add, shift_mult


def calcular_tiebreak_boost(stats1, stats2, hold1, hold2, surface, p1_big, p2_big):
    """
    v16 Tie-break Intelligence Engine.
    Estima el entorno de tie-break con:
    - hold combinado
    - ace%
    - 1st serve won
    - 2nd serve won
    - superficie
    - big server profile
    """
    ace1 = stats1.get("ace", 0.05)
    ace2 = stats2.get("ace", 0.05)

    first_won1 = stats1.get("1w", 0.70)
    first_won2 = stats2.get("1w", 0.70)

    second_won1 = stats1.get("2w", 0.50)
    second_won2 = stats2.get("2w", 0.50)

    hold_avg = (hold1 + hold2) / 2
    ace_avg = (ace1 + ace2) / 2
    first_avg = (first_won1 + first_won2) / 2
    second_avg = (second_won1 + second_won2) / 2

    boost = 0.0

    # Hold alto de ambos = más 6-6
    if hold1 > 0.78 and hold2 > 0.78:
        boost += 0.070
    elif hold1 > 0.76 and hold2 > 0.76:
        boost += 0.050
    elif hold1 > 0.74 and hold2 > 0.74:
        boost += 0.030
    elif hold_avg < 0.66:
        boost -= 0.025

    # Aces y primeros servicios potentes
    if ace_avg >= 0.12:
        boost += 0.050
    elif ace_avg >= 0.09:
        boost += 0.030
    elif ace_avg >= 0.07:
        boost += 0.015

    if first_avg >= 0.76:
        boost += 0.030
    elif first_avg >= 0.72:
        boost += 0.015

    if second_avg >= 0.55:
        boost += 0.015

    # Perfil de sacadores
    if p1_big and p2_big:
        boost += 0.060
    elif p1_big or p2_big:
        boost += 0.030

    # Superficie
    if surface == "Grass":
        boost += 0.055
    elif surface == "Hard":
        boost += 0.035
    elif surface == "Clay":
        boost -= 0.015

    return float(np.clip(boost, -0.040, 0.160))


def pressure_collapse_params(stats1, stats2, surface):
    """
    v16 Pressure Collapse.
    Ajusta ligeramente los games finales según BP saved / BP conversion.
    No cambia mucho el ML; afecta más al cierre de sets y tie-breaks.
    """
    bp_saved1 = stats1.get("bp_saved", None)
    bp_saved2 = stats2.get("bp_saved", None)
    bp_conv1 = stats1.get("bp_conv", None)
    bp_conv2 = stats2.get("bp_conv", None)

    pressure1 = 0.0
    pressure2 = 0.0

    if bp_saved1 is not None:
        pressure1 += np.clip((bp_saved1 - 0.58) * 0.08, -0.012, 0.014)
    if bp_saved2 is not None:
        pressure2 += np.clip((bp_saved2 - 0.58) * 0.08, -0.012, 0.014)

    if bp_conv1 is not None:
        pressure1 += np.clip((bp_conv1 - 0.38) * 0.04, -0.008, 0.010)
    if bp_conv2 is not None:
        pressure2 += np.clip((bp_conv2 - 0.38) * 0.04, -0.008, 0.010)

    if surface == "Clay":
        pressure1 *= 1.10
        pressure2 *= 1.10

    return float(np.clip(pressure1, -0.018, 0.020)), float(np.clip(pressure2, -0.018, 0.020))



def sim_set(hold1, hold2, surface, shift, p1_big, p2_big, fav_raw_est=0.5, stats1=None, stats2=None):
    g1 = g2 = 0
    tb = False
    server = random.choice([1, 2])

    stats1 = stats1 or {}
    stats2 = stats2 or {}
    tb_boost = calcular_tiebreak_boost(stats1, stats2, hold1, hold2, surface, p1_big, p2_big)
    pressure_skill1, pressure_skill2 = pressure_collapse_params(stats1, stats2, surface)

    if surface == "Clay":
        noise, pressure = 0.068, -0.085
    elif surface == "Hard":
        noise, pressure = 0.038, -0.030
    else:
        noise, pressure = 0.028, -0.018

    nm, pa, sm = hard_compression(surface, fav_raw_est, hold1, hold2)
    noise *= nm
    pressure += pa
    shift *= sm

    while True:
        extra = pressure if g1 >= 4 and g2 >= 4 else 0
        # En games finales, BP saved/BP converted modula el cierre.
        clutch1 = pressure_skill1 if g1 >= 4 and g2 >= 4 else 0.0
        clutch2 = pressure_skill2 if g1 >= 4 and g2 >= 4 else 0.0

        h1 = np.clip(np.random.normal(hold1 + shift, noise) + extra + clutch1, 0.30, 0.93)
        h2 = np.clip(np.random.normal(hold2 - shift, noise) + extra + clutch2, 0.30, 0.93)

        if server == 1:
            if random.random() < h1: g1 += 1
            else: g2 += 1
        else:
            if random.random() < h2: g2 += 1
            else: g1 += 1

        server = 1 if server == 2 else 2

        if g1 >= 6 and g1 - g2 >= 2: return g1, g2, tb
        if g2 >= 6 and g2 - g1 >= 2: return g1, g2, tb

        if g1 == 6 and g2 == 6:
            tb = True
            p_tb = hold1 / (hold1 + hold2)

            # v16: boost inteligente según saque/hold/superficie
            p_tb += tb_boost

            p_tb = np.clip(p_tb, 0.30, 0.82)
            return (7, 6, tb) if random.random() < p_tb else (6, 7, tb)

def sim_match(d1, d2, surface, circuito, best_of=3, n=5000):
    e1, e2 = d1[surface], d2[surface]
    elo_diff = e1 - e2
    # v15: usa stats específicas de superficie si existen
    s1 = get_stats_surface(d1, surface)
    s2 = get_stats_surface(d2, surface)

    raw1 = calc_hold(s1, elo_diff, surface, circuito)
    raw2 = calc_hold(s2, -elo_diff, surface, circuito)
    ret1 = calc_return_strength(s1, e1, surface)
    ret2 = calc_return_strength(s2, e2, surface)
    hold1, hold2 = aplicar_return_pressure(raw1, raw2, ret1, ret2, surface)

    # v17 Fatigue Engine
    fatigue1 = d1.get("Fatigue", {})
    fatigue2 = d2.get("Fatigue", {})
    fat_adj1, fat_adj2, fatigue_vol_extra = fatigue_adjustments(fatigue1, fatigue2, surface)

    hold1 = np.clip(hold1 + fat_adj1, 0.42, 0.84)
    hold2 = np.clip(hold2 + fat_adj2, 0.42, 0.84)

    ret1 = np.clip(ret1 + fat_adj1 * 0.35, 0.10, 0.40)
    ret2 = np.clip(ret2 + fat_adj2 * 0.35, 0.10, 0.40)

    p1_profile = s1.get("serve_profile", "normal")
    p2_profile = s2.get("serve_profile", "normal")
    p1_big = p1_profile in ["big_server", "elite_server"]
    p2_big = p2_profile in ["big_server", "elite_server"]

    tb_intel_boost = calcular_tiebreak_boost(s1, s2, hold1, hold2, surface, p1_big, p2_big)
    pressure_skill1, pressure_skill2 = pressure_collapse_params(s1, s2, surface)

    sets_to_win = 3 if best_of == 5 else 2
    fav_est = max(elo_prob(e1, e2), 1 - elo_prob(e1, e2))
    vol = calcular_match_volatility(e1, e2, surface, fav_est)
    if p1_big or p2_big: vol += 0.006
    vol += fatigue_vol_extra

    res = {"p1":0, "p2":0, "set3":0, "tb":0, "games":[], "p1_fs":0, "p2_fs":0, "fav_under22":0, "dog_over20":0, "fav_2_0":0, "dog_wins_set":0, "long_match":0}

    for _ in range(n):
        sets1 = sets2 = games = 0
        tb_seen = False
        first_done = False
        shift = np.random.normal(0, vol)

        while sets1 < sets_to_win and sets2 < sets_to_win:
            g1, g2, tb = sim_set(
                hold1, hold2, surface, shift, p1_big, p2_big, fav_est,
                stats1=s1, stats2=s2
            )
            games += g1 + g2
            if tb: tb_seen = True

            if not first_done:
                if g1 > g2: res["p1_fs"] += 1
                else: res["p2_fs"] += 1
                first_done = True

            if g1 > g2: sets1 += 1
            else: sets2 += 1

        p1_wins = sets1 > sets2
        if p1_wins: res["p1"] += 1
        else: res["p2"] += 1

        if (sets1, sets2) in [(2,1), (1,2)]: res["set3"] += 1
        if tb_seen: res["tb"] += 1

        p1_is_fav = e1 >= e2
        fav_wins = p1_wins if p1_is_fav else (not p1_wins)
        dog_wins = not fav_wins

        if fav_wins and games < 22.5: res["fav_under22"] += 1
        if dog_wins and games > 20.5: res["dog_over20"] += 1

        # v17 Smart Markets
        if p1_is_fav:
            fav_sets = sets1
            dog_sets = sets2
        else:
            fav_sets = sets2
            dog_sets = sets1

        if fav_wins and dog_sets == 0:
            res["fav_2_0"] += 1

        if dog_sets >= 1:
            res["dog_wins_set"] += 1

        if games > 22.5 or tb_seen or ((sets1, sets2) in [(2,1), (1,2)]):
            res["long_match"] += 1

        res["games"].append(games)

    p1_raw = res["p1"] / n
    p1_cal = calibrar_probabilidad(p1_raw, surface)

    return {
        "p1": p1_raw, "p2": 1-p1_raw, "p1_cal": p1_cal, "p2_cal": 1-p1_cal,
        "p1_fs": res["p1_fs"]/n, "p2_fs": res["p2_fs"]/n,
        "set3": res["set3"]/n, "tb": res["tb"]/n,
        "fav_under22": res["fav_under22"]/n, "dog_over20": res["dog_over20"]/n,
        "fav_2_0": res["fav_2_0"]/n,
        "dog_wins_set": res["dog_wins_set"]/n,
        "long_match": res["long_match"]/n,
        "games": res["games"], "hold1": hold1, "hold2": hold2,
        "raw_hold1": raw1, "raw_hold2": raw2, "ret1": ret1, "ret2": ret2,
        "p1_profile": p1_profile, "p2_profile": p2_profile,
        "vol": vol, "fav_raw_est": fav_est,
        "tb_intel_boost": tb_intel_boost,
        "pressure_skill1": pressure_skill1,
        "pressure_skill2": pressure_skill2,
        "fatigue1": fatigue1,
        "fatigue2": fatigue2,
        "fatigue_adj1": fat_adj1,
        "fatigue_adj2": fat_adj2,
        "fatigue_vol_extra": fatigue_vol_extra
    }

def cargar_historicos(circuito):
    folder = rutas(circuito)["historicos"]
    files = sorted(glob.glob(os.path.join(folder, "*.xlsx")))
    dfs = []
    for f in files:
        try:
            df = pd.read_excel(f)
            df["SourceFile"] = os.path.basename(f)
            dfs.append(df)
        except Exception:
            pass
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


@st.cache_data
def crear_fatigue_map(circuito):
    """
    v17 Fatigue Engine.
    Calcula desgaste reciente desde históricos:
    - partidos últimos 7 días
    - games últimos 7 días
    - sets últimos 7 días
    - tie-breaks últimos 7 días
    - back-to-back
    - descanso estimado
    Nota: para predictor usa la fecha máxima del histórico cargado como referencia.
    """
    hist = cargar_historicos(circuito)
    fatigue = {}

    if hist.empty or "Date" not in hist.columns:
        return fatigue

    df = hist.copy()
    df = df[df["Comment"].astype(str).str.contains("Completed", na=False)]
    df["DateParsed"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["DateParsed", "Winner", "Loser"])
    if df.empty:
        return fatigue

    ref_date = df["DateParsed"].max()

    def row_games(row):
        total = 0
        sets = 0
        tb = 0
        for i in range(1, 6):
            w = row.get(f"W{i}", np.nan)
            l = row.get(f"L{i}", np.nan)
            if not pd.isna(w) and not pd.isna(l):
                try:
                    wi, li = int(w), int(l)
                    total += wi + li
                    sets += 1
                    if (wi, li) in [(7, 6), (6, 7)]:
                        tb += 1
                except:
                    pass
        return total, sets, tb

    player_rows = {}

    for _, row in df.iterrows():
        date = row["DateParsed"]
        surface = str(row.get("Surface", "Hard"))
        games, sets, tbs = row_games(row)
        for player in [normalizar_texto(row.get("Winner", "")), normalizar_texto(row.get("Loser", ""))]:
            pid = limpiar(player)
            if not pid:
                continue
            player_rows.setdefault(pid, []).append({
                "date": date,
                "surface": surface,
                "games": games,
                "sets": sets,
                "tbs": tbs
            })

    for pid, rows in player_rows.items():
        rows = sorted(rows, key=lambda x: x["date"])
        recent7 = [r for r in rows if 0 <= (ref_date - r["date"]).days <= 7]
        recent14 = [r for r in rows if 0 <= (ref_date - r["date"]).days <= 14]

        last_date = rows[-1]["date"]
        rest_days = int((ref_date - last_date).days)

        matches7 = len(recent7)
        games7 = sum(r["games"] for r in recent7)
        sets7 = sum(r["sets"] for r in recent7)
        tbs7 = sum(r["tbs"] for r in recent7)

        matches14 = len(recent14)
        clay_games7 = sum(r["games"] for r in recent7 if r["surface"] == "Clay")

        fatigue_score = 0.0
        fatigue_score += matches7 * 0.008
        fatigue_score += max(0, games7 - 45) * 0.0007
        fatigue_score += max(0, sets7 - 6) * 0.004
        fatigue_score += tbs7 * 0.004
        fatigue_score += max(0, clay_games7 - 35) * 0.0005

        if rest_days <= 1:
            fatigue_score += 0.018
        elif rest_days <= 2:
            fatigue_score += 0.010
        elif rest_days >= 7:
            fatigue_score -= 0.006
        elif rest_days >= 4:
            fatigue_score -= 0.003

        fatigue_score = float(np.clip(fatigue_score, -0.010, 0.055))

        fatigue[pid] = {
            "fatigue_score": fatigue_score,
            "matches7": matches7,
            "matches14": matches14,
            "games7": games7,
            "sets7": sets7,
            "tbs7": tbs7,
            "rest_days": rest_days,
            "latest_date": str(last_date.date())
        }

    return fatigue


def buscar_fatigue(nombre, fatigue_map):
    nid = limpiar(nombre)
    if nid in fatigue_map:
        return fatigue_map[nid]

    mejor, best = None, 0
    for fid, data in fatigue_map.items():
        score = similitud_nombre(nombre, fid)
        if score > best:
            best, mejor = score, data

    if mejor is not None and best >= 0.72:
        return mejor

    return {
        "fatigue_score": 0.0,
        "matches7": 0,
        "matches14": 0,
        "games7": 0,
        "sets7": 0,
        "tbs7": 0,
        "rest_days": 7,
        "latest_date": "N/A"
    }


def fatigue_adjustments(f1, f2, surface):
    """
    Devuelve ajustes suaves para cada jugador.
    Mayor fatiga = menor hold/return y algo más de volatilidad.
    """
    fat1 = f1.get("fatigue_score", 0.0)
    fat2 = f2.get("fatigue_score", 0.0)

    if surface == "Clay":
        mult = 1.18
    elif surface == "Grass":
        mult = 0.82
    else:
        mult = 1.0

    adj1 = -fat1 * mult
    adj2 = -fat2 * mult

    vol_extra = abs(fat1 - fat2) * 0.35
    if fat1 > 0.030 or fat2 > 0.030:
        vol_extra += 0.003

    return float(np.clip(adj1, -0.055, 0.010)), float(np.clip(adj2, -0.055, 0.010)), float(np.clip(vol_extra, 0, 0.018))


def encontrar_jugador(nombre_hist, db):
    if nombre_hist in db: return nombre_hist
    mejor, best = None, 0
    for nombre in db:
        score = similitud_nombre(nombre_hist, nombre)
        if score > best:
            best, mejor = score, nombre
    return mejor if mejor is not None and best >= 0.70 else None

def total_games_row(row):
    total = 0
    for i in range(1,6):
        w, l = row.get(f"W{i}", np.nan), row.get(f"L{i}", np.nan)
        if not pd.isna(w) and not pd.isna(l): total += int(w) + int(l)
    return total

def hay_tiebreak_row(row):
    for i in range(1,6):
        w, l = row.get(f"W{i}", np.nan), row.get(f"L{i}", np.nan)
        if not pd.isna(w) and not pd.isna(l):
            if (int(w), int(l)) in [(7,6), (6,7)]: return True
    return False

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

        p_win = encontrar_jugador(winner_hist, db)
        p_los = encontrar_jugador(loser_hist, db)
        if p_win is None or p_los is None: continue

        d_win, d_los = db[p_win], db[p_los]
        sim = sim_match(d_win, d_los, surface, circuito, best_of, sims_bt)

        p_raw, p_cal = sim["p1"], sim["p1_cal"]
        games_real = total_games_row(row)
        games_model = sim["games"]

        try:
            set3_real = int(row.get("Wsets", 0)) == 2 and int(row.get("Lsets", 0)) == 1
        except:
            set3_real = False

        fav_under22_real = (p_raw >= 0.50 and games_real < 22.5)
        dog_over20_real = (p_raw < 0.50 and games_real > 20.5)

        rows.append({
            "Date": row.get("Date", ""), "Tournament": row.get("Tournament", ""),
            "Series": row.get("Series", ""), "Round": row.get("Round", ""),
            "Surface": surface, "WinnerHist": winner_hist, "LoserHist": loser_hist,
            "WinnerMatched": p_win, "LoserMatched": p_los,
            "WinnerRank": leer_float(row.get("WRank", np.nan), np.nan),
            "LoserRank": leer_float(row.get("LRank", np.nan), np.nan),
            "ModelWinnerProbRaw": p_raw, "ModelWinnerProbCal": p_cal,
            "RawFavWasWinner": p_raw >= 0.50, "CalFavWasWinner": p_cal >= 0.50,
            "RealGames": games_real, "ModelAvgGames": np.mean(games_model),
            "Real3Sets": set3_real, "Model3Sets": sim["set3"],
            "RealTB": hay_tiebreak_row(row), "ModelTB": sim["tb"],
            "RealOver18": games_real > 18.5, "ModelOver18": sum(x > 18.5 for x in games_model)/sims_bt,
            "RealOver19": games_real > 19.5, "ModelOver19": sum(x > 19.5 for x in games_model)/sims_bt,
            "RealOver20": games_real > 20.5, "ModelOver20": sum(x > 20.5 for x in games_model)/sims_bt,
            "RealOver22": games_real > 22.5, "ModelOver22": sum(x > 22.5 for x in games_model)/sims_bt,
            "RealFavUnder22": fav_under22_real, "ModelFavUnder22": sim["fav_under22"],
            "RealDogOver20": dog_over20_real, "ModelDogOver20": sim["dog_over20"],
            "ModelFav2_0": sim.get("fav_2_0", 0),
            "ModelDogWinsSet": sim.get("dog_wins_set", 0),
            "ModelLongMatch": sim.get("long_match", 0),
            "WinnerFatigueScore": sim.get("fatigue1", {}).get("fatigue_score", 0),
            "LoserFatigueScore": sim.get("fatigue2", {}).get("fatigue_score", 0),
            "WinnerStats": get_stats_surface(d_win, surface).get("match_type", "N/A"), "LoserStats": get_stats_surface(d_los, surface).get("match_type", "N/A"),
            "WinnerHold": sim["hold1"], "LoserHold": sim["hold2"],
            "WinnerReturn": sim["ret1"], "LoserReturn": sim["ret2"],
            "WinnerServeProfile": sim["p1_profile"], "LoserServeProfile": sim["p2_profile"],
            "FavRawEst": sim["fav_raw_est"],
            "TBIntelBoost": sim.get("tb_intel_boost", 0),
            "WinnerPressureSkill": sim.get("pressure_skill1", 0),
            "LoserPressureSkill": sim.get("pressure_skill2", 0)
        })

        if total:
            progress.progress(min((idx+1)/total, 1.0))
    progress.empty()
    return pd.DataFrame(rows)

def market_hit_rate(df, model_col, real_col, threshold):
    sub = df[df[model_col] >= threshold].copy()
    if len(sub) == 0: return None
    return {"Casos": len(sub), "Prob media modelo": sub[model_col].mean(), "Acierto real": sub[real_col].mean()}

def crear_analyzer_tables(val, min_casos=20):
    val = val.copy()
    tables = {}
    val["FavProbCal"] = val["ModelWinnerProbCal"].apply(lambda x: max(x, 1-x))
    val["MLBin"] = pd.cut(val["FavProbCal"], bins=[0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.90], labels=["50-55","55-60","60-65","65-70","70-75","75-80","80-90"])
    ml = val.groupby("MLBin", observed=True).agg(Casos=("FavProbCal","count"), ProbMedia=("FavProbCal","mean"), AciertoReal=("CalFavWasWinner","mean")).reset_index()
    tables["ML por tramos"] = ml[ml["Casos"] >= min_casos]

    rows = []
    for name, model, real in [
        ("Over 18.5","ModelOver18","RealOver18"),
        ("Over 19.5","ModelOver19","RealOver19"),
        ("Over 20.5","ModelOver20","RealOver20"),
        ("Over 22.5","ModelOver22","RealOver22"),
        ("3 Sets","Model3Sets","Real3Sets"),
        ("Tie-break","ModelTB","RealTB"),
        ("Favorito + Under 22.5","ModelFavUnder22","RealFavUnder22"),
        ("Dog + Over 20.5","ModelDogOver20","RealDogOver20"),
        ("Favorito 2-0","ModelFav2_0","CalFavWasWinner"),
        ("Underdog gana set","ModelDogWinsSet","Real3Sets"),
        ("Partido largo","ModelLongMatch","RealOver22"),
    ]:
        for th in [0.40,0.45,0.50,0.55,0.60,0.65,0.70]:
            r = market_hit_rate(val, model, real, th)
            if r and r["Casos"] >= min_casos:
                rows.append({"Mercado": name, "Umbral modelo": th, **r})
    tables["Mercados por umbral"] = pd.DataFrame(rows)

    surface = val.groupby("Surface").agg(
        Casos=("Surface","count"), MLAccuracy=("CalFavWasWinner","mean"),
        Over18Hit=("RealOver18","mean"), Over20Hit=("RealOver20","mean"),
        Over22Hit=("RealOver22","mean"), ThreeSetsReal=("Real3Sets","mean"),
        TBReal=("RealTB","mean"), TBModel=("ModelTB","mean"),
        GamesReal=("RealGames","mean"), GamesModel=("ModelAvgGames","mean")
    ).reset_index()
    tables["Por superficie"] = surface[surface["Casos"] >= min_casos]

    val["AnyBigServer"] = val["WinnerServeProfile"].isin(["big_server","elite_server"]) | val["LoserServeProfile"].isin(["big_server","elite_server"])
    server = val.groupby("AnyBigServer").agg(
        Casos=("AnyBigServer","count"), MLAccuracy=("CalFavWasWinner","mean"),
        TBReal=("RealTB","mean"), TBModel=("ModelTB","mean"),
        Over22Real=("RealOver22","mean"), Over22Model=("ModelOver22","mean"),
        GamesReal=("RealGames","mean"), GamesModel=("ModelAvgGames","mean")
    ).reset_index()
    tables["Big server"] = server[server["Casos"] >= min_casos]

    val["RankGap"] = abs(val["WinnerRank"] - val["LoserRank"])
    val["RankGapBin"] = pd.cut(val["RankGap"], bins=[0,20,50,100,200,500], labels=["0-20","20-50","50-100","100-200","200+"])
    rg = val.groupby("RankGapBin", observed=True).agg(
        Casos=("RankGap","count"), MLAccuracy=("CalFavWasWinner","mean"),
        ThreeSetsReal=("Real3Sets","mean"), ThreeSetsModel=("Model3Sets","mean"),
        GamesReal=("RealGames","mean"), GamesModel=("ModelAvgGames","mean")
    ).reset_index()
    tables["Ranking gap"] = rg[rg["Casos"] >= min_casos]
    return tables

# =========================================================
# UI
# =========================================================

with st.sidebar:
    st.header("🎾 Tennis IA v17.1")
    st.caption("Fatigue + Smart Markets Engine")
    if st.button("🧹 Limpiar caché"):
        st.cache_data.clear()
        st.success("Caché limpiada")
    circuito = st.radio("Circuito", ["ATP", "WTA"])
    modo = st.radio("Modo", ["Predictor", "Validador histórico", "Analyzer"])

db = cargar_datos(circuito)
if not db:
    st.error("No se encontraron jugadores. Revisa carpetas y archivos.")
    st.stop()

if modo == "Predictor":
    with st.sidebar:
        players = sorted(db.keys())
        surface = st.selectbox("Superficie", ["Hard","Clay","Grass"])
        formato = st.radio("Formato", ["ATP Tour (3 sets)", "Grand Slam (5 sets)"])
        sims = st.select_slider("Simulaciones", [5000,10000,20000], value=10000)

    c1, c2 = st.columns(2)
    with c1: p1_name = st.selectbox("Jugador 1", players)
    with c2: p2_name = st.selectbox("Jugador 2", players, index=min(1, len(players)-1))

    if st.button("🚀 ANALIZAR PARTIDO", use_container_width=True):
        d1, d2 = db[p1_name], db[p2_name]
        best_of = 5 if "5" in formato else 3
        with st.spinner(f"Simulando {sims:,} partidos..."):
            sim = sim_match(d1,d2,surface,circuito,best_of,sims)

        st.caption(
            f"📁 Stats usadas: {stats_filename_label(circuito, 'serve', surface)} · "
            f"{stats_filename_label(circuito, 'return', surface)} · "
            f"{stats_filename_label(circuito, 'break', surface)}"
        )

        p1, p2, p1c, p2c = sim["p1"], sim["p2"], sim["p1_cal"], sim["p2_cal"]
        games = sim["games"]
        avg_games, med_games = np.mean(games), np.median(games)
        over18 = sum(x > 18.5 for x in games)/sims
        over19 = sum(x > 19.5 for x in games)/sims
        over20 = sum(x > 20.5 for x in games)/sims
        over22 = sum(x > 22.5 for x in games)/sims
        under22 = 1-over22
        elo_ref = elo_prob(d1[surface], d2[surface])

        risk = "🟢 Riesgo bajo"
        if max(p1c,p2c) < 0.56: risk = "🔴 Riesgo alto"
        elif max(p1c,p2c) < 0.63: risk = "🟡 Riesgo medio"

        st.divider()
        st.subheader("🏆 Ganador del Partido")
        a,b = st.columns(2)
        with a:
            st.metric(d1["Player"], f"{p1c:.1%}", f"{nivel(p1c)} · bruta {p1:.1%}")
            st.caption(f"Rank #{d1['Rank']} · Elo {surface}: {d1[surface]:.0f} · {edge_calibracion(p1,p1c)}")
        with b:
            st.metric(d2["Player"], f"{p2c:.1%}", f"{nivel(p2c)} · bruta {p2:.1%}")
            st.caption(f"Rank #{d2['Rank']} · Elo {surface}: {d2[surface]:.0f} · {edge_calibracion(p2,p2c)}")
        st.caption(f"Referencia Elo puro: {elo_ref:.1%} / {1-elo_ref:.1%} · {risk}")

        st.divider()
        st.subheader("🎾 Primer Set")
        fs1, fs2 = st.columns(2)
        with fs1: st.metric(f"{d1['Player']} gana", f"{sim['p1_fs']:.1%}", nivel(sim["p1_fs"]))
        with fs2: st.metric(f"{d2['Player']} gana", f"{sim['p2_fs']:.1%}", nivel(sim["p2_fs"]))

        st.divider()
        st.subheader("📊 Mercados")
        m1,m2,m3,m4,m5 = st.columns(5)
        with m1: st.metric("Over 18.5", f"{over18:.1%}", nivel(over18))
        with m2: st.metric("Over 19.5", f"{over19:.1%}", nivel(over19))
        with m3: st.metric("Over 20.5", f"{over20:.1%}", nivel(over20))
        with m4: st.metric("Over 22.5", f"{over22:.1%}", nivel(over22))
        with m5: st.metric("Under 22.5", f"{under22:.1%}", nivel(under22))

        e1,e2,e3,e4,e5 = st.columns(5)
        with e1: st.metric("3 sets", f"{sim['set3']:.1%}", nivel(sim["set3"]))
        with e2: st.metric("Tie-break", f"{sim['tb']:.1%}", nivel(sim["tb"]))
        with e3: st.metric("Underdog gana set", f"{sim['dog_wins_set']:.1%}", nivel(sim["dog_wins_set"]))
        with e4: st.metric("Favorito 2-0", f"{sim['fav_2_0']:.1%}", nivel(sim["fav_2_0"]))
        with e5: st.metric("Partido largo", f"{sim['long_match']:.1%}", nivel(sim["long_match"]))
        st.caption(f"Media games: {avg_games:.1f} · Mediana games: {med_games:.0f}")

        st.divider()
        st.subheader("🎾 Hold / Return Engine")
        h1,h2 = st.columns(2)
        with h1:
            st.metric(d1["Player"], f"{sim['hold1']:.1%}", f"Raw hold {sim['raw_hold1']:.1%}")
            st.caption(f"{perfil_legible(sim['p1_profile'])} · Return strength {sim['ret1']:.1%}")
        with h2:
            st.metric(d2["Player"], f"{sim['hold2']:.1%}", f"Raw hold {sim['raw_hold2']:.1%}")
            st.caption(f"{perfil_legible(sim['p2_profile'])} · Return strength {sim['ret2']:.1%}")

        st.divider()
        st.subheader("🎯 Tie-break Intelligence")

        tb1, tb2, tb3 = st.columns(3)
        with tb1:
            st.metric("TB boost", f"{sim.get('tb_intel_boost', 0):+.1%}")
        with tb2:
            st.metric(f"Presión {d1['Player']}", f"{sim.get('pressure_skill1', 0):+.1%}")
        with tb3:
            st.metric(f"Presión {d2['Player']}", f"{sim.get('pressure_skill2', 0):+.1%}")

        st.divider()
        st.subheader("🔋 Fatigue Engine")

        fcol1, fcol2 = st.columns(2)
        with fcol1:
            f = sim.get("fatigue1", {})
            st.metric(d1["Player"], f"{f.get('fatigue_score',0):.1%}", f"Ajuste {sim.get('fatigue_adj1',0):+.1%}")
            st.caption(f"7 días: {f.get('matches7',0)} partidos · {f.get('games7',0)} games · descanso {f.get('rest_days',7)} días")
        with fcol2:
            f = sim.get("fatigue2", {})
            st.metric(d2["Player"], f"{f.get('fatigue_score',0):.1%}", f"Ajuste {sim.get('fatigue_adj2',0):+.1%}")
            st.caption(f"7 días: {f.get('matches7',0)} partidos · {f.get('games7',0)} games · descanso {f.get('rest_days',7)} días")

        st.divider()
        st.subheader("🧠 Perfil del Partido")
        tags = []
        if sim["p1_profile"] in ["big_server","elite_server"]: tags.append(f"🚀 {d1['Player']} gran sacador")
        if sim["p2_profile"] in ["big_server","elite_server"]: tags.append(f"🚀 {d2['Player']} gran sacador")
        if sim["set3"] > 0.45: tags.append("⚠️ Partido volátil")
        if sim["tb"] > 0.32: tags.append("🎯 Tie-break probable")
        if avg_games > 24: tags.append("📈 Partido largo")
        if avg_games < 21: tags.append("📉 Partido corto")
        if max(p1c,p2c) < 0.55: tags.append("⚠️ Favorito débil")
        if sim["vol"] > 0.06: tags.append("🌪️ Alta volatilidad por diferencia Elo/superficie")
        if surface == "Hard" and sim["fav_raw_est"] >= 0.66: tags.append("🧊 Hard compression activada")
        if sim["hold1"] > 0.76 and sim["hold2"] > 0.76 and surface == "Hard": tags.append("🎯 Smart tie-break boost")
        if sim.get("tb_intel_boost", 0) >= 0.08: tags.append("🧠 TB Intelligence alto")
        if sim.get("fatigue1", {}).get("fatigue_score", 0) >= 0.030: tags.append(f"🔋 Fatiga {d1['Player']}")
        if sim.get("fatigue2", {}).get("fatigue_score", 0) >= 0.030: tags.append(f"🔋 Fatiga {d2['Player']}")
        if sim.get("long_match", 0) >= 0.65: tags.append("📈 Partido largo probable")
        if sim.get("fav_2_0", 0) >= 0.55: tags.append("🔥 Spot favorito 2-0")
        st.info(" · ".join(tags) if tags else "Sin perfil extremo detectado.")

        st.divider()
        st.subheader("🎯 Señal principal del modelo")
        markets = {
            "ML favorito calibrado": max(p1c,p2c), "Over 18.5": over18,
            "Over 19.5": over19, "Over 20.5": over20, "Over 22.5": over22, "Under 22.5": under22,
            "Tie-break": sim["tb"], "Fav + Under 22.5": sim["fav_under22"],
            "Dog + Over 20.5": sim["dog_over20"],
            "Underdog gana set": sim["dog_wins_set"],
            "Favorito 2-0": sim["fav_2_0"],
            "Partido largo": sim["long_match"]
        }
        best = max(markets.items(), key=lambda x: x[1])
        st.success(f"{best[0]} → {best[1]:.1%}")
        st.caption(f"Tennis IA v17.1 · {sims:,} simulaciones Monte Carlo")

elif modo == "Validador histórico":
    st.subheader("📚 Validador histórico")
    hist_df = cargar_historicos(circuito)
    if hist_df.empty:
        st.error("No se encontraron históricos.")
        st.stop()
    with st.sidebar:
        surface_filter = st.selectbox("Superficie histórica", ["Todas","Hard","Clay","Grass"])
        max_matches = st.number_input("Máx partidos a validar", 10, 5000, 500, 50)
        sims_bt = st.select_slider("Simulaciones por partido", [300,500,1000,2000], value=500)
    st.info(f"Históricos cargados: {len(hist_df):,} partidos.")
    if st.button("🚀 EJECUTAR VALIDACIÓN", use_container_width=True):
        with st.spinner("Validando partidos históricos..."):
            val = validar_historico(db,hist_df,circuito,surface_filter,int(max_matches),int(sims_bt))
        if val.empty:
            st.error("No se pudieron emparejar partidos.")
            st.stop()
        ml_acc = val["CalFavWasWinner"].mean()
        over18_acc = ((val["ModelOver18"] >= 0.50) == val["RealOver18"]).mean()
        over19_acc = ((val["ModelOver19"] >= 0.50) == val["RealOver19"]).mean() if "ModelOver19" in val.columns else 0
        over20_acc = ((val["ModelOver20"] >= 0.50) == val["RealOver20"]).mean()
        over22_acc = ((val["ModelOver22"] >= 0.50) == val["RealOver22"]).mean()
        set3_acc = ((val["Model3Sets"] >= 0.50) == val["Real3Sets"]).mean()
        tb_acc = ((val["ModelTB"] >= 0.50) == val["RealTB"]).mean()
        games_error = np.mean(np.abs(val["ModelAvgGames"] - val["RealGames"]))
        st.divider()
        st.subheader("📊 Resumen validación")
        c1,c2,c3,c4 = st.columns(4)
        with c1: st.metric("ML accuracy", f"{ml_acc:.1%}")
        with c2: st.metric("Over 20.5 accuracy", f"{over20_acc:.1%}")
        with c3: st.metric("3 sets accuracy", f"{set3_acc:.1%}")
        with c4: st.metric("Error medio games", f"{games_error:.2f}")
        d1,d2,d3 = st.columns(3)
        with d1: st.metric("Over 18.5 accuracy", f"{over18_acc:.1%}")
        with d2: st.metric("Over 19.5 accuracy", f"{over19_acc:.1%}")
        with d3: st.metric("Tie-break accuracy", f"{tb_acc:.1%}")
        st.caption(f"Over 22.5 accuracy: {over22_acc:.1%}")
        st.dataframe(val, use_container_width=True)
        st.download_button("⬇️ Descargar CSV", data=val.to_csv(index=False).encode("utf-8"), file_name="validacion_tennis_ia_v17_1.csv", mime="text/csv")

else:
    st.subheader("📊 Analyzer Engine")
    hist_df = cargar_historicos(circuito)
    if hist_df.empty:
        st.error("No se encontraron históricos.")
        st.stop()
    with st.sidebar:
        surface_filter = st.selectbox("Superficie analyzer", ["Todas","Hard","Clay","Grass"])
        max_matches = st.number_input("Máx partidos", 50, 5000, 1000, 100)
        sims_bt = st.select_slider("Simulaciones por partido", [300,500,1000], value=500)
        min_casos = st.number_input("Mínimo casos por segmento", 5, 200, 25, 5)
    st.info("Este modo busca patrones históricos por mercado, superficie, ranking gap y perfiles.")
    if st.button("🚀 EJECUTAR ANALYZER", use_container_width=True):
        with st.spinner("Generando validación base para Analyzer..."):
            val = validar_historico(db,hist_df,circuito,surface_filter,int(max_matches),int(sims_bt))
        if val.empty:
            st.error("No se pudieron emparejar partidos.")
            st.stop()
        tables = crear_analyzer_tables(val, int(min_casos))
        st.divider()
        st.subheader("🏆 Resumen general")
        g1,g2,g3,g4 = st.columns(4)
        with g1: st.metric("Partidos analizados", f"{len(val):,}")
        with g2: st.metric("ML accuracy", f"{val['CalFavWasWinner'].mean():.1%}")
        with g3: st.metric("Games error", f"{np.mean(np.abs(val['ModelAvgGames'] - val['RealGames'])):.2f}")
        with g4: st.metric("TB real/modelo", f"{val['RealTB'].mean():.1%} / {val['ModelTB'].mean():.1%}")
        st.divider()
        st.subheader("📈 Mercados por umbral")
        mt = tables.get("Mercados por umbral", pd.DataFrame())
        if not mt.empty:
            st.dataframe(mt.sort_values(["Acierto real","Casos"], ascending=[False,False]), use_container_width=True)
        else:
            st.warning("No hay suficientes casos para mercados por umbral.")
        st.divider()
        st.subheader("🎯 ML por tramos")
        st.dataframe(tables.get("ML por tramos", pd.DataFrame()), use_container_width=True)
        st.divider()
        st.subheader("🌍 Por superficie")
        st.dataframe(tables.get("Por superficie", pd.DataFrame()), use_container_width=True)
        st.divider()
        st.subheader("🚀 Big server")
        st.dataframe(tables.get("Big server", pd.DataFrame()), use_container_width=True)
        st.divider()
        st.subheader("📊 Ranking gap")
        st.dataframe(tables.get("Ranking gap", pd.DataFrame()), use_container_width=True)
        st.divider()
        st.subheader("🧾 Detalle base")
        st.dataframe(val, use_container_width=True)
        st.download_button("⬇️ Descargar Analyzer CSV", data=val.to_csv(index=False).encode("utf-8"), file_name="analyzer_tennis_ia_v17_1.csv", mime="text/csv")
