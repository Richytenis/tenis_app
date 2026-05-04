import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os

ARCHIVO_APUESTAS = "registro_apuestas.csv"

# ================================================================
# REGISTRO APUESTAS
# ================================================================

def guardar_apuesta(j1, j2, apuesta, prob):
    df_nuevo = pd.DataFrame([{
        "Jugador1": j1,
        "Jugador2": j2,
        "Apuesta": apuesta,
        "Probabilidad": prob,
        "Resultado": "Pendiente"
    }])

    if os.path.exists(ARCHIVO_APUESTAS):
        df = pd.read_csv(ARCHIVO_APUESTAS)
        df = pd.concat([df, df_nuevo], ignore_index=True)
    else:
        df = df_nuevo

    df.to_csv(ARCHIVO_APUESTAS, index=False)


def cargar_apuestas():
    if os.path.exists(ARCHIVO_APUESTAS):
        return pd.read_csv(ARCHIVO_APUESTAS)
    return pd.DataFrame()


def actualizar_resultado(i, res):
    df = cargar_apuestas()
    df.loc[i, "Resultado"] = res
    df.to_csv(ARCHIVO_APUESTAS, index=False)

# ================================================================
# UTILS
# ================================================================

def normalizar(n):
    if pd.isna(n): return ""
    n = str(n).upper()
    n = re.sub(r'[^A-Z\s]', '', n)
    return " ".join(n.split())

def mapear_superficie(s):
    s = s.upper()
    if 'CLAY' in s or 'TIERRA' in s: return 'Clay'
    if 'GRASS' in s or 'HIERBA' in s: return 'Grass'
    return 'Hard'

# ================================================================
# RANKING ATP
# ================================================================

def cargar_rankings():
    try:
        df = pd.read_excel("datos/atp.xlsx")
        df.columns = df.columns.str.lower()

        col_player = next(c for c in df.columns if c in ["player", "name"])
        col_rank = next(c for c in df.columns if "rank" in c)

        df[col_player] = df[col_player].apply(normalizar)

        return dict(zip(df[col_player], df[col_rank]))
    except:
        return {}

# ================================================================
# DATA IA
# ================================================================

@st.cache_data
def cargar_big_data():
    ruta = "datos"
    stats = {}
    h2h = {}

    for root, _, files in os.walk(ruta):
        peso = 1
        if "ATP" in root.upper(): peso = 2.5
        elif "WTA" in root.upper(): peso = 2
        elif "CHALLENGER" in root.upper(): peso = 1.5

        for f in files:
            if not (f.endswith(".csv") or f.endswith(".xlsx")):
                continue

            try:
                path = os.path.join(root, f)
                df = pd.read_csv(path, on_bad_lines="skip") if f.endswith(".csv") else pd.read_excel(path)

                df.columns = df.columns.str.lower()

                w = next((c for c in df.columns if "winner" in c), None)
                l = next((c for c in df.columns if "loser" in c), None)
                surf_col = next((c for c in df.columns if "surface" in c), None)

                if not w or not l:
                    continue

                for _, row in df.iterrows():
                    jw = normalizar(row[w])
                    jl = normalizar(row[l])
                    surf = mapear_superficie(str(row.get(surf_col, "Hard")))

                    for p in [jw, jl]:
                        if p not in stats:
                            stats[p] = {
                                "power": 0,
                                "total": 0,
                                "surf": {},
                                "recent": []
                            }

                    # power
                    stats[jw]["power"] += 3 * peso
                    stats[jl]["power"] -= 2 / peso

                    stats[jw]["total"] += 1
                    stats[jl]["total"] += 1

                    # superficie
                    for p in [jw, jl]:
                        if surf not in stats[p]["surf"]:
                            stats[p]["surf"][surf] = {"w": 0, "t": 0}
                        stats[p]["surf"][surf]["t"] += 1

                    stats[jw]["surf"][surf]["w"] += 1

                    # forma
                    stats[jw]["recent"].append(1)
                    stats[jl]["recent"].append(0)
                    stats[jw]["recent"] = stats[jw]["recent"][-10:]
                    stats[jl]["recent"] = stats[jl]["recent"][-10:]

                    # h2h
                    key = tuple(sorted([jw, jl]))
                    if key not in h2h:
                        h2h[key] = {}
                    h2h[key][jw] = h2h[key].get(jw, 0) + 1

            except:
                continue

    return stats, h2h

# ================================================================
# COMPONENTES MODELO
# ================================================================

def forma(nombre, stats):
    r = stats.get(nombre, {}).get("recent", [])
    if not r: return 0
    return (sum(r)/len(r) - 0.5) * 300

def h2h_bonus(j1, j2, h2h):
    key = tuple(sorted([j1, j2]))
    if key not in h2h: return 0

    w1 = h2h[key].get(j1, 0)
    w2 = h2h[key].get(j2, 0)
    t = w1 + w2
    if t == 0: return 0

    return ((w1/t) - 0.5) * 200

def ranking_bonus(nombre, rankings):
    r = rankings.get(nombre)
    if r is None: return 0
    return (200 - r) * 2

def poder(nombre, rival, surf, circ, stats, rankings, h2h):
    s = stats.get(nombre, {"power":0,"total":0,"surf":{}})

    conf = min(1, s["total"]/100)
    base = s["power"] * conf

    surf_stats = s["surf"].get(surf, {"w":0,"t":0})
    surf_b = 0
    if surf_stats["t"] > 0:
        surf_b = ((surf_stats["w"]/surf_stats["t"]) - 0.5) * 200

    return 1200 + base + surf_b + forma(nombre, stats) + h2h_bonus(nombre, rival, h2h) + ranking_bonus(nombre, rankings)

def probs(p1, p2, surf, circ):
    base = 0.76 if circ=="ATP" else 0.64
    diff = np.tanh((p1 - p2)/400)

    p1h = np.clip(base + diff*0.3, 0.55, 0.97)
    p2h = np.clip(base - diff*0.3, 0.55, 0.97)

    return p1h, p2h

def sim_set(p1h, p2h):
    j1=j2=0
    s = random.choice([1,2])
    while True:
        p = p1h if s==1 else (1-p2h)
        if random.random()<p: j1+=1
        else: j2+=1

        if (j1>=6 or j2>=6) and abs(j1-j2)>=2: return j1,j2
        if j1==7 or j2==7: return j1,j2
        s=3-s

# ================================================================
# APP
# ================================================================

st.set_page_config(layout="wide")

stats, h2h = cargar_big_data()
rankings = cargar_rankings()

players = sorted(stats.keys())

st.title("🎾 Tennis Predictor PRO")

circ = st.selectbox("Circuito", ["ATP","WTA","CHALLENGER"])
surf = mapear_superficie(st.selectbox("Superficie", ["Hard","Clay","Grass"]))

p1 = st.selectbox("Jugador 1", players)
p2 = st.selectbox("Jugador 2", players, index=1)

if st.button("SIMULAR"):
    pow1 = poder(p1,p2,surf,circ,stats,rankings,h2h)
    pow2 = poder(p2,p1,surf,circ,stats,rankings,h2h)

    p1h,p2h = probs(pow1,pow2,surf,circ)

    wins=0
    sims=10000

    for _ in range(sims):
        s1=s2=0
        while s1<2 and s2<2:
            r1,r2 = sim_set(p1h,p2h)
            if r1>r2: s1+=1
            else: s2+=1
        if s1==2: wins+=1

    prob = wins/sims

    st.metric("Probabilidad P1", f"{prob:.1%}")