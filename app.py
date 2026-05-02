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
# 2. CARGADOR RECURSIVO (Entra en todas las subcarpetas)
# =================================================================
@st.cache_data
def cargar_jugadores_recursivo():
    jugadores = set()
    base_path = 'datos'
    conteo_archivos = 0
    
    if os.path.exists(base_path):
        # os.walk recorre carpetas y subcarpetas (atp, wta, itf, challenger)
        for root, dirs, files in os.walk(base_path):
            for nombre_f in files:
                if nombre_f.startswith('.'): continue
                
                archivo_path = os.path.join(root, nombre_f)
                conteo_archivos += 1
                
                try:
                    # Intentamos leer como CSV o Excel
                    if nombre_f.lower().endswith(('.xlsx', '.xls')):
                        df = pd.read_excel(archivo_path)
                    else:
                        # Para CSV o archivos sin extensión, probamos lectura flexible
                        df = pd.read_csv(archivo_path, sep=None, engine='python', on_bad_lines='skip')
                    
                    # Extraer nombres de todas las columnas
                    for col in df.columns:
                        # Añadir el nombre de la columna por si acaso
                        c_str = str(col).strip().upper()
                        if len(c_str) > 3 and not c_str.isdigit() and 'UNNAMED' not in c_str:
                            jugadores.add(c_str)
                            
                        # Añadir los datos de las filas
                        for val in df[col].dropna().unique():
                            n = str(val).strip().upper()
                            if len(n) > 3 and len(n) < 35 and not n.replace('.','').isdigit() and 'NAN' != n:
                                jugadores.add(n)
                except:
                    # Si falla pandas, probamos lectura de texto crudo (fallback)
                    try:
                        with open(archivo_path, 'r', encoding='utf-8', errors='ignore') as f:
                            for linea in f:
                                for palabra in linea.split(','):
                                    p = palabra.strip().upper()
                                    if 3 < len(p) < 35 and not p.isdigit():
                                        jugadores.add(p)
                    except: continue
                    
    return sorted(list(jugadores)), conteo_archivos

# =================================================================
# 3. INTERFAZ
# =================================================================
st.title("🎾 Tennis IA Predictor")

nombres, total_f = cargar_jugadores_recursivo()

tab1, tab2, tab3 = st.tabs(["📡 API En Vivo", "📂 Modo Manual", "🛠 Status"])

with tab1:
    st.info("Buscando partidos en vivo...")
    if st.button("🔄 ACTUALIZAR CARTELERA"):
        headers = {"x-rapidapi-host": API_HOST, "x-rapidapi-key": API_KEY}
        url = f"https://{API_HOST}/api/v1/events/date/{datetime.now().strftime('%Y-%m-%d')}"
        try:
            r = requests.get(url, headers=headers, params={"sport_id": "2"}, timeout=5)
            data = r.json().get('data', [])
            if data:
                for p in data:
                    st.write(f"🔹 **{p.get('home_team',{}).get('name')}** vs **{p.get('away_team',{}).get('name')}**")
            else:
                st.warning("No hay partidos hoy en la API.")
        except:
            st.error("Error al conectar con la API.")

with tab2:
    if not nombres:
        st.error("⚠️ No se encontraron jugadores dentro de las subcarpetas.")
        st.info("Asegúrate de que dentro de 'atp', 'wta', etc., haya archivos CSV o Excel.")
    else:
        st.success(f"✅ {len(nombres)} Jugadores cargados de todas las categorías.")
        col1, col2 = st.columns(2)
        with col1:
            j1 = st.selectbox("Jugador 1", nombres)
        with col2:
            j2 = st.selectbox("Jugador 2", nombres)
        
        if st.button("🚀 PREDECIR"):
            st.balloons()
            st.markdown(f"""
            <div style="padding:20px; border-radius:15px; background:#e8f5e9; border:2px solid #2e7d32;">
                <h3 style="color:#2e7d32; margin:0;">Análisis de IA</h3>
                <p>Enfrentamiento: <b>{j1}</b> vs <b>{j2}</b></p>
                <p>Calculando probabilidades basadas en histórico...</p>
            </div>
            """, unsafe_allow_html=True)

with tab3:
    st.subheader("Estructura de Datos")
    st.write(f"**Total de archivos encontrados:** {total_f}")
    st.write(f"**Jugadores únicos detectados:** {len(nombres)}")
    
    if st.checkbox("Ver lista de archivos"):
        # Lista los archivos reales para confirmar
        for root, dirs, files in os.walk('datos'):
            for f in files:
                st.text(os.path.join(root, f))

st.divider()
st.caption(f"DB: {len(nombres)} nombres | Origen: Subcarpetas de datos")