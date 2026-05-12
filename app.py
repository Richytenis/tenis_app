
import streamlit as st
import pandas as pd
import numpy as np
import random, re, os, glob, unicodedata, time, io
from difflib import SequenceMatcher

st.set_page_config(page_title="Tennis IA v23.1 Batch Excel", page_icon="🎾", layout="wide")

APP_VERSION = "v23.1"
QUALITY_ENGINE_VERSION = "v23.1-batch-excel-2026-05-12"

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

# =========================================================
# v22.3 MATCH COUNT FIX + TOUR QUALITY ENGINE
# =========================================================

def detectar_nivel_torneo(row):
    """
    v22.17 Tour Quality + Challenger CSV Fix.

    Soporta dos familias de históricos:
    1) Excel tipo tennis-data ATP Tour con columnas Series/Tournament/Round.
    2) CSV Jeff Sackmann / tennis-data qual_chall con columnas:
       tourney_level, tourney_name, round, winner_name, loser_name.

    Reglas:
    - tourney_level = C => Challenger.
    - round Q1/Q2/Q3/QR... o winner_entry/loser_entry=Q => Qualy, salvo Challenger explícito.
    - tourney_level = G/M/A/F/D => Tour si NO es qualy.
    - SourceFile con qual_chall no convierte por sí solo; solo ayuda al diagnóstico.
    - Si no hay evidencia clara, Unknown.
    """
    def val(*names):
        for c in names:
            try:
                if c in row.index:
                    v = normalizar_texto(row.get(c, ""))
                    if v != "" and v.lower() != "nan":
                        return v
            except Exception:
                pass
        return ""

    # Columnas estándar Jeff Sackmann / tennis-data CSV.
    tl_raw = val("MC_Level", "tourney_level", "Tourney Level", "level", "Level", "Series")
    round_raw = val("MC_Round", "round", "Round", "ronda")
    entry_raw = " ".join([
        val("winner_entry", "Winner Entry", "w_entry"),
        val("loser_entry", "Loser Entry", "l_entry")
    ])
    tourney_raw = val("MC_Tournament", "tourney_name", "Tournament", "Event", "Location")
    source_raw = val("SourceFile", "source_file")

    tl = limpiar(tl_raw)
    rnd = limpiar(round_raw)
    entry = limpiar(entry_raw)

    # 1) Challenger explícito por tourney_level C. Esto es lo más importante para tus CSV qual_chall.
    if tl in ["C", "CH", "CHALLENGER", "ATPCHALLENGER"]:
        return "challenger"

    # 2) Qualy explícita. En CSV qual_chall los partidos de previa ATP suelen venir como tourney_level=A + round=Q1/Q2.
    if rnd in ["Q", "Q1", "Q2", "Q3", "Q4", "QR", "QR1", "QR2", "QR3"]:
        return "qualy"
    if entry in ["Q", "WCQ"] or "QUAL" in entry:
        return "qualy"

    # 3) Tour explícito por código o texto.
    if tl in ["G", "M", "A", "F", "D", "ATPM", "ATP", "ATP250", "ATP500", "MASTERS1000", "GRANDSLAM"]:
        return "tour"

    def _txt(cols):
        return " ".join(str(row.get(c, "")) for c in cols if c in getattr(row, 'index', []))

    level_txt = _txt(["MC_Level", "Series", "Level", "Tour", "Category", "Circuit", "Event Type", "tourney_level"])
    event_txt = _txt(["MC_Tournament", "MC_Round", "Tournament", "Event", "Location", "Round", "Comment", "tourney_name", "round"])
    source_txt = _txt(["SourceFile", "source_file"])

    all_txt = f" {level_txt} {event_txt} {source_txt} ".lower()
    all_clean = " " + re.sub(r"[^a-z0-9]+", " ", all_txt) + " "
    level_clean = " " + re.sub(r"[^a-z0-9]+", " ", level_txt.lower()) + " "
    event_clean = " " + re.sub(r"[^a-z0-9]+", " ", event_txt.lower()) + " "

    # Qualy por texto.
    qualy_tokens = [
        " qual ", " qualifying ", " qualification ", " qualies ",
        " q1 ", " q2 ", " q3 ", " qr1 ", " qr2 ", " qr3 ",
        " qualifying draw "
    ]
    if any(x in all_clean for x in qualy_tokens):
        return "qualy"

    challenger_tokens = [
        " challenger ", " atp challenger ", " wta 125 ", " wta125 ",
        " ch50 ", " ch 50 ", " ch75 ", " ch 75 ", " ch100 ", " ch 100 ",
        " ch125 ", " ch 125 ", " ch175 ", " ch 175 "
    ]
    if any(x in all_clean for x in challenger_tokens):
        return "challenger"

    itf_tokens = [
        " itf ", " futures ", " future ", " m15 ", " m25 ", " m35 ",
        " w15 ", " w25 ", " w35 ", " w50 ", " w75 ", " w100 "
    ]
    if any(x in all_clean for x in itf_tokens):
        return "itf"

    tour_tokens = [
        " grand slam ", " grandslam ", " gs ",
        " masters 1000 ", " atp masters ", " wta 1000 ", " wta1000 ", " atp1000 ", " atp 1000 ",
        " atp 500 ", " atp500 ", " wta 500 ", " wta500 ",
        " atp 250 ", " atp250 ", " wta 250 ", " wta250 ",
        " atp finals ", " wta finals ", " main tour ", " tour level ",
        " olympics ", " united cup ", " davis cup ", " billie jean king cup "
    ]
    if any(x in level_clean for x in tour_tokens):
        return "tour"

    major_tour_events = [
        " australian open ", " roland garros ", " french open ", " wimbledon ", " us open ",
        " monte carlo ", " indian wells ", " miami ", " madrid ", " rome ", " roma ",
        " canada masters ", " cincinnati ", " shanghai ", " paris masters ",
        " queens ", " halle ", " basel ", " vienna ", " barcelona ", " doha ",
        " dubai ", " acapulco ", " rotterdam ", " beijing ", " tokyo "
    ]
    if any(x in event_clean for x in major_tour_events):
        return "tour"

    return "unknown"

def normalizar_superficie_hist(v, default="Hard"):
    """Normaliza superficies históricas: C/Clay/Red Clay, H/Hard, G/Grass."""
    raw = normalizar_texto(v).strip()
    key = limpiar(raw)
    if key in ["C", "CL", "CLAY", "REDCLAY", "RCLAY", "TIERRA", "TIERRABATIDA"] or "CLAY" in key:
        return "Clay"
    if key in ["G", "GR", "GRASS", "LAWN", "HIERBA"] or "GRASS" in key:
        return "Grass"
    if key in ["H", "HD", "HARD", "HARDO", "INDOORHARD", "OUTDOORHARD"] or "HARD" in key:
        return "Hard"
    if key in ["CARPET", "CARPETA"]:
        return "Hard"
    return default




def detectar_superficie_quality(row, col_surface=None):
    """Detecta superficie desde columna Surface o, si falta, desde Tournament/SourceFile."""
    primary = row.get(col_surface, "") if col_surface else ""
    surf = normalizar_superficie_hist(primary, default="")
    if surf in ["Hard", "Clay", "Grass"]:
        return surf

    txt = " ".join(str(row.get(c, "")) for c in [
        "MC_Surface", "Surface", "surface", "Superficie", "Court", "Court Surface", "MC_Tournament", "Tournament", "Event", "SourceFile", "Location"
    ])
    key = limpiar(txt)
    if any(x in key for x in ["CLAY", "REDCLAY", "TIERRA", "RG", "ROLANDGARROS", "MONTECARLO", "MADRID", "ROMA", "ROME"]):
        return "Clay"
    if any(x in key for x in ["GRASS", "HIERBA", "WIMBLEDON", "HALLE", "QUEENS", "NEWPORT"]):
        return "Grass"
    return "Hard"

def apellido_inicial_key(nombre):
    """Clave canónica tipo tennis-data: Matteo Arnaldi <-> Arnaldi M.
    Devuelve ARNALDI_M. Evita que el Match Count dependa del orden exacto.
    """
    toks = tokens(nombre)
    if len(toks) < 2:
        return ""

    # Si viene como "Bublik A." o "Arnaldi M.": apellido + inicial.
    if len(toks[-1]) == 1:
        surname = toks[0]
        initial = toks[-1][0]
    else:
        # Si viene como "Matteo Arnaldi": último token = apellido, primero = inicial.
        surname = toks[-1]
        initial = toks[0][0]

    surname = limpiar(surname)
    initial = limpiar(initial)
    return f"{surname}_{initial}" if surname and initial else ""


def surname_key(nombre):
    toks = tokens(nombre)
    if not toks:
        return ""
    if len(toks) >= 2 and len(toks[-1]) == 1:
        return limpiar(toks[0])
    return limpiar(toks[-1])


def variantes_nombre_quality(nombre):
    """
    Genera claves de búsqueda robustas para históricos:
    - Matteo Arnaldi
    - Arnaldi Matteo
    - Arnaldi M / M Arnaldi
    - clave canónica ARNALDI_M
    - MATTEOARNALDI limpio
    """
    raw = normalizar_texto(nombre)
    toks = tokens(raw)
    out = set()
    clean = limpiar(raw)
    if clean:
        out.add(clean)

    ai = apellido_inicial_key(raw)
    if ai:
        out.add(ai)
        out.add(limpiar(ai))

    sk = surname_key(raw)
    if sk:
        out.add(sk)

    if len(toks) >= 2:
        # Formato normal completo
        first, last = toks[0], toks[-1]
        out.add(limpiar(f"{last} {first}"))
        out.add(limpiar(f"{last} {first[0]}"))
        out.add(limpiar(f"{first[0]} {last}"))
        out.add(limpiar(f"{last}{first[0]}"))
        out.add(limpiar(f"{first[0]}{last}"))

        # Si el histórico viene abreviado tipo "Arnaldi M.", toks[0]=apellido, toks[1]=inicial.
        if len(toks[-1]) == 1:
            surname, initial = toks[0], toks[-1][0]
            out.add(limpiar(f"{surname} {initial}"))
            out.add(limpiar(f"{initial} {surname}"))
            out.add(limpiar(f"{surname}{initial}"))
            out.add(limpiar(f"{initial}{surname}"))

    return {x for x in out if x}


def fusionar_quality_rows(items):
    """Fusiona varias identidades históricas que pertenecen al mismo jugador."""
    rows = []
    raw_names = set()
    aliases = set()
    source_files = set()
    for item in items:
        rows.extend(item.get("_rows", []))
        raw_names.update(item.get("raw_names", []))
        aliases.update(item.get("aliases", []))
        source_files.update(item.get("source_files", []))

    total = len(rows)
    if total <= 0:
        return None

    surface_counts = {sf: sum(1 for r in rows if r["surface"] == sf) for sf in ["Hard", "Clay", "Grass"]}
    level_counts = {lv: sum(1 for r in rows if r["level"] == lv) for lv in ["tour", "challenger", "itf", "qualy", "unknown"]}

    tour_weighted = (
        level_counts["tour"] * 1.00 +
        level_counts["challenger"] * 0.62 +
        level_counts["qualy"] * 0.50 +
        level_counts["itf"] * 0.32 +
        level_counts["unknown"] * 0.42
    ) / total

    out = {
        "matches_total": total,
        "matches_surface": surface_counts,
        "level_counts": level_counts,
        "tour_quality": float(np.clip(tour_weighted, 0.30, 1.00)),
        "raw_names": sorted(raw_names)[:12],
        "aliases": sorted(aliases),
        "source_files": sorted(source_files)[:8],
        "_rows": rows,
    }

    stability = {}
    confidence = {}
    for sf in ["Hard", "Clay", "Grass"]:
        n_sf = surface_counts.get(sf, 0)
        sample_score = np.sqrt(n_sf / (n_sf + 14)) if n_sf > 0 else 0.0
        total_score = np.sqrt(total / (total + 28))
        stab = (sample_score * 0.72) + (total_score * 0.28)
        conf = 0.38 + 0.62 * stab * out["tour_quality"]

        if n_sf < 5:
            conf -= 0.18
        elif n_sf < 10:
            conf -= 0.09
        elif n_sf < 18:
            conf -= 0.04

        if level_counts["tour"] == 0 and level_counts["challenger"] >= 1:
            conf -= 0.07
        if level_counts["itf"] >= max(3, total * 0.45):
            conf -= 0.10
        if level_counts["unknown"] >= max(4, total * 0.50):
            conf -= 0.08

        stability[sf] = float(np.clip(stab, 0.05, 1.00))
        confidence[sf] = float(np.clip(conf, 0.28, 1.00))

    out["stability"] = stability
    out["confidence"] = confidence
    return out


@st.cache_data(show_spinner=False)
def crear_quality_map(circuito, cache_version=QUALITY_ENGINE_VERSION):
    """
    v22.3 Match Count Fix.
    Cuenta partidos desde históricos aunque los nombres vengan en formatos distintos.
    Devuelve también raw_names/source_files para debug visual.
    """
    hist = cargar_historicos(circuito, cache_version=cache_version)
    quality = {}

    if hist.empty:
        return quality

    df = hist.copy()
    if "Comment" in df.columns:
        # v22.17: filtro por Comment sin borrar filas CSV Challenger/Qualy.
        # Al concatenar Excel Tour + CSV qual_chall, las filas CSV suelen tener Comment vacío/NaN.
        # Antes, como los Excel sí tenían Comment=Completed, se aplicaba df[completed_mask]
        # y se eliminaban TODOS los CSV. Ahora solo filtramos filas que realmente traen Comment.
        comment_txt = df["Comment"].apply(normalizar_texto).replace({"nan": "", "NaN": "", "None": ""})
        has_comment = comment_txt.str.strip().ne("")
        completed_mask = comment_txt.str.contains("Completed", case=False, na=False)
        if has_comment.any() and completed_mask.sum() > 0:
            df = df[(~has_comment) | completed_mask]

    col_winner = buscar_columna(df, ["MC_Winner", "Winner", "Ganador", "Player1", "Player 1", "WName", "winner_name", "winner_name_clean", "Jugador1", "Home", "P1"])
    col_loser = buscar_columna(df, ["MC_Loser", "Loser", "Perdedor", "Player2", "Player 2", "LName", "loser_name", "loser_name_clean", "Jugador2", "Away", "P2"])
    col_surface = buscar_columna(df, ["MC_Surface", "Surface", "surface", "Superficie", "Court Surface", "Court", "surface_name"])

    if col_winner is None or col_loser is None:
        return quality

    player_buckets = {}

    for _, row in df.iterrows():
        level = detectar_nivel_torneo(row)
        surface = detectar_superficie_quality(row, col_surface)
        source = normalizar_texto(row.get("SourceFile", ""))

        for player in [normalizar_texto(row.get(col_winner, "")), normalizar_texto(row.get(col_loser, ""))]:
            if not player:
                continue
            pid = limpiar(player)
            if not pid:
                continue
            bucket = player_buckets.setdefault(pid, {
                "_rows": [], "raw_names": set(), "aliases": set(), "source_files": set()
            })
            bucket["_rows"].append({"surface": surface, "level": level})
            bucket["raw_names"].add(player)
            bucket["aliases"].update(variantes_nombre_quality(player))
            ai = apellido_inicial_key(player)
            if ai:
                bucket["aliases"].add(ai)
                bucket["aliases"].add(limpiar(ai))
            if source:
                bucket["source_files"].add(source)

    # Primera pasada: identidad exacta por PID histórico.
    alias_usage = {}
    for pid, data in player_buckets.items():
        for alias in data.get("aliases", []):
            alias_usage.setdefault(str(alias), set()).add(pid)

    for pid, data in player_buckets.items():
        q = fusionar_quality_rows([data])
        if q:
            quality[pid] = q
            # Índice espejo por clave apellido_inicial.
            # Esto permite casar Matteo Arnaldi con Arnaldi M. sin depender de fuzzy matching.
            for alias in data.get("aliases", []):
                alias = str(alias)
                # Guardamos alias fuertes siempre y alias simples solo si no chocan con otro jugador.
                if "_" in alias or len(alias_usage.get(alias, set())) == 1:
                    quality.setdefault(alias, q)
                    quality.setdefault(limpiar(alias), q)

    # Meta interna para debug/cache.
    raw_player_count = len(player_buckets)
    quality["__meta__"] = {
        "version": QUALITY_ENGINE_VERSION,
        "raw_player_count": raw_player_count,
        "quality_keys": len([k for k in quality.keys() if not str(k).startswith("__")]),
        "sample_names": sorted([next(iter(v.get("raw_names", [k])), k) if isinstance(v.get("raw_names", []), list) and v.get("raw_names", []) else str(k) for k, v in list(quality.items())[:12] if not str(k).startswith("__")])[:8],
    }

    return quality



def closest_quality_candidates(nombre, quality_map, limit=8):
    """
    v22.6 Name Radar Pro.
    Devuelve candidatos aunque el jugador no exista, y da prioridad a:
    - clave apellido_inicial exacta: ARNALDI_M
    - mismo apellido
    - fuzzy score normal
    """
    candidates = []
    user_ai = apellido_inicial_key(nombre)
    user_surname = surname_key(nombre)

    seen_objs = set()
    for qid, data in quality_map.items():
        if str(qid).startswith("__"):
            continue
        # Evita duplicados por índices espejo.
        obj_id = id(data)
        if obj_id in seen_objs:
            continue
        seen_objs.add(obj_id)

        labels = [qid] + list(data.get("raw_names", [])) + list(data.get("aliases", []))
        best_score = 0.0
        best_label = qid
        reason = "fuzzy"

        for cand in labels:
            cand_ai = apellido_inicial_key(cand)
            cand_surname = surname_key(cand)
            sc = similitud_nombre(nombre, cand)

            if user_ai and cand_ai and user_ai == cand_ai:
                sc = max(sc, 0.995)
                reason = "apellido+inicial"
            elif user_surname and cand_surname and user_surname == cand_surname:
                sc = max(sc, 0.86)
                reason = "apellido"
            elif user_surname and cand_surname and user_surname != cand_surname:
                # v22.21: radar estricto, no elevar candidatos con otro apellido por compartir nombre común.
                sc = min(sc, 0.89)

            t_user = tokens(nombre)
            t_cand = tokens(cand)
            if len(t_user) >= 2 and len(t_cand) >= 1:
                user_first = t_user[0]
                user_last = t_user[-1]
                if user_last in t_cand and any(x.startswith(user_first[0]) for x in t_cand if x != user_last):
                    sc = max(sc, 0.94)
                    reason = "apellido+inicial"
                if user_last in t_cand and user_first in t_cand:
                    sc = max(sc, 0.98)
                    reason = "nombre completo"

            if sc > best_score:
                best_score = sc
                best_label = cand

        if best_score >= 0.18 or (user_surname and user_surname in " ".join(map(str, labels))):
            candidates.append({
                "name": best_label,
                "score": float(best_score),
                "reason": reason,
                "matches_total": int(data.get("matches_total", 0)),
                "surface": data.get("matches_surface", {}),
                "source_files": data.get("source_files", [])[:3],
            })
    candidates.sort(key=lambda x: (x["score"], x["matches_total"]), reverse=True)
    return candidates[:limit]



def nombre_score_quality_direct(objetivo, candidato):
    """
    v22.21 Name Match Strict.
    Evita falsos positivos tipo:
    - Martin Landaluce -> Alvaro Lopez San Martin

    Reglas:
    - Exacto limpio: 1.00
    - Apellido + inicial exactos: 0.995
    - Mismo apellido + inicial compatible: 0.96
    - Mismo apellido sin inicial clara: 0.84
    - Fuzzy sin mismo apellido queda capado a 0.89, aunque SequenceMatcher dé alto.
    """
    if not objetivo or not candidato:
        return 0.0, "empty"

    n1, n2 = limpiar(objetivo), limpiar(candidato)
    if n1 and n1 == n2:
        return 1.0, "exacto"

    ai1, ai2 = apellido_inicial_key(objetivo), apellido_inicial_key(candidato)
    if ai1 and ai2 and ai1 == ai2:
        return 0.995, "apellido+inicial"

    s1, s2 = surname_key(objetivo), surname_key(candidato)
    t1, t2 = tokens(objetivo), tokens(candidato)

    if s1 and s2 and s1 == s2:
        initials1 = {x[0] for x in t1 if x and limpiar(x) != s1}
        initials2 = {x[0] for x in t2 if x and limpiar(x) != s2}
        if initials1 and initials2 and initials1 & initials2:
            return 0.96, "apellido+inicial"
        return 0.84, "apellido"

    # Si el apellido objetivo no aparece como token del candidato, NO permitimos match fuerte.
    # Esto bloquea falsos positivos por nombres comunes: Martin, Alejandro, Rafael, etc.
    sc = float(similitud_nombre(objetivo, candidato))
    if s1 and s1 not in {limpiar(x) for x in t2}:
        sc = min(sc, 0.89)

    return sc, "fuzzy"


