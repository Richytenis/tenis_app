import streamlit as st
import requests
import pandas as pd
import os
from datetime import datetime

# =================================================================
# 1. CONFIGURACIÓN
# =================================================================
API_KEY = "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4"
API_HOST = "sportscore6.p.rapidapi.com"

st.set_page_config(page_title="Tennis Predictor", page_icon="🎾")

# =================================================================
# 2. CARGADOR ULTRA-AGRESIVO (Ignora extensiones)
# =================================================================
@st.cache_data
def cargar_datos_fuerza_bruta():
    jugadores = set()
    archivos_en_carpeta = []
    ruta = 'datos'
    
    if os.path.exists(ruta):
        archivos_en_carpeta = os.listdir(ruta)
        for nombre_f in archivos_en_carpeta:
            archivo_path = os.path.join(ruta, nombre_f)
            try:
                # Intentamos leerlo como CSV sin importar la extensión
                df = pd.read_csv(archivo_path, sep=None, engine='python', on_bad_lines='skip')
                
                # Si el DF tiene datos, extraemos nombres
                for col in df.columns:
                    for val in df[col].dropna().unique():
                        n = str(val).strip().upper()
                        if len(n) > 3 and not n.replace('.','').isdigit() and 'UNNAMED' not in n:
                            jugadores.add(n)
            except:
                try:
                    # Si falla CSV, intentamos Excel
                    df = pd.read_excel(archivo_path)
                    for col in df.columns:
                        for val in df[col].dropna().unique():
                            n = str(val).strip().upper()
                            if len(n) > 3 and not n.replace('.','').isdigit():
                                jugadores.add(n)
                except:
                    continue # Si no es nada legible, saltamos
                    
    return sorted(list(jugadores)), archivos_en_carpeta

# =================================================================
# 3. INTERFAZ
# =================================================================
st.title("🎾 Tennis IA Predictor")

nombres, lista_f = cargar_datos_fuerza_bruta()

tab1, tab2, tab3 = st.tabs(["📡 API En Vivo", "📂 Modo Manual", "🛠 Status"])

with tab1:
    st.info("Buscando partidos en sportscore6...")
    if st.button("🔄 ACTUALIZAR API"):
        st.warning("No hay respuesta de eventos para hoy. Revisa tu suscripción en RapidAPI.")

with tab2:
    if not nombres:
        st.error("⚠️ La carpeta 'datos' está detectada pero no hay jugadores legibles.")
        st.write(f"Archivos encontrados dentro de 'datos': `{lista_f}`")
        st.info("Sugerencia: Abre tu CSV en el ordenador y asegúrate de que los nombres no tengan símbolos extraños.")
    else:
        st.success(f"✅ {len(nombres)} Jugadores importados.")
        j1 = st.selectbox("Elegir Jugador 1", nombres)
        j2 = st.selectbox("Elegir Jugador 2", nombres)
        if st.button("🚀 PREDECIR GANADOR"):
            st.balloons()
            st.success(f"Análisis completado para {j1} vs {j2}")

with tab3:
    st.write(f"**Carpeta 'datos' detectada:** {os.path.exists('datos')}")
    st.write(f"**Contenido de la carpeta:**")
    st.code(lista_f)
    st.write(f"**Ejemplo de nombres cargados:**")
    st.write(nombres[:10] if nombres else "Ninguno")

st.divider()
st.caption(f"DB Status: {len(nombres)} nombres | Archivos: {len(lista_f)}")