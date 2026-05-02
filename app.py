import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import requests
from datetime import datetime, timedelta
from difflib import get_close_matches

# =================================================================
# 1. CONFIGURACIÓN
# =================================================================
st.set_page_config(page_title="Tennis IA Live", page_icon="🎾")

API_KEY = "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4"
API_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"

# =================================================================
# 2. FUNCIONES DE DATOS E IA (MANTENIDAS)
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
                if w_col and l_col:
                    for _, row in df.iterrows():
                        w, l = normalizar(row[w_col]), normalizar(row[l_col])
                        surf = mapear_superficie(str(row.get('surface', 'Hard')))
                        for p in [w, l]:
                            if p not in stats_jugador: stats_jugador[p] = {'power_score': 0, 'total': 0, 'surf_stats': {}}
                            stats_jugador[p]['total'] += 1
                            if surf not in stats_jugador[p]['surf_stats']: stats_jugador[p]['surf_stats'][surf] = {'wins': 0, 'total': 0}
                            stats_jugador[p]['surf_stats'][surf]['total'] += 1
                            if p == w: 
                                stats_jugador[p]['power_score'] += (10 * peso_nivel)
                                stats_jugador[p]['surf_stats'][surf]['wins'] += 1
                            else: stats_jugador[p]['power_score'] -= (6 / peso_nivel)
            except: continue
    return stats_jugador

def simular_partido(p1, p2, superficie, circuito, stats_ia):
    def get_pow(nombre):
        s = stats_ia.get(nombre, {'power_score': 0, 'total': 0, 'surf_stats': {}})
        ss = s['surf_stats'].get(superficie, {'wins': 0, 'total': 0})
        bonus = (ss['wins']/ss['total'] - 0.5) * 400 if ss['total'] > 0 else 0
        return max(1200 + s['power_score'] + bonus, 1400)
    pow1, pow2 = get_pow(p1), get_pow(p2)
    base_h = 0.74 if circuito != 'WTA' else 0.64
    p1_h = np.clip(base_h + (pow1 - pow2)/1200, 0.50, 0.95)
    p2_h = np.clip(base_h - (pow1 - pow2)/1200, 0.50, 0.95)
    sims = 3000
    p1_sets = 0
    for _ in range(sims):
        s1, s2 = 0, 0
        while s1 < 2 and s2 < 2:
            if random.random() < (p1_h / (p1_h + (1 - p2_h))): s1 += 1
            else: s2 += 1
        if s1 == 2: p1_sets += 1
    return p1_sets / sims

# =================================================================
# 3. CONEXIÓN API MEJORADA (VIVO / HOY / MAÑANA)
# =================================================================
def obtener_partidos(modo):
    headers = {"X-RapidAPI-Key": API_KEY, "X-RapidAPI-Host": API_HOST}
    
    # Determinar endpoint y fecha
    if modo == "En Vivo":
        url = f"https://{API_HOST}/live" # Endpoint típico para Live
        params = {}
    else:
        url = f"https://{API_HOST}/fixtures"
        dias = 0 if modo == "Hoy" else 1
        fecha = (datetime.now() + timedelta(days=dias)).strftime('%Y-%m-%d')
        params = {"date": fecha}
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get('data', data.get('results', []))
        return []
    except:
        return []

# =================================================================
# 4. INTERFAZ
# =================================================================
st.title("🎾 Tennis IA Multidía")
stats_ia = cargar_big_data()
lista_jugadores = sorted(list(stats_ia.keys()))

tab1, tab2 = st.tabs(["📅 Cartelera API", "⌨️ Manual"])

with tab1:
    # Selector de tiempo para la API
    opcion_tiempo = st.radio("Ver partidos de:", ["En Vivo", "Hoy", "Mañana"], horizontal=True)
    
    if st.button(f"🔍 Cargar Partidos ({opcion_tiempo})"):
        partidos = obtener_partidos(opcion_tiempo)
        
        if not partidos:
            st.warning(f"No se encontraron partidos para '{opcion_tiempo}'.")
        else:
            st.success(f"Encontrados {len(partidos)} partidos.")
            for m in partidos:
                p1_api = m.get('home_player', m.get('player_1_name', ''))
                p2_api = m.get('away_player', m.get('player_2_name', ''))
                surf_api = m.get('surface', 'Hard')
                
                m1 = get_close_matches(normalizar(p1_api), lista_jugadores, n=1, cutoff=0.3)
                m2 = get_close_matches(normalizar(p2_api), lista_jugadores, n=1, cutoff=0.3)
                
                if m1 and m2:
                    with st.expander(f"📌 {m1[0]} vs {m2[0]}"):
                        if st.button("Analizar", key=f"btn_{opcion_tiempo}_{p1_api}"):
                            prob = simular_partido(m1[0], m2[0], mapear_superficie(surf_api), 'ATP', stats_ia)
                            st.metric("Probabilidad Ganador", f"{m1[0] if prob > 0.5 else m2[0]}", f"{max(prob, 1-prob):.1%}")
                else:
                    st.caption(f"⚪ {p1_api} vs {p2_api} (Faltan datos históricos)")

with tab2:
    # Lógica manual...
    st.write("Selecciona jugadores manualmente de tu base de datos.")
    j1 = st.selectbox("Jugador 1", lista_jugadores)
    j2 = st.selectbox("Jugador 2", lista_jugadores)
    if st.button("Simulación Manual"):
        p = simular_partido(j1, j2, "Hard", "ATP", stats_ia)
        st.write(f"Ganador: {j1 if p > 0.5 else j2} ({max(p, 1-p):.1%})")