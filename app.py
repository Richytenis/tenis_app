import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import requests
from datetime import datetime, timedelta
from difflib import get_close_matches

# =================================================================
# 1. CONFIGURACIÓN
# =================================================================
st.set_page_config(page_title="Tennis IA Ultra", page_icon="🎾")

API_KEY = "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4"
API_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"

# =================================================================
# 2. CARGA DE DATOS (REFORZADA)
# =================================================================
@st.cache_data
def cargar_big_data():
    ruta_base = 'datos'
    stats_jugador = {} 
    if not os.path.exists(ruta_base): return {}
    for root, _, files in os.walk(ruta_base):
        folder_name = os.path.basename(root).upper()
        peso = 2.5 if 'ATP' in folder_name else (2.0 if 'WTA' in folder_name else 1.0)
        for f in files:
            try:
                df = pd.read_csv(os.path.join(root, f)) if f.endswith('.csv') else pd.read_excel(os.path.join(root, f))
                df.columns = df.columns.str.lower().str.strip()
                w_col = next((c for c in df.columns if 'winner' in c), None)
                l_col = next((c for c in df.columns if 'loser' in c), None)
                if w_col and l_col:
                    for _, row in df.iterrows():
                        w, l = str(row[w_col]).upper(), str(row[l_col]).upper()
                        if w not in stats_jugador: stats_jugador[w] = 1500
                        if l not in stats_jugador[l]: stats_jugador[l] = 1500
                        stats_jugador[w] += (10 * peso)
                        stats_jugador[l] -= (5 / peso)
            except: continue
    return stats_jugador

# =================================================================
# 3. CONEXIÓN API "CAZADORA"
# =================================================================
def buscar_partidos_en_api(modo):
    headers = {"X-RapidAPI-Key": API_KEY, "X-RapidAPI-Host": API_HOST}
    
    # Calculamos fechas
    hoy = datetime.now().strftime('%Y-%m-%d')
    manana = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    fecha_target = hoy if modo == "Hoy" else manana

    # Lista de posibles rutas que esa API suele usar
    rutas_a_probar = []
    if modo == "En Vivo":
        rutas_a_probar = ["/live", "/matches/live", "/fixtures/live"]
    else:
        # Probamos con parámetros 'date' y 'day' que son comunes
        rutas_a_probar = [
            f"/fixtures?date={fecha_target}",
            f"/matches?date={fecha_target}",
            f"/calendar?date={fecha_target}",
            f"/fixtures?day={fecha_target}"
        ]

    for ruta in rutas_a_probar:
        url = f"https://{API_HOST}{ruta}"
        try:
            r = requests.get(url, headers=headers, timeout=8)
            if r.status_code == 200:
                data = r.json()
                # Buscamos la lista de partidos en cualquier clave común
                for clave in ['data', 'results', 'matches', 'fixtures']:
                    if clave in data and isinstance(data[clave], list) and len(data[clave]) > 0:
                        return data[clave]
                # Si el JSON es una lista directa
                if isinstance(data, list) and len(data) > 0:
                    return data
        except: continue
    return []

# =================================================================
# 4. INTERFAZ
# =================================================================
st.title("🎾 Tennis IA Predictor")
stats_ia = cargar_big_data()
nombres_db = list(stats_ia.keys())

menu = st.radio("Selecciona temporalidad:", ["En Vivo", "Hoy", "Mañana"], horizontal=True)

if st.button("🔄 BUSCAR PARTIDOS"):
    with st.spinner("Cazando partidos..."):
        partidos = buscar_partidos_en_api(menu)
        
        if not partidos:
            st.error(f"No hay datos para {menu}. Intenta con otra opción.")
        else:
            st.success(f"¡Se han encontrado {len(partidos)} partidos!")
            for p in partidos:
                # Intentamos sacar nombres de cualquier clave posible
                n1 = p.get('home_player', p.get('player_1_name', p.get('player1', 'Unknown')))
                n2 = p.get('away_player', p.get('player_2_name', p.get('player2', 'Unknown')))
                
                # Búsqueda difusa (MUY PERMISIVA para iPhone)
                match1 = get_close_matches(str(n1).upper(), nombres_db, n=1, cutoff=0.2)
                match2 = get_close_matches(str(n2).upper(), nombres_db, n=1, cutoff=0.2)
                
                if match1 and match2:
                    with st.expander(f"✅ {match1[0]} vs {match2[0]}"):
                        p1, p2 = match1[0], match2[0]
                        prob = 1 / (1 + 10 ** ((stats_ia[p2] - stats_ia[p1]) / 400))
                        st.write(f"**Favorito:** {p1 if prob > 0.5 else p2}")
                        st.write(f"**Probabilidad:** {max(prob, 1-prob):.1%}")
                else:
                    st.text(f"⚪ {n1} vs {n2} (Sin datos históricos)")

st.divider()
st.caption("Si la API falla, usa la selección manual en tu carpeta de datos.")