import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import unicodedata

# =========================================================
# MOTOR v8.6 - THE SURFACE TRAP (Anti-Parity Bias)
# =========================================================
st.set_page_config(page_title="Tennis IA Predictor v8.6", page_icon="🎾", layout="wide")

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
                    "ace": float(str(row.get('Ace%', '5')).replace('%',''))/100,
                    "df": float(str(row.get('DF%', '3')).replace('%',''))/100,
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
            # Guardamos todos los Elos para detectar disparidad
            elos = [row.get('HELO', 1500), row.get('CELO', 1500), row.get('GELO', 1500)]
            max_elo = max([e for e in elos if e is not None] or [1500])
            
            base_datos[f"{nombre_raw}"] = {
                "Player": nombre_raw,
                "Age": row.get('AGE', 25),
                "Rank": row.get('ATPRANK') or 'N/A',
                "Hard": row.get('HELO') or row.get('ELO'),
                "Clay": row.get('CELO') or row.get('ELO'),
                "Grass": row.get('GELO') or row.get('ELO'),
                "General": row.get('ELO', 1500),
                "MaxElo": max_elo,
                "Stats": s
            }
    return base_datos

def sim_game(s_data, r_data, elo_diff, surface, momentum=1.0):
    p1_pts = p2_pts = 0
    s_stats = s_data.get('Stats', {})
    
    # Reducción de ventaja de saque en Clay
    ace_mod = 0.65 if surface == "Clay" else 1.2 if surface == "Grass" else 1.0
    # Elo adj más agresivo para evitar sets infinitos
    elo_adj = (elo_diff / 4200) * momentum
    
    while True:
        p_ace = s_stats.get('ace', 0.06) * ace_mod
        if random.random() < p_ace: p1_pts += 1
        elif random.random() < s_stats.get('df', 0.03): p2_pts += 1
        else:
            is_bp = (p2_pts >= 3 and p2_pts > p1_pts)
            # Clutch factor v8.6: Más peso a la jerarquía
            clutch = 0.05 if (elo_diff > 50 and is_bp) else -0.04 if (elo_diff < -50 and is_bp) else 0
            
            p_in = s_stats.get("1in", 0.62)
            p_w1 = np.clip(s_stats.get("1w", 0.70) + elo_adj + clutch, 0.25, 0.95)
            p_w2 = np.clip(s_stats.get("2w", 0.50) + elo_adj, 0.15, 0.85)

            if random.random() < p_in:
                if random.random() < p_w1: p1_pts += 1
                else: p2_pts += 1
            else:
                if random.random() < p_w2: p1_pts += 1
                else: p2_pts += 1
        
        if p1_pts >= 4 and p1_pts - p2_pts >= 2: return 1
        if p2_pts >= 4 and p2_pts - p1_pts >= 2: return 0

def sim_set(d1, d2, elo_diff, surface, p1_m=1.0, p2_m=1.0):
    g1 = g2 = 0; sacador = 1 if random.random() > 0.5 else 2
    while True:
        if sacador == 1:
            if sim_game(d1, d2, elo_diff, surface, p1_m): g1 += 1
            else: g2 += 1
        else:
            if sim_game(d2, d1, -elo_diff, surface, p2_m): g2 += 1
            else: g1 += 1
        sacador = 3 - sacador
        if (g1 >= 6 and g1-g2 >= 2) or g1 == 7: return g1, g2
        if (g2 >= 6 and g2-g1 >= 2) or g2 == 7: return g1, g2

# --- UI ---
base_datos = cargar_todo()
with st.sidebar:
    st.header("🎾 IA Predictor v8.6")
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
        
        # Detección de "Alergia"
        a1 = (d1['MaxElo'] - e1) > 80
        a2 = (d2['MaxElo'] - e2) > 80

        res = {"j1_w":0, "j1_s1":0, "j2_s1":0, "j1_any":0, "j2_any":0, "over18":0, "over19":0, "gms":[], "set3":0}
        sets_to_win = 3 if "5 sets" in formato else 2
        
        for _ in range(10000):
            s1 = s2 = gt = 0
            p1_m = p2_m = 1.0
            set_n = 0
            while s1 < sets_to_win and s2 < sets_to_win:
                g1, g2 = sim_set(d1, d2, elo_diff, superficie, p1_m, p2_m)
                gt += (g1 + g2)
                
                if set_n == 0:
                    if g1 > g2: 
                        res["j1_s1"] += 1
                        # Si P2 es alérgico a la superficie y pierde el 1ero, colapsa más
                        p2_m = 0.75 if a2 else 0.88
                    else: 
                        res["j2_s1"] += 1
                        p1_m = 0.75 if a1 else 0.88

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

        prob_elo = 1 / (1 + 10 ** ((e2 - e1) / 400))
        p_final = (res["j1_w"]/10000 * 0.20) + (prob_elo * 0.80)

        st.divider()
        st.subheader("🏆 Probabilidad de Victoria")
        l1, l2 = st.columns(2)
        l1.metric(f"{d1['Player']}", f"{p_final:.1%}")
        l2.metric(f"{d2['Player']}", f"{(1-p_final):.1%}")

        st.subheader("🎾 Sets y Rendimiento")
        s1, s2, s3, s4, s5 = st.columns(5)
        s1.metric("¿Habrá 3 sets?", f"{res['set3']/10000:.1%}")
        s2.metric("1er Set P1", f"{res['j1_s1']/10000:.1%}")
        s3.metric("1er Set P2", f"{res['j2_s1']/10000:.1%}")
        s4.metric("P1 Gana 1 Set", f"{res['j1_any']/10000:.1%}")
        s5.metric("P2 Gana 1 Set", f"{res['j2_any']/10000:.1%}")

        st.subheader("📊 Mercados de Games")
        g1, g2, g3 = st.columns(3)
        g1.metric("Over 18.5", f"{res['over18']/10000:.1%}")
        g2.metric("Over 19.5", f"{res['over19']/10000:.1%}")
        g3.metric("Promedio Games", f"{np.mean(res['gms']):.1f}")