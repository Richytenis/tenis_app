import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os

# =========================================================
# CONFIGURACIÓN Y MOTOR (v5.1 - CORREGIDO)
# =========================================================
st.set_page_config(page_title="Tennis IA Predictor v5.1", page_icon="🎾", layout="wide")

def normalizar(n):
    if pd.isna(n): return ""
    n = str(n).replace('\xa0', ' ').upper()
    return " ".join(re.sub(r'[^A-Z\s]', '', n).split()).strip()

@st.cache_data
def cargar_base_elos():
    elos = {}
    archivos = {"ATP": "datos/atp/atp_elo.xlsx", "WTA": "datos/wta/wta_elo.xlsx"}
    for circuito, ruta in archivos.items():
        if os.path.exists(ruta):
            try:
                df = pd.read_excel(ruta, engine='openpyxl')
                for _, row in df.iterrows():
                    nombre = normalizar(row['Player'])
                    if nombre:
                        elos[f"{nombre} ({circuito})"] = {
                            "Player": nombre, "Hard": row.get('hElo'), "Clay": row.get('cElo'),
                            "Grass": row.get('gElo'), "General": row.get('Elo'), "Circuito": circuito
                        }
            except Exception: pass
    return elos

def obtener_hold_rate(e1, e2, circuito_ui, superficie):
    if circuito_ui == "ATP":
        base = 0.73 if superficie == "Clay" else 0.81
        divisor = 850
        min_h = 0.30
    elif circuito_ui == "WTA":
        base = 0.70 if superficie == "Clay" else 0.74
        divisor = 3500 
        min_h = 0.55
    else: # Challenger
        base = 0.73 if superficie == "Clay" else 0.78
        divisor = 4000
        min_h = 0.48
    
    diff = (e1 - e2) / divisor
    return np.clip(base + diff, min_h, 0.95), np.clip(base - diff, min_h, 0.95)

def sim_set(p1_h, p2_h):
    g1 = g2 = 0
    sacador = 1
    while True:
        boost = 0.06 if abs(g1 - g2) >= 2 else 0
        prob = (p1_h + boost) if sacador == 1 else (1 - p2_h - boost)
        if random.random() < prob: g1 += 1
        else: g2 += 1
        if (g1 >= 6 and g1-g2 >= 2) or g1 == 7: return g1, g2
        if (g2 >= 6 and g2-g1 >= 2) or g2 == 7: return g1, g2
        sacador = 3 - sacador

# =========================================================
# INTERFAZ DE USUARIO
# =========================================================
base_elos = cargar_base_elos()

with st.sidebar:
    st.header("⚙️ Ajustes")
    circuito = st.selectbox("Circuito", ["ATP", "WTA", "CHALLENGER"])
    tag = "WTA" if circuito == "WTA" else "ATP"
    jugadores = sorted([k for k, v in base_elos.items() if v["Circuito"] == tag])
    nivel = st.radio("Nivel", ["Tour", "Grand Slam (5 sets)"])
    superficie = st.selectbox("Superficie", ["Clay", "Hard", "Grass"])
    n_sims = 10000

if not jugadores:
    st.error("⚠️ No se encontraron archivos de Excel en /datos/atp o /datos/wta")
else:
    c1, c2 = st.columns(2)
    with c1: j1_n = st.selectbox("Jugador 1", jugadores)
    with c2: j2_n = st.selectbox("Jugador 2", jugadores, index=min(1, len(jugadores)-1))

    if st.button("🚀 CALCULAR PREDICCIÓN", use_container_width=True):
        d1, d2 = base_elos[j1_n], base_elos[j2_n]
        e1 = d1.get(superficie) or d1.get("General") or 1500
        e2 = d2.get(superficie) or d2.get("General") or 1500
        h1, h2 = obtener_hold_rate(e1, e2, circuito, superficie)
        
        results = {"j1_win":0, "j1_set1":0, "j1_any":0, "j2_any":0, "games":[]}
        sets_n = 3 if (nivel == "Grand Slam (5 sets)" and circuito == "ATP") else 2
        
        for _ in range(n_sims):
            s1 = s2 = 0; g_m = 0
            while s1 < sets_n and s2 < sets_n:
                g1, g2 = sim_set(h1, h2)
                g_m += (g1 + g2)
                if (s1+s2) == 0 and g1 > g2: results["j1_set1"] += 1
                if g1 > g2: s1 += 1
                else: s2 += 1
            if s1 == sets_n: results["j1_win"] += 1
            if s1 >= 1: results["j1_any"] += 1
            if s2 >= 1: results["j2_any"] += 1
            results["games"].append(g_m)

        # --- VISUALIZACIÓN EN 3 LÍNEAS ---
        st.divider()
        
        # Línea 1: Victoria
        st.markdown("#### 🏆 Probabilidades de Victoria")
        v1, v2, v3 = st.columns(3)
        p1 = results["j1_win"]/n_sims
        v1.metric(f"Ganador: {d1['Player']}", f"{p1:.1%}")
        v2.metric(f"Ganador: {d2['Player']}", f"{(1-p1):.1%}")
        v3.metric("Favorito", d1['Player'] if p1 > 0.5 else d2['Player'])

        # Línea 2: Over/Under
        st.markdown("#### 📊 Líneas de Juegos")
        o1, o2, o3 = st.columns(3)
        o1.metric("Over 18.5", f"{sum(g > 18.5 for g in results['games'])/n_sims:.1%}")
        o2.metric("Over 19.5", f"{sum(g > 19.5 for g in results['games'])/n_sims:.1%}")
        o3.metric("Promedio Total", f"{sum(results['games'])/n_sims:.1f} j.")

        # Línea 3: Mercados de Sets
        st.markdown("#### 🎾 Mercados de Sets")
        s1, s2, s3 = st.columns(3)
        s1.metric("Gana 1er Set (P1)", f"{results['j1_set1']/n_sims:.1%}")
        s2.metric(f"{d1['Player']} gana +1 set", f"{results['j1_any']/n_sims:.1%}")
        s3.metric(f"{d2['Player']} gana +1 set", f"{results['j2_any']/n_sims:.1%}")

        st.info(f"Análisis basado en Elo {superficie}. Saque estimado: {h1:.1%} vs {h2:.1%}")