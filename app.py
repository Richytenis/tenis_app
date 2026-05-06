import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import unicodedata
import plotly.express as px

# =========================================================
# MOTOR v7.0 - POINT-BY-POINT MONTE CARLO
# =========================================================
st.set_page_config(page_title="Tennis IA Predictor v7.0", page_icon="🎾", layout="wide")

def limpieza_extrema(texto):
    if pd.isna(texto): return ""
    t = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode('ascii')
    t = re.sub(r'\[.*?\]|\(.*?\)', '', t)
    return re.sub(r'[^A-Z0-9]', '', t.upper())

@st.cache_data
def cargar_todo():
    base_datos = {}
    stats_detalladas = {}
    
    # 1. CARGAR STATS DETALLADAS (atp_completa.xlsx)
    if os.path.exists('atp_completa.xlsx'):
        df_s = pd.read_excel('atp_completa.xlsx')
        # No limpiamos nombres de columnas aquí para mapear exacto lo que vimos en el log
        for _, row in df_s.iterrows():
            nombre_raw = str(row.get('Player', ''))
            nid = limpieza_extrema(nombre_raw)
            try:
                # Extraemos métricas del archivo
                stats_detalladas[nid] = {
                    "hld": float(str(row.get('Hld%', '75')).replace('%', '')) / 100,
                    "first_in": float(str(row.get('1stIn', '62')).replace('%', '')) / 100,
                    "first_w": float(str(row.get('1st%', '72')).replace('%', '')) / 100,
                    "second_w": float(str(row.get('2nd%', '50')).replace('%', '')) / 100,
                    "rank": row.get('Rk', 'N/A')
                }
            except: pass

    # 2. CARGAR ELOS (atp_elo.xlsx)
    if os.path.exists('atp_elo.xlsx'):
        df_elo = pd.read_excel('atp_elo.xlsx')
        df_elo.columns = [limpieza_extrema(c) for c in df_elo.columns]
        
        for _, row in df_elo.iterrows():
            nombre_raw = str(row.get('PLAYER', 'Unknown')).replace('\xa0', ' ').strip()
            nid = limpieza_extrema(nombre_raw)
            
            # Unimos los datos de ambos archivos
            s = stats_detalladas.get(nid, {})
            
            base_datos[f"{nombre_raw}"] = {
                "Player": nombre_raw,
                "Rank": s.get("rank") or row.get('ATPRANK') or 'N/A',
                "Hard": row.get('HELO') or row.get('ELO'),
                "Clay": row.get('CELO') or row.get('ELO'),
                "Grass": row.get('GELO') or row.get('ELO'),
                "General": row.get('ELO'),
                "Stats": s
            }
    return base_datos

def sim_game(s_stats, r_elo_diff):
    """Simula un juego punto a punto"""
    p1_pts = 0
    p2_pts = 0
    # Ajuste leve por diferencia de Elo en el éxito del punto
    adj = r_elo_diff / 5000 
    
    p_in = s_stats.get("first_in", 0.62)
    p_w1 = np.clip(s_stats.get("first_w", 0.72) + adj, 0.4, 0.9)
    p_w2 = np.clip(s_stats.get("second_w", 0.50) + adj, 0.3, 0.7)

    while True:
        # Lógica de punto
        if random.random() < p_in:
            if random.random() < p_w1: p1_pts += 1
            else: p2_pts += 1
        else:
            if random.random() < p_w2: p1_pts += 1
            else: p2_pts += 1
        
        if p1_pts >= 4 and p1_pts - p2_pts >= 2: return 1
        if p2_pts >= 4 and p2_pts - p1_pts >= 2: return 0

def sim_set(d1, d2, elo_diff):
    g1 = g2 = 0
    sacador = 1 if random.random() > 0.5 else 2
    while True:
        if sacador == 1:
            res = sim_game(d1["Stats"], elo_diff)
            if res == 1: g1 += 1
            else: g2 += 1
        else:
            res = sim_game(d2["Stats"], -elo_diff)
            if res == 1: g2 += 1
            else: g1 += 1
        
        sacador = 3 - sacador
        if (g1 >= 6 and g1-g2 >= 2) or g1 == 7: return g1, g2
        if (g2 >= 6 and g2-g1 >= 2) or g2 == 7: return g1, g2

# --- INTERFAZ ---
base_datos = cargar_todo()
with st.sidebar:
    st.header("🎾 Tennis IA v7.0")
    lista = sorted(list(base_datos.keys()))
    superficie = st.selectbox("Superficie", ["Clay", "Hard", "Grass"])
    nivel = st.radio("Formato", ["Tour (3 sets)", "Grand Slam (5 sets)"])

if lista:
    c1, c2 = st.columns(2)
    with c1: j1_n = st.selectbox("Jugador 1", lista)
    with c2: j2_n = st.selectbox("Jugador 2", lista, index=min(1, len(lista)-1))

    if st.button("🚀 INICIAR SIMULACIÓN PROFESIONAL", use_container_width=True):
        d1, d2 = base_datos[j1_n], base_datos[j2_n]
        
        # Diferencia de Elo para el ajuste de puntos
        e1 = d1.get(superficie) or d1.get("General") or 1500
        e2 = d2.get(superficie) or d2.get("General") or 1500
        elo_diff = e1 - e2
        prob_elo = 1 / (1 + 10 ** ((e2 - e1) / 400))

        # SIMULACIÓN MONTE CARLO
        iteraciones = 10000
        res = {"j1_w":0, "j1_s1":0, "j1_any":0, "j2_any":0, "over18":0, "over19":0, "gms":[]}
        sets_target = 3 if "5 sets" in nivel else 2
        
        for _ in range(iteraciones):
            s1 = s2 = gt = 0
            while s1 < sets_target and s2 < sets_target:
                g1, g2 = sim_set(d1, d2, elo_diff)
                gt += (g1 + g2)
                if (s1+s2) == 0 and g1 > g2: res["j1_s1"] += 1
                if g1 > g2: s1 += 1
                else: s2 += 1
            
            if s1 == sets_target: res["j1_w"] += 1
            if s1 >= 1: res["j1_any"] += 1
            if s2 >= 1: res["j2_any"] += 1
            if gt > 18.5: res["over18"] += 1
            if gt > 19.5: res["over19"] += 1
            res["gms"].append(gt)

        # MOSTRAR RESULTADOS
        st.divider()
        p_final = (res["j1_w"]/iteraciones * 0.4) + (prob_elo * 0.6)
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Win P1 (Final)", f"{p_final:.1%}")
        m2.metric("1er Set P1", f"{res['j1_s1']/iteraciones:.1%}")
        m3.metric("Gana +1 Set P1", f"{res['j1_any']/iteraciones:.1%}")
        m4.metric("Gana +1 Set P2", f"{res['j2_any']/iteraciones:.1%}")

        st.markdown("#### 📊 Mercados de Games (Over/Under)")
        o1, o2, o3 = st.columns(3)
        o1.metric("Over 18.5", f"{res['over18']/iteraciones:.1%}")
        o2.metric("Over 19.5", f"{res['over19']/iteraciones:.1%}")
        o3.metric("Promedio Games", f"{np.mean(res['gms']):.1f}")

        # Gráfico de distribución
        fig = px.histogram(res["gms"], nbins=20, title="Distribución de Games Totales", 
                           labels={'value':'Games'}, color_discrete_sequence=['#3498db'])
        st.plotly_chart(fig, use_container_width=True)