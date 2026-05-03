import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os

# =================================================================
# 0. REGISTRO DE APUESTAS
# =================================================================

ARCHIVO_APUESTAS = "registro_apuestas.csv"

def guardar_apuesta(jugador1, jugador2, apuesta, prob):
    df_nuevo = pd.DataFrame([{
        "Jugador1": jugador1,
        "Jugador2": jugador2,
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
    return pd.DataFrame(columns=["Jugador1", "Jugador2", "Apuesta", "Probabilidad", "Resultado"])


def actualizar_resultado(index, resultado):
    df = cargar_apuestas()
    df.loc[index, "Resultado"] = resultado
    df.to_csv(ARCHIVO_APUESTAS, index=False)

# =================================================================
# 1. CONFIG
# =================================================================

st.set_page_config(page_title="Tennis IA Predictor Pro", page_icon="🎾", layout="wide")

# =================================================================
# 2. FUNCIONES IA (IGUAL)
# =================================================================

def normalizar(n):
    if pd.isna(n): return ""
    n = str(n).upper()
    n = re.sub(r'[^A-Z\s]', '', n)
    return " ".join(n.split())

def mapear_superficie(s):
    s = s.upper()
    if any(x in s for x in ['TIERRA', 'CLAY', 'ARCILLA']): return 'Clay'
    if any(x in s for x in ['HIERBA', 'GRASS', 'CESPED']): return 'Grass'
    return 'Hard'

@st.cache_data
def cargar_big_data():
    ruta_base = 'datos'
    stats_jugador = {} 
    if not os.path.exists(ruta_base): return {}

    for root, _, files in os.walk(ruta_base):
        folder_name = os.path.basename(root).upper()
        peso_nivel = 1.0  
        if 'ATP' in folder_name: peso_nivel = 2.5
        elif 'WTA' in folder_name: peso_nivel = 2.0
        elif 'CHALLENGER' in folder_name: peso_nivel = 1.5

        for f in files:
            if not (f.endswith('.xlsx') or f.endswith('.csv')): continue
            try:
                if f.endswith('.csv'):
                    df = pd.read_csv(os.path.join(root, f), engine='python', on_bad_lines='skip', encoding_errors='ignore')
                else:
                    df = pd.read_excel(os.path.join(root, f))
                
                df.columns = df.columns.str.lower().str.strip()
                w_col = next((c for c in df.columns if c in ['winner', 'winner_name']), None)
                l_col = next((c for c in df.columns if c in ['loser', 'loser_name']), None)
                surf_col = next((c for c in df.columns if 'surface' in c), 'surface')

                if w_col and l_col:
                    for _, row in df.iterrows():
                        w, l = normalizar(row[w_col]), normalizar(row[l_col])
                        surf = mapear_superficie(str(row.get(surf_col, 'Hard')))
                        for p in [w, l]:
                            if p not in stats_jugador: 
                                stats_jugador[p] = {'power_score': 0, 'total': 0, 'surf_stats': {}}
                            stats_jugador[p]['total'] += 1
                            if surf not in stats_jugador[p]['surf_stats']:
                                stats_jugador[p]['surf_stats'][surf] = {'wins': 0, 'total': 0}
                            stats_jugador[p]['surf_stats'][surf]['total'] += 1
                            if p == w: 
                                stats_jugador[p]['power_score'] += (10 * peso_nivel)
                                stats_jugador[p]['surf_stats'][surf]['wins'] += 1
                            else:
                                stats_jugador[p]['power_score'] -= (6 / peso_nivel)
            except: continue
    return stats_jugador

def calcular_poder_real(nombre, superficie, circuito, stats_ia):
    suelo_min = 1750 if circuito in ['ATP', 'WTA'] else 1400
    stats = stats_ia.get(nombre, {'power_score': 0, 'total': 0, 'surf_stats': {}})
    pts_score = stats['power_score']
    s_stats = stats['surf_stats'].get(superficie, {'wins': 0, 'total': 0})
    surf_bonus = 0
    if s_stats['total'] > 0:
        surf_rate = s_stats['wins'] / s_stats['total']
        surf_bonus = (surf_rate - 0.5) * 400
    poder_final = 1200 + pts_score + surf_bonus
    return max(poder_final, suelo_min)

def calcular_probabilidades_saque(pow1, pow2, superficie, circuito):
    if circuito == 'WTA':
        base_h = {'Clay': 0.58, 'Hard': 0.64, 'Grass': 0.70}.get(superficie, 0.62)
        suelo_tenis = 0.45
    else:
        base_h = {'Clay': 0.68, 'Hard': 0.76, 'Grass': 0.82}.get(superficie, 0.74)
        suelo_tenis = 0.55

    raw_diff = (pow1 - pow2)
    diff_log = np.sign(raw_diff) * (np.log1p(abs(raw_diff)) / 25)
    p1_hold = base_h + (diff_log * 0.35)
    p2_hold = base_h - (diff_log * 0.35)
    return np.clip(p1_hold, suelo_tenis, 0.97), np.clip(p2_hold, suelo_tenis, 0.97)

def simular_set(p1_h, p2_h):
    j1, j2 = 0, 0
    servidor = 1 if random.random() > 0.5 else 2
    while True:
        prob = p1_h if servidor == 1 else (1 - p2_h)
        if random.random() < prob: j1 += 1
        else: j2 += 1
        if (j1 >= 6 or j2 >= 6) and abs(j1 - j2) >= 2: return j1, j2
        if j1 == 7 or j2 == 7: return j1, j2
        servidor = 3 - servidor

# =================================================================
# APP
# =================================================================

stats_ia = cargar_big_data()
lista_jugadores = sorted(list(stats_ia.keys()))

st.title("🎾 Tennis IA")

tab1, tab2 = st.tabs(["Simulador", "Historial"])

# ---------------- TAB 1 ----------------
with tab1:

    circ = st.selectbox("Circuito", ["ATP", "WTA", "CHALLENGER"])
    surf_in = st.selectbox("Superficie", ["Dura", "Tierra", "Hierba"])
    sims = st.slider("Simulaciones", 5000, 20000, 10000)

    umbral_ou = st.number_input("Over/Under", value=22.5, step=0.5)
    h_val = st.number_input("Hándicap", value=-2.5, step=0.5)

    p1_in = st.selectbox("Jugador 1", lista_jugadores)
    p2_in = st.selectbox("Jugador 2", lista_jugadores, index=1)

    if st.button("🚀 SIMULAR"):
        superficie = mapear_superficie(surf_in)
        pow1 = calcular_poder_real(p1_in, superficie, circ, stats_ia)
        pow2 = calcular_poder_real(p2_in, superficie, circ, stats_ia)
        p1_h, p2_h = calcular_probabilidades_saque(pow1, pow2, superficie, circ)

        sets_p1 = 0
        j_totales, d_juegos = [], []

        for _ in range(sims):
            s1, s2, jp1, jp2 = 0, 0, 0, 0
            while s1 < 2 and s2 < 2:
                r1, r2 = simular_set(p1_h, p2_h)
                jp1 += r1; jp2 += r2
                if r1 > r2: s1 += 1
                else: s2 += 1
            j_totales.append(jp1 + jp2)
            d_juegos.append(jp1 - jp2)
            if s1 == 2: sets_p1 += 1

        st.session_state["res"] = {
            "p1": p1_in, "p2": p2_in,
            "win": sets_p1 / sims,
            "over": sum(j > umbral_ou for j in j_totales) / sims,
            "hcap": sum(d + h_val > 0 for d in d_juegos) / sims,
            "ou": umbral_ou,
            "h": h_val
        }

    if "res" in st.session_state:
        r = st.session_state["res"]

        st.metric(f"Ganador {r['p1']}", f"{r['win']:.1%}")
        st.metric(f"Over {r['ou']}", f"{r['over']:.1%}")
        st.metric(f"Hcap {r['h']}", f"{r['hcap']:.1%}")

        opcion = st.selectbox("Apuesta", [
            f"Ganador {r['p1']}",
            f"Ganador {r['p2']}",
            f"Over {r['ou']}",
            f"Hándicap {r['h']}"
        ])

        if st.button("Guardar"):
            prob_map = {
                f"Ganador {r['p1']}": r["win"],
                f"Ganador {r['p2']}": 1 - r["win"],
                f"Over {r['ou']}": r["over"],
                f"Hándicap {r['h']}": r["hcap"]
            }

            guardar_apuesta(r["p1"], r["p2"], opcion, prob_map[opcion])
            st.success("Guardado")

# ---------------- TAB 2 ----------------
with tab2:

    df = cargar_apuestas()
    st.dataframe(df)

    for i, row in df.iterrows():
        if row["Resultado"] == "Pendiente":
            if st.button(f"✔️ {i}", key=f"a{i}"):
                actualizar_resultado(i, "Acierto")
                st.rerun()
            if st.button(f"❌ {i}", key=f"f{i}"):
                actualizar_resultado(i, "Fallo")
                st.rerun()

    total = len(df[df["Resultado"] != "Pendiente"])
    aciertos = len(df[df["Resultado"] == "Acierto"])

    if total > 0:
        st.metric("Acierto %", f"{(aciertos/total):.1%}")