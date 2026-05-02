import streamlit as st
import requests
from datetime import datetime

# =================================================================
# 1. CONFIGURACIÓN TOTAL (SportScore 6)
# =================================================================
st.set_page_config(page_title="Tennis Predictor PRO", page_icon="🎾")

API_KEY = "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4"
API_HOST = "sportscore6.p.rapidapi.com"

# Diseño Minimalista para iPhone
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background-color: #2e7d32; color: white; font-weight: bold; border: none; }
    .match-card { padding: 15px; border-radius: 12px; background-color: #ffffff; border: 1px solid #e0e0e0; margin-bottom: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
    .tour-name { color: #666; font-size: 0.75em; text-transform: uppercase; letter-spacing: 1px; }
    .vs-text { color: #2e7d32; font-weight: bold; font-size: 0.9em; }
    </style>
    """, unsafe_allow_html=True)

# =================================================================
# 2. MOTOR DE BÚSQUEDA MULTI-RUTA
# =================================================================
def buscar_partidos_hoy():
    headers = {
        "x-rapidapi-host": API_HOST,
        "x-rapidapi-key": API_KEY,
        "Content-Type": "application/json"
    }
    
    fecha = datetime.now().strftime('%Y-%m-%d')
    
    # Lista de rutas posibles ordenadas por probabilidad de éxito en v6
    intentos = [
        f"https://{API_HOST}/api/v1/events/date/{fecha}",
        f"https://{API_HOST}/api/event/date/{fecha}",
        f"https://{API_HOST}/api/v1/events"
    ]
    
    for url in intentos:
        try:
            # Parámetros para filtrar por Tenis (ID 2 o 5)
            params = {"sport_id": "2", "date": fecha}
            response = requests.get(url, headers=headers, params=params, timeout=8)
            
            if response.status_code == 200:
                data = response.json().get('data', [])
                if data:
                    return data, url # Retorna los datos y la ruta que funcionó
        except:
            continue
            
    return [], None

# =================================================================
# 3. INTERFAZ DE USUARIO
# =================================================================
st.title("🎾 Tennis Live Predictor")
st.caption(f"Server: {API_HOST} • {datetime.now().strftime('%d %b %Y')}")

if st.button("🔄 ACTUALIZAR CARTELERA"):
    with st.spinner("Buscando partidos activos..."):
        partidos, ruta_ok = buscar_partidos_hoy()
        
        if not partidos:
            st.error("No se encontraron partidos en las rutas conocidas.")
            st.info("💡 Si ya te suscribiste al plan Free, es posible que el ID del tenis sea diferente o no haya torneos hoy.")
        else:
            st.success(f"Conectado con éxito!")
            
            for p in partidos:
                try:
                    # Extracción segura de datos
                    h_team = p.get('home_team', {})
                    a_team = p.get('away_team', {})
                    
                    nombre1 = h_team.get('name', 'Jugador 1')
                    nombre2 = a_team.get('name', 'Jugador 2')
                    torneo = p.get('season', {}).get('name', 'Torneo ATP/WTA')
                    hora = p.get('start_at', '').split(' ')[-1][:5] # Toma HH:MM

                    # Renderizado de Tarjeta
                    st.markdown(f"""
                    <div class="match-card">
                        <div class="tour-name">🏆 {torneo}</div>
                        <div style="margin: 8px 0; font-size: 1.1em;">
                            <strong>{nombre1}</strong> <span class="vs-text">vs</span> <strong>{nombre2}</strong>
                        </div>
                        <div style="font-size: 0.85em; color: #888;">
                            ⏰ Inicio: {hora if hora else 'Verificar'}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                except Exception as e:
                    continue

st.divider()
st.caption("App diseñada para visualización rápida en dispositivos móviles.")