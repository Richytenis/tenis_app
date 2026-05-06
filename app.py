import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os

# =========================================================
# CONFIGURACIÓN DE PÁGINA
# =========================================================
st.set_page_config(page_title="Tennis IA Predictor Ultra v4.7", page_icon="🎾", layout="wide")

def normalizar(n):
    if pd.isna(n): return ""
    n = str(n).replace('\xa0', ' ').replace('\u00a0', ' ').upper()
    n = re.sub(r'[^A-Z\s]', '', n)
    return " ".join(n.split()).strip()

@st.cache_data
def cargar_base_elos():
    elos = {}
    archivos = {"ATP": "datos/atp/atp_elo.xlsx", "WTA": "datos/wta/wta_elo.xlsx"}
    for circuito, ruta in archivos.items():
        if os.path.exists(ruta):
            try:
                df = pd.read_excel(ruta, engine='openpyxl')
                df.columns = [c.replace('\xa0', ' ').strip() for c in df.columns]
                for _, row in df.iterrows():
                    nombre = normalizar(row['Player'])
                    if nombre:
                        key = f"{nombre} ({circuito})"
                        elos[key] = {
                            "Player": nombre,
                            "Hard": row.get('hElo'), "Clay": row.get('cElo'),
                            "Grass": row.get('gElo'), "General": row.get('Elo'),
                            "Circuito": circuito
                        }
            except Exception: pass
    return elos

# =========================================================
# MOTOR DE CÁLCULO VERSIÓN 4.7 (EQUILIBRIO TOTAL)
# =========================================================
def obtener_hold_rate(e1, e2, circuito_ui, superficie, nivel_torneo):
    # --- LÓGICA ATP (ESTÁNDAR) ---
    if circuito_ui == "ATP":
        base = 0.81
        if superficie == "Clay": base -= 0.08
        elif superficie == "Grass": base += 0.04
        
        if nivel_torneo == "Challenger / ITF":
            base -= 0.05
            divisor = 750
        elif nivel_torneo == "Grand Slam (5 sets)":
            base += 0.02
            divisor = 950
        else:
            divisor = 850
        min_h = 0.25

    # --- LÓGICA WTA (DIVISOR AMPLIADO PARA EVITAR FALSOS FAVORITOS) ---
    elif circuito_ui == "WTA":
        base = 0.72
        if superficie == "Clay": base -= 0.05
        # Divisor a 2800: Las diferencias de Elo pesan menos, reconociendo la igualdad del circuito
        divisor = 2800 
        min_h = 0.48 # Subimos el suelo de saque para evitar "lluvia de breaks" irreal

    # --- LÓGICA CHALLENGER ---
    else: 
        base = 0.76 
        if superficie == "Clay": base -= 0.04
        avg_elo = (e1 + e2) / 2
        divisor = 4500 if avg_elo < 1600 else 2500
        min_h = 0.45 

    diff = (e1 - e2) / divisor
    p1_hold = np.clip(base + diff, min_h, 0.96)
    p2_hold = np.clip(base - diff, min_h, 0.96)
    return p1_hold, p2_hold

# =========================================================
# SIMULADOR CON BOOST DE 5% (MÁXIMO REALISMO EN MARCADOR)
# =========================================================
def sim_set(p1_h, p2_h):
    g1 = g2 = 0
    sacador = 1
    while True:
        # Boost del 5%: Si alguien rompe y se pone 4-2, es mucho más probable que cierre 6-3/6-2
        boost_p1 = 0.05 if (g1 - g2 >= 2) else 0
        boost_p2 = 0.05 if (g2 - g1 >= 2) else 0
        
        prob = (p1_h + boost_p1) if sacador == 1 else (1 - p2_h - boost_p2)
        
        if random.random() < prob: g1 += 1
        else: g2 += 1
        
        if (g1 >= 6 and g1-g2 >= 2) or g1 == 7: return g1, g2
        if (g2 >= 6 and g2-g1 >= 2) or g2 == 7: return g1, g2
        sacador = 3 - sacador

# =========================================================
# INTERFAZ
# =========================================================
st.title("🎾 Tennis IA Predictor Ultra v4.7")

base_elos = cargar_base_elos()

with st.sidebar:
    st.header("⚙️ Configuración")
    circuito_seleccionado = st.selectbox("Circuito", ["ATP", "WTA", "CHALLENGER"])
    tag = "WTA" if circuito_seleccionado == "WTA" else "ATP"
    jugadores_filtrados = sorted([k for k, v in base_elos.items() if v["Circuito"] == tag])
    st.divider()
    nivel_torneo = st.radio("Nivel", ["ATP / WTA Tour", "Challenger / ITF", "Grand Slam (5 sets)"])
    superficie_ui = st.selectbox("Superficie", ["Tierra (Clay)", "Dura (Hard)", "Hierba (Grass)"])
    surf_key = "Clay" if "Tierra" in superficie_ui else ("Grass" if "Hierba" in superficie_ui else "Hard")
    n_sims = st.select_slider("Simulaciones", options=[5000, 10000, 20000], value=10000)
    linea_ou = st.number_input("Línea O/U", value=21.5, step=0.5)

if not jugadores_filtrados:
    st.error("Error de carga.")
else:
    c1, c2 = st.columns(2)
    with c1: j1_name = st.selectbox("Jugador 1", jugadores_filtrados)
    with c2: j2_name = st.selectbox("Jugador 2", jugadores_filtrados, index=min(1, len(jugadores_filtrados)-1))

    if st.button("🚀 ANALIZAR PARTIDO", use_container_width=True):
        d1, d2 = base_elos[j1_name], base_elos[j2_name]
        e1 = d1.get(surf_key) or d1.get("General") or 1500
        e2 = d2.get(surf_key) or d2.get("General") or 1500
        h1, h2 = obtener_hold_rate(e1, e2, circuito_seleccionado, surf_key, nivel_torneo)
        
        j1_wins = 0; juegos = []
        sets_a_ganar = 3 if (nivel_torneo == "Grand Slam (5 sets)" and circuito_seleccionado == "ATP") else 2
        
        for _ in range(n_sims):
            s1 = s2 = 0; g_m = 0
            while s1 < sets_a_ganar and s2 < sets_a_ganar:
                g1, g2 = sim_set(h1, h2)
                g_m += (g1 + g2)
                if g1 > g2: s1 += 1
                else: s2 += 1
            if s1 == sets_a_ganar: j1_wins += 1
            juegos.append(g_m)
            
        st.divider()
        m1, m2, m3 = st.columns(3)
        p1 = j1_wins / n_sims
        m1.metric(f"V. {d1['Player']}", f"{p1:.1%}")
        m2.metric(f"V. {d2['Player']}", f"{(1-p1):.1%}")
        m3.metric(f"Over {linea_ou}", f"{sum(g > linea_ou for g in juegos)/n_sims:.1%}")
        st.info(f"**Análisis:** Elo: {e1:.0f} vs {e2:.0f} | Promedio Juegos: {sum(juegos)/n_sims:.1f} | Saque: {h1:.1%} / {h2:.1%}")