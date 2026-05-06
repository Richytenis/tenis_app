import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import unicodedata
import plotly.express as px

# =========================================================
# MOTOR v8.0 - SURFACE ELO & STATS INTEGRATION
# =========================================================
st.set_page_config(page_title="Tennis IA Predictor v8.0", page_icon="🎾", layout="wide")

def limpieza_extrema(texto):
    if pd.isna(texto): return ""
    # Normalizar Unicode para quitar \xa0 y otros caracteres invisibles
    t = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode('ascii')
    # Quitar países [ITA], (ESP) y dejar solo letras/números
    t = re.sub(r'\[.*?\]|\(.*?\)', '', t)
    return re.sub(r'[^A-Z0-9]', '', t.upper())

@st.cache_data
def cargar_todo():
    base_datos = {}
    stats_detalladas = {}
    
    # 1. CARGAR STATS (atp_completa.xlsx)
    if os.path.exists('atp_completa.xlsx'):
        df_s = pd.read_excel('atp_completa.xlsx')
        for _, row in df_s.iterrows():
            nid = limpieza_extrema(row.get('Player'))
            try:
                stats_detalladas[nid] = {
                    "hld": float(str(row.get('Hld%', '75')).replace('%',''))/100,
                    "1in": float(str(row.get('1stIn', '62')).replace('%',''))/100,
                    "1w": float(str(row.get('1st%', '72')).replace('%',''))/100,
                    "2w": float(str(row.get('2nd%', '50')).replace('%',''))/100
                }
            except: pass

    # 2. CARGAR ELOS POR SUPERFICIE (atp_elo.xlsx)
    if os.path.exists('atp_elo.xlsx'):
        df_elo = pd.read_excel('atp_elo.xlsx')
        # Limpieza de columnas para evitar problemas con \xa0
        df_elo.columns = [limpieza_extrema(c) for c in df_elo.columns]
        
        for _, row in df_elo.iterrows():
            nombre_raw = str(row.get('PLAYER', 'Unknown')).replace('\xa0', ' ').strip()
            nid = limpieza_extrema(nombre_raw)
            
            s = stats_detalladas.get(nid, {})
            # Buscamos columnas según limpieza_extrema (HELO, CELO, GELO)
            base_datos[f"{nombre_raw}"] = {
                "Player": nombre_raw,
                "Rank": row.get('ATPRANK') or 'N/A',
                "Hard": row.get('HELO') or row.get('ELO'),
                "Clay": row.get('CELO') or row.get('ELO'),
                "Grass": row.get('GELO') or row.get('ELO'),
                "General": row.get('ELO'),
                "Stats": s
            }
    return base_datos

def sim_game(s_stats, r_elo_diff):
    p1_pts = 0
    p2_pts = 0
    # Ajuste de punto basado en diferencia de Elo
    adj = r_elo_diff / 4500 
    
    p_in = s_stats.get("1in", 0.62)
    p_w1 = np.clip(s_stats.get("1w", 0.72) + adj, 0.40, 0.90)
    p_w2 = np.clip(s_stats.get("2w", 0.50) + adj, 0.30, 0.75)

    while True:
        if random.random() < p_in:
            if random.random() < p_w1: p1_pts += 1
            else: p2_pts += 1
        else:
            if random.random() < p_w2: p1_pts += 1
            else: p2_pts += 1
        
        if p1_pts >= 4 and p1_pts - p2_pts >= 2: return 1
        if p2_pts >= 4 and p2_pts - p1_pts >= 2: return 0

def sim_set(d1, d2, elo_diff, stats1, stats2):
    g1 = g2 = 0
    sacador = 1 if random.random() > 0.5 else 2
    while True:
        if sacador == 1:
            if sim_game(stats1, elo_diff): g1 += 1
            else: g2 += 1
        else:
            if sim_game(stats2, -elo_diff): g2 += 1
            else: g1 += 1
        sacador = 3 - sacador
        if (g1 >= 6 and g1-g2 >= 2) or g1 == 7: return g1, g2
        if (g2 >= 6 and g2-g1 >= 2) or g2 == 7: return g1, g2

# --- INTERFAZ ---
base_datos = cargar_todo()
with st.sidebar:
    st.header("🎾 IA Tennis v8.0")
    lista = sorted(list(base_datos.keys()))
    superficie = st.selectbox("Superficie del Partido", ["Hard", "Clay", "Grass"])
    nivel = st.radio("Formato de Partido", ["Tour (3 sets)", "Grand Slam (5 sets)"])

