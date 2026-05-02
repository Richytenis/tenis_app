import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
from difflib import get_close_matches

# =================================================================
# 1. CONFIGURACIÓN DE LA APP (INTERFAZ MÓVIL)
# =================================================================
st.set_page_config(page_title="Tennis Predictor IA", page_icon="🎾", layout="centered")

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 10px; height: 3.5em; background-color: #2e7d32; color: white; font-weight: bold; }
    .reportview-container { background: #f0f2f6; }
    </style>
    """, unsafe_allow_html=True)

# =================================================================
# 2. UTILIDADES Y LÓGICA (TU CÓDIGO ORIGINAL)
# =================================================================
def normalizar(n):
    if pd.isna(n): return ""
    n = str(n).upper()
    n = re.sub(r'[^A-Z\s]', '', n)
    return " ".join(n.split())

def mapear_superficie(s):
    s = s.upper()
    if any(x in s for x in ['TIERRA', 'CLAY', 'ARCILLA']): return 'Clay'
    if any(x in s for x in ['HIERBA', 'GRASS', 'CESPED']): return 'Grass'
    return 'Hard'

def cargar_big_data():
    ruta_base = 'datos'
    stats_jugador = {} 
    if not os.path.exists(ruta_base): 
        return {}

    for root, _, files in os.walk(ruta_base):
        folder_name = os.path.basename(root).upper()
        peso_nivel = 1.0  
        if 'ATP' in folder_name: peso_nivel = 2.5
        elif 'WTA' in folder_name: peso_nivel = 2.0
        elif 'CHALLENGER' in folder_name: peso_nivel = 1.5

        for f in files:
            if not (f.endswith('.xlsx') or f.endswith('.csv')): continue
            try:
                path_completo = os.path.join(root, f)
                df = pd.read_csv(path_completo, engine='python') if f.endswith('.csv') else pd.read_excel(path_completo)
                df.columns = df.columns.str.lower().str.strip()
                
                w_col = next((c for c in df.columns if c in ['winner', 'winner_name']), None)
                l_col = next((c for c in df.columns if c in ['loser', 'loser_name']), None)
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

def calcular_poder_real(nombre, superficie, circuito, stats_ia):
    suelo_min = 1750 if circuito in ['ATP', 'WTA'] else 1400
    stats = stats_ia.get(nombre, {'power_score': 0, 'total': 0, 'surf_stats': {}})
    pts_score = stats['power_score']
    s_stats = stats['surf_stats'].get(superficie, {'wins': 0, 'total': 0})
    
    surf_bonus = 0
    if s_stats['total'] > 0:
        surf_rate = s_stats['wins'] / s_stats['total']
        surf_bonus = (surf_rate - 0.5) * 400
    
    poder_final = 1200 + pts_score + surf_bonus
    return max(poder_final, suelo_min)

def calcular_probabilidades_saque(pow1, pow2, superficie, circuito):
    if circuito == 'WTA':
        base_h = {'Clay': 0.58, 'Hard': 0.64, 'Grass': 0.70}.get(superficie, 0.62)
        suelo_tenis = 0.45
    else:
        base_h = {'Clay': 0.68, 'Hard': 0.76, 'Grass': 0.82}.get(superficie, 0.74)
        suelo_tenis = 0.55

    if pow1 <= 1410 and pow2 <= 1410:
        base_h -= 0.08
        suelo_tenis -= 0.10

    raw_diff = (pow1 - pow2)
    diff_log = np.sign(raw_diff) * (np.log1p(abs(raw_diff)) / 25) 
    
    p1_hold = base_h + (diff_log * 0.35)
    p2_hold = base_h - (diff_log * 0.35)
    
    return np.clip(p1_hold, suelo_tenis, 0.97), np.clip(p2_hold, suelo_tenis, 0.97)

def simular_set(p1_h, p2_h):
    j1, j2 = 0, 0
    servidor = 1 if random.random() > 0.5 else 2
    while True:
        prob = p1_h if servidor == 1 else (1 - p2_h)
        if random.random() < prob: j1 += 1
        else: j2 += 1
        if (j1 >= 6 or j2 >= 6) and abs(j1 - j2) >= 2: return j1, j2
        if j1 == 7 or j2 == 7: return j1, j2
        servidor = 3 - servidor

# =================================================================
# 3. MOTOR DE LA APP (CACHE)
# =================================================================
@st.cache_data
def obtener_datos_procesados():
    return cargar_big_data()

# =================================================================
# 4. INTERFAZ DE USUARIO (UI)
# =================================================================
st.title("🎾 Tennis IA Predictor")

stats_ia = obtener_datos_procesados()

if not stats_ia:
    st.error("❌ No se encontraron datos en la carpeta '/datos'. Verifica que los archivos estén en GitHub.")
else:
    # Sidebar / Opciones principales
    circ = st.selectbox("🏆 CIRCUITO", ["ATP", "WTA", "CHALLENGER"])
    surf_in = st.selectbox("🏟️ SUPERFICIE", ["Tierra", "Dura", "Hierba"])
    superficie = mapear_superficie(surf_in)

    lista_jugadores = sorted(list(stats_ia.keys()))
    p1_in = st.selectbox("👤 JUGADOR 1", lista_jugadores)
    p2_in = st.selectbox("👤 JUGADOR 2", lista_jugadores)

    if st.button("🚀 SIMULAR ENCUENTRO"):
        if p1_in == p2_in:
            st.warning("Selecciona dos jugadores distintos.")
        else:
            with st.spinner('Ejecutando 10,000 simulaciones...'):
                pow1 = calcular_poder_real(p1_in, superficie, circ, stats_ia)
                pow2 = calcular_poder_real(p2_in, superficie, circ, stats_ia)
                p1_h, p2_h = calcular_probabilidades_saque(pow1, pow2, superficie, circ)

                sims = 10000
                juegos_totales, sets_p1, tres_sets = [], 0, 0

                for _ in range(sims):
                    s1, s2, j_tot = 0, 0, 0
                    while s1 < 2 and s2 < 2:
                        res1, res2 = simular_set(p1_h, p2_h)
                        j_tot += (res1 + res2)
                        if res1 > res2: s1 += 1
                        else: s2 += 1
                    juegos_totales.append(j_tot)
                    if s1 == 2: sets_p1 += 1
                    if (s1 + s2) == 3: tres_sets += 1

                prob_p1 = sets_p1 / sims
                p_win = max(prob_p1, 1 - prob_p1)
                ganador_final = p1_in if prob_p1 > 0.5 else p2_in
                
                o18 = sum(1 for j in juegos_totales if j > 18.5) / sims
                u24 = sum(1 for j in juegos_totales if j < 24.5) / sims
                p3s = tres_sets / sims

                # Símbolos
                s_win = "🔥" if p_win > 0.85 else ("✅" if p_win > 0.75 else "")
                
                # Visualización de resultados
                st.divider()
                st.header(f"🏆 {ganador_final}")
                st.subheader(f"Probabilidad de victoria: {p_win:.1%} {s_win}")
                
                col1, col2 = st.columns(2)
                col1.metric("Prob. 3 Sets", f"{p3s:.1%}")
                col2.metric("Poder Dif.", f"{int(abs(pow1-pow2))}")
                
                st.divider()
                st.write("### 🎯 Mercado de Juegos")
                c_o, c_u = st.columns(2)
                c_o.metric("Over 18.5", f"{o18:.1%}")
                c_u.metric("Under 24.5", f"{u24:.1%}")

                if p_win > 0.85 and u24 > 0.65:
                    st.info("🌟 PRONÓSTICO PREMIUM: Victoria clara del favorito + Under de juegos.")
                elif p3s > 0.40 and o18 > 0.75:
                    st.info("🌟 PRONÓSTICO PREMIUM: Partido de alta intensidad / Over de juegos.")