@st.cache_data(show_spinner=False)
def buscar_quality_directo_historicos(nombre, circuito, cache_version=QUALITY_ENGINE_VERSION):
    """
    v22.9 Direct Match Count + Tour Quality Fix.
    No depende del quality_map guardado en cargar_datos/cache.
    Lee históricos cargados y cuenta el jugador en Winner/Loser al vuelo.
    """
    hist = cargar_historicos(circuito, cache_version=cache_version)
    meta = {
        "version": QUALITY_ENGINE_VERSION,
        "mode": "direct_historicos_cached",
        "hist_rows": int(len(hist)) if hist is not None else 0,
        "raw_player_count": 0,
        "quality_keys": 0,
        "sample_names": [],
    }

    fallback = {
        "matches_total": 0,
        "matches_surface": {"Hard": 0, "Clay": 0, "Grass": 0},
        "level_counts": {"tour": 0, "challenger": 0, "itf": 0, "qualy": 0, "unknown": 0},
        "tour_quality": 0.45,
        "stability": {"Hard": 0.05, "Clay": 0.05, "Grass": 0.05},
        "confidence": {"Hard": 0.32, "Clay": 0.32, "Grass": 0.32},
        "raw_names": [],
        "aliases": [],
        "source_files": [],
        "matched_name": "NO ENCONTRADO",
        "match_score": 0.0,
        "quality_map_size": 0,
        "quality_meta": meta,
        "candidate_matches": [],
        "direct_engine": True,
    }

    if hist is None or hist.empty:
        return fallback

    df = hist.copy()
    if "Comment" in df.columns:
        # v22.18: conservar CSV Challenger/Qualy aunque no traigan Comment.
        comment_txt = df["Comment"].apply(normalizar_texto).replace({"nan": "", "NaN": "", "None": ""})
        has_comment = comment_txt.str.strip().ne("")
        completed_mask = comment_txt.str.contains("Completed", case=False, na=False)
        if has_comment.any() and completed_mask.sum() > 0:
            df = df[(~has_comment) | completed_mask]

    col_winner = buscar_columna(df, ["MC_Winner", "Winner", "Ganador", "Player1", "Player 1", "WName", "winner_name", "winner_name_clean", "Jugador1", "Home", "P1"])
    col_loser = buscar_columna(df, ["MC_Loser", "Loser", "Perdedor", "Player2", "Player 2", "LName", "loser_name", "loser_name_clean", "Jugador2", "Away", "P2"])
    col_surface = buscar_columna(df, ["MC_Surface", "Surface", "surface", "Superficie", "Court Surface", "Court", "surface_name"])

    if col_winner is None or col_loser is None:
        return fallback

    rows = []
    raw_names = set()
    aliases = set()
    source_files = set()
    candidate_best = {}
    unique_players = set()
    best_score = 0.0
    best_name = "NO ENCONTRADO"

    # Umbral algo flexible: apellido+inicial entra seguro; fuzzy puro exige más.
    ACCEPT_SCORE = 0.92

    for _, row in df.iterrows():
        for col in [col_winner, col_loser]:
            cand = normalizar_texto(row.get(col, ""))
            if not cand:
                continue
            unique_players.add(cand)
            sc, reason = nombre_score_quality_direct(nombre, cand)

            # Guardamos radar de candidatos por nombre histórico.
            old = candidate_best.get(cand)
            if old is None or sc > old["score"]:
                candidate_best[cand] = {
                    "name": cand,
                    "score": float(sc),
                    "reason": reason,
                    "matches_total": 0,
                    "surface": {"Hard": 0, "Clay": 0, "Grass": 0},
                    "source_files": [],
                }

            if sc > best_score:
                best_score = float(sc)
                best_name = cand

            if sc >= ACCEPT_SCORE:
                surface = detectar_superficie_quality(row, col_surface)
                level = detectar_nivel_torneo(row)
                rows.append({"surface": surface, "level": level})
                raw_names.add(cand)
                aliases.update(variantes_nombre_quality(cand))
                ai = apellido_inicial_key(cand)
                if ai:
                    aliases.add(ai)
                    aliases.add(limpiar(ai))
                src = normalizar_texto(row.get("SourceFile", ""))
                if src:
                    source_files.add(src)

                cb = candidate_best[cand]
                cb["matches_total"] += 1
                cb["surface"][surface] = cb["surface"].get(surface, 0) + 1
                if src and src not in cb["source_files"]:
                    cb["source_files"].append(src)

    meta["raw_player_count"] = int(len(unique_players))
    meta["quality_keys"] = int(len(unique_players))
    meta["sample_names"] = sorted(list(unique_players))[:8]
    fallback["quality_meta"] = meta
    fallback["quality_map_size"] = int(len(unique_players))

    radar = sorted(candidate_best.values(), key=lambda x: (x["score"], x["matches_total"]), reverse=True)[:8]
    fallback["candidate_matches"] = radar
    if best_score > 0:
        fallback["matched_name"] = best_name
        fallback["match_score"] = float(best_score)

    if not rows:
        return fallback

    q = fusionar_quality_rows([{
        "_rows": rows,
        "raw_names": raw_names,
        "aliases": aliases,
        "source_files": source_files,
    }])
    if not q:
        return fallback

    q["matched_name"] = sorted(raw_names)[0] if raw_names else best_name
    q["match_score"] = float(best_score)
    q["quality_map_size"] = int(len(unique_players))
    q["quality_meta"] = meta
    q["candidate_matches"] = radar
    q["direct_engine"] = True
    return q

def buscar_quality(nombre, quality_map):
    """
    v22.3: busca primero por alias fuerte y después por similitud contra nombres reales.
    """
    nid = limpiar(nombre)
    variants = variantes_nombre_quality(nombre)
    ai_key = apellido_inicial_key(nombre)

    # Exacto o clave canónica apellido_inicial.
    for key in [nid, ai_key, limpiar(ai_key)]:
        if key and key in quality_map:
            out = quality_map[key].copy()
            raw = out.get("raw_names", [])
            out["matched_name"] = raw[0] if raw else key
            out["match_score"] = 1.0
            return out

    alias_hits = []
    for qid, data in quality_map.items():
        aliases = set(data.get("aliases", [])) | {qid}
        if variants & aliases:
            alias_hits.append((qid, data))

    if alias_hits:
        fused = fusionar_quality_rows([x[1] for x in alias_hits])
        if fused:
            fused["matched_name"] = ", ".join(sorted({x[0] for x in alias_hits})[:3])
            fused["match_score"] = 0.96
            return fused

    mejor, best = None, 0.0
    best_label = ""
    for qid, data in quality_map.items():
        candidates = [qid] + data.get("raw_names", []) + data.get("aliases", [])
        for cand in candidates:
            score = similitud_nombre(nombre, cand)
            # Refuerzo apellido+inicial para formatos tipo ARNALDI M.
            t_user = tokens(nombre)
            t_cand = tokens(cand)
            if len(t_user) >= 2 and len(t_cand) >= 1:
                user_last = t_user[-1]
                user_first_initial = t_user[0][0]
                cand_txt = " ".join(t_cand)
                if user_last in t_cand and user_first_initial in cand_txt:
                    score = max(score, 0.94)
            if score > best:
                best = score
                mejor = data
                best_label = cand

    if mejor is not None and best >= 0.72:
        out = mejor.copy()
        out["matched_name"] = best_label
        out["match_score"] = float(best)
        return out

    # No encontrado: devolvemos radar de candidatos para depurar el histórico.
    return {
        "matches_total": 0,
        "matches_surface": {"Hard": 0, "Clay": 0, "Grass": 0},
        "level_counts": {"tour": 0, "challenger": 0, "itf": 0, "qualy": 0, "unknown": 0},
        "tour_quality": 0.45,
        "stability": {"Hard": 0.05, "Clay": 0.05, "Grass": 0.05},
        "confidence": {"Hard": 0.32, "Clay": 0.32, "Grass": 0.32},
        "raw_names": [],
        "aliases": [],
        "source_files": [],
        "matched_name": "NO ENCONTRADO",
        "match_score": 0.0,
        "quality_map_size": len([k for k in quality_map.keys() if not str(k).startswith("__")]),
        "quality_meta": quality_map.get("__meta__", {}),
        "candidate_matches": closest_quality_candidates(nombre, quality_map, limit=8),
    }

@st.cache_data
def cargar_datos(circuito, cache_version=QUALITY_ENGINE_VERSION):
    r = rutas(circuito)
    fatigue_map = crear_fatigue_map(circuito)
    quality_map = crear_quality_map(circuito)

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

    # v22.29 safety: ensure fatigue_map exists even after cache/merge issues
    if 'fatigue_map' not in locals() or fatigue_map is None:
        fatigue_map = {}

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
            "Fatigue": buscar_fatigue(nombre, fatigue_map),
            "Quality": buscar_quality(nombre, quality_map)
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


def smart_set_dynamics(p1_win, p2_win, hold1, hold2, tb_rate, vol, surface, circuito="ATP", rank1=999, rank2=999):
    """
    v19 Smart Set Dynamics.
    ATP: mantiene estructura.
    WTA: evita coinflips artificiales y dog-set exagerado.
    """
    fav = max(p1_win, p2_win)
    hold_gap = abs(hold1 - hold2)

    dog_set_suppress = 0.0
    fav20_boost = 0.0
    long_match_adj = 0.0

    if fav >= 0.72:
        fav20_boost += 0.08
        dog_set_suppress += 0.10
        long_match_adj -= 0.05
    elif fav >= 0.66:
        fav20_boost += 0.05
        dog_set_suppress += 0.06
        long_match_adj -= 0.03

    if hold_gap >= 0.09:
        fav20_boost += 0.05
        dog_set_suppress += 0.06
    elif hold_gap >= 0.06:
        fav20_boost += 0.03
        dog_set_suppress += 0.03

    if tb_rate <= 0.24:
        fav20_boost += 0.04
        dog_set_suppress += 0.04
        long_match_adj -= 0.04

    if surface == "Clay":
        dog_set_suppress *= 0.85
        fav20_boost *= 0.90

    if vol >= 0.035:
        dog_set_suppress *= 0.70
        fav20_boost *= 0.75
        long_match_adj += 0.05

    if circuito == "WTA":
        top_player = rank1 <= 15 or rank2 <= 15
        rank_gap = abs(rank1 - rank2)

        if fav >= 0.68 and top_player:
            dog_set_suppress += 0.055
            fav20_boost += 0.040
            long_match_adj -= 0.035
        elif fav >= 0.64 and top_player:
            dog_set_suppress += 0.035
            fav20_boost += 0.025
            long_match_adj -= 0.020

        if rank_gap >= 40 and fav >= 0.62:
            dog_set_suppress += 0.035
            fav20_boost += 0.020
            long_match_adj -= 0.020

        if surface == "Clay":
            dog_set_suppress *= 0.92
            fav20_boost *= 0.92
            long_match_adj *= 0.85

        if fav < 0.58:
            dog_set_suppress *= 0.50
            fav20_boost *= 0.45
            long_match_adj += 0.025

    return {
        "dog_set_suppress": float(np.clip(dog_set_suppress, 0, 0.22)),
        "fav20_boost": float(np.clip(fav20_boost, 0, 0.20)),
        "long_match_adj": float(np.clip(long_match_adj, -0.12, 0.12))
    }







def straight_sets_guard_engine(circuito, surface, fav_prob, hold1, hold2, tb_rate, vol, rating_sanity, fav20, dogset, longm):
    """
    v22.20 Straight Sets Guard.
    Separa dos ideas que antes se mezclaban demasiado:
    - Over bajo útil: 6-4 6-4 / 7-5 6-3 puede ser buen over.
    - Partido largo / dog gana set: no debe inflarse si el favorito tiene control real.

    No toca ganador ni mercados over calculados por games. Solo ajusta:
    - favorito 2-0
    - underdog gana set
    - partido largo
    """
    out = {
        "active": False,
        "profile": "neutral",
        "fav20_boost": 0.0,
        "dogset_cut": 0.0,
        "long_cut": 0.0,
        "hold_gap": float(abs(hold1 - hold2)),
        "notes": []
    }

    if circuito != "ATP":
        return fav20, dogset, longm, out

    rs = rating_sanity or {}
    p1_rs = rs.get("p1", {}) or {}
    p2_rs = rs.get("p2", {}) or {}
    min_conf = min(p1_rs.get("confidence", 1.0), p2_rs.get("confidence", 1.0))
    min_surface = min(p1_rs.get("matches_surface", 99), p2_rs.get("matches_surface", 99))
    min_stability = min(p1_rs.get("stability", 1.0), p2_rs.get("stability", 1.0))

    hold_gap = abs(hold1 - hold2)

    # Condiciones de activación: favorito real, datos fiables y diferencia clara de hold.
    if fav_prob < 0.615:
        return fav20, dogset, longm, out
    # v22.21: favoritos muy claros también necesitan guardia si el hold gap es enorme.
    # Antes se excluían >73.5% y por eso spots tipo 6-4 6-3 podían inflar "dog gana set".
    clear_fav_mode = fav_prob >= 0.735

    if clear_fav_mode:
        if min_conf < 0.60 or min_surface < 18 or min_stability < 0.55:
            return fav20, dogset, longm, out
        if hold_gap < 0.115:
            return fav20, dogset, longm, out
        if tb_rate >= 0.32:
            return fav20, dogset, longm, out
    else:
        if min_conf < 0.74 or min_surface < 35 or min_stability < 0.72:
            return fav20, dogset, longm, out
        if hold_gap < 0.070:
            return fav20, dogset, longm, out
        if tb_rate >= 0.34:
            # Si hay entorno fuerte de tie-break, no forzamos 2-0.
            return fav20, dogset, longm, out

    boost = 0.030
    if fav_prob >= 0.64: boost += 0.012
    if fav_prob >= 0.67: boost += 0.010
    if fav_prob >= 0.735: boost += 0.018
    if fav_prob >= 0.78: boost += 0.010
    if hold_gap >= 0.085: boost += 0.018
    if hold_gap >= 0.105: boost += 0.012
    if hold_gap >= 0.140: boost += 0.014
    if min_conf >= 0.82: boost += 0.010
    if min_surface >= 100: boost += 0.008
    if tb_rate <= 0.27: boost += 0.006
    if surface == "Clay": boost *= 0.95

    boost = float(np.clip(boost, 0.0, 0.125))
    dog_cut = float(np.clip(boost * 1.10, 0.0, 0.135))
    long_cut = float(np.clip(boost * 0.82, 0.0, 0.105))

    out["active"] = True
    out["profile"] = "clear_favorite_control" if fav_prob >= 0.735 else "controlled_favorite"
    out["fav20_boost"] = boost
    out["dogset_cut"] = dog_cut
    out["long_cut"] = long_cut
    out["notes"].append("favorito fiable con ventaja clara de hold")
    out["notes"].append("over bajo no implica partido largo")

    fav20 = float(np.clip(fav20 + boost, 0.0, 0.95))
    dogset = float(np.clip(dogset - dog_cut, 0.05, 0.95))
    longm = float(np.clip(longm - long_cut, 0.05, 0.95))

    return fav20, dogset, longm, out


def favorite_2_0_sanity_guard(circuito, surface, fav_prob, fav20, dogset, longm, rating_sanity):
    """
    v22.25 Favorite 2-0 Sanity Guard.
    Evita probabilidades absurdamente altas de 2-0 cuando la confianza
    real o la calidad del histórico no justifican tanta seguridad.
    No toca ML ni overs; solo mercados derivados de sets.
    """
    out = {
        "active": False,
        "fav20_cap": None,
        "dogset_floor": None,
        "long_floor": None,
        "notes": []
    }

    if circuito != "ATP":
        return fav20, dogset, longm, out

    rs = rating_sanity or {}
    p1 = rs.get("p1", {}) or {}
    p2 = rs.get("p2", {}) or {}
    min_conf = min(p1.get("confidence", 1.0), p2.get("confidence", 1.0))
    min_quality = min(p1.get("tour_quality", 1.0), p2.get("tour_quality", 1.0))
    min_surface = min(p1.get("matches_surface", 99), p2.get("matches_surface", 99))
    min_stability = min(p1.get("stability", 1.0), p2.get("stability", 1.0))

    flags = []
    flags += list(p1.get("flags", []) or [])
    flags += list(p2.get("flags", []) or [])
    challenger_flag = any("challenger" in str(x).lower() or "qualy" in str(x).lower() for x in flags)

    cap = None
    floor = None
    long_floor = None

    # Con confianza real limitada no puede existir un 2-0 del 90-95%.
    if min_conf < 0.60:
        cap = 0.66
        floor = 0.26
        long_floor = 0.24
        out["notes"].append("cap 2-0 por confianza limitada")
    elif min_conf < 0.68:
        cap = 0.74
        floor = 0.20
        long_floor = 0.22
        out["notes"].append("cap 2-0 por confianza media")

    # Mucho Challenger/Qualy o calidad <70%: menos seguridad en sets corridos.
    if min_quality < 0.70 or challenger_flag:
        cap = min(cap if cap is not None else 0.82, 0.76)
        floor = max(floor if floor is not None else 0.16, 0.18)
        long_floor = max(long_floor if long_floor is not None else 0.18, 0.20)
        out["notes"].append("cap 2-0 por calidad Challenger/Qualy")

    # Muestra en superficie suficiente pero no elite: no bloquear, solo evitar 95%.
    if min_surface < 60 or min_stability < 0.78:
        cap = min(cap if cap is not None else 0.84, 0.80)
        floor = max(floor if floor is not None else 0.14, 0.16)
        out["notes"].append("cap 2-0 por muestra/stability no elite")

    # Incluso un favorito ATP clay al 80% rara vez merece 95% de 2-0 salvo confianza extrema.
    if fav_prob < 0.82:
        cap = min(cap if cap is not None else 0.86, 0.82)

    if cap is not None and fav20 > cap:
        out["active"] = True
        out["fav20_cap"] = float(cap)
        fav20 = float(cap)

    if floor is not None and dogset < floor:
        out["active"] = True
        out["dogset_floor"] = float(floor)
        dogset = float(floor)

    if long_floor is not None and longm < long_floor:
        out["active"] = True
        out["long_floor"] = float(long_floor)
        longm = float(long_floor)

    return float(np.clip(fav20, 0.0, 0.95)), float(np.clip(dogset, 0.05, 0.95)), float(np.clip(longm, 0.05, 0.95)), out