if lista:
    c1, c2 = st.columns(2)
    with c1: j1_n = st.selectbox("Jugador 1 (Favorito/Local)", lista)
    with c2: j2_n = st.selectbox("Jugador 2 (Rival)", lista, index=min(1, len(lista)-1))

    if st.button("🚀 ANALIZAR PARTIDO CON ELO ESPECÍFICO", use_container_width=True):
        d1, d2 = base_datos[j1_n], base_datos[j2_n]
        
        # 1. Obtener Elos de la superficie elegida
        e1 = d1.get(superficie) or d1.get("General") or 1500
        e2 = d2.get(superficie) or d2.get("General") or 1500
        elo_diff = e1 - e2
        prob_elo = 1 / (1 + 10 ** ((e2 - e1) / 400))

        # 2. Mostrar Verificación de Datos
        st.markdown(f"### 🔍 Verificador de Datos: {superficie}")
        v1, v2 = st.columns(2)
        with v1:
            st.metric(d1['Player'], f"Rank: {int(d1['Rank']) if d1['Rank'] != 'N/A' else 'N/A'}")
            st.caption(f"Elo {superficie}: **{e1:.1f}** | 1stW: {d1['Stats'].get('1w',0.70):.1%}")
        with v2:
            st.metric(d2['Player'], f"Rank: {int(d2['Rank']) if d2['Rank'] != 'N/A' else 'N/A'}")
            st.caption(f"Elo {superficie}: **{e2:.1f}** | 1stW: {d2['Stats'].get('1w',0.70):.1%}")

        # 3. Simulación Monte Carlo
        res = {"j1_w":0, "j1_s1":0, "j1_any":0, "j2_any":0, "over18":0, "over19":0, "gms":[]}
        sets_target = 3 if "5 sets" in nivel else 2
        
        for _ in range(10000):
            s1 = s2 = gt = 0
            # Copiamos stats para aplicar factor fatiga/desplome por set
            curr_stats1 = d1["Stats"].copy()
            curr_stats2 = d2["Stats"].copy()
            
            set_n = 0
            while s1 < sets_target and s2 < sets_target:
                g1, g2 = sim_set(d1, d2, elo_diff, curr_stats1, curr_stats2)
                gt += (g1 + g2)
                
                if set_n == 0:
                    if g1 > g2: res["j1_s1"] += 1
                
                # Lógica de Desplome: si pierde un set muy fácil (6-0, 6-1, 6-2)
                if g1 >= 6 and g2 <= 2: curr_stats2["2w"] *= 0.85
                if g2 >= 6 and g1 <= 2: curr_stats1["2w"] *= 0.85
                
                if g1 > g2: s1 += 1
                else: s2 += 1
                set_n += 1
            
            if s1 == sets_target: res["j1_w"] += 1
            if s1 >= 1: res["j1_any"] += 1
            if s2 >= 1: res["j2_any"] += 1
            if gt > 18.5: res["over18"] += 1
            if gt > 19.5: res["over19"] += 1
            res["gms"].append(gt)

        # 4. Resultados Finales
        st.divider()
        p_final = (res["j1_w"]/10000 * 0.4) + (prob_elo * 0.6)
        
        c_res1, c_res2, c_res3, c_res4 = st.columns(4)
        c_res1.metric("Win Prob P1", f"{p_final:.1%}")
        c_res2.metric("Gana 1er Set P1", f"{res['j1_s1']/10000:.1%}")
        c_res3.metric("Gana +1 Set P1", f"{res['j1_any']/10000:.1%}")
        c_res4.metric("Gana +1 Set P2", f"{res['j2_any']/10000:.1%}")

        st.markdown("#### 📊 Mercados de Probabilidad")
        o1, o2, o3 = st.columns(3)
        o1.metric("Over 18.5", f"{res['over18']/10000:.1%}")
        o2.metric("Over 19.5", f"{res['over19']/10000:.1%}")
        o3.metric("Promedio Games", f"{np.mean(res['gms']):.1f}")

        # Filtro de alerta para Overs peligrosos
        if (res["j1_any"]/10000 < 0.65 or res["j2_any"]/10000 < 0.65) and (res["over19"]/10000 > 0.70):
            st.warning("⚠️ **ALERTA DE VOLATILIDAD:** La probabilidad de Over es alta, pero un jugador tiene pocas opciones de ganar un set. Riesgo de resultado corto (6-2, 6-1).")

        fig = px.histogram(res["gms"], nbins=15, title="Frecuencia de Juegos Totales", 
                           labels={'value':'Games'}, color_discrete_sequence=['#27ae60'])
        st.plotly_chart(fig, use_container_width=True)