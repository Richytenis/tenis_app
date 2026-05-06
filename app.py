import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import unicodedata

# =========================================================
# MOTOR v8.2 - VISUAL PRO & DATA SHIELD
# =========================================================
st.set_page_config(page_title="Tennis IA Predictor v8.2", page_icon="🎾", layout="wide")

def limpieza_extrema(texto):
    if pd.isna(texto): return ""
    t = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode('ascii')
    t = re.sub(r'\[.*?\]|\(.*?\)', '', t)
    return re.sub(r'[^A-Z0-9]', '', t.upper())

@st.cache_data
def cargar_todo():
    base_datos = {}
    stats_detalladas = {}
    
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

    if os.path.exists('atp_elo.xlsx'):
        df_elo = pd.read_excel('atp_elo.xlsx')
        df_elo.columns = [limpieza_extrema(c) for c in df_elo.columns]
        for _, row in df_elo.iterrows():
            nombre_raw = str(row.get('PLAYER', 'Unknown')).replace('\xa0', ' ').strip()
            nid = limpieza_extrema(nombre_raw)
            s = stats_detalladas.get(nid, {})
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
    p1_pts = p2_pts = 0
    adj = r_elo_diff / 5000 
    p_in = s_stats.get("1in", 0.62); p_w1 = np.clip(s_stats.get("1w", 0.70) + adj, 0.4, 0.9); p_w2 = np.clip(s_stats.get("2w", 0.50) + adj, 0.3, 0.75)
    while True:
        if random.random() < p_in:
            if random.random() < p_w1: p1_pts += 1
            else: p2_pts += 1
        else:
            if random.random() < p_w2: p1_pts += 1
            else: p2_pts += 1
        if p1_pts >= 4 and p1_pts - p2_pts >= 2: return 1
        if p2_pts >= 4 and p2_pts - p1_pts >= 2: return 0

def sim_set(elo_diff, stats1, stats2):
    g1 = g2 = 0; sacador = 1 if random.random() > 0.5 else 2
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

# --- UI ---
base_datos = cargar_todo()
with st.sidebar:
    st.header("🎾 Tennis IA v8.2")
    lista = sorted(list(base_datos.keys()))
    superficie = st.selectbox("Superficie", ["Hard", "Clay", "Grass"])
    formato = st.radio("Formato", ["Tour (3 sets)", "Grand Slam (5 sets)"])

if lista:
    c1, c2 = st.columns(2)
    with c1: j1_n = st.selectbox("Jugador 1", lista)
    with c2: j2_n = st.selectbox("Jugador 2", lista, index=min(1, len(lista)-1))

    if st.button("🚀 ANALIZAR PARTIDO", use_container_width=True):
        d1, d2 = base_datos[j1_n], base_datos[j2_n]
        e1 = d1.get(superficie) or d1.get("General") or 1500
        e2 = d2.get(superficie) or d2.get("General") or 1500
        elo_diff = e1 - e2
        prob_elo = 1 / (1 + 10 ** ((e2 - e1) / 400))

        # Simulación
        res = {"j1_w":0, "j1_s1":0, "j1_any":0, "j2_any":0, "over18":0, "over19":0, "gms":[], "set3":0}
        sets_to_win = 3 if "5 sets" in formato else 2
        default_stats = {"hld": 0.75, "1in": 0.62, "1w": 0.70, "2w": 0.50}

        for _ in range(10000):
            s1 = s2 = gt = 0
            c_s1 = d1.get("Stats", default_stats).copy(); c_s2 = d2.get("Stats", default_stats).copy()
            if not c_s1: c_s1 = default_stats.copy()
            if not c_s2: c_s2 = default_stats.copy()
            
            set_n = 0
            while s1 < sets_to_win and s2 < sets_to_win:
                g1, g2 = sim_set(elo_diff, c_s1, c_s2)
                gt += (g1 + g2)
                if set_n == 0 and g1 > g2: res["j1_s1"] += 1
                if g1 >= 6 and g2 <= 2: c_s2["2w"] *= 0.88
                if g2 >= 6 and g1 <= 2: c_s1["2w"] *= 0.88
                if g1 > g2: s1 += 1
                else: s2 += 1
                set_n += 1
            
            if s1 == sets_to_win: res["j1_w"] += 1
            if s1 >= 1: res["j1_any"] += 1
            if s2 >= 1: res["j2_any"] += 1
            if gt > 18.5: res["over18"] += 1
            if gt > 19.5: res["over19"] += 1
            if set_n >= 3: res["set3"] += 1
            res["gms"].append(gt)

        p_final = (res["j1_w"]/10000 * 0.4) + (prob_elo * 0.6)

        # --- DISEÑO DE SALIDA ---
        st.divider()
        st.subheader("🏆 Probabilidad de Victoria")
        l1_1, l1_2 = st.columns(2)
        l1_1.metric(f"Ganador: {d1['Player']}", f"{p_final:.1%}")
        l1_2.metric(f"Ganador: {d2['Player']}", f"{(1-p_final):.1%}")

        st.subheader("🎾 Sets y Rendimiento")
        l2_1, l2_2, l2_3, l2_4 = st.columns(4)
        l2_1.metric("3 Sets?", f"{res['set3']/10000:.1%}")
        l2_2.metric("Gana 1er Set P1", f"{res['j1_s1']/10000:.1%}")
        l2_3.metric("P1 Gana +1 Set", f"{res['j1_any']/10000:.1%}")
        l2_4.metric("P2 Gana +1 Set", f"{res['j2_any']/10000:.1%}")

        st.subheader("📊 Mercados Over / Under")
        l3_1, l3_2, l3_3 = st.columns(3)
        l3_1.metric("Over 18.5 Games", f"{res['over18']/10000:.1%}")
        l3_2.metric("Over 19.5 Games", f"{res['over19']/10000:.1%}")
        l3_3.metric("Promedio Games", f"{np.mean(res['gms']):.1f}")

        # Info de Verificación al final (más discreto)
        with st.expander("Verificar Datos del Servidor"):
            st.write(f"**{d1['Player']}**: Rank {d1['Rank']} | Elo {superficie}: {e1:.1f}")
            st.write(f"**{d2['Player']}**: Rank {d2['Rank']} | Elo {superficie}: {e2:.1f}")