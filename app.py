import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import unicodedata

# =========================================================
# MOTOR v6.5 - COLUMNS SHIELD & UNICODE MATCH
# =========================================================
st.set_page_config(page_title="Tennis IA Predictor v6.5", page_icon="🎾", layout="wide")

def limpieza_extrema(texto):
    if pd.isna(texto): return ""
    # Normalizar Unicode (mata espacios raros \xa0)
    t = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode('ascii')
    # Quitar países y dejar solo letras pegadas
    t = re.sub(r'\[.*?\]|\(.*?\)', '', t)
    return re.sub(r'[^A-Z]', '', t.upper())

@st.cache_data
def cargar_todo():
    base_datos = {}
    stats_reales = {}
    
    # 1. CARGAR STATS (atp_completa.xlsx)
    if os.path.exists('atp_completa.xlsx'):
        df_s = pd.read_excel('atp_completa.xlsx')
        # Limpiar nombres de columnas (quitar espacios raros)
        df_s.columns = [limpieza_extrema(c) for c in df_s.columns]
        for _, row in df_s.iterrows():
            nid = limpieza_extrema(row.get('PLAYER'))
            try:
                # Buscamos la columna HLD% (que tras limpieza será HLD)
                val = str(row.get('HLD', '75')).replace('%', '')
                stats_reales[nid] = float(val) / 100.0 if float(val) > 1 else float(val)
            except: pass

    # 2. CARGAR ELOS (atp_elo.xlsx)
    if os.path.exists('atp_elo.xlsx'):
        df = pd.read_excel('atp_elo.xlsx')
        # Limpiar nombres de columnas del ELO
        # 'ATP RANK' se convertirá en 'ATPRANK', 'CELO' en 'CELO', etc.
        df.columns = [limpieza_extrema(c) for c in df.columns]
        
        for _, row in df.iterrows():
            nombre_raw = str(row.get('PLAYER', 'Unknown')).replace('\xa0', ' ').strip()
            nid = limpieza_extrema(nombre_raw)
            hld_final = stats_reales.get(nid, None)
            
            # Extraer valores con los nuevos nombres de columna limpios
            base_datos[f"{nombre_raw} (ATP)"] = {
                "Player": nombre_raw,
                "Rank": row.get('ATPRANK') or row.get('RANK') or 'N/A',
                "Hard": row.get('HELO') or row.get('ELO'),
                "Clay": row.get('CELO') or row.get('ELO'),
                "Grass": row.get('GELO') or row.get('ELO'),
                "General": row.get('ELO'),
                "Hold_Real": hld_final
            }
    return base_datos

def obtener_probabilidades(d1, d2, superficie):
    # Mapeo de superficie a la clave del diccionario
    key = "CLAY" if superficie == "Clay" else ("HELO" if superficie == "Hard" else "GELO")
    e1 = d1.get(superficie) or d1.get("General") or 1500
    e2 = d2.get(superficie) or d2.get("General") or 1500
    
    prob_v1_elo = 1 / (1 + 10 ** ((e2 - e1) / 300)) # Divisor más agresivo para mayor realismo
    
    h1 = d1["Hold_Real"] if d1["Hold_Real"] else (0.76 + (e1 - 1600)/2000)
    h2 = d2["Hold_Real"] if d2["Hold_Real"] else (0.76 + (e2 - 1600)/2000)
    
    if superficie == "Clay": h1 -= 0.06; h2 -= 0.06
    
    p1_p = 0.62 + (h1 - 0.76)
    p2_p = 0.62 + (h2 - 0.76)
    return np.clip(p1_p, 0.50, 0.80), np.clip(p2_p, 0.50, 0.80), prob_v1_elo

