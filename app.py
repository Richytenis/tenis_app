import streamlit as st
import requests
import pandas as pd
import os
from datetime import datetime

# =================================================================
# 1. CONFIGURACIÓN Y ESTILOS
# =================================================================
API_KEY = "TU_API_KEY"
API_HOST = "sportscore6.p.rapidapi.com"

st.set_page_config(page_title="Tennis Auto-Predict", page_icon="🎾")

st.markdown("""
    <style>
    .match-box { padding: 15px; border-radius: 15px; background: #ffffff; border: 1px solid #e0e0e0; margin-bottom: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .player-name { font-size: 1.1em; font-weight: bold; color: #1e88e5; }
    .vs-label { color: #666; font-size: 0.8em; margin: 0 10px; }
    </style>
    """, unsafe_allow_html=True)

# =================================================================
# 2. MOTOR DE DATOS
# =================================================================
@st.cache_data
def cargar_base_jugadores():
    jugadores = set()
    if os.path.exists('datos'):
        for root, _, files in os.walk('datos'):
            for f in files:
                if f.startswith('.') or not f.lower().endswith(('.csv', '.xlsx')): continue
                try:
                    df = pd.read_csv(os.path.join(root, f), engine='python', on_bad_lines='skip')
                    for col in df.columns:
                        for v in df[col].dropna().unique():
                            jugadores.add(str(v).strip().upper())
                except: continue
    return jugadores

def ejecutar_pronostico(home, away, db_local):
    """Aquí centralizamos la lógica de cálculo que ya te funcionaba"""
    home = home.strip().upper()
    away = away.strip().upper()
    
    if home in db_local and away in db_local:
        st.success(f"✅ Análisis completado para: {home} vs {away}")
        # --- TU LÓGICA DE CÁLCULO AQUÍ ---
        st.metric(label=f"Probabilidad {home}", value="65%", delta="Favorito")
        st.progress(0.65)
    else:
        st.error("Faltan datos de uno o ambos jugadores en la base local.")
        if home not in db_local: st.warning(f"Falta: {home}")
        if away not in db_local: st.warning(f"Falta: {away}")

# =================================================================
# 3. INTERFAZ PRINCIPAL
# =================================================================
st.title("🎾 Tennis Predictor Pro")

# Cargamos base de datos
db_jugadores = cargar_base_jugadores()

# Menú de selección de modo
modo = st.radio("Selecciona modo de uso:", 
                ["📅 Partidos de Hoy (Auto)", "⌨️ Entrada Manual"], 
                horizontal=True)

st.divider()

if modo == "📅 Partidos de Hoy (Auto)":
    st.subheader("Cartelera del día")
    if st.button("🔍 BUSCAR PARTIDOS EN VIVO"):
        headers = {"x-rapidapi-host": API_HOST, "x-rapidapi-key": API_KEY}
        url = f"https://{API_HOST}/api/v1/events/date/{datetime.now().strftime('%Y-%m-%d')}"
        
        try:
            with st.spinner('Conectando con la API...'):
                r = requests.get(url, headers=headers, params={"sport_id": "2"}, timeout=7)
                eventos = r.json().get('data', [])

            if not eventos:
                st.info("No se encontraron partidos para hoy.")
            
            for ev in eventos:
                home = ev.get('home_team', {}).get('name', '').upper()
                away = ev.get('away_team', {}).get('name', '').upper()
                torneo = ev.get('season', {}).get('name', 'Torneo')
                
                with st.container():
                    st.markdown(f"""
                    <div class="match-box">
                        <small>🏆 {torneo}</small><br>
                        <span class="player-name">{home}</span> <span class="vs-label">VS</span> <span class="player-name">{away}</span>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button(f"Pronosticar", key=f"btn_{home}_{away}"):
                        ejecutar_pronostico(home, away, db_jugadores)
                        
        except Exception as e:
            st.error(f"Error en API: {e}")

else:
    st.subheader("Entrada de Jugadores Manual")
    col1, col2 = st.columns(2)
    with col1:
        jugador_1 = st.text_input("Jugador 1 (Local)", placeholder="Ej: ALCARAZ C.")
    with col2:
        jugador_2 = st.text_input("Jugador 2 (Visitante)", placeholder="Ej: DJOKOVIC N.")
    
    if st.button("🎯 GENERAR PRONÓSTICO MANUAL", use_container_width=True):
        if jugador_1 and jugador_2:
            ejecutar_pronostico(jugador_1, jugador_2, db_jugadores)
        else:
            st.warning("Por favor, introduce ambos nombres.")

# =================================================================
# FOOTER
# =================================================================
st.sidebar.caption(f"📊 {len(db_jugadores)} jugadores en DB")
if st.sidebar.button("Limpiar Caché"):
    st.cache_data.clear()