def upset_risk_guard_engine(circuito, surface, p1_cal, p1_raw, fav20, dogset, longm, rating_sanity):
    """
    v22.25 Upset Risk Guard.
    Evita que favoritos ATP Clay aparentemente claros se vendan como spots limpios
    cuando el propio sanity marca inflación/confianza limitada/calidad Challenger.
    No cambia el ganador bruto ni los overs; solo calibra ML final y mercados de sets.
    """
    out = {
        "active": False,
        "profile": "neutral",
        "ml_cap": None,
        "fav20_cap": None,
        "dogset_floor": None,
        "long_floor": None,
        "notes": []
    }

    if circuito != "ATP" or surface != "Clay":
        return p1_cal, fav20, dogset, longm, out

    rs = rating_sanity or {}
    p1 = rs.get("p1", {}) or {}
    p2 = rs.get("p2", {}) or {}

    min_conf = min(p1.get("confidence", 1.0), p2.get("confidence", 1.0))
    min_quality = min(p1.get("tour_quality", 1.0), p2.get("tour_quality", 1.0))
    min_surface = min(p1.get("matches_surface", 99), p2.get("matches_surface", 99))
    min_stability = min(p1.get("stability", 1.0), p2.get("stability", 1.0))

    flags = []
    flags += list(p1.get("flags", []) or [])
    flags += list(p2.get("flags", []) or [])
    flag_text = " | ".join(str(x).lower() for x in flags)

    fav_prob = max(p1_cal, 1 - p1_cal)
    raw_cal_gap = abs(float(p1_raw) - float(p1_cal))

    challenger_pressure = (min_quality < 0.72) or ("challenger" in flag_text) or ("qualy" in flag_text)
    rating_inflation = (raw_cal_gap >= 0.050) or ("inflado" in flag_text) or ("incoherente" in flag_text)
    data_limited = (min_conf < 0.65) or (min_stability < 0.82)
    # v22.27: en clay, un dog con 10-24 partidos de superficie NO es "sin datos";
    # es una muestra corta pero suficiente para exigir prudencia si el favorito sale demasiado limpio.
    dog_has_clay_data = min_surface >= 10
    short_surface_sample = 10 <= min_surface < 25

    # Caso típico: favorito 75-82%, pero con señales internas de fragilidad.
    # v22.27 relaja el trigger para capturar spots tipo big-server / favorito frágil en clay,
    # donde el Elo favorece mucho pero el underdog tiene muestra clay corta y potencial de swing.
    trigger = (
        fav_prob >= 0.75
        and dog_has_clay_data
        and (data_limited or challenger_pressure or short_surface_sample)
        and (rating_inflation or min_quality < 0.70 or min_conf < 0.70 or short_surface_sample)
    )

    if not trigger:
        return p1_cal, fav20, dogset, longm, out

    ml_cap = 0.765
    if min_conf < 0.60:
        ml_cap = 0.745
    if min_quality < 0.66:
        ml_cap -= 0.010
    if raw_cal_gap >= 0.070:
        ml_cap -= 0.010
    # v22.27: muestra clay corta del underdog = no permitir lectura de favorito 80%+ limpia.
    if short_surface_sample and fav_prob >= 0.78:
        ml_cap = min(ml_cap, 0.745)
    ml_cap = float(np.clip(ml_cap, 0.70, 0.77))

    fav20_cap = 0.62
    if min_conf < 0.60 or min_quality < 0.66:
        fav20_cap = 0.58
    if raw_cal_gap >= 0.070:
        fav20_cap -= 0.02
    if short_surface_sample and fav_prob >= 0.78:
        fav20_cap = min(fav20_cap, 0.58)
    fav20_cap = float(np.clip(fav20_cap, 0.52, 0.64))

    dog_floor = 0.34
    if min_surface >= 80:
        dog_floor = 0.36
    if min_conf < 0.58:
        dog_floor += 0.02
    if short_surface_sample and fav_prob >= 0.78:
        dog_floor = max(dog_floor, 0.38)
    dog_floor = float(np.clip(dog_floor, 0.30, 0.42))

    long_floor = 0.30
    if min_surface >= 80:
        long_floor = 0.32
    if short_surface_sample and fav_prob >= 0.78:
        long_floor = 0.34

    fav_is_p1 = p1_cal >= 0.50
    if fav_prob > ml_cap:
        p1_cal = ml_cap if fav_is_p1 else 1 - ml_cap

    fav20 = min(float(fav20), fav20_cap)
    dogset = max(float(dogset), dog_floor)
    longm = max(float(longm), long_floor)

    out["active"] = True
    out["profile"] = "inflated_favorite_upset_risk"
    out["ml_cap"] = ml_cap
    out["fav20_cap"] = fav20_cap
    out["dogset_floor"] = dog_floor
    out["long_floor"] = long_floor
    out["notes"].append("riesgo upset por favorito inflado/confianza limitada")
    if challenger_pressure:
        out["notes"].append("calidad Challenger/Qualy reduce seguridad")
    if rating_inflation:
        out["notes"].append("rating comprimido/inflado")
    if short_surface_sample:
        out["notes"].append("muestra clay corta: favorito vulnerable")

    return float(np.clip(p1_cal, 0.05, 0.95)), float(np.clip(fav20, 0.0, 0.95)), float(np.clip(dogset, 0.05, 0.95)), float(np.clip(longm, 0.05, 0.95)), out



def low_over_long_match_split_guard(circuito, surface, p1_cal, e1, e2, hold1, hold2, raw_tb, rating_sanity, fav20, dogset, longm, upset_risk_guard=None):
    """
    v22.30 Low Over vs Long Match Split.
    Separa una señal fuerte de Over 18.5 de la lectura de partido largo/dog set.
    Caso objetivo: favorito clay fiable 56-64%, mucha muestra, Elo clay elite,
    TB bajo/medio. No toca ML ni overs; solo mercados derivados de sets.
    """
    out = {
        "active": False,
        "profile": "neutral",
        "fav20_boost": 0.0,
        "dogset_cut": 0.0,
        "long_cut": 0.0,
        "notes": []
    }

    if circuito != "ATP" or surface != "Clay":
        return fav20, dogset, longm, out

    if upset_risk_guard and upset_risk_guard.get("active", False):
        return fav20, dogset, longm, out

    rs = rating_sanity or {}
    p1 = rs.get("p1", {}) or {}
    p2 = rs.get("p2", {}) or {}
    min_conf = min(p1.get("confidence", 1.0), p2.get("confidence", 1.0))
    min_surface = min(p1.get("matches_surface", 99), p2.get("matches_surface", 99))
    min_quality = min(p1.get("tour_quality", 1.0), p2.get("tour_quality", 1.0))

    fav_prob = max(float(p1_cal), 1.0 - float(p1_cal))
    fav_is_p1 = p1_cal >= 0.50
    fav_elo = e1 if fav_is_p1 else e2
    dog_elo = e2 if fav_is_p1 else e1
    fav_hold = hold1 if fav_is_p1 else hold2
    dog_hold = hold2 if fav_is_p1 else hold1

    elo_gap = fav_elo - dog_elo
    hold_gap = fav_hold - dog_hold

    # Solo favoritos clay realmente fiables, no favoritos de hard ni favoritos vulnerables.
    trigger = (
        0.555 <= fav_prob <= 0.645
        and fav_elo >= 1900
        and elo_gap >= 65
        and min_conf >= 0.80
        and min_surface >= 80
        and min_quality >= 0.74
        and raw_tb <= 0.32
        and hold_gap >= 0.025
    )

    if not trigger:
        return fav20, dogset, longm, out

    boost = 0.055
    dog_cut = 0.055
    long_cut = 0.035

    if fav_prob >= 0.59:
        boost += 0.015
        dog_cut += 0.010

    if fav_elo >= 1930 and elo_gap >= 80:
        boost += 0.015
        dog_cut += 0.010
        long_cut += 0.010

    # No convertirlo en "spot 2-0 fuerte"; solo corregir el sesgo de dog set/long.
    fav20 = float(np.clip(fav20 + boost, 0.0, 0.58))
    dogset = float(np.clip(dogset - dog_cut, 0.34, 0.95))
    longm = float(np.clip(longm - long_cut, 0.34, 0.95))

    out["active"] = True
    out["profile"] = "low_over_not_long_match"
    out["fav20_boost"] = float(boost)
    out["dogset_cut"] = float(dog_cut)
    out["long_cut"] = float(long_cut)
    out["notes"].append("over bajo fuerte no implica dog set/partido largo")
    out["notes"].append("favorito clay fiable con muestra alta")

    return fav20, dogset, longm, out


def elite_clay_opponent_guard(circuito, surface, p1_cal, e1, e2, rating_sanity, fav20, dogset, longm):
    """
    v22.31 Elite Clay Opponent Guard.
    Evita 2-0 demasiado extremos cuando el underdog también es jugador clay fuerte.
    No toca ML ni overs; solo mercados derivados de sets.
    """
    out = {
        "active": False,
        "profile": "neutral",
        "fav20_cap": None,
        "dogset_floor": None,
        "notes": []
    }

    if circuito != "ATP" or surface != "Clay":
        return fav20, dogset, longm, out

    rs = rating_sanity or {}
    p1 = rs.get("p1", {}) or {}
    p2 = rs.get("p2", {}) or {}

    min_conf = min(p1.get("confidence", 1.0), p2.get("confidence", 1.0))
    min_surface = min(p1.get("matches_surface", 99), p2.get("matches_surface", 99))
    min_quality = min(p1.get("tour_quality", 1.0), p2.get("tour_quality", 1.0))

    fav_prob = max(float(p1_cal), 1.0 - float(p1_cal))
    fav_is_p1 = p1_cal >= 0.50

    fav_elo = e1 if fav_is_p1 else e2
    dog_elo = e2 if fav_is_p1 else e1
    elo_gap = fav_elo - dog_elo

    # Rival clay fuerte: no tratar su set como casi imposible.
    trigger = (
        circuito == "ATP"
        and surface == "Clay"
        and 0.68 <= fav_prob <= 0.80
        and fav20 >= 0.74
        and dog_elo >= 1840
        and elo_gap <= 115
        and min_conf >= 0.78
        and min_surface >= 90
        and min_quality >= 0.72
    )

    if not trigger:
        return fav20, dogset, longm, out

    cap = 0.72
    floor = 0.26

    # Si el favorito no llega al 75%, todavía menos agresivo con el 2-0.
    if fav_prob < 0.75:
        cap = 0.70
        floor = 0.28

    # Si el underdog clay está por encima de 1870, subir un poco su capacidad de set.
    if dog_elo >= 1870:
        cap = min(cap, 0.70)
        floor = max(floor, 0.28)

    fav20 = float(min(fav20, cap))
    dogset = float(max(dogset, floor))

    # Partido largo no lo subimos demasiado: puede ser 7-6 6-4 como Musetti/Cerundolo.
    longm = float(max(longm, 0.30))

    out["active"] = True
    out["profile"] = "elite_clay_opponent"
    out["fav20_cap"] = float(cap)
    out["dogset_floor"] = float(floor)
    out["notes"].append("underdog clay fuerte: 2-0 no debe ser extremo")

    return float(np.clip(fav20, 0.0, 0.95)), float(np.clip(dogset, 0.05, 0.95)), float(np.clip(longm, 0.05, 0.95)), out

def wta_match_script_engine(d1, d2, s1, s2, hold1, hold2, ret1, ret2, surface, circuito):
    """
    v19.2 Rating Sanity Engine
    Detecta perfiles reales WTA:
    - dominadora top
    - clay grinder
    - streaky hitter
    - dangerous dog
    """
    out = {
        "active": False,
        "script": "neutral",
        "fav20_mult": 1.0,
        "dogset_mult": 1.0,
        "long_mult": 1.0,
        "vol_mult": 1.0
    }

    if circuito != "WTA":
        return out

    r1 = d1.get("Rank", 999)
    r2 = d2.get("Rank", 999)

    e1 = d1.get(surface, 1500)
    e2 = d2.get(surface, 1500)

    fav_is_p1 = e1 >= e2
    fav_rank = r1 if fav_is_p1 else r2
    dog_rank = r2 if fav_is_p1 else r1

    fav_hold = hold1 if fav_is_p1 else hold2
    fav_ret = ret1 if fav_is_p1 else ret2

    dog_hold = hold2 if fav_is_p1 else hold1

    hold_gap = abs(hold1 - hold2)

    ace1 = s1.get("Ace%", 0)
    ace2 = s2.get("Ace%", 0)

    # 1) Dominadora top WTA
    if fav_rank <= 12 and fav_ret >= 0.36 and hold_gap >= 0.06:
        out["active"] = True
        out["script"] = "top_dominator"
        out["fav20_mult"] = 1.22
        out["dogset_mult"] = 0.78
        out["long_mult"] = 0.78
        out["vol_mult"] = 0.82

    # 2) Clay grinder
    elif surface == "Clay" and fav_ret >= 0.34 and dog_hold <= 0.58:
        out["active"] = True
        out["script"] = "clay_grinder"
        out["fav20_mult"] = 1.14
        out["dogset_mult"] = 0.84
        out["long_mult"] = 0.88
        out["vol_mult"] = 0.90

    # 3) Streaky hitter
    elif ace1 >= 8 or ace2 >= 8:
        out["active"] = True
        out["script"] = "streaky_hitter"
        out["fav20_mult"] = 0.92
        out["dogset_mult"] = 1.10
        out["long_mult"] = 1.08
        out["vol_mult"] = 1.10

    # 4) Dangerous underdog
    elif dog_rank <= 35 and hold_gap <= 0.04:
        out["active"] = True
        out["script"] = "dangerous_dog"
        out["fav20_mult"] = 0.88
        out["dogset_mult"] = 1.14
        out["long_mult"] = 1.12
        out["vol_mult"] = 1.12

    return out


def elite_wta_separation(d1, d2, hold1, hold2, ret1, ret2, surface, circuito):
    """
    v19.1 Rating Sanity Engine.
    La WTA no solo es caos: las top consolidan ventajas y castigan más.
    Ajusta solo WTA y protege ATP.
    """
    info = {
        "active": False,
        "hold_adj1": 0.0,
        "hold_adj2": 0.0,
        "ret_adj1": 0.0,
        "ret_adj2": 0.0,
        "vol_mult": 1.0,
        "top_player": "",
        "edge_label": "normal"
    }

    if circuito != "WTA":
        return hold1, hold2, ret1, ret2, info

    r1 = d1.get("Rank", 999)
    r2 = d2.get("Rank", 999)
    e1 = d1.get(surface, 1500)
    e2 = d2.get(surface, 1500)

    elo_gap = abs(e1 - e2)
    rank_gap = abs(r1 - r2)

    p1_top = r1 <= 15
    p2_top = r2 <= 15

    # Jugadora top con ventaja Elo/ranking: más separación real.
    if p1_top and (e1 >= e2 + 80 or r1 + 20 <= r2):
        info["active"] = True
        info["top_player"] = d1.get("Player", "Jugador 1")
        info["hold_adj1"] += 0.020
        info["ret_adj1"] += 0.020
        info["hold_adj2"] -= 0.010
        info["vol_mult"] *= 0.82
        info["edge_label"] = "top_wta_p1"

    if p2_top and (e2 >= e1 + 80 or r2 + 20 <= r1):
        info["active"] = True
        info["top_player"] = d2.get("Player", "Jugador 2")
        info["hold_adj2"] += 0.020
        info["ret_adj2"] += 0.020
        info["hold_adj1"] -= 0.010
        info["vol_mult"] *= 0.82
        info["edge_label"] = "top_wta_p2"

    # Diferencia grande aunque no sea top15.
    if rank_gap >= 45 and elo_gap >= 120:
        info["active"] = True
        if e1 > e2:
            info["hold_adj1"] += 0.012
            info["ret_adj1"] += 0.012
            info["hold_adj2"] -= 0.006
        else:
            info["hold_adj2"] += 0.012
            info["ret_adj2"] += 0.012
            info["hold_adj1"] -= 0.006
        info["vol_mult"] *= 0.90
        if info["edge_label"] == "normal":
            info["edge_label"] = "rank_elo_gap"

    # En clay dejamos algo más de swing, pero no anulamos élite.
    if surface == "Clay":
        info["vol_mult"] = min(1.0, info["vol_mult"] * 1.04)

    hold1 = np.clip(hold1 + info["hold_adj1"], 0.42, 0.86)
    hold2 = np.clip(hold2 + info["hold_adj2"], 0.42, 0.86)
    ret1 = np.clip(ret1 + info["ret_adj1"], 0.10, 0.42)
    ret2 = np.clip(ret2 + info["ret_adj2"], 0.10, 0.42)

    return hold1, hold2, ret1, ret2, info



def clay_return_weight_engine(d1, d2, s1, s2, hold1, hold2, ret1, ret2, surface, circuito):
    out = {
        "active": False, "profile": "neutral", "vol_mult": 1.0,
        "hold_adj1": 0.0, "hold_adj2": 0.0,
        "ret_adj1": 0.0, "ret_adj2": 0.0,
        "notes": []
    }
    if circuito != "ATP" or surface != "Clay":
        return hold1, hold2, ret1, ret2, out

    e1, e2 = d1.get("Clay",1500), d2.get("Clay",1500)
    r1, r2 = d1.get("Rank",999), d2.get("Rank",999)
    gap = abs(e1 - e2)
    ace1, ace2 = s1.get("ace",0.05), s2.get("ace",0.05)

    if ret1 >= 0.335 and hold1 <= 0.705:
        out["active"] = True
        out["profile"] = "clay_grinder_p1"
        out["ret_adj1"] += 0.018
        out["hold_adj1"] -= 0.006
        out["vol_mult"] *= 0.94
        out["notes"].append("P1 grinder")

    if ret2 >= 0.335 and hold2 <= 0.705:
        out["active"] = True
        out["profile"] = "clay_grinder_p2"
        out["ret_adj2"] += 0.018
        out["hold_adj2"] -= 0.006
        out["vol_mult"] *= 0.94
        out["notes"].append("P2 grinder")

    if gap >= 115:
        out["active"] = True
        if e1 > e2:
            out["profile"] = "clay_specialist_p1"
            out["ret_adj1"] += 0.018
            out["hold_adj1"] += 0.008
            out["hold_adj2"] -= 0.006
            out["vol_mult"] *= 0.89
            out["notes"].append("P1 clay edge")
        else:
            out["profile"] = "clay_specialist_p2"
            out["ret_adj2"] += 0.018
            out["hold_adj2"] += 0.008
            out["hold_adj1"] -= 0.006
            out["vol_mult"] *= 0.89
            out["notes"].append("P2 clay edge")

    if e1 > e2 + 80 and r1 + 35 <= r2:
        out["active"] = True
        out["profile"] = "clay_favorite_p1"
        out["ret_adj1"] += 0.012
        out["hold_adj1"] += 0.006
        out["vol_mult"] *= 0.92
        out["notes"].append("P1 rank+clay edge")

    if e2 > e1 + 80 and r2 + 35 <= r1:
        out["active"] = True
        out["profile"] = "clay_favorite_p2"
        out["ret_adj2"] += 0.012
        out["hold_adj2"] += 0.006
        out["vol_mult"] *= 0.92
        out["notes"].append("P2 rank+clay edge")

    if ace1 >= 0.105 and ret1 <= 0.275:
        out["active"] = True
        out["hold_adj1"] -= 0.014
        out["vol_mult"] *= 1.04
        out["notes"].append("P1 big server clay nerf")
        if out["profile"] == "neutral":
            out["profile"] = "big_server_nerf_p1"

    if ace2 >= 0.105 and ret2 <= 0.275:
        out["active"] = True
        out["hold_adj2"] -= 0.014
        out["vol_mult"] *= 1.04
        out["notes"].append("P2 big server clay nerf")
        if out["profile"] == "neutral":
            out["profile"] = "big_server_nerf_p2"

    out["hold_adj1"] = float(np.clip(out["hold_adj1"], -0.025, 0.030))
    out["hold_adj2"] = float(np.clip(out["hold_adj2"], -0.025, 0.030))
    out["ret_adj1"] = float(np.clip(out["ret_adj1"], -0.005, 0.035))
    out["ret_adj2"] = float(np.clip(out["ret_adj2"], -0.005, 0.035))
    out["vol_mult"] = float(np.clip(out["vol_mult"], 0.82, 1.10))

    hold1 = np.clip(hold1 + out["hold_adj1"], 0.42, 0.84)
    hold2 = np.clip(hold2 + out["hold_adj2"], 0.42, 0.84)
    ret1 = np.clip(ret1 + out["ret_adj1"], 0.10, 0.42)
    ret2 = np.clip(ret2 + out["ret_adj2"], 0.10, 0.42)

    return hold1, hold2, ret1, ret2, out



def elite_atp_clay_protection(d1, d2, hold1, hold2, ret1, ret2, surface, circuito):
    """
    v21.1 Protección para élites ATP en clay.
    Evita compresión artificial tipo coinflip para top5 con clara ventaja clay.
    """
    out = {
        "active": False,
        "fav": "",
        "hold_boost": 0.0,
        "ret_boost": 0.0,
        "dog_hold_nerf": 0.0,
        "vol_mult": 1.0
    }

    if circuito != "ATP" or surface != "Clay":
        return hold1, hold2, ret1, ret2, out

    r1, r2 = d1.get("Rank", 999), d2.get("Rank", 999)
    e1, e2 = d1.get("Clay", 1500), d2.get("Clay", 1500)

    gap = abs(e1 - e2)
    rank_gap = abs(r1 - r2)

    p1_elite = r1 <= 5 and e1 >= 1950
    p2_elite = r2 <= 5 and e2 >= 1950

    if p1_elite and e1 > e2 and gap >= 130 and rank_gap >= 20:
        out["active"] = True
        out["fav"] = "p1"
        out["hold_boost"] = 0.018
        out["ret_boost"] = 0.010
        out["dog_hold_nerf"] = -0.010
        out["vol_mult"] = 0.84

    elif p2_elite and e2 > e1 and gap >= 130 and rank_gap >= 20:
        out["active"] = True
        out["fav"] = "p2"
        out["hold_boost"] = 0.018
        out["ret_boost"] = 0.010
        out["dog_hold_nerf"] = -0.010
        out["vol_mult"] = 0.84

    if out["active"]:
        if out["fav"] == "p1":
            hold1 += out["hold_boost"]
            ret1 += out["ret_boost"]
            hold2 += out["dog_hold_nerf"]
        else:
            hold2 += out["hold_boost"]
            ret2 += out["ret_boost"]
            hold1 += out["dog_hold_nerf"]

    hold1 = np.clip(hold1, 0.42, 0.86)
    hold2 = np.clip(hold2, 0.42, 0.86)
    ret1 = np.clip(ret1, 0.10, 0.42)
    ret2 = np.clip(ret2, 0.10, 0.42)

    return hold1, hold2, ret1, ret2, out


