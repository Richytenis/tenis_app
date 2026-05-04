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
# CARGA DATA
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

            # ignorar ranking
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
# DIAGNOSTICO
# =========================================================
def diagnostico(nombre, superficie, stats):
    s = stats.get(nombre)

    if not s:
        return "❌ Sin datos"

    total = s["total"]
    surf = s["surf"].get(superficie, {"total":0})["total"]

    if total < 20:
        return f"⚠️ Muy pocos datos ({total})"
    if surf < 5:
        return f"⚠️ Pocos datos en {superficie} ({surf})"

    return f"✅ OK ({total} partidos, {surf} en {superficie})"

# =========================================================
# FEATURES (AJUSTADAS)
# =========================================================
def forma(nombre, stats):
    r = stats.get(nombre, {}).get("recent", [])
    if not r: return 0
    return (sum(r)/len(r) - 0.5) * 120   # 🔽 reducido


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
    return (150 - r) * 1.2   # 🔽 reducido

# =========================================================
# MOTOR
# =========================================================
def calcular_poder(nombre, rival, superficie, circuito, stats, rankings, h2h):
    s = stats.get(nombre, {"power":0,"total":0,"surf":{}})

    confianza = min(1, s["total"]/100)
    power = s["power"] * confianza

    surf_stats = s["surf"].get(superficie, {"wins":0,"total":0})
    surf_bonus = 0
    if surf_stats["total"] > 0:
        surf_bonus = ((surf_stats["wins"]/surf_stats["total"]) - 0.5) * 200

    return (
        1200
        + power
        + surf_bonus
        + forma(nombre, stats)
        + h2h_bonus(nombre, rival, h2h)
        + ranking_bonus(nombre, rankings)
    )


def calcular_hold(pow1, pow2, circuito):
    base = 0.76 if circuito == "ATP" else 0.64

    # 🔥 aplanado
    diff = np.tanh((pow1 - pow2)/700)

    p1 = np.clip(base + diff*0.30, 0.55, 0.97)
    p2 = np.clip(base - diff*0.30, 0.55, 0.97)

    return p1, p2


def simular_set(p1_hold, p2_hold):
    j1=j2=0
    server = random.choice([1,2])

    while True:
        prob = p1_hold if server==1 else (1-p2_hold)

        if random.random()<prob: j1+=1
        else: j2+=1

        if (j1>=6 or j2>=6) and abs(j1-j2)>=2:
            return j1,j2

        if j1==7 or j2==7:
            return j1,j2

        server = 3 - server

# =========================================================
# APP
# =========================================================
stats, h2h = cargar_big_data()
rankings = cargar_rankings()

jugadores = sorted(stats.keys())

st.title("🎾 Tennis IA Predictor PRO")

tab1, tab2 = st.tabs(["Simulador","Historial"])

with tab1:
    circuito = st.selectbox("Circuito", ["ATP","WTA","CHALLENGER"])
    superficie = mapear_superficie(st.selectbox("Superficie", ["Dura","Tierra","Hierba"]))

    sims = st.slider("Simulaciones", 5000, 20000, 10000, step=1000)

    ou_line = st.number_input("Over/Under", value=22.5, step=0.5)
    hcap = st.number_input("Hándicap", value=-2.5, step=0.5)

    j1 = st.selectbox("Jugador 1", jugadores)
    j2 = st.selectbox("Jugador 2", jugadores, index=1)

    st.write("📊 J1:", diagnostico(j1, superficie, stats))
    st.write("📊 J2:", diagnostico(j2, superficie, stats))

    if st.button("🚀 SIMULAR"):
        pow1 = calcular_poder(j1,j2,superficie,circuito,stats,rankings,h2h)
        pow2 = calcular_poder(j2,j1,superficie,circuito,stats,rankings,h2h)

        p1h,p2h = calcular_hold(pow1,pow2,circuito)

        wins1=0
        totals=[]
        diffs=[]

        for _ in range(sims):
            s1=s2=0
            g1=g2=0

            while s1<2 and s2<2:
                r1,r2 = simular_set(p1h,p2h)
                g1+=r1; g2+=r2

                if r1>r2: s1+=1
                else: s2+=1

            if s1==2: wins1+=1

            totals.append(g1+g2)
            diffs.append(g1-g2)

        res_win = wins1/sims

        # 🔥 freno anti-extremos
        res_win = np.clip(res_win, 0.05, 0.95)

        res_over = sum(x>ou_line for x in totals)/sims
        res_hcap = sum(x+hcap>0 for x in diffs)/sims

        st.metric(f"Ganador {j1}", f"{res_win:.1%}")
        st.metric(f"Ganador {j2}", f"{1-res_win:.1%}")
        st.metric(f"Over {ou_line}", f"{res_over:.1%}")
        st.metric(f"Hándicap {hcap}", f"{res_hcap:.1%}")

with tab2:
    df = cargar_apuestas()
    st.dataframe(df)

    for i,row in df.iterrows():
        if row["Resultado"]=="Pendiente":
            c1,c2 = st.columns(2)

            with c1:
                if st.button(f"✔️ {i}", key=f"a{i}"):
                    actualizar_resultado(i,"Acierto")
                    st.rerun()

            with c2:
                if st.button(f"❌ {i}", key=f"f{i}"):
                    actualizar_resultado(i,"Fallo")
                    st.rerun()

    total = len(df[df["Resultado"]!="Pendiente"])
    aciertos = len(df[df["Resultado"]=="Acierto"])

    if total>0:
        st.metric("Acierto %", f"{aciertos/total:.1%}")