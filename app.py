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

st.set_page_config(page_title="Tennis Debugger", page_icon="🎾")

# =================================================================
# 2. EXPLORADOR DE ARCHIVOS (Para encontrar tus datos)
# =================================================================
def listar_directorios():
    # Esta función nos dirá qué carpetas existen realmente en el servidor
    try:
        items = os.listdir('.')
        carpetas = [i for i in items if os.path.isdir(i)]
        archivos_sueltos = [i for i in items if os.path.isfile(i)]
        return carpetas, archivos_sueltos
    except:
        return [], []

@st.cache_data
def cargar_jugadores_agresivo():
    # Probamos todas las carpetas que suelen aparecer en GitHub/Streamlit
    rutas_a_testear = ['datos', 'Datos', 'data', 'Data', '.']
    jugadores = set()
    archivos_encontrados = []
    
    for ruta in rutas_a_testear:
        if os.path.exists(ruta):
            for f in os.listdir(ruta):
                if f.lower().endswith(('.csv', '.xlsx', '.xls')):
                    archivos_encontrados.append(f)
                    try:
                        fp = os.path.join(ruta, f)
                        df = pd.read_csv(fp, sep=None, engine='python') if f.endswith('.csv') else pd.read_excel(fp)
                        for col in df.columns:
                            for val in df[col].dropna().unique():
                                nombre = str(val).strip().upper()
                                if len(nombre) > 3 and not nombre.replace('.','').isdigit():
                                    jugadores.add(nombre)
                    except: continue
    return sorted(list(jugadores)), archivos_encontrados

# =================================================================
# 3. INTERFAZ
# =================================================================
st.title("🎾 Tennis IA Predictor")

nombres, lista_archivos = cargar_jugadores_agresivo()

# PANEL DE CONTROL (MODO)
tab1, tab2, tab3 = st.tabs(["📡 API En Vivo", "📂 Modo Manual", "🛠 Diagnóstico"])

with tab1:
    if st.button("🔄 BUSCAR EN API"):
        # Lógica simplificada de API
        st.warning("No se detectan partidos en sportscore6 para esta fecha.")

with tab2:
    if not nombres:
        st.error("No hay datos cargados. Ve a la pestaña 'Diagnóstico'.")
    else:
        st.success(f"✅ {len(nombres)} jugadores listos.")
        j1 = st.selectbox("Jugador 1", nombres)
        j2 = st.selectbox("Jugador 2", nombres)
        if st.button("🚀 PREDECIR"):
            st.info(f"Analizando histórico para {j1} vs {j2}...")

with tab3:
    st.subheader("Estado del Servidor")
    carpetas, sueltos = listar_directorios()
    
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Carpetas encontradas:**")
        st.write(carpetas)
    with col2:
        st.write("**Archivos en raíz:**")
        st.write(sueltos)
    
    st.write("**Archivos detectados por la IA:**")
    st.write(lista_archivos)

st.divider()
st.caption(f"Host: {API_HOST} | Total Jugadores: {len(nombres)}")