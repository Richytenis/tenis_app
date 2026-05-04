import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os

# =========================================================
# CONFIGURACIÓN DE PÁGINA
# =========================================================
st.set_page_config(page_title="Tennis IA Predictor Ultra v3", page_icon="🎾", layout="wide")

def normalizar(n):
    if pd.isna(n): return ""
    n = str(n).replace('\xa0', ' ').replace('\u00a0', ' ').upper()
    n = re.sub(r'[^A-Z\s]', '', n)
    return " ".join(n.split()).strip()

@st.cache_data
def cargar_base_elos():
    elos = {}
    archivos = {"ATP": "datos/atp/atp_elo.xlsx", "WTA": "datos/wta/wta_elo.xlsx"}
    errores = []
    for circuito, ruta in archivos.items():
        if os.path.exists(ruta):
            try:
                df = pd.read_excel(ruta, engine='openpyxl')
                df.columns = [c.replace('\xa0', ' ').strip() for c in df.columns]
                for _, row in df.iterrows():
                    nombre = normalizar(row['Player'])
                    if nombre:
                        elos[nombre] = {
                            "Hard": row.get('hElo'), "Clay": row.get('cElo'),
                            "Grass": row.get('gElo'), "General": row.get('Elo'),
                            "Circuito": circuito
                        }
            except Exception as e: errores.append(f"Error en {circuito}: {e}")
        else: errores.append(f"No existe: {ruta}")
    return elos, errores

# =========================================================
# MOTOR MEJORADO CON CATEGORÍA DE TORNEO
# =========================================================
def obtener_hold_rate(e1, e2, circuito, superficie, nivel_torneo):
    # Base por Circuito
    base = 0.81 if circuito == "ATP" else 0.66
    
    # Ajuste por Superficie
    if superficie == "Clay": base -= 0.08
    elif superficie == "Grass": base += 0.04
    
    # AJUSTE POR NIVEL DE TORNEO (La gran mejora)
    if nivel_torneo == "Challenger / ITF":
        base -= 0.05 # Más breaks en niveles bajos
        divisor = 750 # La diferencia de nivel pesa mucho más
    elif nivel_torneo == "Grand Slam (5 sets)":
        base += 0.02 # Saque más concentrado
        divisor = 950
    else: # ATP / WTA Tour Standard
        divisor = 850
        
    diff = (e1 - e2) / divisor
    p1_hold = np.clip(base + diff, 0.25, 0.96)
    p2_hold = np.clip(base - diff, 0.25, 0.96)
    return p1_hold, p2_hold

def sim_set(p1_h, p2_h):
    g1 = g2 = 0
    sacador = 1
    while True:
        prob = p1_h if sacador == 1 else (1 - p2_h)
        if random.random() < prob: g1 += 1
        else: g2 += 1
        if (g1 >= 6 and g1-g2 >= 2) or g1 == 7: return g1, g2
        if (g2 >= 6 and g2-g1 >= 2) or g2 == 7: return g1, g2
        sacador = 3 - sacador

# =========================================================
# INTERFAZ
# =========================================================
st.title("🎾 Tennis IA Predictor Ultra v3")

base_elos, logs = cargar_base_elos()
lista_jugadores = sorted(list(base_elos.keys()))

if not lista_jugadores:
    st.error("Error cargando base de datos.")
else:
    with st.sidebar:
        st.header("⚙️ Ajustes")
        # NUEVO SELECTOR
        nivel_torneo = st.radio("Nivel del Torneo", ["ATP / WTA Tour", "Challenger / ITF", "Grand Slam (5 sets)"])
        
        superficie_ui = st.selectbox("Superficie", ["Tierra (Clay)", "Dura (Hard)", "Hierba (Grass)"])
        surf_key = "Clay" if "Tierra" in superficie_ui else ("Grass" if "Hierba" in superficie_ui else "Hard")
        
        n_sims = st.select_slider("Simulaciones", options=[5000, 10000, 20000], value=10000)
        linea_ou = st.number_input("Línea O/U Juegos", value=21.5, step=0.5)

    c1, c2 = st.columns(2)
    with c1: j1 = st.selectbox("Jugador 1", lista_jugadores)
    with c2: j2 = st.selectbox("Jugador 2", lista_jugadores, index=min(1, len(lista_jugadores)-1))

    if st.button("🚀 PREDECIR PARTIDO", use_container_width=True):
        # Lógica de simulación
        d1, d2 = base_elos[j1], base_elos[j2]
        # Elo superficie -> Elo General
        e1 = d1.get(surf_key) or d1.get("General") or 1500
        e2 = d2.get(surf_key) or d2.get("General") or 1500
        
        # El circuito se toma del J1 (asumiendo que juegan el mismo)
        circuito = d1["Circuito"]
        h1, h2 = obtener_hold_rate(e1, e2, circuito, surf_key, nivel_torneo)
        
        # Simulación de partidos
        j1_wins = 0; juegos = []; sets3 = 0
        sets_necesarios = 3 if nivel_torneo == "Grand Slam (5 sets)" and circuito == "ATP" else 2
        
        for _ in range(n_sims):
            s1 = s2 = 0; m_games = 0
            while s1 < sets_necesarios and s2 < sets_necesarios:
                g1, g2 = sim_set(h1, h2)
                m_games += (g1 + g2)
                if g1 > g2: s1 += 1
                else: s2 += 1
            if s1 == sets_necesarios: j1_wins += 1
            if (s1 + s2) >= 3: sets3 += 1
            juegos.append(m_games)
            
        # UI DE RESULTADOS
        st.divider()
        res1, res2, res3 = st.columns(3)
        res1.metric(f"Victoria {j1}", f"{j1_wins/n_sims:.1%}")
        res2.metric(f"Victoria {j2}", f"{(n_sims-j1_wins)/n_sims:.1%}")
        p_over = sum(g > linea_ou for g in juegos) / n_sims
        res3.metric(f"Over {linea_ou}", f"{p_over:.1%}")
        
        st.info(f"**Análisis:** Elo {surf_key}: {e1:.0f} vs {e2:.0f} | Promedio Juegos: {sum(juegos)/n_sims:.1f}")