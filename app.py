import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os

# =========================================================
# CONFIGURACIÓN DE PÁGINA
# =========================================================
st.set_page_config(page_title="Tennis IA Predictor Ultra v4.4", page_icon="🎾", layout="wide")

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
# MOTOR DE CÁLCULO VERSIÓN 4.4 (ANTI-INFLACIÓN)
# =========================================================
def obtener_hold_rate(e1, e2, circuito_ui, superficie, nivel_torneo):
    # --- LÓGICA ATP (TUYA - TOTALMENTE INTACTA) ---
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

    # --- LÓGICA WTA (ESCALA PROTEGIDA) ---
    elif circuito_ui == "WTA":
        base = 0.72
        if superficie == "Clay": base -= 0.05
        divisor = 2200 
        min_h = 0.42 

    # --- LÓGICA CHALLENGER (ELIMINANDO EL ERROR BARRENA/HOLMGREN) ---
    else: 
        # Bajamos la base ligeramente para permitir sets que terminen 6-2 o 6-3
        base = 0.76 
        if superficie == "Clay": base -= 0.04
        
        avg_elo = (e1 + e2) / 2
        # DIVISOR MASIVO para Elos bajos: 4500 hace que 38 puntos sea casi 50/50
        if avg_elo < 1600:
            divisor = 4500 
        else:
            divisor = 2500
        
        min_h = 0.45 

    diff = (e1 - e2) / divisor
    p1_hold = np.clip(base + diff, min_h, 0.96)
    p2_hold = np.clip(base - diff, min_h, 0.96)
    return p1_hold, p2_hold

def sim_set(p1_h, p2_h):
    g1 = g2 = 0
    sacador = 1
    while True:
        prob = p1_h if sacador == 1 else (1 - p2_h)
        if random.random() < prob: g1 += 1
        else: g2 += 1
        # Set normal
        if (g1 >= 6 and g1-g2 >= 2) or g1 == 7: return g1, g2
        if (g2 >= 6 and g2-g1 >= 2) or g2 == 7: return g1, g2
        sacador = 3 - sacador

# =========================================================
# INTERFAZ
# =========================================================
st.title("🎾 Tennis IA Predictor Ultra v4.4")

base_elos = cargar_base_elos()

with st.sidebar:
    st.header("⚙️ Ajustes")
    circuito_seleccionado = st.selectbox("Circuito", ["ATP", "WTA", "CHALLENGER"])
    
    tag = "WTA" if circuito_seleccionado == "WTA" else "ATP"
    jugadores_filtrados = [k for k, v in base_elos.items() if v["Circuito"] == tag]
    
    st.divider()
    nivel_torneo = st.radio("Nivel", ["ATP / WTA Tour", "Challenger / ITF", "Grand Slam (5 sets)"])
    superficie_ui = st.selectbox("Superficie", ["Tierra (Clay)", "Dura (Hard)", "Hierba (Grass)"])
    surf_key = "Clay" if "Tierra" in superficie_ui else ("Grass" if "Hierba" in superficie_ui else "Hard")
    n_sims = st.select_slider("Sims", options=[5000, 10000, 20000], value=10000)
    linea_ou = st.number_input("Línea O/U", value=21.5, step=0.5)

if not jugadores_filtrados:
    st.error("Error al cargar jugadores.")
else:
    c1, c2 = st.columns(2)
    with c1: j1_k = st.selectbox("Jugador 1", jugadores_filtrados)
    with c2: j2_k = st.selectbox("Jugador 2", jugadores_filtrados, index=min(1, len(jugadores_filtrados)-1))

    if st.button("🚀 PREDECIR PARTIDO", use_container_width=True):
        d1, d2 = base_elos[j1_k], base_elos[j2_k]
        e1 = d1.get(surf_key) or d1.get("General") or 1500
        e2 = d2.get(surf_key) or d2.get("General") or 1500
        
        h1, h2 = obtener_hold_rate(e1, e2, circuito_seleccionado, surf_key, nivel_torneo)
        
        j1_wins = 0; juegos = []
        sets_n = 3 if (nivel_torneo == "Grand Slam (5 sets)" and circuito_seleccionado == "ATP") else 2
        
        for _ in range(n_sims):
            s1 = s2 = 0; m_g = 0
            while s1 < sets_n and s2 < sets_n:
                g1, g2 = sim_set(h1, h2)
                m_g += (g1 + g2)
                if g1 > g2: s1 += 1
                else: s2 += 1
            if s1 == sets_n: j1_wins += 1
            juegos.append(m_g)
            
        st.divider()
        res1, res2, res3 = st.columns(3)
        p1 = j1_wins / n_sims
        res1.metric(f"Victoria {d1['Player']}", f"{p1:.1%}")
        res2.metric(f"Victoria {d2['Player']}", f"{(1-p1):.1%}")
        res3.metric(f"Over {linea_ou}", f"{sum(g > linea_ou for g in juegos)/n_sims:.1%}")
        
        st.info(f"**Análisis:** Elo: {e1:.0f} vs {e2:.0f} | Promedio Juegos: {sum(juegos)/n_sims:.1f} | Saque: {h1:.1%} / {h2:.1%}")