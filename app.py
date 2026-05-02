import streamlit as st
import requests
from datetime import datetime

# =================================================================
# 1. CREDENCIALES EXACTAS
# =================================================================
API_KEY = "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4"
API_HOST = "sportscore6.p.rapidapi.com"

st.set_page_config(page_title="Tennis IA Live", page_icon="🎾")

# --- Estilo para el iPhone ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background-color: #1a73e8; color: white; font-weight: bold; }
    .match-card { padding: 15px; border-radius: 12px; background-color: #f8f9fa; border-left: 5px solid #1a73e8; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# =================================================================
# 2. FUNCIÓN DE CONEXIÓN (Estructura v6)
# =================================================================
def obtener_datos():
    headers = {
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": API_KEY
    }
    
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    
    # En la v6, la ruta de eventos suele ser /api/event o /api/events
    # Intentamos la ruta más común de esta versión:
    url = f"https://{API_HOST}/api/events/date/{fecha_hoy}"
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
        
        # Si da 404, probamos la ruta de 'list' con el prefijo /api/
        if r.status_code == 404:
            url_alt = f"https://{API_HOST}/api/event/list"
            r = requests.get(url_alt, headers=headers, params={"sport_id": "2", "date": fecha_hoy}, timeout=10)
            
        if r.status_code == 200:
            return r.json().get('data', [])
        else:
            st.error(f"Error {r.status_code}: La API no reconoce la ruta.")
            return []
    except Exception as e:
        st.error(f"Fallo: {e}")
        return []

# =================================================================
# 3. INTERFAZ
# =================================================================
st.title("🎾 Tennis Live Predictor")

if st.button("🔄 CARGAR PARTIDOS DE HOY"):
    with st.spinner("Conectando con SportScore 6..."):
        partidos = obtener_datos()
        
        if not partidos:
            st.warning("No se encontraron partidos.")
            st.info("💡 Consejo: Entra al Playground de RapidAPI y copia el 'Request URL' del endpoint que te funcione (probablemente 'Events by Date').")
        else:
            st.success(f"¡{len(partidos)} partidos encontrados!")
            for p in partidos:
                # SportScore 6 usa nombres con guiones bajos
                home = p.get('home_team', {}).get('name', 'N/A')
                away = p.get('away_team', {}).get('name', 'N/A')
                torneo = p.get('season', {}).get('name', 'Torneo')
                
                with st.container():
                    st.markdown(f"""
                    <div class="match-card">
                        <small style="color:gray;">{torneo}</small><br>
                        <strong>{home}</strong> vs <strong>{away}</strong>
                    </div>
                    """, unsafe_allow_html=True)

st.divider()
st.caption(f"Host: {API_HOST}")