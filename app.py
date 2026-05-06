import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import unicodedata

# =========================================================
# MOTOR v8.3 - TOTAL DATA INTEGRATION (Aces, Age, Peak)
# =========================================================
st.set_page_config(page_title="Tennis IA Predictor v8.3", page_icon="🎾", layout="wide")

def limpieza_extrema(texto):
    if pd.isna(texto): return ""
    t = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode('ascii')
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
                    "ace": float(str(row.get('Ace%', '5')).replace('%',''))/100,
                    "df": float(str(row.get('DF%', '3')).replace('%',''))/100,
                    "1in": float(str(row.get('1stIn', '62')).replace('%',''))/100,
                    "1w": float(str(row.get('1st%', '72')).replace('%',''))/100,
                    "2w": float(str(row.get('2nd%', '50')).replace('%',''))/100
                }
            except: pass

    # 2. CARGAR ELOS Y EDAD (atp_elo.xlsx)
    if os.path.exists('atp_elo.xlsx'):
        df_elo = pd.read_excel('atp_elo.xlsx')
        # Limpiar nombres de columnas (quita \xa0)
        df_elo.columns = [limpieza_extrema(c) for c in df_elo.columns]
        
        for _, row in df_elo.iterrows():
            nombre_raw = str(row.get('PLAYER', 'Unknown')).replace('\xa0', ' ').strip()
            nid = limpieza_extrema(nombre_raw)
            s = stats_detalladas.get(nid, {})
            
            base_datos[f"{nombre_raw}"] = {
                "Player": nombre_raw,
                "Age": row.get('AGE', 25),
                "Peak": row.get('PEAKELO', 1500),
                "Rank": row.get('ATPRANK') or 'N/A',
                "Hard": row.get('HELO') or row.get('ELO'),
                "Clay": row.get('CELO') or row.get('ELO'),
                "Grass": row.get('GELO') or row.get('ELO'),
                "General": row.get('ELO', 1500),
                "Stats": s
            }
    return base_datos

def sim_game(s_data, r_data, elo_diff, surface):
    p1_pts = p2_pts = 0
    s_stats = s_data['Stats']
    
    # Ajuste de jerarquía (Elo)
    elo_adj = elo_diff / 5000 
    
    while True:
        # --- Lógica de Punto ---
        # 1. Ace o Doble Falta (Resolución inmediata)
        if random.random() < s_stats.get('ace', 0.05):
            p1_pts += 1
        elif random.random() < s_stats.get('df', 0.03):
            p2_pts += 1
        else:
            # 2. Intercambio (Saque In/Out)
            is_clutch = (p1_pts >= 3 or p2_pts >= 3) and abs(p1_pts - p2_pts) <= 1
            clutch_adj = 0.02 if (elo_diff > 0 and is_clutch) else 0
            
            p_in = s_stats.get("1in", 0.62)
            p_w1 = np.clip(s_stats.get("1w", 0.70) + elo_adj + clutch_adj, 0.4, 0.9)
            p_w2 = np.clip(s_stats.get("2w", 0.50) + elo_adj, 0.3, 0.75)

            if random.random() < p_in:
                if random.random() < p_w1: p1_pts += 1
                else: p2_pts += 1
            else:
                if random.random() < p_w2: p1_pts += 1
                else: p2_pts += 1
        
        if p1_pts >= 4 and p1_pts - p2_pts >= 2: return 1
        if p2_pts >= 4 and p2_pts - p1_pts >= 2: return 0

def sim_set(d1, d2, elo_diff, surface):
    g1 = g2 = 0; sacador = 1 if random.random() > 0.5 else 2
    while True:
        if sacador == 1:
            if sim_game(d1, d2, elo_diff, surface): g1 += 1
            else: g2 += 1
        else:
            if sim_game(d2, d1, -elo_diff, surface): g2 += 1
            else: g1 += 1
        sacador = 3 - sacador
        if (g1 >= 6 and g1-g2 >= 2) or g1 == 7: return g1, g2
        if (g2 >= 6 and g2-g1 >= 2) or g2 == 7: return g1, g2

# --- UI ---
base_datos = cargar_todo()
with st.sidebar:
    st.header("🎾 Tennis IA v8.3")
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
        
        for _ in range(10000):
            s1 = s2 = gt = 0
            # Copias locales para decaimiento por edad/cansancio
            stats_p1 = d1.copy(); stats_p2 = d2.copy()
            
            set_n = 0
            while s1 < sets_to_win and s2 < sets_to_win:
                # Decaimiento por cansancio (más severo si > 30 años)
                fatiga = 1.0 - (gt * 0.001) if d1['Age'] < 30 else 1.0 - (gt * 0.002)
                
                g1, g2 = sim_set(stats_p1, stats_p2, elo_diff, superficie)
                gt += (g1 + g2)
                if set_n == 0 and g1 > g2: res["j1_s1"] += 1
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

        p_final = (res["j1_w"]/10000 * 0.3) + (prob_elo * 0.7)

        # --- SALIDA VISUAL v8.3 ---
        st.divider()
        st.subheader("🏆 Probabilidad de Victoria")
        l1_1, l1_2 = st.columns(2)
        l1_1.metric(f"Ganador: {d1['Player']}", f"{p_final:.1%}")
        l1_2.metric(f"Ganador: {d2['Player']}", f"{(1-p_final):.1%}")

        st.subheader("🎾 Sets y Rendimiento")
        l2_1, l2_2, l2_3, l2_4 = st.columns(4)
        l2_1.metric("Irán a 3 sets?", f"{res['set3']/10000:.1%}")
        l2_2.metric("Gana 1er Set P1", f"{res['j1_s1']/10000:.1%}")
        l2_3.metric("P1 Gana +1 Set", f"{res['j1_any']/10000:.1%}")
        l2_4.metric("P2 Gana +1 Set", f"{res['j2_any']/10000:.1%}")

        st.subheader("📊 Mercados Over / Under")
        l3_1, l3_2, l3_3 = st.columns(3)
        l3_1.metric("Over 18.5 Games", f"{res['over18']/10000:.1%}")
        l3_2.metric("Over 19.5 Games", f"{res['over19']/10000:.1%}")
        l3_3.metric("Promedio Games", f"{np.mean(res['gms']):.1f}")