import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import requests
from difflib import get_close_matches

# =================================================================
# 1. CONFIGURACIÓN Y CREDENCIALES
# =================================================================
st.set_page_config(page_title="Tennis IA Live", page_icon="🎾", layout="centered")

# Credenciales de RapidAPI
API_KEY = "b6e30442c9mshea9fbba5c27adebp1fa8adjsn322f35fdd7f4"
API_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"

# Estilo CSS para mejorar la interfaz en iPhone
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background-color: #2e7d32; color: white; font-weight: bold; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { background-color: #f0f2f6; border-radius: 8px; padding: 10px; }
    .main { background-color: #ffffff; }
    </style>
    """, unsafe_allow_html=True)

# =================================================================
# 2. FUNCIONES DE PROCESAMIENTO DE DATOS
# =================================================================
def normalizar(n):
    if pd.isna(n): return ""
    n = str(n).upper()
    n = re.sub(r'[^A-Z\s]', '', n)
    return " ".join(n.split())

def mapear_superficie(s):
    s = str(s).upper() if s else "HARD"
    if any(x in s for x in ['TIERRA', 'CLAY', 'ARCILLA']): return 'Clay'
    if any(x in s for x in ['HIERBA', 'GRASS', 'CESPED']): return 'Grass'
    return 'Hard'

@st.cache_data
def cargar_big_data():
    ruta_base = 'datos'
    stats_jugador = {} 
    if not os.path.exists(ruta_base): return {}

    for root, _, files in os.walk(ruta_base):
        folder_name = os.path.basename(root).upper()
        # Peso según importancia del circuito
        peso_nivel = 2.5 if 'ATP' in folder_name else (2.0 if 'WTA' in folder_name else 1.5)

        for f in files:
            if not (f.endswith('.xlsx') or f.endswith('.csv')): continue
            try:
                df = pd.read_csv(os.path.join(root, f)) if f.endswith('.csv') else pd.read_excel(os.path.join(root, f))
                df.columns = df.columns.str.lower().str.strip()
                
                w_col = next((c for c in df.columns if 'winner' in c), None)
                l_col = next((c for c in df.columns if 'loser' in c), None)
                surf_col = next((c for c in df.columns if 'surface' in c), 'surface')

                if w_col and l_col:
                    for _, row in df.iterrows():
                        w, l = normalizar(row[w_col]), normalizar(row[l_col])
                        surf = mapear_superficie(str(row.get(surf_col, 'Hard')))
                        for p in [w, l]:
                            if p not in stats_jugador: 
                                stats_jugador[p] = {'power_score': 0, 'total': 0, 'surf_stats': {}}
                            stats_jugador[p]['total'] += 1
                            if surf not in stats_jugador[p]['surf_stats']:
                                stats_jugador[p]['surf_stats'][surf] = {'wins': 0, 'total': 0}
                            stats_jugador[p]['surf_stats'][surf]['total'] += 1
                            if p == w: 
                                stats_jugador[p]['power_score'] += (10 * peso_nivel)
                                stats_jugador[p]['surf_stats'][surf]['wins'] += 1
                            else:
                                stats_jugador[p]['power_score'] -= (6 / peso_nivel)
            except: continue
    return stats_jugador

# =================================================================
# 3. MOTOR DE SIMULACIÓN IA
# =================================================================
def simular_partido(p1, p2, superficie, circuito, stats_ia):
    def get_pow(nombre):
        s = stats_ia.get(nombre, {'power_score': 0, 'total': 0, 'surf_stats': {}})
        ss = s['surf_stats'].get(superficie, {'wins': 0, 'total': 0})
        bonus = (ss['wins']/ss['total'] - 0.5) * 400 if ss['total'] > 0 else 0
        base = 1750 if circuito in ['ATP', 'WTA'] else 1400
        return max(1200 + s['power_score'] + bonus, base)

    pow1, pow2 = get_pow(p1), get_pow(p2)
    base_h = 0.74 if circuito != 'WTA' else 0.64
    diff = (pow1 - pow2) / 1200
    p1_h = np.clip(base_h + diff, 0.50, 0.95)
    p2_h = np.clip(base_h - diff, 0.50, 0.95)

    sims = 5000
    p1_sets = 0
    juegos_totales = []
    
    for _ in range(sims):
        s1, s2, juegos = 0, 0, 0
        while s1 < 2 and s2 < 2:
            prob_set = p1_h / (p1_h + (1 - p2_h))
            if random.random() < prob_set: s1 += 1
            else: s2 += 1
            juegos += random.uniform(8.2, 12.8) # Simulación de juegos por set
        if s1 == 2: p1_sets += 1
        juegos_totales.append(juegos)

    return {
        'prob_p1': p1_sets / sims,
        'over18': sum(1 for j in juegos_totales if j > 18.5) / sims
    }

# =================================================================
# 4. CONEXIÓN API (SOLUCIÓN ERROR 404)
# =================================================================
def obtener_partidos_hoy():
    headers = {"X-RapidAPI-Key": API_KEY, "X-RapidAPI-Host": API_HOST}
    fecha_hoy = pd.Timestamp.now().strftime('%Y-%m-%d')
    
    # Probamos los 3 endpoints más comunes para esta API
    endpoints = ["/fixtures", "/calendar", "/matches"]
    
    for ep in endpoints:
        try:
            url = f"https://{API_HOST}{ep}"
            r = requests.get(url, headers=headers, params={"date": fecha_hoy}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                res = data.get('data', data.get('results', []))
                if res: return res
        except:
            continue
    return []

# =================================================================
# 5. INTERFAZ DE USUARIO (STREAMLIT)
# =================================================================
st.title("🎾 Tennis IA Predictor")

with st.spinner("Cargando base de datos..."):
    stats_ia = cargar_big_data()
    lista_jugadores = sorted(list(stats_ia.keys()))

if not stats_ia:
    st.error("❌ No se encontraron archivos en la carpeta /datos. Sube tus Excel/CSV primero.")
else:
    tab1, tab2 = st.tabs(["📅 PARTIDOS DE HOY", "⌨️ SELECCIÓN MANUAL"])

    with tab1:
        if st.button("🔄 BUSCAR PARTIDOS EN VIVO"):
            partidos = obtener_partidos_hoy()
            if not partidos:
                st.warning("No hay partidos disponibles en la API para hoy.")
            else:
                st.success(f"Se han encontrado {len(partidos)} partidos.")
                for m in partidos:
                    # Extraer nombres de la API (soporta varios formatos de respuesta)
                    p1_api = m.get('home_player', m.get('player_1_name', 'Jugador 1'))
                    p2_api = m.get('away_player', m.get('player_2_name', 'Jugador 2'))
                    surf_api = m.get('surface', 'Hard')
                    
                    # Búsqueda inteligente en tu base de datos
                    m1 = get_close_matches(normalizar(p1_api), lista_jugadores, n=1, cutoff=0.3)
                    m2 = get_close_matches(normalizar(p2_api), lista_jugadores, n=1, cutoff=0.3)
                    
                    if m1 and m2:
                        with st.expander(f"🎾 {m1[0]} vs {m2[0]}"):
                            st.caption(f"Superficie: {surf_api}")
                            if st.button(f"Analizar Partido", key=f"btn_{p1_api}"):
                                res = simular_partido(m1[0], m2[0], mapear_superficie(surf_api), 'ATP', stats_ia)
                                
                                g_fav = m1[0] if res['prob_p1'] > 0.5 else m2[0]
                                prob = res['prob_p1'] if res['prob_p1'] > 0.5 else 1 - res['prob_p1']
                                
                                c1, c2 = st.columns(2)
                                c1.metric("Favorito", g_fav, f"{prob:.1%}")
                                c2.metric("Over 18.5", f"{res['over18']:.1%}")
                    else:
                        st.text(f"⚪ {p1_api} vs {p2_api} (Faltan datos en historial)")

    with tab2:
        st.subheader("Simulación personalizada")
        col1, col2 = st.columns(2)
        jug1 = col1.selectbox("Selecciona Jugador 1", lista_jugadores)
        jug2 = col2.selectbox("Selecciona Jugador 2", lista_jugadores)
        
        superficie = st.selectbox("Superficie del partido", ["Dura", "Tierra", "Hierba"])
        circuito = st.selectbox("Categoría", ["ATP", "WTA", "Challenger"])

        if st.button("🚀 INICIAR SIMULACIÓN"):
            res = simular_partido(jug1, jug2, mapear_superficie(superficie), circuito, stats_ia)
            
            ganador = jug1 if res['prob_p1'] > 0.5 else jug2
            probabilidad = max(res['prob_p1'], 1 - res['prob_p1'])
            
            st.divider()
            st.markdown(f"### 🏆 Ganador estimado: **{ganador}**")
            st.progress(probabilidad)
            st.write(f"**Confianza de la IA:** {probabilidad:.1%}")
            st.write(f"**Probabilidad de Over 18.5 Juegos:** {res['over18']:.1%}")