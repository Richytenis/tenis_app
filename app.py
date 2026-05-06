import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os

# =========================================================
# CONFIGURACIÓN Y MOTOR (v6.2 - DEEP MATCH & AGGRESSIVE ELO)
# =========================================================
st.set_page_config(page_title="Tennis IA Predictor v6.2", page_icon="🎾", layout="wide")

def extraer_apellido(texto):
    if pd.isna(texto): return ""
    # Limpieza estándar
    t = str(texto).replace('\xa0', ' ')
    t = re.sub(r'\[.*?\]', '', t).upper().strip()
    partes = t.split()
    return partes[-1] if partes else ""

def normalizar_id(texto):
    if pd.isna(texto): return ""
    t = str(texto).replace('\xa0', ' ')
    t = re.sub(r'\[.*?\]', '', t).upper().strip()
    return re.sub(r'[^A-Z]', '', t) # Solo letras pegadas para match total

@st.cache_data
def cargar_todo():
    base_datos = {}
    stats_reales = {}
    
    # 1. Cargar Stats Reales (atp_completa.xlsx)
    if os.path.exists('atp_completa.xlsx'):
        df_s = pd.read_excel('atp_completa.xlsx')
        df_s.columns = [c.replace('\xa0', ' ').strip().upper() for c in df_s.columns]
        for _, row in df_s.iterrows():
            # Guardamos por ID normalizado (ej: CRISTIANGARIN)
            nid = normalizar_id(row.get('PLAYER'))
            try:
                hld = str(row.get('HLD%', '75%')).replace('%', '')
                stats_reales[nid] = float(hld) / 100.0
            except: pass

    # 2. Cargar Elos y Ranks (atp_elo.xlsx)
    if os.path.exists('atp_elo.xlsx'):
        df = pd.read_excel('atp_elo.xlsx')
        df.columns = [c.replace('\xa0', ' ').strip().upper() for c in df.columns]
        for _, row in df.iterrows():
            nombre_raw = row.get('PLAYER', 'Unknown')
            nid = normalizar_id(nombre_raw)
            
            # Intentamos match por ID exacto, si no, se queda en None
            hld_final = stats_reales.get(nid, None)
            
            base_datos[f"{nombre_raw.strip()} (ATP)"] = {
                "Player": nombre_raw.replace('\xa0', ' ').strip(),
                "Rank": row.get('ATP RANK') or row.get('RANK') or 'N/A',
                "Hard": row.get('HELO'), "Clay": row.get('CELO'),
                "Grass": row.get('GELO'), "General": row.get('ELO'),
                "Hold_Real": hld_final,
                "Circuito": "ATP"
            }
    return base_datos

def obtener_probabilidades(d1, d2, superficie):
    e1 = d1.get(superficie) or d1.get("General") or 1500
    e2 = d2.get(superficie) or d2.get("General") or 1500
    
    # Probabilidad de victoria basada en ELO (Fórmula Logística corregida)
    # Una diferencia de 100 puntos ahora dará aprox un 75-80% de victoria
    prob_v1 = 1 / (1 + 10 ** ((e2 - e1) / 350))
    
    # HOLD RATE: Si no hay real, estimamos basándonos en la calidad
    # Un jugador de 1700 Elo saca mejor que uno de 1400
    h1 = d1["Hold_Real"] if d1["Hold_Real"] else (0.75 + (e1 - 1500)/2000)
    h2 = d2["Hold_Real"] if d2["Hold_Real"] else (0.75 + (e2 - 1500)/2000)
    
    if superficie == "Clay":
        h1 -= 0.07; h2 -= 0.07
    elif superficie == "Grass":
        h1 += 0.04; h2 += 0.04

    # Convertimos Hold% a probabilidad de ganar punto individual al saque
    p1_p = 0.62 + (h1 - 0.75)
    p2_p = 0.62 + (h2 - 0.75)
    
    return np.clip(p1_p, 0.52, 0.78), np.clip(p2_p, 0.52, 0.78), prob_v1

