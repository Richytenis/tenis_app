import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os

# =========================================================
# CONFIGURACIÓN Y MOTOR (v6.1 - SETS RESTORED & NAME MATCH)
# =========================================================
st.set_page_config(page_title="Tennis IA Predictor v6.1", page_icon="🎾", layout="wide")

def normalizar_texto(texto):
    if pd.isna(texto): return ""
    texto = str(texto).replace('\xa0', ' ')
    # ELIMINAR PAÍS: Borra "[CHI]", "[ESP]", etc. para que coincidan los nombres
    texto = re.sub(r'\[.*?\]', '', texto) 
    texto = " ".join(texto.split()).upper()
    return re.sub(r'[^A-Z\s]', '', texto).strip()

@st.cache_data
def cargar_todo():
    base_datos = {}
    
    # 1. Cargar Estadísticas Reales (atp_completa.xlsx)
    stats_reales = {}
    if os.path.exists('atp_completa.xlsx'):
        df_s = pd.read_excel('atp_completa.xlsx')
        df_s.columns = [c.replace('\xa0', ' ').strip().upper() for c in df_s.columns]
        for _, row in df_s.iterrows():
            name_id = normalizar_texto(row.get('PLAYER'))
            try:
                hld = str(row.get('HLD%', '75%')).replace('%', '')
                stats_reales[name_id] = float(hld) / 100.0
            except: stats_reales[name_id] = 0.75

    # 2. Cargar Elos y Ranks (atp_elo.xlsx)
    if os.path.exists('atp_elo.xlsx'):
        df = pd.read_excel('atp_elo.xlsx')
        df.columns = [c.replace('\xa0', ' ').strip().upper() for c in df.columns]
        for _, row in df.iterrows():
            nombre_raw = row.get('PLAYER')
            nombre_id = normalizar_texto(nombre_raw)
            if nombre_id:
                # Ahora el match será exitoso aunque uno diga [CHI] y el otro no
                hld_real = stats_reales.get(nombre_id, None)
                
                base_datos[f"{nombre_id} (ATP)"] = {
                    "Player": nombre_raw.replace('\xa0', ' '),
                    "Rank": row.get('ATP RANK') or row.get('RANK') or 'N/A',
                    "Hard": row.get('HELO'), "Clay": row.get('CELO'),
                    "Grass": row.get('GELO'), "General": row.get('ELO'),
                    "Hold_Real": hld_real,
                    "Circuito": "ATP"
                }
    return base_datos

def obtener_probabilidades(d1, d2, superficie):
    e1 = d1.get(superficie) or d1.get("General") or 1500
    e2 = d2.get(superficie) or d2.get("General") or 1500
    
    # HOLD RATE: Stat Real > Estimación Elo
    h1 = d1["Hold_Real"] if d1["Hold_Real"] else (0.78 + (e1-e2)/2500)
    h2 = d2["Hold_Real"] if d2["Hold_Real"] else (0.78 + (e2-e1)/2500)
    
    if superficie == "Clay":
        h1 -= 0.06; h2 -= 0.06
    elif superficie == "Grass":
        h1 += 0.04; h2 += 0.04

    # Conversión a probabilidad de punto individual
    p1_p = 0.63 + (h1 - 0.78)
    p2_p = 0.63 + (h2 - 0.78)
    
    return np.clip(p1_p, 0.55, 0.75), np.clip(p2_p, 0.55, 0.75)

def sim_set(p1_p, p2_p):
    g1 = g2 = 0; sacador = 1
    while True:
        prob_game = p1_p if sacador == 1 else (1 - p2_p)
        if random.random() < prob_game: g1 += 1
        else: g2 += 1
        if (g1 >= 6 and g1-g2 >= 2) or g1 == 7: return g1, g2
        if (g2 >= 6 and g2-g1 >= 2) or g2 == 7: return g1, g2
        sacador = 3 - sacador