def sim_set(p1_p, p2_p):
    g1 = g2 = 0; sacador = 1
    while True:
        prob_game = p1_p + 0.18 if sacador == 1 else (1 - p2_p - 0.18)
        if random.random() < prob_game: g1 += 1
        else: g2 += 1
        if (g1 >= 6 and g1-g2 >= 2) or g1 == 7: return g1, g2
        if (g2 >= 6 and g2-g1 >= 2) or g2 == 7: return g1, g2
        sacador = 3 - sacador

# --- INTERFAZ ---
base_datos = cargar_todo()
with st.sidebar:
    st.header("🏆 IA Tennis v6.5")
    lista = sorted(list(base_datos.keys()))
    superficie = st.selectbox("Superficie", ["Clay", "Hard", "Grass"])
    nivel = st.radio("Formato", ["Tour (3 sets)", "Grand Slam (5 sets)"])

if lista:
    c1, c2 = st.columns(2)
    with c1: j1_n = st.selectbox("Jugador 1", lista)
    with c2: j2_n = st.selectbox("Jugador 2", lista, index=min(1, len(lista)-1))

    if st.button("🚀 ANALIZAR PARTIDO", use_container_width=True):
        d1, d2 = base_datos[j1_n], base_datos[j2_n]
        p1_p, p2_p, p_elo = obtener_probabilidades(d1, d2, superficie)
        
        st.divider()
        st.markdown("### 🔍 Data Verifier (Final Shield)")
        v1, v2 = st.columns(2)
        with v1:
            h_lab = f"✅ {d1['Hold_Real']:.1%}" if d1['Hold_Real'] else "⚠️ Estimado"
            rk_val = str(d1['Rank']).split('.')[0] if d1['Rank'] != 'N/A' else 'N/A'
            st.metric(d1['Player'], f"Rank: {rk_val}")
            st.caption(f"Hold%: {h_lab} | Elo {superficie}: {d1.get(superficie, 1500):.0f}")
        with v2:
            h_lab2 = f"✅ {d2['Hold_Real']:.1%}" if d2['Hold_Real'] else "⚠️ Estimado"
            rk_val2 = str(d2['Rank']).split('.')[0] if d2['Rank'] != 'N/A' else 'N/A'
            st.metric(d2['Player'], f"Rank: {rk_val2}")
            st.caption(f"Hold%: {h_lab2} | Elo {superficie}: {d2.get(superficie, 1500):.0f}")

        # SIMULACIÓN
        res = {"j1_w":0, "j1_s1":0, "j1_any":0, "j2_any":0, "gms":[]}
        sets_target = 3 if "5 sets" in nivel else 2
        for _ in range(10000):
            s1 = s2 = gt = 0
            while s1 < sets_target and s2 < sets_target:
                g1, g2 = sim_set(p1_p, p2_p)
                gt += (g1 + g2)
                if (s1+s2) == 0 and g1 > g2: res["j1_s1"] += 1
                if g1 > g2: s1 += 1
                else: s2 += 1
            if s1 == sets_target: res["j1_w"] += 1
            if s1 >= 1: res["j1_any"] += 1
            if s2 >= 1: res["j2_any"] += 1
            res["gms"].append(gt)

        # RESULTADOS
        st.divider()
        st.markdown("#### 🏆 Victoria")
        m1, m2, m3 = st.columns(3)
        p_final = (res["j1_w"]/10000 * 0.3) + (p_elo * 0.7)
        m1.metric("Win P1", f"{p_final:.1%}")
        m2.metric("Win P2", f"{(1-p_final):.1%}")
        m3.metric("Favorito", d1['Player'] if p_final > 0.5 else d2['Player'])

        st.markdown("#### 📊 Mercados de Probabilidad")
        l1, l2, l3 = st.columns(3)
        l1.metric("Over 21.5", f"{sum(g > 21.5 for g in res['gms'])/10000:.1%}")
        l2.metric("P1 gana 2-0 / 3-0", f"{res['j1_w']/10000:.1%}")
        l3.metric("P2 gana +1 set", f"{res['j2_any']/10000:.1%}")