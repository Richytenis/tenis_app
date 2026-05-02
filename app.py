import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import requests
from difflib import get_close_matches

# =================================================================
# 1. CONFIGURACIÓN Y LLAVES
# =================================================================
st.set_page_config(page_title="Tennis IA Live", page_icon="🎾", layout="centered")

API_KEY = "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4"
API_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"

# Estilos para móvil
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background-color: #2e7d32; color: white; font-weight: bold; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #f0f2f6; border-radius: 10px; padding: 10px; }
    </style>
    """, unsafe_allow_html=True)

# =================================================================
# 2. LÓGICA DE PROCESAMIENTO DE DATOS
# =================================================================
def normalizar(n):
    if pd.isna(n): return ""
    n = str(n).upper()
    n = re.sub(r'[^A-Z\s]', '', n)
    return " ".join(n.split())

def mapear_superficie(s):
    s = str(s).upper() if s else "HARD"
    if any(x in s for x in ['TIERRA', 'CLAY', 'ARCILLA']): return 'Clay'
    if any(x in s for x in ['HIERBA', 'GRASS', 'CESPED']): return 'Grass'
    return 'Hard'

@st.cache_data
def cargar_big_data():
    ruta_base = 'datos'
    stats_jugador = {} 
    if not os.path.exists(ruta_base): return {}

    for root, _, files in os.walk(ruta_base):
        folder_name = os.path.basename(root).upper()
        peso_nivel = 2.5 if 'ATP' in folder_name else (2.0 if 'WTA' in folder_name else 1.5)

        for f in files:
            if not (f.endswith('.xlsx') or f.endswith('.csv')): continue
            try:
                df = pd.read_csv(os.path.join(root, f)) if f.endswith('.csv') else pd.read_excel(os.path.join(root, f))
                df.columns = df.columns.str.lower().str.strip()
                w_col = next((c for c in df.columns if 'winner' in c), None)
                l_col = next((c for c in df.columns if 'loser' in c), None)
                surf_col = next((c for c in df.columns if 'surface' in c), 'surface')

                if w_col and l_col:
                    for _, row in df.iterrows():
                        w, l = normalizar(row[w_col]), normalizar(row[l_col])
                        surf = mapear_superficie(str(row.get(surf_col, 'Hard')))
                        for p in [w, l]:
                            if p not in stats_jugador: 
                                stats_jugador[p] = {'power_score': 0, 'total': 0, 'surf_stats': {}}
                            stats_jugador[p]['total'] += 1
                            if surf not in stats_jugador[p]['surf_stats']:
                                stats_jugador[p]['surf_stats'][surf] = {'wins': 0, 'total': 0}
                            stats_jugador[p]['surf_stats'][surf]['total'] += 1
                            if p == w: 
                                stats_jugador[p]['power_score'] += (10 * peso_nivel)
                                stats_jugador[p]['surf_stats'][surf]['wins'] += 1
                            else:
                                stats_jugador[p]['power_score'] -= (6 / peso_nivel)
            except: continue
    return stats_jugador

# =================================================================
# 3. MOTOR DE SIMULACIÓN
# =================================================================
def simular_partido(p1, p2, superficie, circuito, stats_ia):
    # Cálculo de Poder Real
    def get_pow(nombre):
        s = stats_ia.get(nombre, {'power_score': 0, 'total': 0, 'surf_stats': {}})
        ss = s['surf_stats'].get(superficie, {'wins': 0, 'total': 0})
        bonus = (ss['wins']/ss['total'] - 0.5) * 400 if ss['total'] > 0 else 0
        base = 1750 if circuito in ['ATP', 'WTA'] else 1400
        return max(1200 + s['power_score'] + bonus, base)

    pow1, pow2 = get_pow(p1), get_pow(p2)
    
    # Probabilidades de Saque
    base_h = 0.74 if circuito != 'WTA' else 0.64
    diff = (pow1 - pow2) / 1200
    p1_h = np.clip(base_h + diff, 0.50, 0.95)
    p2_h = np.clip(base_h - diff, 0.50, 0.95)

    sims = 5000
    p1_sets = 0
    juegos = []
    
    for _ in range(sims):
        s1, s2, tot_j = 0, 0, 0
        while s1 < 2 and s2 < 2:
            # Simulación simplificada de set
            prob_set = p1_h / (p1_h + (1 - p2_h))
            if random.random() < prob_set: s1 += 1
            else: s2 += 1
            tot_j += 9.5 # Promedio de juegos por set
        if s1 == 2: p1_sets += 1
        juegos.append(tot_j)

    return {
        'prob_p1': p1_sets / sims,
        'over18': sum(1 for j in juegos if j > 18.5) / sims,
        'pow_dif': abs(pow1 - pow2)
    }

# =================================================================
# 4. CONEXIÓN API EN VIVO
# =================================================================
def obtener_partidos_hoy():
    url = f"https://{API_HOST}/matches"
    querystring = {"date": pd.Timestamp.now().strftime('%Y-%m-%d')}
    headers = {"X-RapidAPI-Key": API_KEY, "X-RapidAPI-Host": API_HOST}
    try:
        r = requests.get(url, headers=headers, params=querystring, timeout=15)
        if r.status_code == 200:
            return r.json().get('data', [])
        return []
    except:
        return []

# =================================================================
# 5. INTERFAZ STREAMLIT
# =================================================================
st.title("🎾 Tennis IA Live")
stats_ia = cargar_big_data()
lista_jugadores = sorted(list(stats_ia.keys()))

if not stats_ia:
    st.error("No hay archivos en la carpeta /datos")
else:
    tab1, tab2 = st.tabs(["📅 HOY", "⌨️ MANUAL"])

    with tab1:
        if st.button("🔄 BUSCAR PARTIDOS DE HOY"):
            partidos = obtener_partidos_hoy()
            if not partidos:
                st.warning("No se encontraron partidos. Verifica tu suscripción en RapidAPI.")
            else:
                for m in partidos:
                    p1_api = m.get('home_player', '')
                    p2_api = m.get('away_player', '')
                    
                    # Mapeo difuso
                    m1 = get_close_matches(normalizar(p1_api), lista_jugadores, n=1, cutoff=0.3)
                    m2 = get_close_matches(normalizar(p2_api), lista_jugadores, n=1, cutoff=0.3)
                    
                    if m1 and m2:
                        with st.container():
                            st.markdown(f"**{m1[0]} vs {m2[0]}**")
                            st.caption(f"🏆 {m.get('tournament_name', 'Torneo')} | 🏟️ {m.get('surface', 'Hard')}")
                            if st.button(f"Analizar", key=f"api_{p1_api}"):
                                res = simular_partido(m1[0], m2[0], mapear_superficie(m.get('surface')), 'ATP', stats_ia)
                                
                                col1, col2 = st.columns(2)
                                win_p = res['prob_p1'] if res['prob_p1'] > 0.5 else 1 - res['prob_p1']
                                ganador = m1[0] if res['prob_p1'] > 0.5 else m2[0]
                                
                                col1.metric("Ganador", ganador, f"{win_p:.1%}")
                                col2.metric("Over 18.5", f"{res['over18']:.1%}")
                                st.divider()
                    else:
                        pass # Jugadores no encontrados en histórico

    with tab2:
        c1, c2 = st.columns(2)
        p1_m = c1.selectbox("Jugador 1", lista_jugadores)
        p2_m = c2.selectbox("Jugador 2", lista_jugadores)
        surf_m = st.selectbox("Superficie", ["Tierra", "Dura", "Hierba"])
        circ_m = st.selectbox("Circuito", ["ATP", "WTA", "CHALLENGER"])

        if st.button("🚀 SIMULAR MANUAL"):
            res = simular_partido(p1_m, p2_m, mapear_superficie(surf_m), circ_m, stats_ia)
            ganador = p1_m if res['prob_p1'] > 0.5 else p2_m
            win_p = res['prob_p1'] if res['prob_p1'] > 0.5 else 1 - res['prob_p1']
            
            st.success(f"### 🏆 {ganador} ({win_p:.1%})")
            st.write(f"**Probabilidad Over 18.5 juegos:** {res['over18']:.1%}")