import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os

st.set_page_config(page_title="Tennis IA Predictor Pro", page_icon="🎾", layout="wide")

ARCHIVO_APUESTAS = "registro_apuestas.csv"

# =========================================================
# APUESTAS
# =========================================================
def guardar_apuesta(jugador1, jugador2, apuesta, prob):
    nuevo = pd.DataFrame([{
        "Jugador1": jugador1,
        "Jugador2": jugador2,
        "Apuesta": apuesta,
        "Probabilidad": prob,
        "Resultado": "Pendiente"
    }])

    if os.path.exists(ARCHIVO_APUESTAS):
        df = pd.read_csv(ARCHIVO_APUESTAS)
        df = pd.concat([df, nuevo], ignore_index=True)
    else:
        df = nuevo

    df.to_csv(ARCHIVO_APUESTAS, index=False)


def cargar_apuestas():
    if os.path.exists(ARCHIVO_APUESTAS):
        return pd.read_csv(ARCHIVO_APUESTAS)
    return pd.DataFrame(columns=["Jugador1","Jugador2","Apuesta","Probabilidad","Resultado"])


def actualizar_resultado(index, resultado):
    df = cargar_apuestas()
    df.loc[index, "Resultado"] = resultado
    df.to_csv(ARCHIVO_APUESTAS, index=False)

# =========================================================
# UTILS
# =========================================================
def normalizar(n):
    if pd.isna(n): return ""
    n = str(n).upper()
    n = re.sub(r'[^A-Z\s]', '', n)
    return " ".join(n.split())


def mapear_superficie(s):
    s = s.upper()
    if any(x in s for x in ["TIERRA","CLAY","ARCILLA"]): return "Clay"
    if any(x in s for x in ["HIERBA","GRASS","CESPED"]): return "Grass"
    return "Hard"

# =========================================================
# RANKING ATP
# =========================================================
def cargar_rankings():
    try:
        df = pd.read_excel("datos/atp.xlsx")
        df.columns = df.columns.str.lower().str.strip()

        col_player = next((c for c in df.columns if c in ["player","name"]), None)
        col_rank = next((c for c in df.columns if "rank" in c), None)

        if not col_player or not col_rank:
            return {}

        df[col_player] = df[col_player].apply(normalizar)
        return dict(zip(df[col_player], df[col_rank]))

    except:
        return {}

# =========================================================
# DATA
# =========================================================
@st.cache_data
def cargar_big_data():
    ruta_base = "datos"
    stats = {}
    h2h = {}

    if not os.path.exists(ruta_base):
        return {}, {}

    for root, _, files in os.walk(ruta_base):
        folder = os.path.basename(root).upper()

        peso = 1
        if "ATP" in folder: peso = 2.5
        elif "WTA" in folder: peso = 2
        elif "CHALLENGER" in folder: peso = 1.5

        for f in files:
            if f.lower() == "atp.xlsx":
                continue

            if not (f.endswith(".csv") or f.endswith(".xlsx")):
                continue

            try:
                path = os.path.join(root, f)

                if f.endswith(".csv"):
                    df = pd.read_csv(path, engine="python", on_bad_lines="skip")
                else:
                    df = pd.read_excel(path)

                df.columns = df.columns.str.lower().str.strip()

                w_col = next((c for c in df.columns if "winner" in c), None)
                l_col = next((c for c in df.columns if "loser" in c), None)
                s_col = next((c for c in df.columns if "surface" in c), None)

                if not w_col or not l_col:
                    continue

                for _, row in df.iterrows():
                    w = normalizar(row[w_col])
                    l = normalizar(row[l_col])
                    surf = mapear_superficie(str(row.get(s_col,"Hard")))

                    for p in [w,l]:
                        if p not in stats:
                            stats[p] = {
                                "power":0,
                                "total":0,
                                "surf":{},
                                "recent":[]
                            }

                    stats[w]["power"] += 3 * peso
                    stats[l]["power"] -= 2 / peso

                    stats[w]["total"] += 1
                    stats[l]["total"] += 1

                    for p in [w,l]:
                        if surf not in stats[p]["surf"]:
                            stats[p]["surf"][surf] = {"wins":0,"total":0}
                        stats[p]["surf"][surf]["total"] += 1

                    stats[w]["surf"][surf]["wins"] += 1

                    stats[w]["recent"].append(1)
                    stats[l]["recent"].append(0)

                    stats[w]["recent"] = stats[w]["recent"][-10:]
                    stats[l]["recent"] = stats[l]["recent"][-10:]

                    key = tuple(sorted([w,l]))
                    if key not in h2h:
                        h2h[key] = {}
                    h2h[key][w] = h2h[key].get(w,0) + 1

            except:
                continue

    return stats, h2h