def clay_market_adjustments(circuito, surface, clay_engine, fav20, dogset, longm, p1_cal):
    if circuito != "ATP" or surface != "Clay" or not clay_engine.get("active", False):
        return fav20, dogset, longm

    profile = clay_engine.get("profile", "")
    fav_prob = max(p1_cal, 1 - p1_cal)

    if "grinder" in profile:
        longm *= 1.06
        dogset *= 1.03

    if "specialist" in profile or "favorite" in profile:
        if fav_prob >= 0.62:
            fav20 *= 1.08
            dogset *= 0.94
            longm *= 0.96
        if fav_prob >= 0.70:
            fav20 *= 1.10
            dogset *= 0.88
            longm *= 0.92

    if "big_server_nerf" in profile:
        dogset *= 1.06
        longm *= 1.04

    return (
        float(np.clip(fav20, 0.0, 0.95)),
        float(np.clip(dogset, 0.05, 0.95)),
        float(np.clip(longm, 0.05, 0.95))
    )



def clay_dominance_preservation(d1, d2, hold1, hold2, ret1, ret2, surface, circuito):
    out = {
        "active": False, "fav": "", "profile": "neutral", "vol_mult": 1.0,
        "market_fav20_mult": 1.0, "market_dogset_mult": 1.0, "market_long_mult": 1.0
    }
    if circuito != "ATP" or surface != "Clay":
        return hold1, hold2, ret1, ret2, out

    r1, r2 = d1.get("Rank",999), d2.get("Rank",999)
    e1, e2 = d1.get("Clay",1500), d2.get("Clay",1500)
    h1elo, h2elo = d1.get("Hard",1500), d2.get("Hard",1500)

    if e1 >= e2:
        fav = "p1"; fav_rank = r1; fav_elo = e1; dog_elo = e2; fav_delta = e1-h1elo; dog_delta = e2-h2elo
    else:
        fav = "p2"; fav_rank = r2; fav_elo = e2; dog_elo = e1; fav_delta = e2-h2elo; dog_delta = e1-h1elo

    elo_gap = fav_elo - dog_elo
    elite_specialist = fav_elo >= 1920 and elo_gap >= 70
    clay_identity = fav_delta >= dog_delta + 45 and elo_gap >= 60
    proven = fav_rank <= 30 and elo_gap >= 75

    if elite_specialist or clay_identity or proven:
        out["active"] = True
        out["fav"] = fav
        out["profile"] = "clay_dominator"
        hold_boost = 0.022 if elite_specialist else 0.016
        ret_boost = 0.016 if elite_specialist else 0.012
        dog_hold_nerf = -0.012
        dog_ret_nerf = -0.006
        out["vol_mult"] = 0.82 if elite_specialist else 0.88
        out["market_fav20_mult"] = 1.24 if elite_specialist else 1.16
        out["market_dogset_mult"] = 0.72 if elite_specialist else 0.82
        out["market_long_mult"] = 0.76 if elite_specialist else 0.84

        if fav == "p1":
            hold1 += hold_boost; ret1 += ret_boost; hold2 += dog_hold_nerf; ret2 += dog_ret_nerf
        else:
            hold2 += hold_boost; ret2 += ret_boost; hold1 += dog_hold_nerf; ret1 += dog_ret_nerf

    return (
        np.clip(hold1,0.42,0.86),
        np.clip(hold2,0.42,0.86),
        np.clip(ret1,0.10,0.42),
        np.clip(ret2,0.10,0.42),
        out
    )


# =========================================================
# v22 RATING SANITY ENGINE
# =========================================================

def rating_sanity_engine(d1, d2, surface, circuito):
    """
    v22.1 Match Count + Tour Quality Engine.
    Combina el sanity v22 con evidencia real de históricos:
    - nº partidos por superficie
    - calidad Tour / Challenger / ITF
    - stability score
    - confidence real del Elo
    - penalización de ratings pequeños o inflados
    """
    def player_sanity(d):
        rank = d.get("Rank", 999)
        elo_surface = d.get(surface, 1500)
        elo_hard = d.get("Hard", 1500)
        elo_clay = d.get("Clay", 1500)
        elo_grass = d.get("Grass", 1500)
        q = d.get("Quality", {}) or {}
        # v22.18: fuerza un conteo directo cacheado y lo usa si aporta más partidos.
        # Esto corrige el caso en el que el QualityMap global queda indexado solo con ATP Tour
        # aunque los CSV Challenger estén cargados. Al estar cacheado, no bloquea la simulación.
        q_direct = buscar_quality_directo_historicos(d.get("Player", ""), circuito)
        try:
            q_total = int(q.get("matches_total", 0) or 0)
            d_total = int(q_direct.get("matches_total", 0) or 0)
            q_ch = int((q.get("level_counts", {}) or {}).get("challenger", 0) or 0) + int((q.get("level_counts", {}) or {}).get("qualy", 0) or 0)
            d_ch = int((q_direct.get("level_counts", {}) or {}).get("challenger", 0) or 0) + int((q_direct.get("level_counts", {}) or {}).get("qualy", 0) or 0)
        except Exception:
            q_total, d_total, q_ch, d_ch = 0, 0, 0, 0
        if (d_total > q_total) or (d_ch > q_ch) or (not q.get("quality_meta")) or q.get("matched_name") in [None, "", "NO ENCONTRADO"]:
            q = q_direct

        matches_total = q.get("matches_total", 0)
        surface_counts = q.get("matches_surface", {}) if isinstance(q.get("matches_surface", {}), dict) else {}
        matches_surface = surface_counts.get(surface, 0)
        level_counts = q.get("level_counts", {})
        tour_quality = q.get("tour_quality", 0.45)
        stability = q.get("stability", {}).get(surface, 0.05)
        data_conf = q.get("confidence", {}).get(surface, 0.32)

        confidence = float(data_conf)
        flags = []

        if matches_total == 0 and q.get("match_score", 0.0) == 0.0:
            flags.append("jugador no encontrado en históricos cargados")

        if matches_surface < 5:
            confidence -= 0.16
            flags.append("muy pocos partidos superficie")
        elif matches_surface < 10:
            confidence -= 0.08
            flags.append("muestra superficie baja")
        elif matches_surface < 18:
            confidence -= 0.04
            flags.append("muestra superficie media")

        if matches_total < 20:
            confidence -= 0.06
            flags.append("pocos partidos totales")

        if matches_surface < 10 and matches_total < 30 and level_counts.get("tour", 0) >= max(1, int(matches_total * 0.80)):
            flags.append("muestra ATP pequeña")

        if tour_quality < 0.52:
            confidence -= 0.10
            flags.append("calidad ITF/unknown alta")
        elif tour_quality < 0.68:
            confidence -= 0.05
            flags.append("calidad challenger/qualy")

        # Elo muy alto con ranking no equivalente
        if elo_surface >= 1900 and rank > 50:
            confidence -= 0.18
            flags.append("elo_surface_inflado")

        if elo_surface >= 1850 and rank > 80:
            confidence -= 0.22
            flags.append("elo/rank incoherente")

        # Delta clay-hard sospechoso
        if surface == "Clay" and (elo_clay - elo_hard) >= 180:
            confidence -= 0.13
            flags.append("delta clay-hard alto")

        # Jugador fuera top100 con Elo top
        if rank > 100 and elo_surface >= 1800:
            confidence -= 0.18
            flags.append("posible challenger/junior inflation")

        confidence = float(np.clip(confidence, 0.25, 1.00))

        # Elo efectivo: si la confianza es baja, reduce ventaja extrema hacia su Elo general medio.
        baseline = np.mean([elo_hard, elo_clay, elo_grass])
        shrink = (1.0 - confidence) * 0.52
        elo_effective = elo_surface - (elo_surface - baseline) * shrink

        # Penalización adicional para Elo alto con muestra débil.
        elo_penalty = 0.0
        if elo_surface >= 1800 and confidence < 0.62:
            elo_penalty = min(70, (0.62 - confidence) * 150)
            elo_effective -= elo_penalty

        return {
            "confidence": confidence,
            "flags": flags,
            "rank": rank,
            "elo_surface": elo_surface,
            "elo_effective": float(elo_effective),
            "elo_penalty": float(elo_surface - elo_effective),
            "matches_total": int(matches_total),
            "matches_surface": int(matches_surface),
            "matches_by_surface": {"Hard": int(surface_counts.get("Hard", 0)), "Clay": int(surface_counts.get("Clay", 0)), "Grass": int(surface_counts.get("Grass", 0))},
            "tour_quality": float(tour_quality),
            "stability": float(stability),
            "level_counts": level_counts,
            "matched_name": q.get("matched_name", "N/A"),
            "match_score": float(q.get("match_score", 0.0)),
            "raw_names": q.get("raw_names", []),
            "source_files": q.get("source_files", []),
            "quality_map_size": int(q.get("quality_map_size", 0)),
            "quality_meta": q.get("quality_meta", {}),
            "candidate_matches": q.get("candidate_matches", [])
        }

    s1 = player_sanity(d1)
    s2 = player_sanity(d2)

    min_conf = min(s1["confidence"], s2["confidence"])
    vol_mult = 1.0
    if min_conf < 0.45:
        vol_mult = 1.16
    elif min_conf < 0.60:
        vol_mult = 1.11
    elif min_conf < 0.75:
        vol_mult = 1.06

    return {
        "p1": s1,
        "p2": s2,
        "vol_mult": vol_mult,
        "active": bool(s1["flags"] or s2["flags"]),
        "version": APP_VERSION
    }


