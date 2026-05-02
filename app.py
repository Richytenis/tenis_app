import streamlit as st
import requests
import pandas as pd
import os
from datetime import datetime

# =================================================================
# 1. CONFIGURACIÓN Y CREDENCIALES
# =================================================================
API_KEY = "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4"
API_HOST = "sportscore6.p.rapidapi.com"

st.set_page_config(page_title="Tennis Predictor", page_icon="🎾")

# Estilo profesional para iPhone
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background: #2e7d32; color: white; font-weight: bold; }
    .card { padding: 15px; border-radius: 15px; background: white; border: 1px solid #eee; margin-bottom: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
    .mode-box { padding: 10px; background: #e8f5e9; border-radius: 10px; margin-bottom: 20px; text-align: center; font-weight: bold; color: #2e7d32; }
    </style>
    """, unsafe_allow_html=True)

# =================================================================
# 2. FUNCIONES CORE (API Y DATOS LOCALES)
# =================================================================

def obtener_partidos_api():
    headers = {"x-rapidapi-host": API_HOST, "x-rapidapi-key": API_KEY}
    fecha = datetime.now().strftime('%Y-%m-%d')
    # Intentamos la ruta más probable de sportscore6
    url = f"https://{API_HOST}/api/v1/events/date/{fecha}"
    try:
        r = requests.get(url, headers=headers, params={"sport_id": "2"}, timeout=8)
        if r.status_code == 200:
            return r.json().get('data', [])
    except: pass
    return []

@st.cache_data
def cargar_jugadores_locales():
    ruta = 'datos'
    jugadores = []
    if os.path.exists(ruta):
        for f in os.listdir(ruta):
            if f.endswith(('.csv', '.xlsx')):
                try:
                    df = pd.read_csv(os.path.join(ruta, f)) if f.endswith('.csv') else pd.read_excel(os.path.join(ruta, f))
                    # Buscamos columnas que contengan 'winner' o 'player'
                    cols = [c for c in df.columns if 'winner' in c.lower() or 'player' in c.lower()]
                    for c in cols:
                        jugadores.extend(df[c].astype(str).unique())
                except: continue
    return sorted(list(set([j.upper() for j in jugadores if len(j) > 2])))

# =================================================================
# 3. INTERFAZ PRINCIPAL
# =================================================================

st.title("🎾 Tennis IA Predictor")

# SELECTOR DE MODO
modo = st.radio("Selecciona origen de datos:", ["📡 Cartelera API (En vivo)", "manual Selección Manual (Mis Datos)"], horizontal=True)

if modo == "📡 Cartelera API (En vivo)":
    st.markdown('<div class="mode-box">Buscando partidos programados para hoy</div>', unsafe_allow_html=True)
    
    if st.button("🔄 ACTUALIZAR CARTELERA"):
        with st.spinner("Conectando con SportScore6..."):
            partidos = obtener_partidos_api()
            
            if not partidos:
                st.error("No se encontraron partidos en la API para hoy.")
                st.info("Usa el 'Modo Manual' si quieres analizar jugadores de tu base de datos.")
            else:
                st.success(f"Se han encontrado {len(partidos)} partidos.")
                for p in partidos:
                    h = p.get('home_team', {}).get('name', 'N/A')
                    a = p.get('away_team', {}).get('name', 'N/A')
                    t = p.get('season', {}).get('name', 'Torneo')
                    
                    with st.container():
                        st.markdown(f"""
                        <div class="card">
                            <small>🏆 {t}</small><br>
                            <strong>{h}</strong> vs <strong>{a}</strong>
                        </div>
                        """, unsafe_allow_html=True)
                        if st.button(f"Analizar {h} vs {a}", key=f"btn_{h}"):
                            st.write(f"✨ Procesando estadísticas de **{h}** y **{a}**...")

else:
    st.markdown('<div class="mode-box">Modo Manual: Usa tus archivos en /datos</div>', unsafe_allow_html=True)
    jugadores = cargar_jugadores_locales()
    
    if not jugadores:
        st.warning("No se detectaron jugadores en la carpeta /datos.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            j1 = st.selectbox("Jugador 1", jugadores)
        with col2:
            j2 = st.selectbox("Jugador 2", jugadores)
            
        superficie = st.selectbox("Superficie", ["Hard", "Clay", "Grass"])
        
        if st.button("🚀 PREDECIR GANADOR"):
            st.success(f"Analizando enfrentamiento: {j1} vs {j2}")
            # Aquí va tu lógica de cálculo (Elo, PowerScore, etc.)
            st.info("Predicción: Simulando resultado basado en datos históricos...")

st.divider()
st.caption(f"Host activo: {API_HOST} | Base de datos: {len(cargar_jugadores_locales())} jugadores")