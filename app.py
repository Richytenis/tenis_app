import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import requests
from datetime import datetime

# =================================================================
# 1. CONFIGURACIÓN Y CREDENCIALES
# =================================================================
st.set_page_config(page_title="Tennis Live Predictor", page_icon="🎾", layout="centered")

API_KEY = "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4"
API_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"

# Estilo para iPhone (Botones grandes y legibles)
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background-color: #2e7d32; color: white; font-weight: bold; }
    .match-card { padding: 15px; border-radius: 10px; border: 1px solid #e0e0e0; margin-bottom: 10px; background-color: #f9f9f9; }
    </style>
    """, unsafe_allow_html=True)

# =================================================================
# 2. MOTOR DE IA (BASADO EN TUS DATOS)
# =================================================================
@st.cache_data
def cargar_big_data():
    ruta_base = 'datos'
    stats_jugador = {} 
    if not os.path.exists(ruta_base): return {}
    
    for root, _, files in os.walk(ruta_base):
        folder_name = os.path.basename(root).upper()
        peso = 2.5 if 'ATP' in folder_name else (2.0 if 'WTA' in folder_name else 1.5)
        for f in files:
            if f.endswith(('.csv', '.xlsx')):
                try:
                    df = pd.read_csv(os.path.join(root, f)) if f.endswith('.csv') else pd.read_excel(os.path.join(root, f))
                    df.columns = df.columns.str.lower().str.strip()
                    w_col = next((c for c in df.columns if 'winner' in c), None)
                    l_col = next((c for c in df.columns if 'loser' in c), None)
                    if w_col and l_col:
                        for _, row in df.iterrows():
                            w, l = str(row[w_col]).upper(), str(row[l_col]).upper()
                            if w not in stats_jugador: stats_jugador[w] = 1500
                            if l not in stats_jugador[l]: stats_jugador[l] = 1500
                            stats_jugador[w] += (10 * peso)
                            stats_jugador[l] -= (5 / peso)
                except: continue
    return stats_jugador

def predecir_ganador(p1, p2, stats_ia):
    # Elo simple: Si no existe en base de datos, asignamos 1500 neutro
    rank1 = stats_ia.get(p1.upper(), 1500)
    rank2 = stats_ia.get(p2.upper(), 1500)
    
    prob = 1 / (1 + 10 ** ((rank2 - rank1) / 400))
    return prob

# =================================================================
# 3. CONEXIÓN A LA CARTELERA (API)
# =================================================================
def obtener_partidos_hoy():
    # Usamos /matches que es el endpoint para la cartelera diaria
    url = f"https://{API_HOST}/matches"
    headers = {"X-RapidAPI-Key": API_KEY, "X-RapidAPI-Host": API_HOST}
    fecha = datetime.now().strftime('%Y-%m-%d')
    
    try:
        r = requests.get(url, headers=headers, params={"date": fecha}, timeout=10)
        if r.status_code == 200:
            return r.json().get('data', [])
        return []
    except:
        return []

# =================================================================
# 4. INTERFAZ PRINCIPAL
# =================================================================
st.title("🎾 Tennis Live Predictor")
stats_ia = cargar_big_data()

if st.button("🔄 ACTUALIZAR CARTELERA"):
    with st.spinner("Buscando partidos de hoy..."):
        partidos = obtener_partidos_hoy()
        
        if not partidos:
            st.warning("No hay partidos registrados para hoy en la API.")
        else:
            st.success(f"Se han encontrado {len(partidos)} partidos.")
            
            for p in partidos:
                # Extraemos datos de la API
                p1 = p.get('home_player', p.get('player1_name', 'Jugador 1'))
                p2 = p.get('away_player', p.get('player2_name', 'Jugador 2'))
                torneo = p.get('tournament_name', 'Torneo')
                ronda = p.get('round', 'N/A')
                
                # Cálculo de IA
                prob_p1 = predecir_ganador(p1, p2, stats_ia)
                ganador = p1 if prob_p1 > 0.5 else p2
                confianza = prob_p1 if prob_p1 > 0.5 else 1 - prob_p1
                
                # Mostrar en tarjeta
                with st.container():
                    st.markdown(f"""
                    <div class="match-card">
                        <strong>🏆 {torneo} ({ronda})</strong><br>
                        🎾 {p1} vs {p2}<br>
                        <hr>
                        🔮 <b>Predicción IA:</b> {ganador}<br>
                        📈 <b>Confianza:</b> {confianza:.1%}
                    </div>
                    """, unsafe_allow_html=True)

st.divider()
st.caption("Esta app cruza los partidos en vivo de la API con tu base de datos histórica en /datos.")