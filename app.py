import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# =================================================================
# 1. CONFIGURACIÓN DE LA APP
# =================================================================
st.set_page_config(page_title="Tennis IA Live", page_icon="🎾")

# Mantén tus credenciales
API_KEY = "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4"
API_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"

st.title("🎾 Tennis Live Predictor")
st.markdown("---")

# =================================================================
# 2. FUNCIÓN CAZADORA DE PARTIDOS (DEBUG MODE)
# =================================================================
def obtener_partidos():
    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": API_HOST
    }
    
    # Intentamos los 3 endpoints que suelen tener los partidos de hoy
    endpoints = ["/matches", "/fixtures", "/live"]
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    
    for endpoint in endpoints:
        url = f"https://{API_HOST}{endpoint}"
        try:
            # Algunas APIs requieren 'date', otras no para el live
            params = {"date": fecha_hoy} if endpoint != "/live" else {}
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                # Extraemos la lista de partidos de donde sea que esté
                partidos = data.get('data', data.get('results', data.get('matches', [])))
                if isinstance(partidos, list) and len(partidos) > 0:
                    return partidos, endpoint
        except:
            continue
    return [], None

# =================================================================
# 3. INTERFAZ Y RENDERIZADO
# =================================================================
if st.button("🔄 CARGAR PARTIDOS DE HOY"):
    with st.spinner("Consultando cartelera real..."):
        partidos, endpoint_exitoso = obtener_partidos()
        
        if not partidos:
            st.error("⚠️ No se encontraron partidos activos.")
            st.warning("""
            **Diagnóstico de la API:**
            1. La suscripción gratuita de esta API puede estar limitada a estadísticas históricas.
            2. Es posible que hoy no haya partidos en los torneos que cubre esta API.
            3. Verifica en RapidAPI que el endpoint '/matches' devuelva datos en el 'Test Endpoint'.
            """)
        else:
            st.success(f"¡Conexión exitosa vía {endpoint_exitoso}!")
            st.write(f"Se han encontrado **{len(partidos)}** encuentros:")
            
            for p in partidos:
                # Intento de extraer nombres (flexible según la API)
                home = p.get('home_player', p.get('player1_name', p.get('player1', 'N/A')))
                away = p.get('away_player', p.get('player2_name', p.get('player2', 'N/A')))
                torneo = p.get('tournament_name', p.get('event_name', 'Torneo'))
                
                # Diseño de tarjeta para iPhone
                with st.container():
                    st.markdown(f"""
                    <div style="padding:15px; border-radius:10px; background-color:#f0f2f6; margin-bottom:10px; border-left: 5px solid #2e7d32;">
                        <small style="color:gray;">{torneo}</small><br>
                        <strong>{home}</strong> vs <strong>{away}</strong>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"Analizar IA", key=f"btn_{home}_{away}"):
                        st.write("✨ Calculando probabilidades...")

# =================================================================
# 4. PLAN B: SELECCIÓN MANUAL
# =================================================================
st.sidebar.title("Configuración")
if st.sidebar.button("Limpiar Caché"):
    st.cache_data.clear()
    st.rerun()