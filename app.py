import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os

# =========================================================
# CONFIGURACIÓN Y CARGA DE DATOS
# =========================================================
st.set_page_config(page_title="Tennis IA Predictor Ultra", page_icon="🎾", layout="wide")

def normalizar(n):
    if pd.isna(n): return ""
    n = str(n).upper().replace(' ', ' ') # Limpia espacios especiales de Excel
    n = re.sub(r'[^A-Z\s]', '', n)
    return " ".join(n.split())

def mapear_superficie(s):
    s = s.upper()
    if any(x in s for x in ["TIERRA", "CLAY", "ARCILLA"]): return "Clay"
    if any(x in s for x in ["HIERBA", "GRASS", "CESPED"]): return "Grass"
    return "Hard"

@st.cache_data
def cargar_base_elos():
    """Carga y unifica los Elos específicos por superficie"""
    elos = {}
    archivos = {"ATP": "atp_elo.xlsx", "WTA": "wta_elo.xlsx"}
    
    for circuito, ruta in archivos.items():
        if os.path.exists(ruta):
            df = pd.read_excel(ruta)
            df.columns = df.columns.str.strip()
            for _, row in df.iterrows():
                nombre = normalizar(row['Player'])
                elos[nombre] = {
                    "Hard": row.get('hElo'),
                    "Clay": row.get('cElo'),
                    "Grass": row.get('gElo'),
                    "General": row.get('Elo'),
                    "Circuito": circuito
                }
    return elos

# =========================================================
# MOTOR DE PROBABILIDAD (ELO-BASED)
# =========================================================
def calcular_probabilidad_base(j1, j2, superficie, elos):
    """Calcula la prob. de victoria usando la fórmula oficial ELO"""
    d1 = elos.get(j1, {"General": 1500})
    d2 = elos.get(j2, {"General": 1500})
    
    # Prioridad: ELO Superficie -> ELO General -> 1500
    e1 = d1.get(superficie) or d1.get("General") or 1500
    e2 = d2.get(superficie) or d2.get("General") or 1500
    
    # Fórmula ELO
    prob_j1 = 1 / (1 + 10**((e2 - e1) / 400))
    return prob_j1, e1, e2

def obtener_hold_rate(e1, e2, circuito, superficie):
    """Ajusta la capacidad de mantener el saque según ELO y superficie"""
    # En arcilla y WTA hay más quiebres
    base = 0.80 if circuito == "ATP" else 0.65
    if superficie == "Clay": base -= 0.08
    
    diff = (e1 - e2) / 1000
    p1_hold = np.clip(base + diff, 0.40, 0.92)
    p2_hold = np.clip(base - diff, 0.40, 0.92)
    return p1_hold, p2_hold

# =========================================================
# SIMULACIÓN MONTE CARLO
# =========================================================
def sim_juego_alternado(p1_hold, p2_hold):
    g1 = g2 = 0
    sacador = 1
    while True:
        prob = p1_hold if sacador == 1 else (1 - p2_hold)
        if random.random() < prob: g1 += 1
        else: g2 += 1
        
        if (g1 >= 6 and g1-g2 >= 2) or g1 == 7: return g1, g2
        if (g2 >= 6 and g2-g1 >= 2) or g2 == 7: return g1, g2
        sacador = 3 - sacador

# =========================================================
# INTERFAZ
# =========================================================
elos = cargar_base_elos()
jugadores_disponibles = sorted(elos.keys())

st.title("🎾 Tennis IA Predictor Ultra (Elo Surface System)")

col1, col2 = st.columns(2)
with col1:
    superficie = st.selectbox("Superficie del encuentro", ["Dura", "Tierra", "Hierba"])
    surf_key = mapear_superficie(superficie)
    j1 = st.selectbox("Jugador 1", jugadores_disponibles)
    j2 = st.selectbox("Jugador 2", jugadores_disponibles, index=1)

with col2:
    sims = st.slider("Precisión (Simulaciones)", 5000, 20000, 10000)
    ou_line = st.number_input("Línea Over/Under Juegos", value=21.5)

if st.button("🚀 LANZAR PREDICCIÓN PROFESIONAL"):
    prob_base, elo1, elo2 = calcular_probabilidad_base(j1, j2, surf_key, elos)
    circ = elos[j1]["Circuito"]
    h1, h2 = obtener_hold_rate(elo1, elo2, circ, surf_key)
    
    wins = 0
    total_games = []
    sets_count = []
    
    for _ in range(sims):
        s1 = s2 = 0
        games = 0
        while s1 < 2 and s2 < 2:
            r1, r2 = sim_juego_alternado(h1, h2)
            games += (r1 + r2)
            if r1 > r2: s1 += 1
            else: s2 += 1
        
        if s1 == 2: wins += 1
        total_games.append(games)
        sets_count.append(s1 + s2)

    # Resultados
    p_win = wins / sims
    st.divider()
    c_res1, c_res2, c_res3 = st.columns(3)
    
    with c_res1:
        st.metric(f"Prob. {j1}", f"{p_win:.1%}")
        st.caption(f"Elo {surf_key}: {elo1:.0f}")
        
    with c_res2:
        st.metric(f"Prob. {j2}", f"{1-p_win:.1%}")
        st.caption(f"Elo {surf_key}: {elo2:.0f}")

    with c_res3:
        prob_over = sum(g > ou_line for g in total_games) / sims
        st.metric(f"Over {ou_line}", f"{prob_over:.1%}")
        st.progress(prob_over)

    st.info(f"Probabilidad de 3 sets: {sum(s == 3 for s in sets_count)/sims:.1%}")