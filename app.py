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

st.set_page_config(page_title="Tennis Predictor PRO", page_icon="🎾")

# Estilo para iPhone
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background: #1a73e8; color: white; font-weight: bold; }
    .card { padding: 15px; border-radius: 15px; background: white; border: 1px solid #ddd; margin-bottom: 10px; }
    .status-bar { padding: 10px; border-radius: 10px; background: #f8f9fa; font-size: 0.8em; text-align: center; border: 1px solid #eee; }
    </style>
    """, unsafe_allow_html=True)

# =================================================================
# 2. FUNCIONES DE CARGA REFORZADAS
# =================================================================

def obtener_partidos_api():
    headers = {"x-rapidapi-host": API_HOST, "x-rapidapi-key": API_KEY}
    fecha = datetime.now().strftime('%Y-%m-%d')
    url = f"https://{API_HOST}/api/v1/events/date/{fecha}"
    try:
        r = requests.get(url, headers=headers, params={"sport_id": "2"}, timeout=8)
        if r.status_code == 200:
            return r.json().get('data', [])
    except: pass
    return []

@st.cache_data
def cargar_jugadores_locales():
    # Probamos varias rutas posibles en el servidor
    posibles_rutas = ['datos', 'Datos', './datos', '../datos']
    jugadores = set()
    ruta_encontrada = None

    for r in posibles_rutas:
        if os.path.exists(r):
            ruta_encontrada = r
            for f in os.listdir(r):
                if f.endswith(('.csv', '.xlsx', '.xls')):
                    try:
                        full_path = os.path.join(r, f)
                        df = pd.read_csv(full_path) if f.endswith('.csv') else pd.read_excel(full_path)
                        # Escaneamos todas las columnas buscando texto
                        for col in df.columns:
                            items = df[col].dropna().unique()
                            for item in items:
                                val = str(item).strip().upper()
                                if len(val) > 3 and not val.replace('.','').isdigit():
                                    jugadores.add(val)
                    except: continue
            break # Si encontró la carpeta y leyó, paramos
    return sorted(list(jugadores)), ruta_encontrada

# =================================================================
# 3. INTERFAZ PRINCIPAL
# =================================================================

st.title("🎾 Tennis IA Predictor")

# Carga de datos
lista_nombres, carpeta_origen = cargar_jugadores_locales()

# Selector de Modo
modo = st.radio("Origen de datos:", ["📡 En Vivo (API)", "📂 Manual (Mis Datos)"], horizontal=True)

st.markdown("---")

if modo == "📡 En Vivo (API)":
    if st.button("🔄 ACTUALIZAR CARTELERA"):
        with st.spinner("Consultando SportScore6..."):
            partidos = obtener_partidos_api()
            if not partidos:
                st.warning("No hay partidos en la API para hoy.")
                st.info("Pásate al modo 'Manual' para usar tus archivos locales.")
            else:
                for p in partidos:
                    h = p.get('home_team', {}).get('name', 'N/A')
                    a = p.get('away_team', {}).get('name', 'N/A')
                    with st.container():
                        st.markdown(f'<div class="card"><strong>{h}</strong> vs <strong>{a}</strong></div>', unsafe_allow_html=True)

else:
    if not lista_nombres:
        st.error("⚠️ No se detectaron archivos en la carpeta /datos")
        st.info(f"Ruta actual del servidor: {os.getcwd()}")
        st.write("Asegúrate de que tus archivos estén en la carpeta 'datos' de tu GitHub.")
    else:
        st.success(f"✅ {len(lista_nombres)} jugadores cargados desde /datos")
        j1 = st.selectbox("Jugador 1", lista_nombres)
        j2 = st.selectbox("Jugador 2", lista_nombres)
        
        if st.button("🚀 PREDECIR"):
            st.balloons()
            st.markdown(f'<div class="card" style="background:#e8f5e9;">Predicción: <b>{j1}</b> tiene ventaja.</div>', unsafe_allow_html=True)

# BARRA DE ESTADO FINAL
st.markdown("---")
st.markdown(f"""
    <div class="status-bar">
        Host: {API_HOST} | Carpeta: {carpeta_origen if carpeta_origen else 'No detectada'} | DB: {len(lista_nombres)} nombres
    </div>
""", unsafe_allow_html=True)