# =========================================================
# INTERFAZ
# =========================================================
base_datos = cargar_todo()

with st.sidebar:
    st.header("⚙️ Configuración")
    jugadores = sorted(list(base_datos.keys()))
    superficie = st.selectbox("Superficie", ["Clay", "Hard", "Grass"])
    nivel = st.radio("Nivel", ["Tour (3 sets)", "Grand Slam (5 sets)"])
    n_sims = 10000

if jugadores:
    c1, c2 = st.columns(2)
    with c1: j1_n = st.selectbox("Jugador 1", jugadores)
    with c2: j2_n = st.selectbox("Jugador 2", jugadores, index=min(1, len(jugadores)-1))

    if st.button("🚀 ANALIZAR PARTIDO", use_container_width=True):
        d1, d2 = base_datos[j1_n], base_datos[j2_n]
        p1_p, p2_p = obtener_probabilidades(d1, d2, superficie)
        
        # --- BLOQUE DE DATOS ---
        st.divider()
        st.markdown("### 🔍 Data Verifier (Hybrid)")
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            h_val = f"{d1['Hold_Real']:.1%}" if d1['Hold_Real'] else "Basado en Elo"
            st.metric(d1['Player'], f"Rank: {str(d1['Rank']).split('.')[0]}")
            st.caption(f"Hold% Temporada: {h_val} | Elo {superficie}: {d1.get(superficie, d1['General']):.0f}")
        with col_v2:
            h_val2 = f"{d2['Hold_Real']:.1%}" if d2['Hold_Real'] else "Basado en Elo"
            st.metric(d2['Player'], f"Rank: {str(d2['Rank']).split('.')[0]}")
            st.caption(f"Hold% Temporada: {h_val2} | Elo {superficie}: {d2.get(superficie, d2['General']):.0f}")

        # SIMULACIÓN
        results = {"j1_win":0, "j1_set1":0, "j1_any":0, "j2_any":0, "games":[]}
        sets_target = 3 if "5 sets" in nivel else 2
        
        for _ in range(n_sims):
            s1 = s2 = g_total = 0
            while s1 < sets_target and s2 < sets_target:
                g1, g2 = sim_set(p1_p, p2_p)
                g_total += (g1 + g2)
                if (s1+s2) == 0 and g1 > g2: results["j1_set1"] += 1
                if g1 > g2: s1 += 1
                else: s2 += 1
            if s1 == sets_target: results["j1_win"] += 1
            if s1 >= 1: results["j1_any"] += 1
            if s2 >= 1: results["j2_any"] += 1
            results["games"].append(g_total)

        # --- RESULTADOS (RECUPERADOS) ---
        st.divider()
        st.markdown("#### 🏆 Probabilidades de Victoria")
        v1, v2, v3 = st.columns(3)
        p1 = results["j1_win"]/n_sims
        v1.metric("Win P1", f"{p1:.1%}")
        v2.metric("Win P2", f"{(1-p1):.1%}")
        v3.metric("Favorito IA", d1['Player'] if p1 > 0.5 else d2['Player'])

        st.markdown("#### 📊 Líneas de Juegos")
        o1, o2, o3 = st.columns(3)
        o1.metric("Over 18.5", f"{sum(g > 18.5 for g in results['games'])/n_sims:.1%}")
        o2.metric("Over 19.5", f"{sum(g > 19.5 for g in results['games'])/n_sims:.1%}")
        o3.metric("Promedio Juegos", f"{sum(results['games'])/n_sims:.1f}")

        st.markdown("#### 🎾 Mercados de Sets")
        s1, s2, s3 = st.columns(3)
        s1.metric("Gana 1er Set P1", f"{results['j1_set1']/n_sims:.1%}")
        s2.metric("P1 gana +1 set", f"{results['j1_any']/n_sims:.1%}")
        s3.metric("P2 gana +1 set", f"{results['j2_any']/n_sims:.1%}")