# =========================================================
# FEATURES
# =========================================================
def forma(nombre, stats):
    r = stats.get(nombre, {}).get("recent", [])
    if not r: return 0
    return (sum(r)/len(r) - 0.5) * 120


def h2h_bonus(j1, j2, h2h):
    key = tuple(sorted([j1,j2]))
    if key not in h2h: return 0

    w1 = h2h[key].get(j1,0)
    w2 = h2h[key].get(j2,0)
    t = w1 + w2
    if t == 0: return 0

    return ((w1/t) - 0.5) * 200


def ranking_bonus(nombre, rankings):
    r = rankings.get(nombre)
    if r is None: return 0
    return (150 - r) * 1.2

# =========================================================
# MOTOR
# =========================================================
def calcular_poder(nombre, rival, superficie, circuito, stats, rankings, h2h):
    s = stats.get(nombre, {"power":0,"total":0,"surf":{}})

    conf = min(1, s["total"]/100)
    power = s["power"] * conf

    surf_stats = s["surf"].get(superficie, {"wins":0,"total":0})
    surf_bonus = 0
    if surf_stats["total"] > 0:
        surf_bonus = ((surf_stats["wins"]/surf_stats["total"]) - 0.5) * 200

    raw = (
        power +
        surf_bonus +
        forma(nombre, stats) +
        h2h_bonus(nombre, rival, h2h) +
        ranking_bonus(nombre, rankings)
    )

    raw *= 0.65

    return 1200 + raw


def calcular_hold(p1, p2, circ):
    base = 0.76 if circ == "ATP" else 0.64
    diff = np.tanh((p1 - p2)/900)

    return (
        np.clip(base + diff*0.30, 0.55, 0.97),
        np.clip(base - diff*0.30, 0.55, 0.97)
    )


def sim_set(p1, p2):
    j1=j2=0
    s = random.choice([1,2])

    while True:
        prob = p1 if s==1 else (1-p2)

        if random.random()<prob: j1+=1
        else: j2+=1

        if (j1>=6 or j2>=6) and abs(j1-j2)>=2:
            return j1,j2

        if j1==7 or j2==7:
            return j1,j2

        s = 3 - s

# =========================================================
# 🆕 VALUE DETECTION +2.5 SETS
# =========================================================
def lectura_sets(prob_sets):
    if prob_sets >= 0.60:
        return "🟢 VALUE (partido muy igualado)"
    elif prob_sets >= 0.45:
        return "🟡 NEUTRAL"
    else:
        return "🔴 NO VALUE (favorito claro)"

# =========================================================
# APP
# =========================================================
stats, h2h = cargar_big_data()
rankings = cargar_rankings()

players = sorted(stats.keys())

st.title("🎾 Tennis IA Predictor PRO")

tab1, tab2 = st.tabs(["Simulador","Historial"])

with tab1:
    circuito = st.selectbox("Circuito", ["ATP","WTA","CHALLENGER"])
    superficie = mapear_superficie(st.selectbox("Superficie", ["Dura","Tierra","Hierba"]))

    sims = st.slider("Simulaciones", 5000, 20000, 10000, step=1000)

    ou = st.number_input("Over/Under", value=22.5)

    j1 = st.selectbox("Jugador 1", players)
    j2 = st.selectbox("Jugador 2", players, index=1)

    st.write("📊 J1:", "OK")
    st.write("📊 J2:", "OK")

    if st.button("🚀 SIMULAR"):

        p1 = calcular_poder(j1,j2,superficie,circuito,stats,rankings,h2h)
        p2 = calcular_poder(j2,j1,superficie,circuito,stats,rankings,h2h)

        h1,h2 = calcular_hold(p1,p2,circuito)

        wins=0
        sets3=0
        totals=[]

        for _ in range(sims):
            s1=s2=0
            g1=g2=0

            while s1<2 and s2<2:
                r1,r2 = sim_set(h1,h2)
                g1+=r1; g2+=r2

                if r1>r2: s1+=1
                else: s2+=1

            if s1==2 and s2==1:
                sets3+=1
            elif s2==2 and s1==1:
                sets3+=1

            totals.append(g1+g2)
            if s1==2: wins+=1

        prob_win = np.clip(wins/sims,0.10,0.90)
        prob_sets = sets3/sims

        st.metric(f"Ganador {j1}", f"{prob_win:.1%}")
        st.metric(f"Ganador {j2}", f"{1-prob_win:.1%}")

        st.metric("Over 19.5", f"{sum(x>ou for x in totals)/sims:.1%}")

        st.metric("Más de 2.5 sets", f"{prob_sets:.1%} — {lectura_sets(prob_sets)}")

with tab2:
    df = cargar_apuestas()
    st.dataframe(df)