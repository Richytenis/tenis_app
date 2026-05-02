import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# =================================================================
# 1. CONFIGURACIÓN Y CREDENCIALES (SportScore)
# =================================================================
st.set_page_config(page_title="Tennis SportScore Live", page_icon="🎾")

# SUSTITUYE AQUÍ TU API KEY SI ES DIFERENTE
API_KEY = "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4"
API_HOST = "sportscore1.p.rapidapi.com" # Verifica este Host en la pestaña de la API de Charlie Villa

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background-color: #1a73e8; color: white; font-weight: bold; }
    .match-box { padding: 15px; border-radius: 12px; background-color: #f1f3f4; border-left: 6px solid #1a73e8; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# =================================================================
# 2. FUNCIÓN DE CONEXIÓN A SPORTSCORE
# =================================================================
def obtener_partidos_sportscore():
    # El ID 2 suele corresponder a 'Tennis' en SportScore
    url = f"https://{API_HOST}/sports/2/events" 
    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": API_HOST
    }
    
    # Buscamos los de la fecha actual
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    params = {"date": fecha_hoy}
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            return r.json().get('data', [])
        return []
    except:
        return []

# =================================================================
# 3. INTERFAZ PRINCIPAL
# =================================================================
st.title("🎾 SportScore Live")
st.write("Cartelera de tenis actualizada en tiempo real.")

if st.button("🔄 CARGAR CARTELERA DE HOY"):
    with st.spinner("Conectando con SportScore..."):
        eventos = obtener_partidos_sportscore()
        
        if not eventos:
            st.warning("No se encontraron eventos de tenis para hoy.")
            st.info("Asegúrate de estar suscrito al plan (aunque sea el gratuito) de la API de Charlie Villa.")
        else:
            st.success(f"¡{len(eventos)} partidos encontrados!")
            
            for ev in eventos:
                # SportScore suele usar 'home_team' y 'away_team' con una subclave 'name'
                try:
                    home = ev.get('home_team', {}).get('name', 'Jugador 1')
                    away = ev.get('away_team', {}).get('name', 'Jugador 2')
                    torneo = ev.get('season', {}).get('name', 'Torneo')
                    estado = ev.get('status_more', 'Programado')
                    
                    st.markdown(f"""
                    <div class="match-box">
                        <small style="color:#5f6368;">{torneo}</small><br>
                        <strong>{home}</strong> vs <strong>{away}</strong><br>
                        <small style="color:#1a73e8;">Estado: {estado}</small>
                    </div>
                    """, unsafe_allow_html=True)
                except:
                    continue

st.divider()
st.caption("Nota: Si el Host es diferente, cámbialo en la línea 14 del código.")