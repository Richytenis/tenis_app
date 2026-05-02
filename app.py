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

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background: #1a73e8; color: white; font-weight: bold; }
    .card { padding: 15px; border-radius: 15px; background: white; border: 1px solid #ddd; margin-bottom: 10px; }
    .status-bar { padding: 10px; border-radius: 10px; background: #f8f9fa; font-size: 0.8em; text-align: center; border: 1px solid #eee; margin-top: 20px; }
    </style>
    """, unsafe_allow_html=True)

# =================================================================
# 2. FUNCIONES DE CARGA (LECTURA AGRESIVA)
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
    ruta = 'datos'
    jugadores = set()
    archivos_leidos = 0
    
    if os.path.exists(ruta):
        for f in os.listdir(ruta):
            # Aceptamos cualquier variación de extensión
            if f.lower().endswith(('.csv', '.xlsx', '.xls')):
                archivos_leidos += 1
                try:
                    full_path = os.path.join(ruta, f)
                    # Intentamos leer CSV con detección de separador automático
                    if f.lower().endswith('.csv'):
                        df = pd.read_csv(full_path, sep=None, engine='python', on_bad_lines='skip')
                    else:
                        df = pd.read_excel(full_path)
                    
                    # Limpiamos y extraemos nombres de todas las celdas de texto
                    for col in df.columns:
                        # Solo procesamos si la columna tiene texto
                        series_limpia = df[col].astype(str).str.strip().str.upper()
                        for val in series_limpia.unique():
                            if len(val) > 3 and not val.replace('.','').replace(',','').isdigit():
                                if 'UNNAMED' not in val and 'NAN' != val:
                                    jugadores.add(val)
                except Exception as e:
                    st.sidebar.error(f"Error en {f}: {str(e)}")
                    continue
    return sorted(list(jugadores)), archivos_leidos

# =================================================================
# 3. INTERFAZ
# =================================================================

st.title("🎾 Tennis IA Predictor")

# Carga de datos
lista_nombres, total_archivos = cargar_jugadores_locales()

# Selector de Modo
modo = st.radio("Origen de datos:", ["📡 En Vivo (API)", "📂 Manual (Mis Datos)"], horizontal=True)

if modo == "📡 En Vivo (API)":
    if st.button("🔄 ACTUALIZAR CARTELERA"):
        with st.spinner("Buscando partidos..."):
            partidos = obtener_partidos_api()
            if not partidos:
                st.warning("No hay partidos en la API para hoy.")
            else:
                for p in partidos:
                    h = p.get('home_team', {}).get('name', 'Jugador 1')
                    a = p.get('away_team', {}).get('name', 'Jugador 2')
                    st.markdown(f'<div class="card"><strong>{h}</strong> vs <strong>{a}</strong></div>', unsafe_allow_html=True)

else:
    if total_archivos == 0:
        st.error("⚠️ No se encontraron archivos .csv o .xlsx en la carpeta /datos")
    elif not lista_nombres:
        st.warning(f"Se encontraron {total_archivos} archivos, pero no pudimos extraer nombres de jugadores.")
        st.info("Revisa que tus archivos no estén vacíos.")
    else:
        st.success(f"✅ {len(lista_nombres)} jugadores cargados de {total_archivos} archivos.")
        j1 = st.selectbox("Jugador 1", lista_nombres)
        j2 = st.selectbox("Jugador 2", lista_nombres)
        
        if st.button("🚀 PREDECIR"):
            st.balloons()
            st.markdown(f'<div class="card" style="background:#e8f5e9;">Análisis listo para <b>{j1}</b> vs <b>{j2}</b></div>', unsafe_allow_html=True)

# BARRA DE ESTADO
st.markdown(f"""
    <div class="status-bar">
        Host: {API_HOST} | Archivos en /datos: {total_archivos} | Nombres únicos: {len(lista_nombres)}
    </div>
""", unsafe_allow_html=True)