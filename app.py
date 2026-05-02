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

# Tu Key y Host exactos para la "Tennis API (ATP, WTA, ITF)"
API_KEY = "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4"
API_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"

# Estilos optimizados para iPhone
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background-color: #2e7d32; color: white; font-weight: bold; margin-top: 10px; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { background-color: #f0f2f6; border-radius: 8px; padding: 8px 16px; }
    .main { background-color: #ffffff; }
    </style>
    """, unsafe_allow_html=True)

# =================================================================
# 2. PROCESAMIENTO DE DATOS HISTÓRICOS
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
# 3. MOTOR DE SIMULACIÓN (MONTE CARLO)
# =================================================================
def simular_partido(p1, p2, superficie, circuito, stats_ia):
    def get_pow(nombre):
        s = stats_ia.get(nombre, {'power_score': 0, 'total': 0, 'surf_stats': {}})
        ss = s['surf_stats'].get(superficie, {'wins': 0, 'total': 0})
        bonus = (ss['wins']/ss['total'] - 0.5) * 400 if ss['total'] > 0 else 0
        base = 1750 if circuito in ['ATP', 'WTA'] else 1400
        return max(1200 + s['power_score'] + bonus, base)

    pow1, pow2 = get_pow(p1), get_pow(p2)
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
            prob_set = p1_h / (p1_h + (1 - p2_h))
            if random.random() < prob_set: s1 += 1
            else: s2 += 1
            tot_j += random.uniform(8.5, 12.5) # Variabilidad de juegos
        if s1 == 2: p1_sets += 1
        juegos.append(tot_j)

    return {
        'prob_p1': p1_sets / sims,
        'over18': sum(1 for j in juegos if j > 18.5) / sims,
        'pow1': pow1,
        'pow2': pow2
    }

# =================================================================
# 4. CONEXIÓN API (TENNIS API ATP/WTA/ITF)
# =================================================================
def obtener_partidos_hoy():
    url = f"https://{API_HOST}/matches"
    # Usamos la fecha actual del servidor
    fecha_hoy = pd.Timestamp.now().strftime('%Y-%m-%d')
    querystring = {"date": fecha_hoy}
    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": API_HOST
    }
    try:
        r = requests.get(url, headers=headers, params=querystring, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return data.get('data', [])
        elif r.status_code == 403:
            st.error("🔑 Error 403: Verifica tu suscripción gratuita en RapidAPI.")
            return []
        else:
            st.error(f"Error {r.status_code}: {r.text}")
            return []
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return []

# =================================================================
# 5. INTERFAZ PRINCIPAL
# =================================================================
st.title("🎾 Tennis IA Live Predictor")

stats_ia = cargar_big_data()
lista_jugadores = sorted(list(stats_ia.keys()))

if not stats_ia:
    st.error("⚠️ La base de datos está vacía. Sube archivos a la carpeta /datos.")
else:
    tab1, tab2 = st.tabs(["📅 PARTIDOS DE HOY", "⌨️ SELECCIÓN MANUAL"])

    with tab1:
        if st.button("🔄 ACTUALIZAR CARTELERA"):
            with st.spinner("Consultando API..."):
                partidos = obtener_partidos_hoy()
                
                if not partidos:
                    st.warning("No hay partidos programados para hoy en esta API.")
                else:
                    st.success(f"Se han encontrado {len(partidos)} partidos.")
                    st.divider()
                    
                    for m in partidos:
                        # Extraer nombres según estructura de tu API específica
                        p1_api = m.get('home_player', 'Jugador 1')
                        p2_api = m.get('away_player', 'Jugador 2')
                        torneo = m.get('tournament_name', 'Torneo')
                        surf_api = m.get('surface', 'Hard')

                        # Mapeo difuso con tu base de datos (cutoff bajo para iPhone/nombres cortos)
                        m1 = get_close_matches(normalizar(p1_api), lista_jugadores, n=1, cutoff=0.3)
                        m2 = get_close_matches(normalizar(p2_api), lista_jugadores, n=1, cutoff=0.3)
                        
                        if m1 and m2:
                            with st.expander(f"⭐ {m1[0]} vs {m2[0]}"):
                                st.write(f"🏆 {torneo}")
                                if st.button(f"Simular", key=f"api_btn_{p1_api}"):
                                    res = simular_partido(m1[0], m2[0], mapear_superficie(surf_api), 'ATP', stats_ia)
                                    
                                    # Resultados visuales
                                    ganador = m1[0] if res['prob_p1'] > 0.5 else m2[0]
                                    confianza = res['prob_p1'] if res['prob_p1'] > 0.5 else 1 - res['prob_p1']
                                    
                                    c1, c2 = st.columns(2)
                                    c1.metric("Ganador", ganador, f"{confianza:.1%}")
                                    c2.metric("Over 18.5", f"{res['over18']:.1%}")
                        else:
                            # Opción por si no encuentra al jugador exacto
                            st.write(f"⚪ {p1_api} vs {p2_api} (Sin datos históricos)")

    with tab2:
        st.subheader("Simulación a medida")
        col_a, col_b = st.columns(2)
        j1 = col_a.selectbox("Jugador 1", lista_jugadores, key="man_j1")
        j2 = col_b.selectbox("Jugador 2", lista_jugadores, key="man_j2")
        
        surf_m = st.selectbox("Superficie", ["Tierra", "Dura", "Hierba"], key="man_surf")
        circ_m = st.selectbox("Circuito", ["ATP", "WTA", "CHALLENGER"], key="man_circ")

        if st.button("🚀 INICIAR SIMULACIÓN MANUAL"):
            res = simular_partido(j1, j2, mapear_superficie(surf_m), circ_m, stats_ia)
            ganador = j1 if res['prob_p1'] > 0.5 else j2
            conf = res['prob_p1'] if res['prob_p1'] > 0.5 else 1 - res['prob_p1']
            
            st.divider()
            st.success(f"### 🏆 Ganador: {ganador}")
            st.metric("Confianza", f"{conf:.1%}")
            st.metric("Probabilidad Over 18.5", f"{res['over18']:.1%}")