import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os

# =========================================================
# CONFIGURACIÓN DE PÁGINA
# =========================================================
st.set_page_config(page_title="Tennis IA Predictor Ultra v4.9", page_icon="🎾", layout="wide")

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
# MOTOR DE CÁLCULO VERSIÓN 4.9 (SET BETTING LOGIC)
# =========================================================
def obtener_hold_rate(e1, e2, circuito_ui, superficie, nivel_torneo):
    if circuito_ui == "ATP":
        base = 0.81
        if superficie == "Clay": base -= 0.08
        elif superficie == "Grass": base += 0.04
        divisor = 950 if "Grand Slam" in nivel_torneo else 850
        min_h = 0.25
    elif circuito_ui == "WTA":
        base = 0.74
        if superficie == "Clay": base -= 0.04
        divisor = 3500 
        min_h = 0.55 
    else: 
        base = 0.78 
        if superficie == "Clay": base -= 0.05
        divisor = 4000
        min_h = 0.48 

    diff = (e1 - e2) / divisor
    p1_hold = np.clip(base + diff, min_h, 0.95)
    p2_hold = np.clip(base - diff, min_h, 0.95)
    return p1_hold, p2_hold

def sim_set(p1_h, p2_h):
    g1 = g2 = 0
    sacador = 1
    while True:
        boost_p1 = 0.06 if (g1 - g2 >= 2) else 0
        boost_p2 = 0.06 if (g2 - g1 >= 2) else 0
        prob = (p1_h + boost_p1) if sacador == 1 else (1 - p2_h - boost_p2)
        if random.random() < prob: g1 += 1
        else: g2 += 1
        if (g1 >= 6 and g1-g2 >= 2) or g1 == 7: return g1, g2
        if (g2 >= 6 and g2-g1 >= 2) or g2 == 7: return g1, g2
        sacador = 3 - sacador

# =========================================================
# INTERFAZ
# =========================================================
st.title("🎾 Tennis IA Predictor Ultra v4.9")

base_elos = cargar_base_elos()

with st.sidebar:
    st.header("⚙️ Ajustes")
    circuito_seleccionado = st.selectbox("Circuito", ["ATP", "WTA", "CHALLENGER"])
    tag = "WTA" if circuito_seleccionado == "WTA" else "ATP"
    jugadores_filtrados = sorted([k for k, v in base_elos.items() if v["Circuito"] == tag])
    st.divider()
    nivel_torneo = st.radio("Nivel", ["ATP / WTA Tour", "Challenger / ITF", "Grand Slam (5 sets)"])
    superficie_ui = st.selectbox("Superficie", ["Tierra (Clay)", "Dura (Hard)", "Hierba (Grass)"])
    surf_key = "Clay" if "Tierra" in superficie_ui else ("Grass" if "Hierba" in superficie_ui else "Hard")
    n_sims = st.select_slider("Sims", options=[5000, 10000, 20000], value=10000)
    linea_ou = st.number_input("Línea O/U", value=21.5, step=0.5)

if not jugadores_filtrados:
    st.error("Error al cargar base de datos.")
else:
    c1, c2 = st.columns(2)
    with c1: j1_n = st.selectbox("Jugador 1 (Arriba)", jugadores_filtrados)
    with c2: j2_n = st.selectbox("Jugador 2 (Abajo)", jugadores_filtrados, index=min(1, len(jugadores_filtrados)-1))

    if st.button("🚀 ANALIZAR PARTIDO COMPLETO", use_container_width=True):
        d1, d2 = base_elos[j1_n], base_elos[j2_n]
        e1, e2 = d1.get(surf_key, 1500), d2.get(surf_key, 1500)
        h1, h2 = obtener_hold_rate(e1, e2, circuito_seleccionado, surf_key, nivel_torneo)
        
        # Contadores para Sets
        j1_wins = 0; j1_set1_wins = 0; j1_any_set = 0
        j2_wins = 0; j2_set1_wins = 0; j2_any_set = 0
        juegos_lista = []
        
        sets_necesarios = 3 if (nivel_torneo == "Grand Slam (5 sets)" and circuito_seleccionado == "ATP") else 2
        
        for _ in range(n_sims):
            s1 = s2 = 0; g_match = 0
            while s1 < sets_necesarios and s2 < sets_necesarios:
                g1, g2 = sim_set(h1, h2)
                g_match += (g1 + g2)
                if (s1 + s2) == 0: # Es el primer set
                    if g1 > g2: j1_set1_wins += 1
                    else: j2_set1_wins += 1
                
                if g1 > g2: s1 += 1
                else: s2 += 1
            
            # Estadísticas finales de la simulación
            if s1 == sets_necesarios: j1_wins += 1
            if s1 >= 1: j1_any_set += 1
            if s2 >= 1: j2_any_set += 1
            juegos_lista.append(g_match)
            
        # UI DE RESULTADOS
        st.divider()
        st.subheader("🏆 Probabilidades de Victoria")
        m1, m2, m3 = st.columns(3)
        p1 = j1_wins / n_sims
        m1.metric(f"Ganador: {d1['Player']}", f"{p1:.1%}")
        m2.metric(f"Ganador: {d2['Player']}", f"{(1-p1):.1%}")
        m3.metric(f"Over {linea_ou} Juegos", f"{sum(g > linea_ou for g in juegos_lista)/n_sims:.1%}")
        
        st.divider()
        st.subheader("🎾 Mercados de Sets")
        s1, s2, s3 = st.columns(3)
        s1.metric("Gana 1er Set (P1)", f"{j1_set1_wins/n_sims:.1%}")
        s2.metric(f"{d1['Player']} gana +1 Set", f"{j1_any_set/n_sims:.1%}")
        s3.metric(f"{d2['Player']} gana +1 Set", f"{j2_any_set/n_sims:.1%}")
        
        st.info(f"**Análisis de Saque:** {d1['Player']} ({h1:.1%}) vs {d2['Player']} ({h2:.1%}) | Promedio Juegos: {sum(juegos_lista)/n_sims:.1f}")