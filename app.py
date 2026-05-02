import streamlit as st
import requests
from datetime import datetime

# =================================================================
# 1. CONFIGURACIÓN (SportScore 6)
# =================================================================
API_KEY = "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4"
API_HOST = "sportscore6.p.rapidapi.com"

st.set_page_config(page_title="Tennis Live Predictor", page_icon="🎾")

# --- Estilo Visual ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background-color: #2e7d32; color: white; font-weight: bold; }
    .match-card { padding: 15px; border-radius: 12px; background-color: #ffffff; border: 1px solid #e0e0e0; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# =================================================================
# 2. FUNCIÓN DE CONEXIÓN (Ruta específica SportScore 6)
# =================================================================
def obtener_partidos():
    # En SportScore 6, la ruta suele ser /api/event/list
    # El ID 2 suele ser Tenis, pero vamos a pedir la lista general del día
    url = f"https://{API_HOST}/api/event/list"
    
    headers = {
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": API_KEY,
        "Content-Type": "application/json"
    }
    
    # Parámetros comunes para este endpoint
    params = {
        "sport_id": "2",  # 2 = Tenis
        "date": datetime.now().strftime('%Y-%m-%d')
    }
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        
        if r.status_code == 200:
            # SportScore 6 a veces devuelve los datos dentro de 'data' o 'data' -> 'events'
            res = r.json()
            return res.get('data', [])
        else:
            # Si falla, probamos la ruta alternativa de 'actualidad'
            url_live = f"https://{API_HOST}/api/event/live"
            r_live = requests.get(url_live, headers=headers, params={"sport_id": "2"}, timeout=10)
            if r_live.status_code == 200:
                return r_live.json().get('data', [])
            
            st.error(f"Error {r.status_code}: La ruta no es correcta para este host.")
            return []
    except Exception as e:
        st.error(f"Fallo de conexión: {e}")
        return []

# =================================================================
# 3. INTERFAZ
# =================================================================
st.title("🎾 Tennis Live Predictor")

if st.button("🔄 BUSCAR PARTIDOS DE HOY"):
    with st.spinner("Consultando SportScore 6..."):
        partidos = obtener_partidos()
        
        if not partidos:
            st.warning("No hay partidos de tenis detectados hoy en esta ruta.")
            st.info("Prueba a revisar en el Playground de RapidAPI qué endpoint devuelve datos bajo 'Event'.")
        else:
            st.success(f"¡{len(partidos)} partidos encontrados!")
            
            for p in partidos:
                try:
                    # Ajuste de claves para SportScore 6
                    home = p.get('home_team', {}).get('name', 'N/A')
                    away = p.get('away_team', {}).get('name', 'N/A')
                    torneo = p.get('league', {}).get('name', 'Torneo')
                    
                    st.markdown(f"""
                    <div class="match-card">
                        <div style="color:gray; font-size:0.8em;">🏆 {torneo}</div>
                        <div style="font-size:1.1em; margin:5px 0;">
                            <strong>{home}</strong> vs <strong>{away}</strong>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                except:
                    continue

st.divider()
st.caption(f"Host: {API_HOST}")