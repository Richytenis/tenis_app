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
st.set_page_config(page_title="Tennis IA Live", page_icon="🎾", layout="wide")

API_KEY = "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4"
API_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"

# Estilo para iPhone
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3em; background-color: #2e7d32; color: white; font-weight: bold; }
    .stRadio [data-testid="stWidgetLabel"] { font-size: 1.2em; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# =================================================================
# 2. FUNCIONES DE DATOS E IA
# =================================================================
def normalizar(n):
    if pd.isna(n): return ""
    n = str(n).upper()
    n = re.sub(r'[^A-Z\s]', '', n)
    return " ".join(n.split())

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
                        if w not in stats_jugador: stats_jugador[w] = {'power_score': 0}
                        if l not in stats_jugador[l]: stats_jugador[l] = {'power_score': 0}
                        stats_jugador[w]['power_score'] += (10 * peso_nivel)
                        stats_jugador[l]['power_score'] -= (6 / peso_nivel)
            except: continue
    return stats_jugador

def simular_partido(p1, p2, stats_ia):
    pow1 = 1500 + stats_ia.get(p1, {'power_score': 0})['power_score']
    pow2 = 1500 + stats_ia.get(p2, {'power_score': 0})['power_score']
    prob = 1 / (1 + 10 ** ((pow2 - pow1) / 400))
    return prob

# =================================================================
# 3. CONEXIÓN API (DEBUG MODE)
# =================================================================
def obtener_partidos_api(modo):
    headers = {"X-RapidAPI-Key": API_KEY, "X-RapidAPI-Host": API_HOST}
    
    # Mapeo de Endpoints
    if modo == "En Vivo":
        endpoints = ["/live", "/fixtures/live"]
    elif modo == "Mañana":
        fecha = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        endpoints = [f"/fixtures?date={fecha}", f"/calendar?date={fecha}"]
    else: # Hoy
        fecha = datetime.now().strftime('%Y-%m-%d')
        endpoints = [f"/fixtures?date={fecha}", f"/matches?date={fecha}"]

    for ep in endpoints:
        url = f"https://{API_HOST}{ep if ep.startswith('/') else '/' + ep}"
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                res = r.json().get('data', r.json().get('results', []))
                if res: return res
        except: continue
    return []

# =================================================================
# 4. INTERFAZ PRINCIPAL
# =================================================================
st.title("🎾 Tennis IA Multidía")
stats_ia = cargar_big_data()
lista_jugadores = list(stats_ia.keys())

tab1, tab2 = st.tabs(["📅 Cartelera API", "⌨️ Manual"])

with tab1:
    modo = st.radio("Selecciona:", ["En Vivo", "Hoy", "Mañana"], horizontal=True)
    
    if st.button(f"🚀 Cargar Partidos"):
        with st.spinner("Consultando API..."):
            partidos = obtener_partidos_api(modo)
            
            if not partidos:
                st.warning(f"La API no devolvió partidos para {modo}. Prueba con otra opción.")
                # Debug para el usuario
                st.info("Nota: Si estás en el plan gratuito, asegúrate de que haya torneos ATP/WTA activos hoy.")
            else:
                st.success(f"¡{len(partidos)} partidos encontrados!")
                for m in partidos:
                    # Intento de extraer nombres
                    p1_raw = m.get('home_player', m.get('player_1_name', 'Jugador 1'))
                    p2_raw = m.get('away_player', m.get('player_2_name', 'Jugador 2'))
                    
                    # Buscador de nombres en tu base de datos
                    m1 = get_close_matches(normalizar(p1_raw), lista_jugadores, n=1, cutoff=0.3)
                    m2 = get_close_matches(normalizar(p2_raw), lista_jugadores, n=1, cutoff=0.3)
                    
                    if m1 and m2:
                        with st.expander(f"✅ {m1[0]} vs {m2[0]}"):
                            prob = simular_partido(m1[0], m2[0], stats_ia)
                            ganador = m1[0] if prob > 0.5 else m2[0]
                            st.write(f"**Favorito IA:** {ganador}")
                            st.progress(prob if prob > 0.5 else 1-prob)
                            st.write(f"Probabilidad: {max(prob, 1-prob):.1%}")
                    else:
                        st.text(f"⚪ {p1_raw} vs {p2_raw} (Sin datos históricos)")

with tab2:
    st.subheader("Simulación Manual")
    j1 = st.selectbox("Jugador 1", sorted(lista_jugadores))
    j2 = st.selectbox("Jugador 2", sorted(lista_jugadores))
    if st.button("Simular Ahora"):
        p = simular_partido(j1, j2, stats_ia)
        st.success(f"Resultado: {j1 if p > 0.5 else j2} ({max(p, 1-p):.1%})")