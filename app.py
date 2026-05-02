import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# =================================================================
# 1. CONFIGURACIÓN
# =================================================================
st.set_page_config(page_title="Tennis IA Live", page_icon="🎾")

# CONFIGURACIÓN DE API (Verifica el Host en RapidAPI)
API_KEY = "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4"
API_HOST = "sportscore1.p.rapidapi.com" 

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background-color: #007bff; color: white; font-weight: bold; }
    .match-card { padding: 15px; border-radius: 12px; background-color: #ffffff; border: 1px solid #dee2e6; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .tournament-tag { color: #6c757d; font-size: 0.8em; text-transform: uppercase; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# =================================================================
# 2. FUNCIÓN CAZADORA DE EVENTOS
# =================================================================
def buscar_eventos_tenis():
    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": API_HOST
    }
    
    # Probamos los IDs más comunes para Tenis en SportScore (2 es el estándar, a veces 5)
    ids_tenis = [2, 5]
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    
    resultados_totales = []
    
    for sport_id in ids_tenis:
        url = f"https://{API_HOST}/sports/{sport_id}/events"
        try:
            r = requests.get(url, headers=headers, params={"date": fecha_hoy}, timeout=10)
            if r.status_code == 200:
                data = r.json().get('data', [])
                if data:
                    resultados_totales.extend(data)
            elif r.status_code == 403:
                return "ERROR_AUTH", []
        except:
            continue
            
    return "OK", resultados_totales

# =================================================================
# 3. INTERFAZ
# =================================================================
st.title("🎾 Tennis Live Predictor")
st.write("Conectado a SportScore API")

if st.button("🔄 ACTUALIZAR PARTIDOS"):
    with st.spinner("Buscando en los servidores..."):
        status, eventos = buscar_eventos_tenis()
        
        if status == "ERROR_AUTH":
            st.error("❌ Error de Autenticación (403)")
            st.info("Debes entrar a RapidAPI y pulsar el botón azul 'Subscribe to Test' en la API de Charlie Villa.")
        
        elif not eventos:
            st.warning("No se encontraron partidos para hoy.")
            st.info("Nota: Si estás usando el plan gratuito, algunas APIs limitan los resultados a torneos específicos.")
            
        else:
            st.success(f"Se han encontrado {len(eventos)} partidos.")
            for ev in eventos:
                try:
                    # Estructura SportScore: home_team y away_team son objetos
                    home = ev.get('home_team', {}).get('name', 'N/A')
                    away = ev.get('away_team', {}).get('name', 'N/A')
                    comp = ev.get('season', {}).get('name', 'Torneo')
                    status_text = ev.get('status_more', 'Programado')
                    hora = ev.get('start_at', '').split(' ')[-1] # Extrae la hora si existe

                    st.markdown(f"""
                    <div class="match-card">
                        <div class="tournament-tag">🏆 {comp}</div>
                        <div style="font-size: 1.1em; margin: 5px 0;">
                            <strong>{home}</strong> <span style="color:#adb5bd;">vs</span> <strong>{away}</strong>
                        </div>
                        <div style="color: #007bff; font-size: 0.9em;">
                            ⏱️ {hora} | 🟢 {status_text}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                except:
                    continue

st.divider()
st.caption(f"Host configurado: {API_HOST}")