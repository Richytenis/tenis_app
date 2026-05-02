import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import requests
from difflib import get_close_matches

# =================================================================
# 1. CONFIGURACIÓN Y API
# =================================================================
st.set_page_config(page_title="Tennis IA Live", page_icon="🎾")

# TU KEY DE RAPIDAPI
API_KEY = "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4"

# Intentaremos con el host estándar de API-Tennis en RapidAPI
API_HOST = "api-tennis.p.rapidapi.com" 

# =================================================================
# 2. FUNCIONES DE LÓGICA (MANTENIDAS)
# =================================================================
def normalizar(n):
    if pd.isna(n): return ""
    n = str(n).upper()
    n = re.sub(r'[^A-Z\s]', '', n)
    return " ".join(n.split())

def mapear_superficie(s):
    if not s: return 'Hard'
    s = str(s).upper()
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

# --- SIMULACIÓN ---
def calcular_poder_real(nombre, superficie, circuito, stats_ia):
    stats = stats_ia.get(nombre, {'power_score': 0, 'total': 0, 'surf_stats': {}})
    s_stats = stats['surf_stats'].get(superficie, {'wins': 0, 'total': 0})
    surf_bonus = (s_stats['wins'] / s_stats['total'] - 0.5) * 400 if s_stats['total'] > 0 else 0
    return max(1200 + stats['power_score'] + surf_bonus, 1400)

def simular_partido(p1, p2, superficie, circuito, stats_ia):
    pow1 = calcular_poder_real(p1, superficie, circuito, stats_ia)
    pow2 = calcular_poder_real(p2, superficie, circuito, stats_ia)
    # Lógica simplificada para la respuesta
    base_h = 0.74 if circuito == 'ATP' else 0.64
    p1_h = np.clip(base_h + (pow1 - pow2)/1000, 0.50, 0.90)
    p2_h = np.clip(base_h - (pow1 - pow2)/1000, 0.50, 0.90)
    
    sims = 5000
    ganados_p1 = 0
    for _ in range(sims):
        s1, s2 = 0, 0
        while s1 < 2 and s2 < 2:
            if random.random() < (p1_h / (p1_h + (1-p2_h))): s1 += 1
            else: s2 += 1
        if s1 == 2: ganados_p1 += 1
    return ganados_p1 / sims

# =================================================================
# 3. CONEXIÓN CON LA API (CORREGIDA)
# =================================================================
def obtener_partidos_hoy():
    # Nota: El endpoint exacto puede variar según el plan de RapidAPI
    # Probamos con el formato común de 'v2/fixtures' o 'matches'
    url = f"https://{API_HOST}/v2/fixtures/{pd.Timestamp.now().strftime('%Y-%m-%d')}"
    headers = {"X-RapidAPI-Key": API_KEY, "X-RapidAPI-Host": API_HOST}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        # Adaptación según la estructura de la API (data['data'] o data['results'])
        return data.get('data', data.get('results', []))
    except:
        return []

# =================================================================
# 4. INTERFAZ
# =================================================================
st.title("🎾 Tennis Predictor Live")
stats_ia = cargar_big_data()
lista_jugadores = sorted(list(stats_ia.keys()))

tab1, tab2 = st.tabs(["📅 Partidos de Hoy", "⌨️ Manual"])

with tab1:
    if st.button("🔄 Cargar Partidos de Hoy"):
        partidos = obtener_partidos_hoy()
        if not partidos:
            st.warning("No se recibieron datos. Verifica tu suscripción en RapidAPI.")
        else:
            for m in partidos:
                # Ajuste de nombres de campos según la API de RapidAPI
                p1_api = m.get('player_1_name', m.get('home_name', ''))
                p2_api = m.get('player_2_name', m.get('away_name', ''))
                
                # Búsqueda difusa
                m1 = get_close_matches(normalizar(p1_api), lista_jugadores, n=1, cutoff=0.5)
                m2 = get_close_matches(normalizar(p2_api), lista_jugadores, n=1, cutoff=0.5)
                
                if m1 and m2:
                    with st.expander(f"📌 {m1[0]} vs {m2[0]}"):
                        if st.button(f"Analizar", key=f"btn_{p1_api}"):
                            prob = simular_partido(m1[0], m2[0], 'Hard', 'ATP', stats_ia)
                            st.write(f"**Ganador estimado:** {m1[0] if prob > 0.5 else m2[0]}")
                            st.write(f"**Confianza:** {max(prob, 1-prob):.1%}")

with tab2:
    p1_m = st.selectbox("Jugador 1", lista_jugadores)
    p2_m = st.selectbox("Jugador 2", lista_jugadores)
    if st.button("Simular Manual"):
        prob = simular_partido(p1_m, p2_m, 'Hard', 'ATP', stats_ia)
        st.success(f"Probabilidad {p1_m}: {prob:.1%}")