import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# =================================================================
# 1. CONFIGURACIÓN
# =================================================================
st.set_page_config(page_title="Tennis IA Live", page_icon="🎾")

API_KEY = "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4"
API_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"

st.title("🎾 Tennis Live Predictor")

# =================================================================
# 2. MOTOR DE BÚSQUEDA DE PARTIDOS (LLAVE MAESTRA)
# =================================================================
def obtener_cartelera():
    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": API_HOST
    }
    
    # Probamos con Hoy y Mañana por si es un tema de zona horaria
    fechas_a_probar = [
        datetime.now().strftime('%Y-%m-%d'),
        (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    ]
    
    # Lista de rutas que existen en esa API
    rutas = ["/matches", "/fixtures", "/calendar"]
    
    for fecha in fechas_a_probar:
        for ruta in rutas:
            try:
                url = f"https://{API_HOST}{ruta}"
                response = requests.get(url, headers=headers, params={"date": fecha}, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    # Buscamos la lista de partidos en las claves típicas
                    partidos = data.get('data', data.get('results', []))
                    if partidos and len(partidos) > 0:
                        return partidos, fecha
            except:
                continue
    return [], None

# =================================================================
# 3. INTERFAZ DE USUARIO
# =================================================================
if st.button("🔄 BUSCAR PARTIDOS AHORA"):
    with st.spinner("Conectando con el servidor de tenis..."):
        partidos, fecha_encontrada = obtener_cartelera()
        
        if not partidos:
            st.error("⚠️ La API no devolvió partidos.")
            st.info("Esto sucede si no hay torneos ATP/WTA/ITF activos en este momento o si tu suscripción en RapidAPI no tiene acceso a la cartelera en vivo.")
        else:
            st.success(f"¡Se han encontrado {len(partidos)} partidos para la fecha: {fecha_encontrada}!")
            
            for p in partidos:
                # Extraer datos con nombres de campos flexibles
                j1 = p.get('home_player', p.get('player1_name', 'Jugador 1'))
                j2 = p.get('away_player', p.get('player2_name', 'Jugador 2'))
                torneo = p.get('tournament_name', 'Torneo')
                ronda = p.get('round', 'Match')
                
                # Mostrar tarjeta de partido
                with st.expander(f"🎾 {j1} vs {j2}"):
                    st.write(f"**🏆 Torneo:** {torneo}")
                    st.write(f"**📅 Ronda:** {ronda}")
                    
                    # Botón para simular (Si tienes tu lógica de IA, iría aquí)
                    if st.button("Simular Ganador", key=f"sim_{j1}_{fecha_encontrada}"):
                        st.info("Analizando estadísticas históricas...")
                        # Aquí puedes llamar a tu función de predicción