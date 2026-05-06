import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import unicodedata

# =========================================================
# CONFIGURACIÓN Y MOTOR (v6.4 - UNICODE CLEANER & PRO ELO)
# =========================================================
st.set_page_config(page_title="Tennis IA Predictor v6.4", page_icon="🎾", layout="wide")

def limpieza_total(texto):
    if pd.isna(texto): return ""
    # 1. Normalizar Unicode (elimina espacios raros \xa0 y tildes)
    t = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode('ascii')
    # 2. Quitar países entre corchetes o paréntesis
    t = re.sub(r'\[.*?\]|\(.*?\)', '', t)
    # 3. Solo letras de la A a la Z, sin espacios
    t = re.sub(r'[^A-Z]', '', t.upper())
    return t

@st.cache_data
def cargar_todo():
    base_datos = {}
    stats_reales = {}
    
    # Cargar Stats (atp_completa.xlsx)
    if os.path.exists('atp_completa.xlsx'):
        df_s = pd.read_excel('atp_completa.xlsx')
        df_s.columns = [c.strip().upper() for c in df_s.columns]
        for _, row in df_s.iterrows():
            nid = limpieza_total(row.get('PLAYER'))
            try:
                # Extraer HLD% manejando posibles formatos
                val = str(row.get('HLD%', '75')).replace('%', '')
                stats_reales[nid] = float(val) / 100.0 if float(val) > 1 else float(val)
            except: pass

    # Cargar Elos (atp_elo.xlsx)
    if os.path.exists('atp_elo.xlsx'):
        df = pd.read_excel('atp_elo.xlsx')
        df.columns = [c.strip().upper() for c in df.columns]
        for _, row in df.iterrows():
            nombre_raw = str(row.get('PLAYER', 'Unknown')).strip()
            nid = limpieza_total(nombre_raw)
            hld_final = stats_reales.get(nid, None)
            
            base_datos[f"{nombre_raw} (ATP)"] = {
                "Player": nombre_raw,
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
    
    # Victoria por ELO (Fórmula optimizada para ATP Tour)
    prob_v1_elo = 1 / (1 + 10 ** ((e2 - e1) / 320)) 
    
    # Hold Rate (Saque)
    h1 = d1["Hold_Real"] if d1["Hold_Real"] else (0.76 + (e1 - 1600)/2200)
    h2 = d2["Hold_Real"] if d2["Hold_Real"] else (0.76 + (e2 - 1600)/2200)
    
    if superficie == "Clay": h1 -= 0.07; h2 -= 0.07
    
    p1_p = 0.62 + (h1 - 0.76)
    p2_p = 0.62 + (h2 - 0.76)
    return np.clip(p1_p, 0.50, 0.80), np.clip(p2_p, 0.50, 0.80), prob_v1_elo

def sim_set(p1_p, p2_p):
    g1 = g2 = 0; sacador = 1
    while True:
        prob_game = p1_p + 0.17 if sacador == 1 else (1 - p2_p - 0.17)
        if random.random() < prob_game: g1 += 1
        else: g2 += 1
        if (g1 >= 6 and g1-g2 >= 2) or g1 == 7: return g1, g2
        if (g2 >= 6 and g2-g1 >= 2) or g2 == 7: return g1, g2
        sacador = 3 - sacador

# --- INTERFAZ ---
base_datos = cargar_todo()
with st.sidebar:
    st.header("⚙️ Motor v6.4 Final")
    lista = sorted(list(base_datos.keys()))
    superficie = st.selectbox("Superficie", ["Clay", "Hard", "Grass"])
    nivel = st.radio("Formato", ["Tour (3 sets)", "Grand Slam (5 sets)"])

if lista:
    c1, c2 = st.columns(2)
    with c1: j1_n = st.selectbox("Jugador 1", lista)
    with c2: j2_n = st.selectbox("Jugador 2", lista, index=min(1, len(lista)-1))

    if st.button("🚀 REALIZAR PRONÓSTICO PROFESIONAL", use_container_width=True):
        d1, d2 = base_datos[j1_n], base_datos[j2_n]
        p1_p, p2_p, p_elo = obtener_probabilidades(d1, d2, superficie)
        
        # --- VERIFICADOR ---
        st.divider()
        st.markdown("### 🔍 Data Verifier (Unicode Shield)")
        v1, v2 = st.columns(2)
        with v1:
            h_lab = f"✅ {d1['Hold_Real']:.1%}" if d1['Hold_Real'] else "⚠️ Auto-estimado"
            st.metric(d1['Player'], f"Rk: {str(d1['Rank']).split('.')[0]}")
            st.caption(f"Hold%: {h_lab} | Elo: {d1.get(superficie, 1500):.0f}")
        with v2:
            h_lab2 = f"✅ {d2['Hold_Real']:.1%}" if d2['Hold_Real'] else "⚠️ Auto-estimado"
            st.metric(d2['Player'], f"Rk: {str(d2['Rank']).split('.')[0]}")
            st.caption(f"Hold%: {h_lab2} | Elo: {d2.get(superficie, 1500):.0f}")

        # SIMULACIÓN (10k iteraciones)
        res = {"j1_w":0, "j1_s1":0, "j1_any":0, "j2_any":0, "gms":[]}
        sets_req = 3 if "5 sets" in nivel else 2
        for _ in range(10000):
            s1 = s2 = gt = 0
            while s1 < sets_req and s2 < sets_req:
                g1, g2 = sim_set(p1_p, p2_p)
                gt += (g1 + g2)
                if (s1+s2) == 0 and g1 > g2: res["j1_s1"] += 1
                if g1 > g2: s1 += 1
                else: s2 += 1
            if s1 == sets_req: res["j1_w"] += 1
            if s1 >= 1: res["j1_any"] += 1
            if s2 >= 1: res["j2_any"] += 1
            res["gms"].append(gt)

        # RESULTADOS
        st.divider()
        st.markdown("#### 🏆 Victoria")
        m1, m2, m3 = st.columns(3)
        p_final = (res["j1_w"]/10000 * 0.4) + (p_elo * 0.6) # Mayor peso al Elo para victoria
        m1.metric("Win P1", f"{p_final:.1%}")
        m2.metric("Win P2", f"{(1-p_final):.1%}")
        m3.metric("Favorito", d1['Player'] if p_final > 0.5 else d2['Player'])

        st.markdown("#### 📊 Mercados")
        l1, l2, l3 = st.columns(3)
        l1.metric("Over 21.5", f"{sum(g > 21.5 for g in res['gms'])/10000:.1%}")
        l2.metric("1er Set P1", f"{res['j1_s1']/10000:.1%}")
        l3.metric("P2 gana +1 set", f"{res['j2_any']/10000:.1%}")