def sim_set(p1_p, p2_p):
    g1 = g2 = 0; sacador = 1
    while True:
        # Simplificación de probabilidad de ganar el juego
        prob_game = p1_p + 0.15 if sacador == 1 else (1 - p2_p - 0.15)
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
    st.header("⚙️ Motor Pro v6.2")
    lista_jugadores = sorted(list(base_datos.keys()))
    superficie = st.selectbox("Superficie", ["Clay", "Hard", "Grass"])
    nivel = st.radio("Nivel", ["Tour (3 sets)", "Grand Slam (5 sets)"])
    n_sims = 10000

if lista_jugadores:
    c1, c2 = st.columns(2)
    with c1: j1_n = st.selectbox("Jugador 1 (Favorito)", lista_jugadores)
    with c2: j2_n = st.selectbox("Jugador 2 (Underdog)", lista_jugadores, index=min(1, len(lista_jugadores)-1))

    if st.button("🚀 ANALIZAR CON DEEP MATCH", use_container_width=True):
        d1, d2 = base_datos[j1_n], base_datos[j2_n]
        p1_p, p2_p, prob_v1_elo = obtener_probabilidades(d1, d2, superficie)
        
        st.divider()
        st.markdown("### 🔍 Data Verifier (Deep Match)")
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            h_txt = f"{d1['Hold_Real']:.1%}" if d1['Hold_Real'] else "Auto-estimado"
            st.metric(d1['Player'], f"Rank: {str(d1['Rank']).split('.')[0]}")
            st.caption(f"Hold% Stats: {h_txt} | Elo: {d1.get(superficie, 1500):.0f}")
        with col_v2:
            h_txt2 = f"{d2['Hold_Real']:.1%}" if d2['Hold_Real'] else "Auto-estimado"
            st.metric(d2['Player'], f"Rank: {str(d2['Rank']).split('.')[0]}")
            st.caption(f"Hold% Stats: {h_txt2} | Elo: {d2.get(superficie, 1500):.0f}")

        # SIMULACIÓN
        res = {"j1_win":0, "j1_s1":0, "j1_any":0, "j2_any":0, "games":[]}
        sets_req = 3 if "5 sets" in nivel else 2
        
        for _ in range(n_sims):
            s1 = s2 = gt = 0
            while s1 < sets_req and s2 < sets_req:
                g1, g2 = sim_set(p1_p, p2_p)
                gt += (g1 + g2)
                if (s1+s2) == 0 and g1 > g2: res["j1_s1"] += 1
                if g1 > g2: s1 += 1
                else: s2 += 1
            if s1 == sets_req: res["j1_win"] += 1
            if s1 >= 1: res["j1_any"] += 1
            if s2 >= 1: res["j2_any"] += 1
            res["games"].append(gt)

        # MOSTRAR RESULTADOS
        st.divider()
        st.markdown("#### 🏆 Victoria")
        m1, m2, m3 = st.columns(3)
        # Mezclamos la simulación con el Elo directo para mayor estabilidad
        p_final = (res["j1_win"]/n_sims * 0.7) + (prob_v1_elo * 0.3)
        m1.metric("Win P1", f"{p_final:.1%}")
        m2.metric("Win P2", f"{(1-p_final):.1%}")
        m3.metric("Favorito", d1['Player'] if p_final > 0.5 else d2['Player'])

        st.markdown("#### 📊 Líneas de Juegos")
        l1, l2, l3 = st.columns(3)
        l1.metric("Over 18.5", f"{sum(g > 18.5 for g in res['games'])/n_sims:.1%}")
        l2.metric("Over 21.5", f"{sum(g > 21.5 for g in res['games'])/n_sims:.1%}")
        l3.metric("Promedio Juegos", f"{np.mean(res['games']):.1f}")

        st.markdown("#### 🎾 Mercados de Sets")
        s1, s2, s3 = st.columns(3)
        s1.metric("Gana 1er Set P1", f"{res['j1_s1']/n_sims:.1%}")
        s2.metric("P1 gana +1 set", f"{res['j1_any']/n_sims:.1%}")
        s3.metric("P2 gana +1 set", f"{res['j2_any']/n_sims:.1%}")