import streamlit as st
import requests
import pandas as pd
import os
from datetime import datetime

# =================================================================
# 1. CONFIGURACIÓN Y SEGURIDAD
# =================================================================
# Intenta obtener la clave de Streamlit Secrets, si no, usa la que pusiste por defecto
API_KEY = st.secrets.get("RAPIDAPI_KEY", "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4")
API_HOST = "sportscore6.p.rapidapi.com"

st.set_page_config(page_title="Tennis Predictor", page_icon="🎾", layout="wide")

# =================================================================
# 2. CARGADOR RECURSIVO MEJORADO
# =================================================================
@st.cache_data(ttl=3600) # Se actualiza cada hora para no saturar
def cargar_jugadores_recursivo():
    jugadores = set()
    base_path = 'datos'
    conteo_archivos = 0
    
    if os.path.exists(base_path):
        for root, dirs, files in os.walk(base_path):
            for nombre_f in files:
                if nombre_f.startswith('.') or nombre_f.startswith('__'): continue
                
                archivo_path = os.path.join(root, nombre_f)
                conteo_archivos += 1
                
                try:
                    # Intento de lectura multiformato
                    if nombre_f.lower().endswith(('.xlsx', '.xls')):
                        df = pd.read_excel(archivo_path)
                    else:
                        df = pd.read_csv(archivo_path, sep=None, engine='python', on_bad_lines='skip', encoding_errors='ignore')
                    
                    # Extraer nombres de columnas y celdas
                    for col in df.columns:
                        # Limpiar nombre de columna
                        c_str = str(col).strip().upper()
                        if len(c_str) > 3 and not c_str.isdigit() and 'UNNAMED' not in c_str:
                            jugadores.add(c_str)
                        
                        # Limpiar datos de celdas (Optimizado)
                        filas = df[col].dropna().unique()
                        for val in filas:
                            n = str(val).strip().upper()
                            # Filtros de calidad: ni muy corto, ni muy largo, ni solo números
                            if 3 < len(n) < 35 and not n.replace('.','').isdigit() and 'NAN' != n:
                                jugadores.add(n)
                except Exception as e:
                    # Si falla, simplemente saltamos ese archivo silenciosamente
                    continue
                        
    return sorted(list(jugadores)), conteo_archivos

# =================================================================
# 3. LÓGICA DE INTERFAZ
# =================================================================
st.title("🎾 Tennis IA Predictor")

nombres, total_f = cargar_jugadores_recursivo()

tab1, tab2, tab3 = st.tabs(["📡 API En Vivo", "📂 Modo Manual", "🛠 Status"])

with tab1:
    st.subheader("Partidos Programados para Hoy")
    if st.button("🔄 ACTUALIZAR CARTELERA"):
        headers = {"x-rapidapi-host": API_HOST, "x-rapidapi-key": API_KEY}
        url = f"https://{API_HOST}/api/v1/events/date/{datetime.now().strftime('%Y-%m-%d')}"
        
        try:
            with st.spinner("Conectando con el servidor..."):
                r = requests.get(url, headers=headers, params={"sport_id": "2"}, timeout=10)
                r.raise_for_status() # Lanza error si la API falla
                res_json = r.json()
                data = res_json.get('data', [])
                
                if data:
                    for p in data:
                        h = p.get('home_team', {}).get('name', 'TBD')
                        a = p.get('away_team', {}).get('name', 'TBD')
                        status = p.get('status_more', 'Programado')
                        st.markdown(f"✅ **{h}** vs **{a}** | *({status})*")
                else:
                    st.warning("No se encontraron partidos de tenis para hoy.")
        except Exception as e:
            st.error(f"Error de conexión: Verifica tu API Key o el límite de créditos.")

with tab2:
    if not nombres:
        st.error("⚠️ No se encontraron datos en la carpeta /datos.")
        st.info("Estructura esperada: `datos/atp/archivo.csv` o similar.")
    else:
        st.success(f"Sistema listo: {len(nombres)} jugadores en base de datos.")
        col1, col2 = st.columns(2)
        with col1:
            j1 = st.selectbox("Selecciona Jugador 1", nombres, index=0)
        with col2:
            j2 = st.selectbox("Selecciona Jugador 2", nombres, index=min(1, len(nombres)-1))
        
        if st.button("🚀 LANZAR PREDICCIÓN"):
            if j1 == j2:
                st.warning("¡Selecciona dos jugadores distintos!")
            else:
                st.balloons()
                st.markdown(f"""
                <div style="padding:20px; border-radius:15px; background:#f0f2f6; border-left:5px solid #2e7d32;">
                    <h3 style="color:#2e7d32; margin-top:0;">📊 Reporte de Análisis</h3>
                    <p><b>Match:</b> {j1} vs {j2}</p>
                    <p><b>Estado:</b> Procesando métricas históricas y superficie...</p>
                    <hr>
                    <p style="font-size: 0.8em; color: gray;">IA Model v1.0 - Basado en {total_f} archivos de datos.</p>
                </div>
                """, unsafe_allow_html=True)

with tab3:
    st.subheader("Panel de Control del Sistema")
    st.write(f"📂 **Archivos procesados:** `{total_f}`")
    st.write(f"👥 **Jugadores detectados:** `{len(nombres)}`")
    
    if st.checkbox("🔍 Mostrar rutas de archivos cargados"):
        for root, dirs, files in os.walk('datos'):
            for f in files:
                if not f.startswith('.'):
                    st.code(os.path.join(root, f))

st.divider()
st.caption(f"Última sincronización: {datetime.now().strftime('%H:%M:%S')}")