import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os

# =========================================================
# CONFIGURACIÓN Y MOTOR (v5.7 - ASCII CLEANER)
# =========================================================
st.set_page_config(page_title="Tennis IA Predictor v5.7", page_icon="🎾", layout="wide")

def normalizar_texto(texto):
    if pd.isna(texto): return ""
    # Elimina espacios de no ruptura (\xa0), saltos de línea y espacios extra
    texto = str(texto).replace('\xa0', ' ').strip()
    texto = " ".join(texto.split()).upper()
    # Elimina caracteres especiales pero mantiene letras y espacios
    return re.sub(r'[^A-Z\s]', '', texto)

@st.cache_data
def cargar_base_elos():
    elos = {}
    archivos = {"ATP": "datos/atp/atp_elo.xlsx", "WTA": "datos/wta/wta_elo.xlsx"}
    for circuito, ruta in archivos.items():
        if os.path.exists(ruta):
            try:
                df = pd.read_excel(ruta, engine='openpyxl')
                
                # LIMPIEZA AGRESIVA DE COLUMNAS
                # Quitamos \xa0 y pasamos a mayúsculas para comparar fácil
                df.columns = [c.replace('\xa0', ' ').strip().upper() for c in df.columns]
                
                for _, row in df.iterrows():
                    # Normalizamos el nombre del jugador para la búsqueda
                    nombre_raw = row.get('PLAYER')
                    nombre_id = normalizar_texto(nombre_raw)
                    
                    if nombre_id:
                        # Buscamos específicamente ATP RANK o RANK
                        ranking = row.get('ATP RANK') or row.get('RANK') or 'N/A'
                        
                        elos[f"{nombre_id} ({circuito})"] = {
                            "Player": nombre_raw.replace('\xa0', ' '), # Nombre bonito para mostrar
                            "Rank": ranking,
                            "Hard": row.get('HELO'), 
                            "Clay": row.get('CELO'),
                            "Grass": row.get('GELO'), 
                            "General": row.get('ELO'), 
                            "Circuito": circuito
                        }
            except Exception as e:
                st.error(f"Error leyendo {circuito}: {e}")
    return elos

# --- MOTOR ATP CLÁSICO ---
def obtener_hold_rate(e1, e2, circuito_ui, superficie):
    if circuito_ui == "ATP":
        base = 0.81
        if superficie == "Clay": base -= 0.08
        elif superficie == "Grass": base += 0.04
        divisor = 850
        min_h = 0.25
    elif circuito_ui == "WTA":
        base = 0.74
        if superficie == "Clay": base -= 0.04
        divisor = 3500 
        min_h = 0.55
    else: # CHALLENGER
        base = 0.76 
        if superficie == "Clay": base -= 0.04
        divisor = 3000
        min_h = 0.45 
    
    diff = (e1 - e2) / divisor
    return np.clip(base + diff, min_h, 0.96), np.clip(base - diff, min_h, 0.96)

def sim_set(p1_h, p2_h):
    g1 = g2 = 0
    sacador = 1
    while True:
        boost = 0.02 if abs(g1 - g2) >= 2 else 0
        prob = (p1_h + boost) if sacador == 1 else (1 - p2_h - boost)
        if random.random() < prob: g1 += 1
        else: g2 += 1
        if (g1 >= 6 and g1-g2 >= 2) or g1 == 7: return g1, g2
        if (g2 >= 6 and g2-g1 >= 2) or g2 == 7: return g1, g2
        sacador = 3 - sacador

# =========================================================
# INTERFAZ
# =========================================================
base_elos = cargar_base_elos()

with st.sidebar:
    st.header("⚙️ Ajustes")
    circuito = st.selectbox("Circuito", ["ATP", "WTA", "CHALLENGER"])
    tag = "WTA" if circuito == "WTA" else "ATP"
    jugadores = sorted([k for k, v in base_elos.items() if v["Circuito"] == tag])
    nivel = st.radio("Nivel", ["Tour", "Grand Slam (5 sets)"])
    superficie = st.selectbox("Superficie", ["Clay", "Hard", "Grass"])
    n_sims = 10000

if not jugadores:
    st.error("⚠️ No hay datos. Revisa la carpeta /datos/")
else:
    c1, c2 = st.columns(2)
    with c1: j1_n = st.selectbox("Jugador 1", jugadores)
    with c2: j2_n = st.selectbox("Jugador 2", jugadores, index=min(1, len(jugadores)-1))

    if st.button("🚀 CALCULAR CON RANKING REAL", use_container_width=True):
        d1, d2 = base_elos[j1_n], base_elos[j2_n]
        e1 = d1.get(superficie) or d1.get("General") or 1500
        e2 = d2.get(superficie) or d2.get("General") or 1500
        h1, h2 = obtener_hold_rate(e1, e2, circuito, superficie)
        
        # --- LÍNEA DE VERIFICACIÓN ---
        st.divider()
        st.markdown("### 🔍 Verificación de Datos")
        col_d1, col_d2 = st.columns(2)
        
        # Limpieza de decimales para el ranking
        rank1 = str(d1['Rank']).split('.')[0] if d1['Rank'] != 'N/A' else 'N/A'
        rank2 = str(d2['Rank']).split('.')[0] if d2['Rank'] != 'N/A' else 'N/A'
        
        col_d1.metric(d1['Player'], f"ATP Rank: {rank1}")
        col_d1.caption(f"Elo {superficie}: {e1:.1f}")
        col_d2.metric(d2['Player'], f"ATP Rank: {rank2}")
        col_d2.caption(f"Elo {superficie}: {e2:.1f}")

        # --- SIMULACIÓN Y RESULTADOS (TUS TRES LÍNEAS) ---
        results = {"j1_win":0, "j1_set1":0, "j1_any":0, "j2_any":0, "games":[]}
        sets_n = 3 if (nivel == "Grand Slam (5 sets)" and circuito == "ATP") else 2
        
        for _ in range(n_sims):
            s1 = s2 = 0; g_m = 0
            while s1 < sets_n and s2 < sets_n:
                g1, g2 = sim_set(h1, h2)
                g_m += (g1 + g2)
                if (s1+s2) == 0 and g1 > g2: results["j1_set1"] += 1
                if g1 > g2: s1 += 1
                else: s2 += 1
            if s1 == sets_n: results["j1_win"] += 1
            if s1 >= 1: results["j1_any"] += 1
            if s2 >= 1: results["j2_any"] += 1
            results["games"].append(g_m)

        st.divider()
        st.markdown("#### 🏆 Victoria")
        v1, v2, v3 = st.columns(3)
        p1 = results["j1_win"]/n_sims
        v1.metric("Win P1", f"{p1:.1%}")
        v2.metric("Win P2", f"{(1-p1):.1%}")
        v3.metric("Favorito", d1['Player'] if p1 > 0.5 else d2['Player'])

        st.markdown("#### 📊 Over / Under")
        o1, o2, o3 = st.columns(3)
        o1.metric("Over 18.5", f"{sum(g > 18.5 for g in results['games'])/n_sims:.1%}")
        o2.metric("Over 19.5", f"{sum(g > 19.5 for g in results['games'])/n_sims:.1%}")
        o3.metric("Promedio Juegos", f"{sum(results['games'])/n_sims:.1f}")

        st.markdown("#### 🎾 Mercados de Sets")
        s1, s2, s3 = st.columns(3)
        s1.metric("1er Set P1", f"{results['j1_set1']/n_sims:.1%}")
        s2.metric("P1 gana +1 set", f"{results['j1_any']/n_sims:.1%}")
        s3.metric("P2 gana +1 set", f"{results['j2_any']/n_sims:.1%}")