def sim_match(d1, d2, surface, circuito, best_of=3, n=5000, context_row=None, progress_callback=None):
    e1, e2 = d1[surface], d2[surface]

    # v22.1 Match Count + Tour Quality Engine
    rating_sanity = rating_sanity_engine(d1, d2, surface, circuito)
    e1_eff = rating_sanity.get("p1", {}).get("elo_effective", e1)
    e2_eff = rating_sanity.get("p2", {}).get("elo_effective", e2)
    elo_diff = e1_eff - e2_eff

    # v15: usa stats específicas de superficie si existen
    s1 = get_stats_surface(d1, surface)
    s2 = get_stats_surface(d2, surface)

    raw1 = calc_hold(s1, elo_diff, surface, circuito)
    raw2 = calc_hold(s2, -elo_diff, surface, circuito)
    ret1 = calc_return_strength(s1, e1, surface)
    ret2 = calc_return_strength(s2, e2, surface)

    # v19 WTA Return Compression:
    # evita que todas las jugadoras parezcan returners elite y vuelvan el partido coinflip.
    if circuito == "WTA":
        ret1 *= 0.90
        ret2 *= 0.90

        if d1.get("Rank", 999) <= 10:
            ret1 *= 1.06
        elif d1.get("Rank", 999) <= 20:
            ret1 *= 1.03

        if d2.get("Rank", 999) <= 10:
            ret2 *= 1.06
        elif d2.get("Rank", 999) <= 20:
            ret2 *= 1.03

        ret1 = np.clip(ret1, 0.10, 0.38)
        ret2 = np.clip(ret2, 0.10, 0.38)

    hold1, hold2 = aplicar_return_pressure(raw1, raw2, ret1, ret2, surface)

    # v21 Rating Sanity Engine
    hold1, hold2, ret1, ret2, clay_engine = clay_return_weight_engine(
        d1, d2, s1, s2, hold1, hold2, ret1, ret2, surface, circuito
    )

    # v21.1 Elite ATP Clay Protection
    hold1, hold2, ret1, ret2, elite_clay = elite_atp_clay_protection(
        d1, d2, hold1, hold2, ret1, ret2, surface, circuito
    )

    # v21.2 Clay Dominance Preservation
    hold1, hold2, ret1, ret2, dominance_clay = clay_dominance_preservation(
        d1, d2, hold1, hold2, ret1, ret2, surface, circuito
    )

    # v17 Fatigue Engine
    fatigue1 = d1.get("Fatigue", {})
    fatigue2 = d2.get("Fatigue", {})
    fat_adj1, fat_adj2, fatigue_vol_extra = fatigue_adjustments(fatigue1, fatigue2, surface, circuito, d1.get('Rank',999), d2.get('Rank',999))

    hold1 = np.clip(hold1 + fat_adj1, 0.42, 0.84)
    hold2 = np.clip(hold2 + fat_adj2, 0.42, 0.84)

    ret1 = np.clip(ret1 + fat_adj1 * 0.35, 0.10, 0.40)
    ret2 = np.clip(ret2 + fat_adj2 * 0.35, 0.10, 0.40)

    # v18 Tournament Engine
    ctx = tournament_context_adjustments(
        context_row,
        p1_name=s1.get("raw_name_stats", ""),
        p2_name=s2.get("raw_name_stats", "")
    )

    hold1 = np.clip(hold1 + ctx["p1_adj"], 0.42, 0.86)
    hold2 = np.clip(hold2 + ctx["p2_adj"], 0.42, 0.86)

    # v19.1 Elite WTA Separation
    hold1, hold2, ret1, ret2, wta_sep = elite_wta_separation(
        d1, d2, hold1, hold2, ret1, ret2, surface, circuito
    )

    # v19.2 Match Script Engine
    wta_script = wta_match_script_engine(
        d1, d2, s1, s2,
        hold1, hold2,
        ret1, ret2,
        surface, circuito
    )

    p1_profile = s1.get("serve_profile", "normal")
    p2_profile = s2.get("serve_profile", "normal")
    p1_big = p1_profile in ["big_server", "elite_server"]
    p2_big = p2_profile in ["big_server", "elite_server"]

    tb_intel_boost = calcular_tiebreak_boost(s1, s2, hold1, hold2, surface, p1_big, p2_big)
    tb_intel_boost += ctx.get("tb_adj", 0)

    pressure_skill1, pressure_skill2 = pressure_collapse_params(s1, s2, surface)

    sets_to_win = 3 if best_of == 5 else 2
    fav_est = max(elo_prob(e1_eff, e2_eff), 1 - elo_prob(e1_eff, e2_eff))

    vol = calcular_match_volatility(e1, e2, surface, fav_est)
    vol *= rating_sanity.get("vol_mult", 1.0)
    if p1_big or p2_big:
        vol += 0.006
    vol += fatigue_vol_extra
    vol += ctx.get("vol_adj", 0)

    if circuito == "ATP" and surface == "Clay":
        vol *= clay_engine.get("vol_mult", 1.0)
        vol *= elite_clay.get("vol_mult", 1.0)
        vol *= dominance_clay.get("vol_mult", 1.0)
        vol = float(np.clip(vol, 0.016, 0.070))

    # v19 WTA Controlled Chaos:
    # WTA sigue siendo variable, pero protegemos top players y gaps grandes.
    if circuito == "WTA":
        rank_gap = abs(d1.get("Rank",999) - d2.get("Rank",999))

        if d1.get("Rank",999) <= 15 or d2.get("Rank",999) <= 15:
            vol *= 0.78

        if rank_gap >= 40 and fav_est >= 0.62:
            vol *= 0.86

        if surface == "Clay":
            vol *= 1.04
        elif surface == "Grass":
            vol *= 0.94

        vol *= wta_sep.get("vol_mult", 1.0)
        vol *= wta_script.get("vol_mult", 1.0)
        vol = float(np.clip(vol, 0.014, 0.060))

    res = {
        "p1": 0, "p2": 0, "set3": 0, "tb": 0, "games": [],
        # v22.35: juegos esperados por jugador
        "games_p1": [], "games_p2": [],
        "p1_fs": 0, "p2_fs": 0,
        "fav_under22": 0, "dog_over20": 0,
        "fav_2_0": 0, "dog_wins_set": 0, "long_match": 0,
        # v22.25 Favorite Identity Engine:
        # count straight sets / set wins by player, then decide favorite by final model probability,
        # not by raw surface Elo. This avoids labels such as "underdog wins set" being tied to Elo
        # when the final model has flipped the favorite.
        "p1_2_0": 0, "p2_2_0": 0,
        "p1_wins_set_any": 0, "p2_wins_set_any": 0
    }

    # v22.36: progreso más suave sin saturar Streamlit
    progress_step = max(1, min(250, n // 40))

    if progress_callback is not None:
        try:
            progress_callback(0, n)
        except Exception:
            pass

    for sim_i in range(n):
        sets1 = sets2 = games = 0
        games_p1 = games_p2 = 0
        tb_seen = False
        first_done = False
        shift = np.random.normal(0, vol)

        while sets1 < sets_to_win and sets2 < sets_to_win:
            g1, g2, tb = sim_set(
                hold1, hold2, surface, shift, p1_big, p2_big, fav_est,
                stats1=s1, stats2=s2
            )

            games += g1 + g2
            games_p1 += g1
            games_p2 += g2

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

        p1_wins = sets1 > sets2

        if p1_wins:
            res["p1"] += 1
        else:
            res["p2"] += 1

        if (sets1, sets2) in [(2, 1), (1, 2)]:
            res["set3"] += 1

        if tb_seen:
            res["tb"] += 1

        # v22.25: player-specific set outcomes for final-model favorite markets.
        if sets1 == sets_to_win and sets2 == 0:
            res["p1_2_0"] += 1
        if sets2 == sets_to_win and sets1 == 0:
            res["p2_2_0"] += 1
        if sets1 >= 1:
            res["p1_wins_set_any"] += 1
        if sets2 >= 1:
            res["p2_wins_set_any"] += 1

        p1_is_fav = e1 >= e2
        fav_wins = p1_wins if p1_is_fav else (not p1_wins)
        dog_wins = not fav_wins

        if fav_wins and games < 22.5:
            res["fav_under22"] += 1

        if dog_wins and games > 20.5:
            res["dog_over20"] += 1

        if p1_is_fav:
            dog_sets = sets2
        else:
            dog_sets = sets1

        if fav_wins and dog_sets == 0:
            res["fav_2_0"] += 1

        if dog_sets >= 1:
            res["dog_wins_set"] += 1

        if games > 22.5 or tb_seen or ((sets1, sets2) in [(2, 1), (1, 2)]):
            res["long_match"] += 1

        res["games"].append(games)
        res["games_p1"].append(games_p1)
        res["games_p2"].append(games_p2)

        if progress_callback is not None and ((sim_i + 1) % progress_step == 0 or (sim_i + 1) == n):
            try:
                progress_callback(sim_i + 1, n)
            except Exception:
                pass

    p1_raw = res["p1"] / n
    # v22.29 compatibility aliases: older blocks used p1_win/p2_win names
    p1_win = p1_raw
    p2_win = 1 - p1_raw
    p1_cal = calibrar_probabilidad(p1_raw, surface)

    raw_tb = res["tb"] / n

    # v22.25 Favorite Identity Engine:
    # Favorite/underdog derived markets follow the calibrated model favorite, not raw Elo.
    model_fav_is_p1 = p1_cal >= 0.50
    model_fav_name = d1.get("Player", "Jugador 1") if model_fav_is_p1 else d2.get("Player", "Jugador 2")
    model_dog_name = d2.get("Player", "Jugador 2") if model_fav_is_p1 else d1.get("Player", "Jugador 1")
    raw_fav20 = (res["p1_2_0"] if model_fav_is_p1 else res["p2_2_0"]) / n
    raw_dogset = (res["p2_wins_set_any"] if model_fav_is_p1 else res["p1_wins_set_any"]) / n
    raw_long = res["long_match"] / n

    # v18.1 Rating Sanity Engine: se aplica después de simular, no antes.
    set_dyn = smart_set_dynamics(
        p1_raw, 1 - p1_raw,
        hold1, hold2,
        raw_tb,
        vol,
        surface,
        circuito,
        d1.get("Rank",999),
        d2.get("Rank",999)
    )

    fav20 = float(np.clip(raw_fav20 + set_dyn["fav20_boost"], 0.0, 0.95))
    dogset = float(np.clip(raw_dogset - set_dyn["dog_set_suppress"], 0.05, 0.95))
    longm = float(np.clip(raw_long + set_dyn["long_match_adj"], 0.05, 0.95))

    # v19 WTA caps: corrige exceso de "dog gana set" en favoritas claras.
    if circuito == "WTA":
        fav_prob = max(p1_cal, 1 - p1_cal)
        top_player = d1.get("Rank",999) <= 15 or d2.get("Rank",999) <= 15
        rank_gap = abs(d1.get("Rank",999) - d2.get("Rank",999))

        if fav_prob >= 0.70 and top_player:
            dogset *= 0.78
            fav20 = min(0.90, fav20 * 1.12)
            longm *= 0.88
        elif fav_prob >= 0.65 and top_player:
            dogset *= 0.85
            fav20 = min(0.88, fav20 * 1.08)
            longm *= 0.92

        if rank_gap >= 40 and fav_prob >= 0.63:
            dogset *= 0.88
            longm *= 0.94

        # v19.1 Elite WTA set separation:
        # Si hay top WTA con ventaja, no convertir automáticamente en partido largo.
        if wta_sep.get("active", False):
            fav_prob2 = max(p1_cal, 1 - p1_cal)
            if fav_prob2 >= 0.60:
                dogset *= 0.82
                fav20 = min(0.92, fav20 * 1.16)
                longm *= 0.82
            elif fav_prob2 >= 0.56:
                dogset *= 0.90
                fav20 = min(0.90, fav20 * 1.08)
                longm *= 0.90

        # v19.2 Match Script multipliers
        fav20 *= wta_script.get("fav20_mult", 1.0)
        dogset *= wta_script.get("dogset_mult", 1.0)
        longm *= wta_script.get("long_mult", 1.0)

        dogset = float(np.clip(dogset, 0.05, 0.90))
        fav20 = float(np.clip(fav20, 0.0, 0.92))
        longm = float(np.clip(longm, 0.05, 0.92))

    # v21 ATP Clay market logic
    fav20, dogset, longm = clay_market_adjustments(
        circuito, surface, clay_engine, fav20, dogset, longm, p1_cal
    )

    # v21.1 Elite ATP protection market logic
    if circuito == "ATP" and surface == "Clay" and elite_clay.get("active", False):
        fav20 *= 1.18
        dogset *= 0.78
        longm *= 0.84

        fav20 = float(np.clip(fav20, 0.0, 0.95))
        dogset = float(np.clip(dogset, 0.05, 0.95))
        longm = float(np.clip(longm, 0.05, 0.95))

    # v21.2 Clay Dominance market logic
    if circuito == "ATP" and surface == "Clay" and dominance_clay.get("active", False):
        fav20 *= dominance_clay.get("market_fav20_mult", 1.0)
        dogset *= dominance_clay.get("market_dogset_mult", 1.0)
        longm *= dominance_clay.get("market_long_mult", 1.0)
        fav20 = float(np.clip(fav20, 0.0, 0.95))
        dogset = float(np.clip(dogset, 0.05, 0.95))
        longm = float(np.clip(longm, 0.05, 0.95))

    # v22.20 Straight Sets Guard: buen over bajo no debe inflar dog set/partido largo.
    straight_sets_guard = {"active": False, "profile": "neutral"}
    fav_prob_guard = max(p1_cal, 1 - p1_cal)
    fav20, dogset, longm, straight_sets_guard = straight_sets_guard_engine(
        circuito, surface, fav_prob_guard, hold1, hold2, raw_tb, vol,
        rating_sanity, fav20, dogset, longm
    )

    fav20_sanity_guard = {"active": False}
    fav20, dogset, longm, fav20_sanity_guard = favorite_2_0_sanity_guard(
        circuito, surface, fav_prob_guard, fav20, dogset, longm, rating_sanity
    )

    upset_risk_guard = {"active": False, "profile": "neutral"}
    p1_cal, fav20, dogset, longm, upset_risk_guard = upset_risk_guard_engine(
        circuito, surface, p1_cal, p1_raw, fav20, dogset, longm, rating_sanity
    )

    low_over_split_guard = {"active": False, "profile": "neutral"}
    fav20, dogset, longm, low_over_split_guard = low_over_long_match_split_guard(
        circuito, surface, p1_cal, e1, e2, hold1, hold2, raw_tb,
        rating_sanity, fav20, dogset, longm, upset_risk_guard
    )

    elite_clay_opponent_guard_info = {"active": False, "profile": "neutral"}
    fav20, dogset, longm, elite_clay_opponent_guard_info = elite_clay_opponent_guard(
        circuito, surface, p1_cal, e1, e2, rating_sanity, fav20, dogset, longm
    )

    return {
        "p1": p1_raw,
        "p2": 1 - p1_raw,
        "p1_cal": p1_cal,
        "p2_cal": 1 - p1_cal,
        "p1_fs": res["p1_fs"] / n,
        "p2_fs": res["p2_fs"] / n,
        "set3": res["set3"] / n,
        "tb": raw_tb,
        "fav_under22": res["fav_under22"] / n,
        "dog_over20": res["dog_over20"] / n,
        "fav_2_0": fav20,
        "dog_wins_set": dogset,
        "long_match": longm,
        "games": res["games"],
        "games_p1": res["games_p1"],
        "games_p2": res["games_p2"],
        "hold1": hold1,
        "hold2": hold2,
        "raw_hold1": raw1,
        "raw_hold2": raw2,
        "ret1": ret1,
        "ret2": ret2,
        "p1_profile": p1_profile,
        "p2_profile": p2_profile,
        "vol": vol,
        "fav_raw_est": fav_est,
        "model_fav_is_p1": model_fav_is_p1,
        "model_fav_name": model_fav_name,
        "model_dog_name": model_dog_name,
        "elo_effective1": e1_eff,
        "elo_effective2": e2_eff,
        "tb_intel_boost": tb_intel_boost,
        "pressure_skill1": pressure_skill1,
        "pressure_skill2": pressure_skill2,
        "fatigue1": fatigue1,
        "fatigue2": fatigue2,
        "fatigue_adj1": fat_adj1,
        "fatigue_adj2": fat_adj2,
        "fatigue_vol_extra": fatigue_vol_extra,
        "tournament_ctx": ctx,
        "set_dynamics": set_dyn,
        "wta_engine_active": circuito == "WTA",
        "clay_engine": clay_engine,
        "rating_sanity": rating_sanity,
        "elite_clay": elite_clay,
        "dominance_clay": dominance_clay,
        "straight_sets_guard": straight_sets_guard,
        "fav20_sanity_guard": fav20_sanity_guard,
        "upset_risk_guard": upset_risk_guard,
        "low_over_split_guard": low_over_split_guard,
        "elite_clay_opponent_guard": elite_clay_opponent_guard_info,
        "wta_separation": wta_sep,
        "wta_script": wta_script
    }


def _first_nonempty_from_columns(df, candidates):
    """v22.17: crea una serie unificada usando la primera columna no vacía por fila."""
    existing = [c for c in candidates if c in df.columns]
    if not existing:
        return pd.Series([""] * len(df), index=df.index)
    tmp = df[existing].copy()
    for c in existing:
        tmp[c] = tmp[c].apply(normalizar_texto)
        tmp[c] = tmp[c].replace({"nan": "", "NaN": "", "None": ""})
    return tmp.replace("", np.nan).bfill(axis=1).iloc[:, 0].fillna("")


def normalizar_schema_historicos(df):
    """
    v22.17 Unified Historical Schema.
    Al concatenar Excel ATP Tour con CSV qual_chall, pandas deja columnas separadas:
    Winner/Loser para Excel y winner_name/loser_name para CSV. Antes buscar_columna elegía Winner
    y las filas CSV quedaban vacías. Esta función crea columnas MC_* para que todos los loaders
    cuenten Tour + Challenger/Qualy en el mismo mapa.
    """
    if df is None or df.empty:
        return df
    out = df.copy()
    out["MC_Winner"] = _first_nonempty_from_columns(out, [
        "MC_Winner", "Winner", "Ganador", "Player1", "Player 1", "WName",
        "winner_name", "winner_name_clean", "Jugador1", "Home", "P1"
    ])
    out["MC_Loser"] = _first_nonempty_from_columns(out, [
        "MC_Loser", "Loser", "Perdedor", "Player2", "Player 2", "LName",
        "loser_name", "loser_name_clean", "Jugador2", "Away", "P2"
    ])
    out["MC_Surface"] = _first_nonempty_from_columns(out, [
        "MC_Surface", "Surface", "surface", "Superficie", "Court Surface", "Court", "surface_name"
    ])
    # Mantiene columnas originales para detectar nivel, pero añade alias unificados útiles para debug.
    out["MC_Level"] = _first_nonempty_from_columns(out, [
        "MC_Level", "tourney_level", "Tourney Level", "Series", "Level", "Tour", "Category", "Circuit", "Event Type"
    ])
    out["MC_Tournament"] = _first_nonempty_from_columns(out, [
        "MC_Tournament", "tourney_name", "Tournament", "Event", "Location"
    ])
    out["MC_Round"] = _first_nonempty_from_columns(out, [
        "MC_Round", "round", "Round", "ronda"
    ])
    return out

def _historical_folders(circuito):
    base = rutas(circuito)["base"]
    return [
        rutas(circuito)["historicos"],
        os.path.join(base, "challenger"),
        os.path.join(base, "qual_chall"),
        os.path.join(base, "historicos_challenger"),
        os.path.join(base, "historicos_qual_chall"),
    ]


def _is_supported_history_file(path):
    ext = os.path.splitext(str(path))[1].lower()
    return ext in [".xlsx", ".xls", ".csv"]


@st.cache_data(show_spinner=False)
def descubrir_archivos_historicos(circuito, cache_version=QUALITY_ENGINE_VERSION):
    """
    v22.17 Deep File Scanner.
    - Escanea carpetas esperadas.
    - Además escanea TODO datos/atp de forma recursiva por si los CSV están en otra subcarpeta.
    - Detecta extensiones en mayúsculas: .CSV, .XLSX, .XLS.
    """
    base = rutas(circuito)["base"]
    folders = _historical_folders(circuito)
    files = []

    # 1) Carpetas esperadas, recursivo y case-insensitive por extensión.
    for folder in folders:
        if not os.path.exists(folder):
            continue
        for root, _, names in os.walk(folder):
            for name in names:
                fp = os.path.join(root, name)
                if _is_supported_history_file(fp):
                    files.append(fp)

    # 2) v22.17 Fast mode: NO escanea todo datos/atp en cada ejecución.
    # Si los CSV están en datos/atp/challenger o qual_chall, ya entran arriba de forma recursiva.
    # Esto evita cuelgues al pulsar Simular con repos grandes.
    files = sorted(set(files))

    folder_counts = {}
    folder_samples = {}
    for fd in folders:
        fd_name = os.path.relpath(fd, base) if os.path.exists(base) else fd
        found = [f for f in files if os.path.commonpath([os.path.abspath(fd), os.path.abspath(f)]) == os.path.abspath(fd)] if os.path.exists(fd) else []
        folder_counts[fd_name] = len(found)
        folder_samples[fd_name] = [os.path.relpath(x, fd) for x in found[:8]] if os.path.exists(fd) else []

    deep_extra = []
    expected_abs = [os.path.abspath(x) for x in folders if os.path.exists(x)]
    for f in files:
        af = os.path.abspath(f)
        in_expected = False
        for fd in expected_abs:
            try:
                if os.path.commonpath([fd, af]) == fd:
                    in_expected = True
                    break
            except Exception:
                pass
        if not in_expected:
            deep_extra.append(f)
    folder_counts["deep_extra"] = len(deep_extra)
    folder_samples["deep_extra"] = [os.path.relpath(x, base) if os.path.exists(base) else os.path.basename(x) for x in deep_extra[:8]]

    return files, folder_counts, folder_samples


@st.cache_data(show_spinner=False)
def cargar_historicos(circuito, cache_version=QUALITY_ENGINE_VERSION):
    """
    v22.17 Historical Loader.

    Lee históricos Tour y CSV Challenger/Qualy desde carpetas conocidas y también mediante
    escaneo profundo de datos/atp. Soporta .xlsx, .xls, .csv, también con extensión mayúscula.
    """
    base = rutas(circuito)["base"]
    files, _, _ = descubrir_archivos_historicos(circuito, cache_version=cache_version)

    dfs = []
    for f in files:
        try:
            ext = os.path.splitext(f)[1].lower()
            if ext in [".xlsx", ".xls"]:
                df = pd.read_excel(f)
            elif ext == ".csv":
                try:
                    df = pd.read_csv(f)
                except Exception:
                    df = pd.read_csv(f, sep=";")
            else:
                continue
            try:
                rel = os.path.relpath(f, base)
            except Exception:
                rel = os.path.basename(f)
            df["SourceFile"] = rel.replace("\\", "/")
            dfs.append(df)
        except Exception:
            pass
    if not dfs:
        return pd.DataFrame()
    return normalizar_schema_historicos(pd.concat(dfs, ignore_index=True))


@st.cache_data(show_spinner=False)
def historicos_diagnostics(circuito, cache_version=QUALITY_ENGINE_VERSION):
    """Diagnóstico visible para saber si el Match Count está leyendo archivos/columnas."""
    base = rutas(circuito)["base"]
    folder = rutas(circuito)["historicos"]
    files, folder_counts, folder_samples = descubrir_archivos_historicos(circuito, cache_version=cache_version)
    hist = cargar_historicos(circuito, cache_version=cache_version)

    if hist.empty:
        return {
            "folder": folder, "folder_exists": os.path.exists(folder),
            "files_count": len(files), "rows": 0, "columns": [],
            "winner_col": None, "loser_col": None, "surface_col": None,
            "sample_players": [], "sample_files": [os.path.relpath(x, base) if os.path.exists(base) else os.path.basename(x) for x in files[:12]],
            "folder_counts": folder_counts, "folder_samples": folder_samples,
        }

    col_winner = buscar_columna(hist, ["MC_Winner", "Winner", "Ganador", "Player1", "Player 1", "WName", "winner_name", "winner_name_clean", "Jugador1", "Home", "P1"] )
    col_loser = buscar_columna(hist, ["MC_Loser", "Loser", "Perdedor", "Player2", "Player 2", "LName", "loser_name", "loser_name_clean", "Jugador2", "Away", "P2"] )
    col_surface = buscar_columna(hist, ["MC_Surface", "Surface", "surface", "Superficie", "Court Surface", "Court", "surface_name"] )
    level_cols_found = [c for c in ["MC_Level", "MC_Tournament", "MC_Round", "Series", "Level", "Tour", "Category", "Circuit", "Event Type", "Tournament", "Event", "Round", "Comment", "SourceFile", "tourney_level", "tourney_name", "round", "winner_entry", "loser_entry"] if c in hist.columns]
    level_samples = {}
    for c in level_cols_found[:8]:
        try:
            vals = [normalizar_texto(x) for x in hist[c].dropna().astype(str).unique().tolist()[:6]]
            level_samples[c] = vals
        except Exception:
            level_samples[c] = []

    samples = []
    if col_winner is not None:
        samples += [normalizar_texto(x) for x in hist[col_winner].dropna().astype(str).head(5).tolist()]
    if col_loser is not None:
        samples += [normalizar_texto(x) for x in hist[col_loser].dropna().astype(str).head(5).tolist()]

    col_date = buscar_columna(hist, ["Date", "Fecha", "date", "match_date", "tourney_date", "Tourney Date"])
    date_min = date_max = "N/A"
    if col_date is not None:
        raw = hist[col_date]
        # Jeff Sackmann usa YYYYMMDD; pandas con dayfirst puede interpretarlo mal.
        if raw.astype(str).str.fullmatch(r"\d{8}").any():
            dt = pd.to_datetime(raw.astype(str), format="%Y%m%d", errors="coerce")
        else:
            dt = pd.to_datetime(raw, dayfirst=True, errors="coerce")
        if dt.notna().any():
            date_min = str(dt.min().date())
            date_max = str(dt.max().date())

    return {
        "folder": folder, "folder_exists": os.path.exists(folder),
        "files_count": len(files), "rows": int(len(hist)),
        "columns": list(hist.columns)[:20],
        "winner_col": col_winner, "loser_col": col_loser, "surface_col": col_surface,
        "date_min": date_min, "date_max": date_max,
        "sample_players": samples[:8],
        "sample_files": [os.path.relpath(x, base) if os.path.exists(base) else os.path.basename(x) for x in files[:12]],
        "folder_counts": folder_counts, "folder_samples": folder_samples,
        "level_cols": level_cols_found,
        "level_samples": level_samples,
    }


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
    if "Comment" in df.columns:
        completed_mask = df["Comment"].astype(str).str.contains("Completed", case=False, na=False)
        if completed_mask.sum() > 0:
            df = df[completed_mask]
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



def tournament_context_adjustments(context_row, p1_name="", p2_name=""):
    """
    v18 Rating Sanity Engine
    """
    import numpy as np

    if context_row is None:
        context_row = {}

    series = str(context_row.get("Series", ""))
    rnd = str(context_row.get("Round", ""))
    court = str(context_row.get("Court", "Outdoor"))
    location = str(context_row.get("Location", ""))

    p1_adj = 0.0
    p2_adj = 0.0
    vol_adj = 0.0
    tb_adj = 0.0

    # Tournament importance
    if "Grand Slam" in series:
        vol_adj -= 0.004
    elif "Masters" in series or "1000" in series:
        vol_adj -= 0.002
    elif "250" in series:
        vol_adj += 0.003

    # Round pressure
    if "Final" in rnd:
        vol_adj -= 0.004
    elif "Semi" in rnd:
        vol_adj -= 0.002
    elif "1st" in rnd:
        vol_adj += 0.003

    # Indoor boosts
    if "Indoor" in court:
        tb_adj += 0.025

    # Tiny home boosts
    home_map = {
        "Paris": "FRA",
        "Lyon": "FRA",
        "Marseille": "FRA",
        "Madrid": "ESP",
        "Barcelona": "ESP",
        "Mallorca": "ESP",
        "Rome": "ITA",
        "Turin": "ITA",
        "Milan": "ITA",
        "Munich": "GER",
        "Hamburg": "GER"
    }

    hc = home_map.get(location)

    if hc:
        if f"[{hc}]" in str(p1_name):
            p1_adj += 0.006
        if f"[{hc}]" in str(p2_name):
            p2_adj += 0.006

    return {
        "p1_adj": float(np.clip(p1_adj, -0.01, 0.01)),
        "p2_adj": float(np.clip(p2_adj, -0.01, 0.01)),
        "vol_adj": float(np.clip(vol_adj, -0.01, 0.01)),
        "tb_adj": float(np.clip(tb_adj, 0, 0.04)),
        "series": series,
        "round": rnd,
        "court": court
    }


def fatigue_adjustments(f1, f2, surface, circuito="ATP", rank1=999, rank2=999):
    """
    v19 Fatigue Engine.
    ATP: lógica anterior.
    WTA: menos castigo de fatiga y protección de top players.
    """
    fat1 = f1.get("fatigue_score", 0.0)
    fat2 = f2.get("fatigue_score", 0.0)

    if circuito == "WTA":
        if rank1 <= 15:
            fat1 *= 0.62
        elif rank1 <= 30:
            fat1 *= 0.75

        if rank2 <= 15:
            fat2 *= 0.62
        elif rank2 <= 30:
            fat2 *= 0.75

        if surface == "Clay":
            mult = 0.72
        elif surface == "Grass":
            mult = 0.48
        else:
            mult = 0.58
    else:
        if surface == "Clay":
            mult = 1.18
        elif surface == "Grass":
            mult = 0.82
        else:
            mult = 1.0

    adj1 = -fat1 * mult
    adj2 = -fat2 * mult

    vol_extra = abs(fat1 - fat2) * (0.20 if circuito == "WTA" else 0.35)

    if circuito == "ATP":
        if fat1 > 0.030 or fat2 > 0.030:
            vol_extra += 0.003
    else:
        if (fat1 > 0.040 or fat2 > 0.040) and rank1 > 30 and rank2 > 30:
            vol_extra += 0.002

    return (
        float(np.clip(adj1, -0.032 if circuito == "WTA" else -0.055, 0.010)),
        float(np.clip(adj2, -0.032 if circuito == "WTA" else -0.055, 0.010)),
        float(np.clip(vol_extra, 0, 0.010 if circuito == "WTA" else 0.018))
    )


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
        sim = sim_match(d_win, d_los, surface, circuito, best_of, sims_bt, context_row=row)

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
# v22.2 MARKET SANITY CAPS
# =========================================================

def aplicar_market_sanity_caps(sim, circuito, surface, over18, over19, over20, over22):
    """
    v22.2: suaviza mercados de games cuando el propio Rating Sanity
    dice que la confianza del Elo/superficie es baja.
    No cambia el resultado simulado; cambia la probabilidad operativa mostrada.
    """
    rs = sim.get("rating_sanity", {}) or {}
    p1_rs = rs.get("p1", {}) or {}
    p2_rs = rs.get("p2", {}) or {}
    min_conf = min(p1_rs.get("confidence", 1.0), p2_rs.get("confidence", 1.0))
    min_surface_matches = min(p1_rs.get("matches_surface", 99), p2_rs.get("matches_surface", 99))
    fav_prob = max(sim.get("p1_cal", 0.5), sim.get("p2_cal", 0.5))
    elo_pure_gap = abs(sim.get("fav_raw_est", 0.5) - fav_prob)

    notes = []
    o18, o19, o20, o22 = over18, over19, over20, over22

    if circuito == "ATP" and surface == "Clay":
        # Caso detectado: Over 18.5 salía demasiado alto como señal principal
        # aunque ambos jugadores tuvieran confidence ~25% y pocos partidos clay.
        if min_conf < 0.35 or min_surface_matches < 5:
            cap18 = 0.72 if fav_prob < 0.58 else 0.74
            if o18 > cap18:
                o18 = cap18
                notes.append(f"Over 18.5 capado a {cap18:.0%} por baja confianza clay")

            cap19 = 0.68 if fav_prob < 0.58 else 0.70
            if o19 > cap19:
                o19 = cap19
                notes.append(f"Over 19.5 capado a {cap19:.0%} por baja confianza clay")

        # v22.11: muestra aceptable pero todavía corta + Elo puro muy separado del modelo.
        # Ejemplo: dog con 8 partidos clay y gap ~15-16%; no debe escalar a SPOT APTO.
        if min_surface_matches < 10 and elo_pure_gap >= 0.14:
            cap18 = 0.74 if fav_prob < 0.58 else 0.75
            if o18 > cap18:
                o18 = cap18
                notes.append(f"Over 18.5 capado a {cap18:.0%} por muestra clay corta + gap Elo/modelo")

            cap19 = 0.68 if fav_prob < 0.58 else 0.69
            if o19 > cap19:
                o19 = cap19
                notes.append(f"Over 19.5 capado a {cap19:.0%} por muestra clay corta + gap Elo/modelo")

        # Si el favorito es muy débil, evitamos transformar un partido abierto
        # automáticamente en spot fuerte de over bajo.
        if fav_prob < 0.56 and o18 > 0.72:
            o18 = 0.72
            notes.append("Over 18.5 limitado por favorito débil")

        # v22.33 Elite Blowout Guard:
        # cuando el partido ya está en modo dominio claro del favorito, el over bajo
        # no debe seguir apareciendo automáticamente como señal principal.
        fav20 = sim.get("fav_2_0", 0.0)
        dogset = sim.get("dog_wins_set", 1.0)
        e1_eff = sim.get("elo_effective1", 1500)
        e2_eff = sim.get("elo_effective2", 1500)
        fav_is_p1 = sim.get("p1_cal", 0.5) >= sim.get("p2_cal", 0.5)
        fav_elo = e1_eff if fav_is_p1 else e2_eff
        dog_elo = e2_eff if fav_is_p1 else e1_eff
        elo_gap_eff = fav_elo - dog_elo

        elite_blowout = (
            fav_prob >= 0.80
            and fav20 >= 0.78
            and dogset <= 0.22
            and elo_gap_eff >= 250
            and min_conf >= 0.75
            and min_surface_matches >= 60
        )

        if elite_blowout:
            cap18 = 0.56
            cap19 = 0.48
            cap20 = 0.42
            cap22 = 0.30

            # Si el 2-0 es casi total y el dog-set está hundido, cap más fuerte.
            if fav20 >= 0.90 and dogset <= 0.10 and elo_gap_eff >= 350:
                cap18 = 0.54
                cap19 = 0.46
                cap20 = 0.40
                cap22 = 0.28

            if o18 > cap18:
                o18 = cap18
                notes.append(f"Over 18.5 capado a {cap18:.0%} por dominio élite/blowout")
            if o19 > cap19:
                o19 = cap19
                notes.append(f"Over 19.5 capado a {cap19:.0%} por dominio élite/blowout")
            if o20 > cap20:
                o20 = cap20
                notes.append(f"Over 20.5 capado a {cap20:.0%} por dominio élite/blowout")
            if o22 > cap22:
                o22 = cap22
                notes.append(f"Over 22.5 capado a {cap22:.0%} por dominio élite/blowout")

    return {
        "over18": float(np.clip(o18, 0.0, 0.95)),
        "over19": float(np.clip(o19, 0.0, 0.95)),
        "over20": float(np.clip(o20, 0.0, 0.95)),
        "over22": float(np.clip(o22, 0.0, 0.95)),
        "notes": notes
    }


# =========================================================
# v20 BETTING FILTERS ENGINE
# =========================================================

def betting_filter_engine(circuito, surface, sim, p1_name, p2_name):
    p1c = sim.get("p1_cal", 0.5)
    p2c = sim.get("p2_cal", 0.5)
    fav_prob = max(p1c, p2c)
    fav_name = p1_name if p1c >= p2c else p2_name

    games = sim.get("games", [])
    if sim.get("market_over18") is not None:
        over18 = sim.get("market_over18", 0.0)
        over19 = sim.get("market_over19", 0.0)
        over20 = sim.get("market_over20", 0.0)
        over22 = sim.get("market_over22", 0.0)
        under22 = 1 - over22
    elif games:
        over18 = sum(x > 18.5 for x in games) / len(games)
        over19 = sum(x > 19.5 for x in games) / len(games)
        over20 = sum(x > 20.5 for x in games) / len(games)
        over22 = sum(x > 22.5 for x in games) / len(games)
        under22 = 1 - over22
    else:
        over18 = over19 = over20 = over22 = under22 = 0.0

    fav20 = sim.get("fav_2_0", 0)
    dogset = sim.get("dog_wins_set", 0)
    longm = sim.get("long_match", 0)
    tb = sim.get("tb", 0)
    vol = sim.get("vol", 0)

    # v22.2 Signal Trust Gate: una probabilidad puede ser buena,
    # pero no debe etiquetarse como fuerte si el Elo viene de poca muestra.
    rs = sim.get("rating_sanity", {}) or {}
    p1_rs = rs.get("p1", {}) or {}
    p2_rs = rs.get("p2", {}) or {}
    min_conf = min(p1_rs.get("confidence", 1.0), p2_rs.get("confidence", 1.0))
    avg_conf = (p1_rs.get("confidence", 1.0) + p2_rs.get("confidence", 1.0)) / 2
    min_surface_matches = min(p1_rs.get("matches_surface", 99), p2_rs.get("matches_surface", 99))
    elo_pure_gap = abs(sim.get("fav_raw_est", 0.5) - fav_prob)
    upset_guard = sim.get("upset_risk_guard", {}) or {}

    risk_notes = []
    if upset_guard.get("active", False):
        risk_notes.append("riesgo upset por favorito inflado")
    if min_conf < 0.35:
        risk_notes.append("confianza de datos muy baja")
    elif min_conf < 0.50:
        risk_notes.append("confianza de datos baja")
    elif min_conf < 0.65:
        risk_notes.append("confianza insuficiente para ML/2-0 fuerte")
    if min_surface_matches < 5:
        risk_notes.append("muestra de superficie insuficiente")
    elif min_surface_matches < 10:
        risk_notes.append("muestra de superficie corta")
    if elo_pure_gap >= 0.14:
        risk_notes.append("Elo puro y modelo final muy separados")

    zone_score = 0
    if circuito == "ATP" and surface == "Hard":
        zone_score = 3
    elif circuito == "ATP" and surface == "Clay":
        zone_score = 2
    elif circuito == "WTA":
        zone_score = 1
        risk_notes.append("WTA: filtros más exigentes")
    else:
        zone_score = 1

    if vol >= 0.060:
        risk_notes.append("volatilidad alta")
    if fav_prob < 0.56:
        risk_notes.append("favorito débil")
    if tb >= 0.34:
        risk_notes.append("tie-break alto")

    f1 = sim.get("fatigue1", {}).get("fatigue_score", 0)
    f2 = sim.get("fatigue2", {}).get("fatigue_score", 0)
    if f1 >= 0.04 or f2 >= 0.04:
        risk_notes.append("fatiga relevante")

    signals = []

    def add_signal(name, prob, min_prob, market_type, reason, bonus=0):
        score = zone_score + bonus

        # v22.2: no permitimos A+ fácil con muestra pobre.
        if min_conf < 0.35:
            score -= 2
        elif min_conf < 0.50:
            score -= 1

        if min_surface_matches < 5:
            score -= 1

        if elo_pure_gap >= 0.14:
            score -= 1

        # Over 18.5 es útil, pero antes salía demasiado como "spot fuerte".
        if name == "Over 18.5" and min_conf < 0.45:
            score -= 1
        if name == "Over 18.5" and fav_prob < 0.58:
            score -= 1

        if prob >= min_prob:
            score += 2
        if prob >= min_prob + 0.06:
            score += 1
        if prob >= min_prob + 0.12:
            score += 1

        if circuito == "WTA" and market_type in ["over", "long"]:
            score -= 1
        if vol >= 0.060 and market_type in ["ml", "fav20"]:
            score -= 1
        if fav_prob < 0.56 and market_type in ["ml", "fav20"]:
            score -= 2

        if score >= 6:
            grade = "🔥 A+"
            action = "APTO fuerte"
        elif score >= 5:
            grade = "✅ A"
            action = "APTO"
        elif score >= 4:
            grade = "⚖️ B"
            action = "Solo si acompaña lectura"
        else:
            grade = "⚠️ C"
            action = "Evitar / observar"

        # v22.25: con confianza <65% no dejamos señales agresivas ML/fav20.
        # Evita casos tipo favorito 80% + 2-0 95% con calidad Challenger/Qualy.
        if market_type in ["ml", "fav20"] and min_conf < 0.65 and action in ["APTO fuerte", "APTO"]:
            grade = "⚖️ B"
            action = "Solo si acompaña lectura"
            reason = reason + " · degradado por confianza insuficiente para ML/2-0"

        # v22.25: upset risk activo degrada cualquier ML/2-0 agresivo.
        if upset_guard.get("active", False) and market_type in ["ml", "fav20"] and action in ["APTO fuerte", "APTO"]:
            grade = "⚖️ B"
            action = "Solo si acompaña lectura"
            reason = reason + " · degradado por riesgo upset"

        # Trust Gate final: con confianza muy baja, como máximo B.
        if min_conf < 0.35 and action in ["APTO fuerte", "APTO"]:
            grade = "⚖️ B"
            action = "Solo si acompaña lectura"
            reason = reason + " · degradado por baja confianza de datos"
        elif min_conf < 0.50 and action == "APTO fuerte":
            grade = "✅ A"
            action = "APTO"
            reason = reason + " · sin A+ por confianza limitada"

        # v22.11: guardia de calidad combinada. Aunque la probabilidad sea alta,
        # una muestra clay corta y un gap Elo/modelo alto no pueden salir como APTO.
        if min_surface_matches < 10 and elo_pure_gap >= 0.14 and action in ["APTO fuerte", "APTO"]:
            grade = "⚖️ B"
            action = "Solo si acompaña lectura"
            reason = reason + " · degradado por muestra clay corta + gap Elo/modelo"

        signals.append({
            "Mercado": name,
            "Probabilidad": prob,
            "Umbral mínimo": min_prob,
            "Grade": grade,
            "Acción": action,
            "Motivo": reason
        })

    if circuito == "ATP" and surface == "Hard":
        add_signal("Over 18.5", over18, 0.72, "over", "ATP Hard: mercado históricamente más fuerte", 2)
        add_signal("Over 19.5", over19, 0.66, "over", "ATP Hard: mejor equilibrio riesgo/calidad", 2)
        add_signal("Over 20.5", over20, 0.62, "over", "ATP Hard si hay señal clara de games", 1)
        add_signal(f"ML favorito: {fav_name}", fav_prob, 0.68, "ml", "ATP Hard favorito medio/fuerte", 1)

    elif circuito == "ATP" and surface == "Clay":
        add_signal("Over 18.5", over18, 0.72, "over", "ATP Clay: over bajo útil, exige confianza", 2)
        add_signal("Over 19.5", over19, 0.64, "over", "ATP Clay: buena señal si clay engine acompaña", 1)
        add_signal(f"ML favorito: {fav_name}", fav_prob, 0.70, "ml", "ATP Clay con especialista/favorito claro", 0)

    elif circuito == "WTA":
        add_signal(f"ML favorito: {fav_name}", fav_prob, 0.68, "ml", "WTA: exigir probabilidad alta", 1)
        add_signal("Favorito 2-0", fav20, 0.58, "fav20", "WTA: solo con perfil dominador/top", 1)
        add_signal("Underdog gana set", dogset, 0.62, "dogset", "WTA: útil con dog peligroso", 0)
        add_signal("Over 18.5", over18, 0.76, "over", "WTA overs solo con umbral alto", 0)
        add_signal("Partido largo", longm, 0.66, "long", "WTA long match solo con señal clara", 0)

    else:
        add_signal("Over 18.5", over18, 0.74, "over", "Filtro general", 0)
        add_signal(f"ML favorito: {fav_name}", fav_prob, 0.70, "ml", "Filtro general ML", 0)

    grade_order = {"🔥 A+": 4, "✅ A": 3, "⚖️ B": 2, "⚠️ C": 1}
    signals = sorted(signals, key=lambda x: (grade_order.get(x["Grade"], 0), x["Probabilidad"]), reverse=True)

    main = None
    for s in signals:
        if s["Acción"] in ["APTO fuerte", "APTO"]:
            main = s
            break
    if main is None and signals:
        main = signals[0]

    if main and main["Acción"] == "APTO fuerte":
        status = "🔥 SPOT FUERTE"
    elif main and main["Acción"] == "APTO":
        status = "✅ SPOT APTO"
    elif main and main["Acción"].startswith("Solo"):
        status = "⚖️ SPOT DUDOSO"
    else:
        status = "⚠️ NO BET / SOLO OBSERVAR"

    # v22.27 Upset Label Cleanup:
    # Si el guardia anti-upset está activo, no mostramos una lectura limpia de ML/2-0.
    # No cambia probabilidades; solo evita una etiqueta contradictoria en la señal final.
    if upset_guard.get("active", False) and main:
        mt = str(main.get("Mercado", "")).lower()
        if "ml favorito" in mt or "favorito 2-0" in mt:
            status = "⚠️ NO BET / RIESGO UPSET"

    return {
        "status": status,
        "main": main,
        "signals": signals,
        "risk_notes": risk_notes,
        "zone_score": zone_score,
        "min_confidence": min_conf,
        "avg_confidence": avg_conf,
        "min_surface_matches": min_surface_matches,
        "elo_pure_gap": elo_pure_gap
    }


def render_betting_filters(filters):
    st.divider()
    st.subheader("💎 Signal Trust Engine")

    main = filters.get("main")
    status = filters.get("status", "⚠️ NO BET")

    if main:
        if "FUERTE" in status or "APTO" in status:
            st.success(f"{status} · {main['Mercado']} → {main['Probabilidad']:.1%}")
        elif "DUDOSO" in status:
            st.warning(f"{status} · {main['Mercado']} → {main['Probabilidad']:.1%}")
        else:
            st.error(f"{status} · mejor señal: {main['Mercado']} → {main['Probabilidad']:.1%}")
        st.caption(main.get("Motivo", ""))

    if filters.get("risk_notes"):
        st.warning("Riesgos: " + " · ".join(filters["risk_notes"]))

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Confianza mínima", f"{filters.get('min_confidence', 1.0):.0%}")
    with c2:
        st.metric("Mín. partidos superficie", f"{filters.get('min_surface_matches', 0)}")
    with c3:
        st.metric("Gap Elo puro/modelo", f"{filters.get('elo_pure_gap', 0):.1%}")

    rows = []
    for s in filters.get("signals", []):
        rows.append({
            "Mercado": s["Mercado"],
            "Prob": f"{s['Probabilidad']:.1%}",
            "Mín": f"{s['Umbral mínimo']:.1%}",
            "Grade": s["Grade"],
            "Acción": s["Acción"],
            "Motivo": s["Motivo"]
        })

    if rows:
        with st.expander("📋 Ver todas las señales del filtro", expanded=False):
            st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)



# =========================================================
# v23.0 BATCH PASTE ANALYZER
# =========================================================

def _parse_decimal_odd(x):
    s = str(x).strip().replace(",", ".")
    try:
        v = float(s)
        if 1.01 <= v <= 100:
            return v
    except Exception:
        pass
    return None


def _abbr_match_score(abbr, full_name):
    """
    Compara abreviaturas tipo "S. Baez" o "I. Montes de la Torr"
    con nombres completos de la línea de partido.
    """
    a = normalizar_texto(abbr).lower().replace(".", " ")
    f = normalizar_texto(full_name).lower()
    a_parts = [p for p in re.split(r"\s+", a) if p]
    f_parts = [p for p in re.split(r"\s+", f) if p]
    if not a_parts or not f_parts:
        return 0.0

    # Si trae inicial + apellido aproximado.
    if len(a_parts) >= 2 and len(f_parts) >= 2 and len(a_parts[0]) == 1:
        initial_ok = f_parts[0].startswith(a_parts[0])
        last_abbr = " ".join(a_parts[1:])
        last_full = " ".join(f_parts[1:])
        last_score = SequenceMatcher(None, last_abbr, last_full).ratio()
        return (0.35 if initial_ok else 0.0) + 0.65 * last_score

    return SequenceMatcher(None, a, f).ratio()


def _match_quoted_player(quoted, p1_raw, p2_raw):
    quoted = re.sub(r"(?i).*ganador", "", str(quoted)).strip()
    quoted = quoted.replace("Guarantee Logo", "").strip()
    if not quoted:
        return None

    s1 = max(
        SequenceMatcher(None, normalizar_texto(quoted).lower(), normalizar_texto(p1_raw).lower()).ratio(),
        _abbr_match_score(quoted, p1_raw)
    )
    s2 = max(
        SequenceMatcher(None, normalizar_texto(quoted).lower(), normalizar_texto(p2_raw).lower()).ratio(),
        _abbr_match_score(quoted, p2_raw)
    )
    if max(s1, s2) < 0.45:
        return None
    return 1 if s1 >= s2 else 2


def parse_winamax_paste(raw_text):
    """
    Acepta formatos como:
    Jugador A - Jugador B
    Guarantee LogoGanadorS. Baez
    1,32

    También acepta:
    Jugador A - Jugador B | 1,50 | 2,70
    """
    lines = [ln.strip() for ln in str(raw_text).splitlines() if ln.strip()]
    matches = []
    i = 0
    while i < len(lines):
        line = lines[i]
        clean = line.replace("–", "-").replace("—", "-")

        if " - " in clean:
            left, right = clean.split(" - ", 1)
            p1_raw = left.strip()
            rest = right.strip()

            odd1 = odd2 = None
            quoted_side = None
            quoted_odd = None
            quoted_text = None

            # Formato: P1 - P2 | cuota1 | cuota2
            parts = [p.strip() for p in rest.split("|")]
            p2_raw = parts[0].strip()
            if len(parts) >= 3:
                odd1 = _parse_decimal_odd(parts[1])
                odd2 = _parse_decimal_odd(parts[2])

            # Mirar 1-3 líneas siguientes por "Ganador..." y cuota.
            look = lines[i+1:i+4]
            for j, ln in enumerate(look):
                if "ganador" in normalizar_texto(ln).lower():
                    quoted_text = ln
                    quoted_side = _match_quoted_player(ln, p1_raw, p2_raw)
                    # cuota suele venir justo después
                    if i + 1 + j + 1 < len(lines):
                        quoted_odd = _parse_decimal_odd(lines[i + 1 + j + 1])
                    break

            # Si no hay "Ganador", intentar cuota directa siguiente.
            if quoted_odd is None and odd1 is None and i + 1 < len(lines):
                q = _parse_decimal_odd(lines[i+1])
                if q is not None:
                    quoted_odd = q

            matches.append({
                "raw": line,
                "p1_raw": p1_raw,
                "p2_raw": p2_raw,
                "odd1": odd1,
                "odd2": odd2,
                "quoted_side": quoted_side,
                "quoted_odd": quoted_odd,
                "quoted_text": quoted_text
            })
        i += 1

    return matches


def find_player_in_db(name, db):
    target = normalizar_texto(name).lower()
    target_clean = limpiar(name).lower()
    best_key = None
    best_score = 0.0

    for key in db.keys():
        k1 = normalizar_texto(key).lower()
        k2 = limpiar(key).lower()
        score = max(
            SequenceMatcher(None, target, k1).ratio(),
            SequenceMatcher(None, target_clean, k2).ratio()
        )

        # Bonus apellido+inicial en ambos sentidos.
        tparts = [p for p in re.split(r"\s+", target_clean) if p]
        kparts = [p for p in re.split(r"\s+", k2) if p]
        if len(tparts) >= 2 and len(kparts) >= 2:
            if tparts[-1] == kparts[-1] and tparts[0][0] == kparts[0][0]:
                score = max(score, 0.96)
            elif tparts[-1] == kparts[-1]:
                score = max(score, 0.86)

        if score > best_score:
            best_score = score
            best_key = key

    return best_key, best_score


def batch_pick_label(sim, over18, over19, over20, over22, under22, p1_name, p2_name):
    p1c, p2c = sim.get("p1_cal", 0.5), sim.get("p2_cal", 0.5)
    fav_name = p1_name if p1c >= p2c else p2_name
    dog_name = p2_name if p1c >= p2c else p1_name

    candidates = [
        (f"ML {fav_name}", max(p1c, p2c)),
        ("Over 18.5", over18),
        ("Over 19.5", over19),
        ("Over 20.5", over20),
        ("Under 22.5", under22),
        (f"{dog_name} gana al menos 1 set", sim.get("dog_wins_set", 0.0)),
    ]

    # Evitar recomendar overs altos flojos como principal.
    candidates = [(k, v) for k, v in candidates if v is not None]
    label, prob = max(candidates, key=lambda x: x[1])
    return label, float(prob)


def analyze_batch_matches(parsed_matches, db, circuito, surface, best_of, sims, progress_callback=None):
    rows = []
    total = len(parsed_matches)
    for idx, m in enumerate(parsed_matches, start=1):
        if progress_callback:
            progress_callback(idx-1, total, f"Emparejando {m.get('p1_raw')} vs {m.get('p2_raw')}")

        p1_key, p1_score = find_player_in_db(m["p1_raw"], db)
        p2_key, p2_score = find_player_in_db(m["p2_raw"], db)

        if not p1_key or not p2_key or p1_score < 0.72 or p2_score < 0.72:
            rows.append({
                "Partido": f"{m['p1_raw']} vs {m['p2_raw']}",
                "Estado": "No encontrado",
                "Jugador 1 encontrado": p1_key or "N/A",
                "Score J1": f"{p1_score:.0%}",
                "Jugador 2 encontrado": p2_key or "N/A",
                "Score J2": f"{p2_score:.0%}",
            })
            continue

        d1, d2 = db[p1_key], db[p2_key]
        sim = sim_match(d1, d2, surface, circuito, best_of, sims, context_row={})
        games = sim.get("games", [])
        avg_games = float(np.mean(games)) if len(games) else 0.0
        games_p1 = sim.get("games_p1", [])
        games_p2 = sim.get("games_p2", [])
        avg_g1 = float(np.mean(games_p1)) if len(games_p1) else 0.0
        avg_g2 = float(np.mean(games_p2)) if len(games_p2) else 0.0

        over18_raw = sum(x > 18.5 for x in games)/sims if sims else 0
        over19_raw = sum(x > 19.5 for x in games)/sims if sims else 0
        over20_raw = sum(x > 20.5 for x in games)/sims if sims else 0
        over22_raw = sum(x > 22.5 for x in games)/sims if sims else 0
        caps = aplicar_market_sanity_caps(sim, circuito, surface, over18_raw, over19_raw, over20_raw, over22_raw)
        over18, over19, over20, over22 = caps["over18"], caps["over19"], caps["over20"], caps["over22"]
        under22 = 1 - over22
        sim["market_over18"] = over18
        sim["market_over19"] = over19
        sim["market_over20"] = over20
        sim["market_over22"] = over22
        sim["market_cap_notes"] = caps.get("notes", [])

        p1c, p2c = sim["p1_cal"], sim["p2_cal"]
        fav_name = p1_key if p1c >= p2c else p2_key
        fav_prob = max(p1c, p2c)
        dog_name = p2_key if p1c >= p2c else p1_key

        best_label, best_prob = batch_pick_label(sim, over18, over19, over20, over22, under22, p1_key, p2_key)

        filters = betting_filter_engine(circuito, surface, sim, p1_key, p2_key)
        trust = filters.get("status", "")
        rationale = " · ".join(filters.get("reasons", [])[:2]) if isinstance(filters, dict) else ""

        # Cuota pegada: puede ser de un jugador concreto.
        quoted_player = None
        quoted_odd = m.get("quoted_odd")
        quoted_prob_model = None
        edge = None
        fair_odd = None

        if m.get("odd1") is not None:
            # si hay dos cuotas limpias, usar cuota del favorito modelo
            quoted_player = fav_name
            quoted_odd = m["odd1"] if fav_name == p1_key else m["odd2"]
            quoted_prob_model = fav_prob
        elif quoted_odd is not None and m.get("quoted_side") in [1, 2]:
            quoted_player = p1_key if m["quoted_side"] == 1 else p2_key
            quoted_prob_model = p1c if m["quoted_side"] == 1 else p2c

        if quoted_odd and quoted_prob_model:
            fair_odd = 1 / max(0.01, quoted_prob_model)
            edge = quoted_odd * quoted_prob_model - 1

        rows.append({
            "Partido": f"{p1_key} vs {p2_key}",
            "Estado": "OK",
            "Favorito modelo": fav_name,
            "ML favorito": f"{fav_prob:.1%}",
            "Mejor señal": best_label,
            "Prob señal": f"{best_prob:.1%}",
            "Signal Trust": trust,
            "Over 18.5": f"{over18:.1%}",
            "Over 19.5": f"{over19:.1%}",
            "Under 22.5": f"{under22:.1%}",
            "Jugador gana set": dog_name,
            "Prob gana set": f"{sim.get('dog_wins_set', 0):.1%}",
            "Juegos J1": f"{avg_g1:.1f}",
            "Juegos J2": f"{avg_g2:.1f}",
            "Total games": f"{avg_games:.1f}",
            "Cuota pegada": quoted_odd if quoted_odd else "",
            "Jugador cuota": quoted_player or "",
            "Cuota justa": f"{fair_odd:.2f}" if fair_odd else "",
            "Edge": f"{edge:.1%}" if edge is not None else "",
            "Riesgos": rationale,
            "Match J1": f"{p1_score:.0%}",
            "Match J2": f"{p2_score:.0%}",
        })

        if progress_callback:
            progress_callback(idx, total, f"Analizado {p1_key} vs {p2_key}")

    return pd.DataFrame(rows)


def _pct_to_float(x):
    try:
        s = str(x).replace("%", "").replace(",", ".").strip()
        if not s:
            return None
        return float(s) / 100.0
    except Exception:
        return None


def batch_recommendation(row):
    trust = str(row.get("Signal Trust", "")).upper()
    edge = _pct_to_float(row.get("Edge", ""))
    signal = str(row.get("Mejor señal", ""))
    risks = str(row.get("Riesgos", "")).lower()

    if "NO BET" in trust:
        if edge is not None and edge > 0.06:
            return "VALUE NUMÉRICO PERO RIESGO"
        return "NO BET"

    if "FUERTE" in trust:
        if edge is not None:
            return "APTA + VALUE" if edge > 0.03 else "APTA SIN VALUE ML"
        return "APTA"

    if "APTO" in trust:
        if edge is not None:
            return "APTA + VALUE" if edge > 0.03 else "APTA SIN VALUE ML"
        return "APTA"

    if "DUDOSO" in trust:
        if edge is not None and edge > 0.07:
            return "DUDOSA CON VALUE"
        return "DUDOSA"

    if "upset" in risks or "riesgo" in risks:
        return "NO BET / REVISAR"

    return "REVISAR"


def prepare_batch_display_table(ok_df):
    if ok_df is None or ok_df.empty:
        return ok_df

    df = ok_df.copy()

    # Unificar columnas dinámicas del tipo "Jugador set".
    set_cols = [c for c in df.columns if c.endswith(" set")]
    if set_cols:
        jugador_set = []
        prob_set = []
        for _, row in df.iterrows():
            found_name = ""
            found_prob = ""
            for c in set_cols:
                val = row.get(c, "")
                if str(val).strip():
                    found_name = c[:-4]
                    found_prob = val
                    break
            jugador_set.append(found_name)
            prob_set.append(found_prob)
        df["Jugador gana set"] = jugador_set
        df["Prob gana set"] = prob_set
        df = df.drop(columns=set_cols, errors="ignore")

    df["Recomendación"] = df.apply(batch_recommendation, axis=1)

    preferred = [
        "Recomendación",
        "Partido",
        "Favorito modelo",
        "ML favorito",
        "Mejor señal",
        "Prob señal",
        "Signal Trust",
        "Cuota pegada",
        "Jugador cuota",
        "Cuota justa",
        "Edge",
        "Over 18.5",
        "Over 19.5",
        "Under 22.5",
        "Jugador gana set",
        "Prob gana set",
        "Juegos J1",
        "Juegos J2",
        "Total games",
        "Riesgos",
        "Match J1",
        "Match J2",
    ]

    cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
    return df[cols]


def batch_excel_bytes(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Analisis")
        ws = writer.book["Analisis"]

        # Formato básico tipo tabla legible.
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        header_fill = PatternFill("solid", fgColor="1F4E78")
        header_font = Font(color="FFFFFF", bold=True)
        thin = Side(style="thin", color="D9E2F3")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = border

        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.border = border
                cell.alignment = Alignment(vertical="center", wrap_text=False)

        widths = {
            "A": 24, "B": 34, "C": 22, "D": 12, "E": 28, "F": 12,
            "G": 18, "H": 12, "I": 22, "J": 12, "K": 12,
            "L": 12, "M": 12, "N": 12, "O": 22, "P": 12,
            "Q": 10, "R": 10, "S": 11, "T": 42
        }
        for col, width in widths.items():
            ws.column_dimensions[col].width = width

        # Resaltar recomendación
        rec_col = None
        for idx, cell in enumerate(ws[1], start=1):
            if cell.value == "Recomendación":
                rec_col = idx
                break

        if rec_col:
            fills = {
                "APTA": "E2F0D9",
                "APTA + VALUE": "C6EFCE",
                "DUDOSA": "FFF2CC",
                "DUDOSA CON VALUE": "FCE4D6",
                "NO BET": "F4CCCC",
                "VALUE NUMÉRICO PERO RIESGO": "FCE4D6",
            }
            for row in range(2, ws.max_row + 1):
                val = str(ws.cell(row=row, column=rec_col).value or "")
                color = None
                for key, fill in fills.items():
                    if key in val:
                        color = fill
                        break
                if color:
                    ws.cell(row=row, column=rec_col).fill = PatternFill("solid", fgColor=color)

    output.seek(0)
    return output.getvalue()

# =========================================================
# UI
# =========================================================

with st.sidebar:
    st.header("🎾 Tennis IA v23.1 Batch Excel")
    st.caption("Favorite Identity Engine")
    if st.button("🧹 Limpiar caché"):
        st.cache_data.clear()
        st.success("Caché limpiada")
    circuito = st.radio("Circuito", ["ATP", "WTA"])
    modo = st.radio("Modo", ["Predictor", "Analizador por lista", "Validador histórico", "Analyzer"])
    mostrar_debug = st.toggle("🔧 Mostrar diagnóstico técnico", value=False)

# =========================================================
# UX Progress Engine: carga visible de datos
# =========================================================

load_status = st.status("🔄 Preparando datos del modelo...", expanded=False)
with load_status:
    st.caption("Fase 1/3 · Leyendo jugadores, Elo, stats y fatiga. Si es la primera carga puede tardar.")
    load_bar = st.progress(5, text="Fase 1/3 · Cargando base de jugadores...")
    db = cargar_datos(circuito)

    load_bar.progress(65, text="Fase 2/3 · Cargando Match Count / QualityMap...")
    st.caption("Fase 2/3 · Integrando históricos ATP + Challenger/Qualy.")
    try:
        qm_preview = crear_quality_map(circuito)
        q_players = qm_preview.get("_meta", {}).get("raw_player_count", "?") if isinstance(qm_preview, dict) else "?"
    except Exception:
        q_players = "?"

    load_bar.progress(100, text=f"Fase 3/3 · Datos listos · jugadores={len(db)} · quality players={q_players}")
    st.caption("✅ Datos preparados. Las siguientes cargas deberían ir más rápido por caché.")

load_status.update(label=f"✅ Datos listos · {len(db)} jugadores cargados", state="complete", expanded=False)

if not db:
    st.error("No se encontraron jugadores. Revisa carpetas y archivos.")
    st.stop()

if modo == "Predictor":
    with st.sidebar:
        players = sorted(db.keys())
        surface = st.selectbox("Superficie", ["Hard","Clay","Grass"])
        formato = st.radio("Formato", ["ATP Tour (3 sets)", "Grand Slam (5 sets)"])
        modo_velocidad = st.radio(
            "Velocidad",
            ["⚡ Rápido", "⚖️ Equilibrado", "🎯 Preciso"],
            index=1,
            help="Rápido usa menos simulaciones y responde antes. Preciso es más lento."
        )
        sims = st.select_slider(
            "Simulaciones",
            [1000, 2500, 5000, 10000, 20000],
            value=5000
        )

        if modo_velocidad.startswith("⚡"):
            sims = min(sims, 2500)
            st.caption("⚡ Modo rápido: máximo 2.500 sims para acelerar.")
        elif modo_velocidad.startswith("⚖️"):
            sims = min(sims, 5000)
            st.caption("⚖️ Modo equilibrado: máximo 5.000 sims.")
        else:
            st.caption("🎯 Modo preciso: usa el valor seleccionado.")

    c1, c2 = st.columns(2)
    with c1: p1_name = st.selectbox("Jugador 1", players)
    with c2: p2_name = st.selectbox("Jugador 2", players, index=min(1, len(players)-1))

    if st.button("🚀 ANALIZAR PARTIDO", width='stretch'):
        d1, d2 = db[p1_name], db[p2_name]
        best_of = 5 if "5" in formato else 3
        if sims >= 10000:
            st.warning("🎯 Modo preciso: puede tardar bastante en Streamlit Cloud. Para pruebas rápidas usa 2.500 o 5.000 sims.")
        sim_status = st.status(f"🎲 Preparando simulación Monte Carlo...", expanded=True)
        with sim_status:
            sim_bar = st.progress(1, text="Fase 1/2 · Preparando engines...")
            sim_msg = st.empty()
            sim_start = time.time()
            sim_msg.caption("Calculando hold/return, fatiga, rating sanity, clay engines y contexto...")

            last_ui_update = {"t": 0.0}

            def update_sim_progress(done, total):
                elapsed = max(0.001, time.time() - sim_start)

                if done <= 0:
                    sim_bar.progress(3, text=f"Fase 1/2 · Preparando engines · 0 / {total:,}")
                    sim_msg.caption("Aún no ha empezado el bucle Monte Carlo; esto es normal.")
                    return

                # Limitar repintados: suficiente para parecer vivo, sin ralentizar demasiado.
                now = time.time()
                if done < total and (now - last_ui_update["t"]) < 0.20:
                    return
                last_ui_update["t"] = now

                pct_float = min(1.0, max(0.03, done / total)) if total else 1.0
                pct_int = int(round(pct_float * 100))
                rate = done / elapsed if done else 0
                eta = (total - done) / rate if rate > 0 else 0

                sim_bar.progress(
                    pct_int,
                    text=f"Fase 2/2 · Monte Carlo {done:,} / {total:,} ({pct_int}%) · {elapsed:.1f}s · ETA {eta:.1f}s"
                )
                sim_msg.caption(f"Simulando partidos... último lote procesado: {done:,}")

            # Primer repintado antes de entrar al cálculo pesado.
            update_sim_progress(0, sims)

            sim = sim_match(
                d1, d2, surface, circuito, best_of, sims,
                context_row={},
                progress_callback=update_sim_progress
            )
            total_elapsed = time.time() - sim_start
            sim_bar.progress(100, text=f"Simulación completada · {sims:,} partidos · {total_elapsed:.1f}s")
            sim_msg.caption("✅ Resultados listos para pintar en pantalla.")

        sim_status.update(label=f"✅ Simulación completada · {sims:,} partidos", state="complete", expanded=False)

        st.caption(
            f"📁 Stats usadas: {stats_filename_label(circuito, 'serve', surface)} · "
            f"{stats_filename_label(circuito, 'return', surface)} · "
            f"{stats_filename_label(circuito, 'break', surface)}"
        )

        p1, p2, p1c, p2c = sim["p1"], sim["p2"], sim["p1_cal"], sim["p2_cal"]
        games = sim["games"]
        avg_games, med_games = np.mean(games), np.median(games)
        games_p1 = sim.get("games_p1", [])
        games_p2 = sim.get("games_p2", [])
        avg_g1 = float(np.mean(games_p1)) if len(games_p1) else 0.0
        avg_g2 = float(np.mean(games_p2)) if len(games_p2) else 0.0
        med_g1 = float(np.median(games_p1)) if len(games_p1) else 0.0
        med_g2 = float(np.median(games_p2)) if len(games_p2) else 0.0
        game_diff = avg_g1 - avg_g2
        over18_raw = sum(x > 18.5 for x in games)/sims
        over19_raw = sum(x > 19.5 for x in games)/sims
        over20_raw = sum(x > 20.5 for x in games)/sims
        over22_raw = sum(x > 22.5 for x in games)/sims

        market_caps = aplicar_market_sanity_caps(sim, circuito, surface, over18_raw, over19_raw, over20_raw, over22_raw)
        over18 = market_caps["over18"]
        over19 = market_caps["over19"]
        over20 = market_caps["over20"]
        over22 = market_caps["over22"]
        under22 = 1-over22

        sim["market_over18"] = over18
        sim["market_over19"] = over19
        sim["market_over20"] = over20
        sim["market_over22"] = over22
        sim["market_cap_notes"] = market_caps.get("notes", [])

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
        st.subheader("📊 Mercados principales")
        m1,m2,m3,m4,m5 = st.columns(5)
        with m1: st.metric("Over 18.5", f"{over18:.1%}", nivel(over18))
        with m2: st.metric("Over 19.5", f"{over19:.1%}", nivel(over19))
        with m3: st.metric("Over 20.5", f"{over20:.1%}", nivel(over20))
        with m4: st.metric("Over 22.5", f"{over22:.1%}", nivel(over22))
        with m5: st.metric("Under 22.5", f"{under22:.1%}", nivel(under22))

        model_dog_name = sim.get("model_dog_name", "Underdog")
        e1,e2,e3 = st.columns(3)
        with e1: st.metric("3 sets", f"{sim['set3']:.1%}", nivel(sim["set3"]))
        with e2: st.metric("Tie-break", f"{sim['tb']:.1%}", nivel(sim["tb"]))
        with e3: st.metric(f"{model_dog_name} gana al menos 1 set", f"{sim['dog_wins_set']:.1%}", nivel(sim["dog_wins_set"]))

        st.subheader("🎮 Juegos esperados")
        gcol1, gcol2, gcol3, gcol4 = st.columns(4)
        with gcol1:
            st.metric(d1["Player"], f"{avg_g1:.1f}", f"Mediana {med_g1:.0f}")
        with gcol2:
            st.metric(d2["Player"], f"{avg_g2:.1f}", f"Mediana {med_g2:.0f}")
        with gcol3:
            st.metric("Total esperado", f"{avg_games:.1f}", f"Mediana {med_games:.0f}")
        with gcol4:
            diff_label = d1["Player"] if game_diff >= 0 else d2["Player"]
            st.metric("Diferencia juegos", f"{abs(game_diff):.1f}", f"Ventaja {diff_label}")

        st.caption(
            f"Proyección: {d1['Player']} {avg_g1:.1f} - {avg_g2:.1f} {d2['Player']} · "
            f"Total medio {avg_games:.1f}"
        )
        if sim.get("market_cap_notes"):
            st.caption("🧯 Market sanity: " + " · ".join(sim.get("market_cap_notes", [])))

        with st.expander("🔧 Ver diagnóstico técnico", expanded=mostrar_debug):
            st.divider()
            st.subheader("📋 Mercados derivados")
            dm1, dm2, dm3 = st.columns(3)
            with dm1:
                st.metric(f"{sim.get('model_fav_name','Favorito')} 2-0", f"{sim['fav_2_0']:.1%}", nivel(sim["fav_2_0"]))
            with dm2:
                st.metric("Partido largo", f"{sim['long_match']:.1%}", nivel(sim["long_match"]))
            with dm3:
                st.metric("Fav + Under 22.5", f"{sim['fav_under22']:.1%}", nivel(sim["fav_under22"]))

            st.divider()
            st.subheader("🎾 Hold / Return Engine")
            h1,h2 = st.columns(2)
            with h1:
                st.metric(d1["Player"], f"{sim['hold1']:.1%}", f"Raw hold {sim['raw_hold1']:.1%}")
                st.caption(f"{perfil_legible(sim['p1_profile'])} · Return strength {sim['ret1']:.1%}")
            with h2:
                st.metric(d2["Player"], f"{sim['hold2']:.1%}", f"Raw hold {sim['raw_hold2']:.1%}")
                st.caption(f"{perfil_legible(sim['p2_profile'])} · Return strength {sim['ret2']:.1%}")



            if circuito == "ATP" and surface == "Clay" and sim.get("elite_clay", {}).get("active", False):
                st.divider()
                st.subheader("👑 Elite ATP Clay Protection")

                ec = sim.get("elite_clay", {})
                e1,e2,e3 = st.columns(3)

                with e1:
                    st.metric("Activo", "Sí")

                with e2:
                    st.metric("Favorito elite", ec.get("fav","").upper())

                with e3:
                    st.metric("Vol mult", f"{ec.get('vol_mult',1.0):.2f}")

            if circuito == "ATP" and surface == "Clay":
                st.divider()
                st.subheader("🧱 Rating Sanity Engine")

                ce = sim.get("clay_engine", {})
                c1,c2,c3 = st.columns(3)

                with c1:
                    st.metric("Activo", "Sí" if ce.get("active", False) else "No")

                with c2:
                    st.metric("Perfil", ce.get("profile", "neutral"))

                with c3:
                    st.metric("Vol mult", f"{ce.get('vol_mult',1.0):.2f}")

                if ce.get("notes"):
                    st.caption(" · ".join(ce.get("notes", [])))

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
            st.subheader("🏟️ Tournament Engine")

            tc = sim.get("tournament_ctx", {})
            t1,t2,t3 = st.columns(3)

            with t1:
                st.metric("Series", tc.get("series","ATP"))

            with t2:
                st.metric("Court", tc.get("court","Outdoor"))

            with t3:
                st.metric("Round", tc.get("round","Main"))

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
            st.subheader("🎾 Rating Sanity Engine")

            sd = sim.get("set_dynamics", {})

            s1,s2,s3 = st.columns(3)

            with s1:
                st.metric("2-0 boost", f"{sd.get('fav20_boost',0):+.1%}")

            with s2:
                st.metric("Dog suppression", f"{sd.get('dog_set_suppress',0):+.1%}")

            with s3:
                st.metric("Long match adj", f"{sd.get('long_match_adj',0):+.1%}")

            ssg = sim.get("straight_sets_guard", {}) or {}
            if ssg.get("active", False):
                st.info(
                    f"🧭 Straight Sets Guard activo · 2-0 {ssg.get('fav20_boost',0):+.1%} · "
                    f"Dog set {ssg.get('dogset_cut',0):-.1%} · Largo {ssg.get('long_cut',0):-.1%}"
                )
                notes = ssg.get("notes", [])
                if notes:
                    st.caption(" · ".join(notes))



            if sim.get("wta_engine_active", False):
                st.divider()
                st.subheader("🎭 WTA Match Script")

                ws2 = sim.get("wta_script", {})
                m1,m2,m3,m4 = st.columns(4)

                with m1:
                    st.metric("Activo", "Sí" if ws2.get("active", False) else "No")

                with m2:
                    st.metric("Script", ws2.get("script","neutral"))

                with m3:
                    st.metric("Fav2-0", f"{ws2.get('fav20_mult',1.0):.2f}x")

                with m4:
                    st.metric("Long", f"{ws2.get('long_mult',1.0):.2f}x")

            if sim.get("wta_engine_active", False):
                st.divider()
                st.subheader("🎾 Elite WTA Separation")

                ws = sim.get("wta_separation", {})
                w1,w2,w3 = st.columns(3)

                with w1:
                    st.metric("Activo", "Sí" if ws.get("active", False) else "No")

                with w2:
                    st.metric("Perfil", ws.get("edge_label", "normal"))

                with w3:
                    st.metric("Vol mult", f"{ws.get('vol_mult',1.0):.2f}")


            st.divider()
            st.subheader("🧠 Rating Sanity Engine")

            rs = sim.get("rating_sanity", {})
            r1c, r2c, r3c = st.columns(3)

            with r1c:
                p = rs.get("p1", {})
                st.metric(d1["Player"], f"{p.get('confidence',1):.0%}", delta=f"{p.get('matches_surface',0)} partidos {surface}")
                st.caption(f"Quality {p.get('tour_quality',0):.0%} · Stability {p.get('stability',0):.0%} · Elo eff {p.get('elo_effective', d1[surface]):.0f}")
                if p.get("flags"):
                    st.caption(" · ".join(p.get("flags", [])))

            with r2c:
                p = rs.get("p2", {})
                st.metric(d2["Player"], f"{p.get('confidence',1):.0%}", delta=f"{p.get('matches_surface',0)} partidos {surface}")
                st.caption(f"Quality {p.get('tour_quality',0):.0%} · Stability {p.get('stability',0):.0%} · Elo eff {p.get('elo_effective', d2[surface]):.0f}")
                if p.get("flags"):
                    st.caption(" · ".join(p.get("flags", [])))

            with r3c:
                st.metric("Vol mult", f"{rs.get('vol_mult',1.0):.2f}")
                st.caption(f"Engine {rs.get('version','v22')}")

            st.caption("🔎 Match Count Debug")
            hist_diag = historicos_diagnostics(circuito)
            st.caption(
                f"Históricos: files={hist_diag.get('files_count',0)} · rows={hist_diag.get('rows',0)} · "
                f"Winner={hist_diag.get('winner_col')} · Loser={hist_diag.get('loser_col')} · Surface={hist_diag.get('surface_col')} · "
                f"Dates={hist_diag.get('date_min','N/A')}→{hist_diag.get('date_max','N/A')}"
            )
            if hist_diag.get("folder_counts"):
                parts = []
                for fd, cnt in (hist_diag.get("folder_counts", {}) or {}).items():
                    parts.append(f"{fd}={cnt}")
                st.caption("Archivos por carpeta: " + " · ".join(parts))
                for fd, samples in (hist_diag.get("folder_samples", {}) or {}).items():
                    if samples:
                        st.caption(f"Muestras {fd}: " + ", ".join([str(x) for x in samples[:5]]))
            if hist_diag.get("sample_players"):
                st.caption("Ejemplos histórico: " + ", ".join(hist_diag.get("sample_players", [])[:8]))
            if hist_diag.get("level_cols"):
                st.caption("Columnas nivel: " + ", ".join([str(x) for x in hist_diag.get("level_cols", [])[:8]]))
                sample_bits = []
                for col, vals in (hist_diag.get("level_samples", {}) or {}).items():
                    if vals:
                        sample_bits.append(f"{col}={', '.join([str(v) for v in vals[:4]])}")
                if sample_bits:
                    st.caption("Ejemplos nivel: " + " · ".join(sample_bits[:4]))
            # Debug interno del Quality Map/cache. Si esto sale a 0, Streamlit está usando un mapa vacío o cache viejo.
            qm1 = rs.get("p1", {}).get("quality_meta", {}) or rs.get("p2", {}).get("quality_meta", {}) or {}
            if qm1:
                st.caption(
                    f"QualityMap: version={qm1.get('version','N/A')} · players={qm1.get('raw_player_count','?')} · keys={qm1.get('quality_keys','?')}"
                )
                if qm1.get("sample_names"):
                    st.caption("QualityMap ejemplos: " + ", ".join([str(x) for x in qm1.get("sample_names", [])[:8]]))
                st.caption("Tour Quality v22.27: amplía Upset Risk Guard para favoritos clay con dog de muestra corta; limpia etiquetas contradictorias.")
            else:
                st.caption("QualityMap: sin meta visible — posible cache viejo o quality_map vacío")
            if hist_diag.get("files_count", 0) == 0 or hist_diag.get("rows", 0) == 0 or not hist_diag.get("winner_col") or not hist_diag.get("loser_col"):
                st.warning(
                    "Históricos no detectados bien: "
                    f"folder={hist_diag.get('folder')} · existe={hist_diag.get('folder_exists')} · "
                    f"files={hist_diag.get('files_count')} · rows={hist_diag.get('rows')} · "
                    f"Winner={hist_diag.get('winner_col')} · Loser={hist_diag.get('loser_col')} · Surface={hist_diag.get('surface_col')}"
                )
                if hist_diag.get("sample_files"):
                    st.caption("Files detectados: " + ", ".join(hist_diag.get("sample_files", [])))
                if hist_diag.get("columns"):
                    st.caption("Columnas detectadas: " + ", ".join([str(x) for x in hist_diag.get("columns", [])[:12]]))
                if hist_diag.get("sample_players"):
                    st.caption("Jugadores ejemplo: " + ", ".join(hist_diag.get("sample_players", [])[:6]))
            dbg1 = rs.get("p1", {})
            dbg2 = rs.get("p2", {})
            dc1, dc2 = st.columns(2)
            with dc1:
                st.caption(
                    f"{d1['Player']} → match: {dbg1.get('matched_name','N/A')} "
                    f"({dbg1.get('match_score',0):.0%}) · total {dbg1.get('matches_total',0)} · "
                    f"H/C/G {dbg1.get('matches_by_surface',{}).get('Hard',0)}/"
                    f"{dbg1.get('matches_by_surface',{}).get('Clay',0)}/"
                    f"{dbg1.get('matches_by_surface',{}).get('Grass',0)}"
                )
                lc = dbg1.get('level_counts', {})
                st.caption(f"Tour/Ch/ITF/Q/Unk {lc.get('tour',0)}/{lc.get('challenger',0)}/{lc.get('itf',0)}/{lc.get('qualy',0)}/{lc.get('unknown',0)}")
                if dbg1.get('source_files'):
                    st.caption("Files: " + ", ".join(dbg1.get('source_files', [])[:4]))
                radar = []
                for c in dbg1.get('candidate_matches', [])[:5]:
                    sf = c.get('surface', {}) if isinstance(c.get('surface', {}), dict) else {}
                    radar.append(f"{c.get('name','?')} {c.get('score',0):.0%} {c.get('reason','')} ({c.get('matches_total',0)} · C{sf.get('Clay',0)})")
                st.caption("Radar nombres: " + (" | ".join(radar) if radar else "sin candidatos"))
            with dc2:
                st.caption(
                    f"{d2['Player']} → match: {dbg2.get('matched_name','N/A')} "
                    f"({dbg2.get('match_score',0):.0%}) · total {dbg2.get('matches_total',0)} · "
                    f"H/C/G {dbg2.get('matches_by_surface',{}).get('Hard',0)}/"
                    f"{dbg2.get('matches_by_surface',{}).get('Clay',0)}/"
                    f"{dbg2.get('matches_by_surface',{}).get('Grass',0)}"
                )
                lc = dbg2.get('level_counts', {})
                st.caption(f"Tour/Ch/ITF/Q/Unk {lc.get('tour',0)}/{lc.get('challenger',0)}/{lc.get('itf',0)}/{lc.get('qualy',0)}/{lc.get('unknown',0)}")
                if dbg2.get('source_files'):
                    st.caption("Files: " + ", ".join(dbg2.get('source_files', [])[:4]))
                radar = []
                for c in dbg2.get('candidate_matches', [])[:5]:
                    sf = c.get('surface', {}) if isinstance(c.get('surface', {}), dict) else {}
                    radar.append(f"{c.get('name','?')} {c.get('score',0):.0%} {c.get('reason','')} ({c.get('matches_total',0)} · C{sf.get('Clay',0)})")
                st.caption("Radar nombres: " + (" | ".join(radar) if radar else "sin candidatos"))

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
        if sim.get("rating_sanity", {}).get("active", False): tags.append("🧠 Rating sanity activo")
        if circuito == "ATP" and surface == "Clay" and sim.get("clay_engine", {}).get("active", False):
            tags.append(f"🧱 Clay engine: {sim.get('clay_engine', {}).get('profile','neutral')}")
        upset_active = (sim.get("upset_risk_guard", {}) or {}).get("active", False)
        fav20_tag_value = sim.get("fav_2_0", 0)
        elite_opp_active = (sim.get("elite_clay_opponent_guard", {}) or {}).get("active", False)
        high_gap_label = abs(max(p1c, p2c) - sim.get("fav_raw_est", max(p1c, p2c))) >= 0.10
        if fav20_tag_value >= 0.55:
            if upset_active:
                tags.append("⚠️ Favorito vulnerable")
            elif elite_opp_active or high_gap_label:
                if fav20_tag_value >= 0.65:
                    tags.append("✅ Favorito 2-0 viable")
                else:
                    tags.append("⚖️ Favorito 2-0 moderado")
            elif fav20_tag_value >= 0.78:
                tags.append("🔥 Spot favorito 2-0")
            elif fav20_tag_value >= 0.65:
                tags.append("✅ Favorito 2-0 viable")
            else:
                tags.append("⚖️ Favorito 2-0 moderado")
        if upset_active: tags.append("⚠️ Riesgo upset")
        if (sim.get("low_over_split_guard", {}) or {}).get("active", False):
            tags.append("🎚️ Over bajo ≠ partido largo")
        tc = sim.get("tournament_ctx", {})
        if "Indoor" in tc.get("court",""): tags.append("🏟️ Indoor boost")
        if "Final" in tc.get("round",""): tags.append("🎯 Final pressure")
        if "Grand Slam" in tc.get("series",""): tags.append("🏆 Grand Slam intensity")
        if sim.get("wta_engine_active", False): tags.append("🎾 WTA Chaos control")
        if sim.get("wta_separation", {}).get("active", False): tags.append("👑 Elite WTA separation")
        if sim.get("wta_script", {}).get("active", False): tags.append(f"🎭 {sim.get('wta_script',{}).get('script','neutral')}")
        st.info(" · ".join(tags) if tags else "Sin perfil extremo detectado.")

        st.divider()
        st.subheader("🎯 Señal principal del modelo")
        markets = {
            "ML favorito calibrado": max(p1c,p2c), "Over 18.5": over18,
            "Over 19.5": over19, "Over 20.5": over20, "Over 22.5": over22, "Under 22.5": under22,
            "Tie-break": sim["tb"], "Fav + Under 22.5": sim["fav_under22"],
            "Dog + Over 20.5": sim["dog_over20"],
            f"{sim.get('model_dog_name','Underdog')} gana set": sim["dog_wins_set"],
            f"{sim.get('model_fav_name','Favorito')} 2-0": sim["fav_2_0"],
            "Partido largo": sim["long_match"]
        }
        best = max(markets.items(), key=lambda x: x[1])
        st.success(f"{best[0]} → {best[1]:.1%}")
        filters = betting_filter_engine(circuito, surface, sim, d1["Player"], d2["Player"])
        render_betting_filters(filters)

        st.caption(f"Tennis IA v23.1 Batch Excel · {sims:,} simulaciones Monte Carlo")


elif modo == "Analizador por lista":
    st.subheader("📋 Analizador por lista pegada")
    st.caption("Pega partidos copiados de Winamax u otra casa. Acepta formato limpio o texto sucio con Ganador/cuotas.")

    with st.sidebar:
        surface = st.selectbox("Superficie lista", ["Hard","Clay","Grass"], index=1)
        formato = st.radio("Formato lista", ["ATP Tour (3 sets)", "Grand Slam (5 sets)"])
        sims_batch = st.select_slider("Simulaciones por partido", [1000,2500,5000,10000], value=2500)
        max_batch = st.number_input("Máx partidos a analizar", 1, 50, 20, 1)

    ejemplo = """Taylah Preston - Yulia Starodubtseva
Guarantee LogoGanadorY. Starodubtseva
1,26

Rafael Jódar - Learner Tien
Guarantee LogoGanadorR. Jódar
1,28

Sebastián Baez - Roberto Carballés Baena
GanadorS. Baez
1,32"""

    raw_batch = st.text_area(
        "Pega aquí los partidos",
        height=260,
        placeholder=ejemplo
    )

    cprev, crun = st.columns([1,1])
    with cprev:
        preview = parse_winamax_paste(raw_batch) if raw_batch.strip() else []
        st.metric("Partidos detectados", len(preview))
    with crun:
        st.metric("Simulaciones estimadas", f"{min(len(preview), int(max_batch)) * int(sims_batch):,}")

    if preview:
        with st.expander("👀 Vista previa detectada", expanded=True):
            st.dataframe(pd.DataFrame(preview[:int(max_batch)]), width='stretch', hide_index=True)

    if st.button("🚀 ANALIZAR LISTA", width='stretch'):
        parsed = parse_winamax_paste(raw_batch)[:int(max_batch)]
        if not parsed:
            st.error("No he detectado partidos. Prueba formato: Jugador A - Jugador B")
            st.stop()

        best_of = 5 if "5" in formato else 3

        status = st.status(f"📋 Analizando {len(parsed)} partidos...", expanded=True)
        with status:
            bar = st.progress(1, text="Preparando análisis por lote...")
            msg = st.empty()
            start = time.time()

            def update_batch(done, total, label=""):
                pct = int(round((done / total) * 100)) if total else 100
                pct = max(1, min(100, pct))
                elapsed = time.time() - start
                bar.progress(pct, text=f"Analizando lista {done}/{total} · {elapsed:.1f}s")
                if label:
                    msg.caption(label)

            df_batch = analyze_batch_matches(
                parsed, db, circuito, surface, best_of, int(sims_batch),
                progress_callback=update_batch
            )
            bar.progress(100, text=f"Análisis completado · {len(parsed)} partidos")
            msg.caption("✅ Lista analizada.")

        status.update(label=f"✅ Lista analizada · {len(parsed)} partidos", state="complete", expanded=False)

        st.divider()
        st.subheader("🔥 Resumen ordenado")
        if "Estado" in df_batch.columns:
            ok = df_batch[df_batch["Estado"] == "OK"].copy()
            ko = df_batch[df_batch["Estado"] != "OK"].copy()
        else:
            ok, ko = df_batch, pd.DataFrame()

        if not ok.empty:
            ok = prepare_batch_display_table(ok)

            # Orden simple: recomendación/trust/edge.
            def _edge_num(x):
                try:
                    s = str(x).replace("%","").replace(",", ".").strip()
                    return float(s) if s else -999
                except Exception:
                    return -999

            rec_order = {
                "APTA + VALUE": 5,
                "APTA": 4,
                "DUDOSA CON VALUE": 3,
                "DUDOSA": 2,
                "VALUE NUMÉRICO PERO RIESGO": 1,
                "NO BET": 0,
            }

            ok["_edge_sort"] = ok["Edge"].apply(_edge_num) if "Edge" in ok.columns else -999
            ok["_rec_sort"] = ok["Recomendación"].astype(str).apply(lambda x: max([v for k,v in rec_order.items() if k in x] or [0]))
            ok = ok.sort_values(["_rec_sort","_edge_sort"], ascending=[False, False]).drop(columns=["_edge_sort","_rec_sort"], errors="ignore")

            st.dataframe(ok, width='stretch', hide_index=True)

            dl1, dl2 = st.columns(2)
            with dl1:
                st.download_button(
                    "⬇️ Descargar CSV",
                    data=ok.to_csv(index=False).encode("utf-8-sig"),
                    file_name="analisis_lista_tennis_ia.csv",
                    mime="text/csv"
                )
            with dl2:
                st.download_button(
                    "📊 Descargar Excel",
                    data=batch_excel_bytes(ok),
                    file_name="analisis_lista_tennis_ia.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        else:
            st.warning("No se pudo analizar ningún partido.")

        if not ko.empty:
            st.divider()
            st.subheader("⚠️ No encontrados / revisar nombres")
            st.dataframe(ko, width='stretch', hide_index=True)


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
    if st.button("🚀 EJECUTAR VALIDACIÓN", width='stretch'):
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
        st.dataframe(val, width='stretch')
        st.download_button("⬇️ Descargar CSV", data=val.to_csv(index=False).encode("utf-8"), file_name="validacion_tennis_ia_v22.csv", mime="text/csv")

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
    if st.button("🚀 EJECUTAR ANALYZER", width='stretch'):
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
            st.dataframe(mt.sort_values(["Acierto real","Casos"], ascending=[False,False]), width='stretch')
        else:
            st.warning("No hay suficientes casos para mercados por umbral.")
        st.divider()
        st.subheader("🎯 ML por tramos")
        st.dataframe(tables.get("ML por tramos", pd.DataFrame()), width='stretch')
        st.divider()
        st.subheader("🌍 Por superficie")
        st.dataframe(tables.get("Por superficie", pd.DataFrame()), width='stretch')
        st.divider()
        st.subheader("🚀 Big server")
        st.dataframe(tables.get("Big server", pd.DataFrame()), width='stretch')
        st.divider()
        st.subheader("📊 Ranking gap")
        st.dataframe(tables.get("Ranking gap", pd.DataFrame()), width='stretch')
        st.divider()
        st.subheader("🧾 Detalle base")
        st.dataframe(val, width='stretch')
        st.download_button("⬇️ Descargar Analyzer CSV", data=val.to_csv(index=False).encode("utf-8"), file_name="analyzer_tennis_ia_v22.csv", mime="text/csv")
