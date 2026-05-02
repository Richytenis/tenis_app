import streamlit as st
import requests
from datetime import datetime

# =================================================================
# 1. CONFIGURACIÓN BASADA EN TU CURL
# =================================================================
API_KEY = "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4"
API_HOST = "sportscore6.p.rapidapi.com"  # <--- Cambiado según tu mensaje

st.set_page_config(page_title="Tennis Live", page_icon="🎾")

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background-color: #2e7d32; color: white; font-weight: bold; }
    .match-card { padding: 15px; border-radius: 12px; background-color: #ffffff; border: 1px solid #e0e0e0; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# =================================================================
# 2. FUNCIÓN DE CONEXIÓN
# =================================================================
def obtener_partidos():
    # En SportScore, la ruta para eventos de un deporte suele ser esta:
    url = f"https://{API_HOST}/api/sport/tennis/events/today"
    
    headers = {
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": API_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        # Probamos primero la ruta de hoy
        r = requests.get(url, headers=headers, timeout=10)
        
        # Si esa ruta no existe, probamos la genérica de eventos
        if r.status_code != 200:
            url_alt = f"https://{API_HOST}/api/events/date/{datetime.now().strftime('%Y-%m-%d')}"
            r = requests.get(url_alt, headers=headers, timeout=10)
            
        if r.status_code == 200:
            return r.json().get('data', [])
        else:
            st.error(f"Error {r.status_code}: {r.text}")
            return []
    except Exception as e:
        st.error(f"Fallo de conexión: {e}")
        return []

# =================================================================
# 3. INTERFAZ
# =================================================================
st.title("🎾 Tennis Live Predictor")

if st.button("🔄 BUSCAR PARTIDOS DE HOY"):
    with st.spinner("Cargando cartelera desde SportScore6..."):
        partidos = obtener_partidos()
        
        if not partidos:
            st.warning("No se encontraron partidos para hoy.")
            st.info("Verifica que en RapidAPI el deporte 'tennis' esté disponible para este host.")
        else:
            st.success(f"¡{len(partidos)} partidos encontrados!")
            
            for p in partidos:
                try:
                    # Estructura típica de SportScore: homeTeam y awayTeam
                    home = p.get('homeTeam', {}).get('name', 'Jugador 1')
                    away = p.get('awayTeam', {}).get('name', 'Jugador 2')
                    torneo = p.get('slug', 'Torneo')
                    ronda = p.get('status', {}).get('type', 'Programado')
                    
                    st.markdown(f"""
                    <div class="match-card">
                        <div style="color:gray; font-size:0.8em;">🏆 {torneo.upper()}</div>
                        <div style="font-size:1.1em; margin:5px 0;">
                            <strong>{home}</strong> vs <strong>{away}</strong>
                        </div>
                        <div style="color:#2e7d32; font-size:0.9em;">🟢 {ronda}</div>
                    </div>
                    """, unsafe_allow_html=True)
                except:
                    continue

st.divider()
st.caption(f"Conectado a: {API_HOST}")