import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os

# =========================================================
# CONFIGURACIÓN DE PÁGINA
# =========================================================
st.set_page_config(page_title="Tennis IA Predictor Ultra", page_icon="🎾", layout="wide")

# =========================================================
# UTILIDADES DE LIMPIEZA Y CARGA
# =========================================================
def normalizar(n):
    """Limpia nombres eliminando espacios de no ruptura y caracteres especiales."""
    if pd.isna(n): return ""
    # Eliminar espacios especiales de Excel (\xa0)
    n = str(n).replace('\xa0', ' ').replace('\u00a0', ' ')
    n = n.upper()
    # Solo letras y espacios
    n = re.sub(r'[^A-Z\s]', '', n)
    return " ".join(n.split()).strip()

@st.cache_data
def cargar_base_elos():
    """Carga Elos específicos de subcarpetas datos/atp y datos/wta."""
    elos = {}
    # RUTAS ACTUALIZADAS A TUS SUBCARPETAS
    archivos = {
        "ATP": "datos/atp/atp_elo.xlsx", 
        "WTA": "datos/wta/wta_elo.xlsx"
    }
    errores = []
    
    for circuito, ruta in archivos.items():
        if os.path.exists(ruta):
            try:
                # Cargamos el Excel
                df = pd.read_excel(ruta, engine='openpyxl')
                
                # Limpiamos los nombres de las columnas (quitando \xa0)
                df.columns = [c.replace('\xa0', ' ').strip() for c in df.columns]
                
                # Columnas requeridas según tu archivo
                col_player = "Player"
                col_hard = "hElo"
                col_clay = "cElo"
                col_grass = "gElo"
                col_gen = "Elo"

                for _, row in df.iterrows():
                    nombre_limpio = normalizar(row[col_player])
                    if nombre_limpio:
                        elos[nombre_limpio] = {
                            "Hard": row.get(col_hard),
                            "Clay": row.get(col_clay),
                            "Grass": row.get(col_grass),
                            "General": row.get(col_gen),
                            "Circuito": circuito
                        }
            except Exception as e:
                errores.append(f"Error en {circuito} ({ruta}): {str(e)}")
        else:
            errores.append(f"Archivo no encontrado en la ruta: {ruta}")
            
    return elos, errores

def mapear_superficie(s):
    if "Tierra" in s: return "Clay"
    if "Hierba" in s: return "Grass"
    return "Hard"

# =========================================================
# MOTOR DE PROBABILIDAD Y SIMULACIÓN
# =========================================================
def calcular_probabilidad_base(j1, j2, superficie, elos):
    """Fórmula oficial ELO para determinar probabilidad de victoria."""
    d1 = elos.get(j1, {"General": 1500})
    d2 = elos.get(j2, {"General": 1500})
    
    # Prioridad: ELO de superficie -> ELO General -> 1500
    e1 = d1.get(superficie) or d1.get("General") or 1500
    e2 = d2.get(superficie) or d2.get("General") or 1500
    
    prob_j1 = 1 / (1 + 10**((e2 - e1) / 400))
    return prob_j1, e1, e2

def obtener_hold_rate(e1, e2, circuito, superficie):
    """Hold Rate dinámico para ATP/WTA y superficie."""
    base = 0.81 if circuito == "ATP" else 0.66
    if superficie == "Clay": 
        base -= 0.07
    
    # Ajuste por brecha de calidad
    diff = (e1 - e2) / 1200
    p1_hold = np.clip(base + diff, 0.35, 0.94)
    p2_hold = np.clip(base - diff, 0.35, 0.94)
    return p1_hold, p2_hold

def sim_set_profesional(p1_hold, p2_hold):
    """Simula un set juego a juego con alternancia de saque."""
    g1 = g2 = 0
    sacador = 1
    while True:
        prob = p1_hold if sacador == 1 else (1 - p2_hold)
        if random.random() < prob: g1 += 1
        else: g2 += 1
        
        if (g1 >= 6 and g1-g2 >= 2) or g1 == 7: return g1, g2
        if (g2 >= 6 and g2-g1 >= 2) or g2 == 7: return g1, g2
        sacador = 3 - sacador

# =========================================================
# INTERFAZ (UI)
# =========================================================
st.title("🎾 Tennis IA Predictor Ultra")

# Carga de datos con diagnóstico
base_elos, logs_error = cargar_base_elos()
lista_jugadores = sorted(list(base_elos.keys()))

if not lista_jugadores:
    st.error("❌ NO SE CARGARON JUGADORES")
    st.write("### Diagnóstico de rutas:")
    for err in logs_error:
        st.write(f"- {err}")
    st.info("Estructura de carpetas esperada:\n\n"
            "- tu_script.py\n"
            "- datos/\n"
            "  - atp/atp_elo.xlsx\n"
            "  - wta/wta_elo.xlsx")
else:
    with st.sidebar:
        st.header("⚙️ Configuración")
        superficie_ui = st.selectbox("Superficie", ["Dura (Hard)", "Tierra (Clay)", "Hierba (Grass)"])
        surf_key = mapear_superficie(superficie_ui)
        n_sims = st.select_slider("Simulaciones", options=[5000, 10000, 20000], value=10000)
        linea_ou = st.number_input("Línea O/U Juegos", value=21.5, step=0.5)

    col_j1, col_j2 = st.columns(2)
    with col_j1:
        j1 = st.selectbox("Jugador 1", lista_jugadores)
    with col_j2:
        j2 = st.selectbox("Jugador 2", lista_jugadores, index=min(1, len(lista_jugadores)-1))

    if st.button("🚀 CALCULAR PREDICCIÓN", use_container_width=True):
        p_win_base, elo1, elo2 = calcular_probabilidad_base(j1, j2, surf_key, base_elos)
        circuito = base_elos[j1]["Circuito"]
        h1, h2 = obtener_hold_rate(elo1, elo2, circuito, surf_key)
        
        wins_j1 = 0
        juegos = []
        sets_3 = 0
        
        # Barra de progreso
        prog = st.progress(0)
        for i in range(n_sims):
            s1 = s2 = 0
            match_games = 0
            while s1 < 2 and s2 < 2:
                g1, g2 = sim_set_profesional(h1, h2)
                match_games += (g1 + g2)
                if g1 > g2: s1 += 1
                else: s2 += 1
            
            if s1 == 2: wins_j1 += 1
            if (s1 + s2) == 3: sets_3 += 1
            juegos.append(match_games)
            if i % 1000 == 0: prog.progress(i/n_sims)
        prog.empty()

        # RESULTADOS
        st.divider()
        r1, r2, r3 = st.columns(3)
        
        with r1:
            st.metric(f"Ganador {j1}", f"{wins_j1/n_sims:.1%}")
            st.caption(f"Elo {surf_key}: {elo1:.1f}")
        
        with r2:
            st.metric(f"Ganador {j2}", f"{(n_sims-wins_j1)/n_sims:.1%}")
            st.caption(f"Elo {surf_key}: {elo2:.1f}")
            
        with r3:
            p_over = sum(g > linea_ou for g in juegos) / n_sims
            st.metric(f"Over {linea_ou}", f"{p_over:.1%}")
            st.progress(p_over)

        st.markdown(f"**Análisis Final:** Promedio juegos: **{sum(juegos)/n_sims:.1f}** | Probabilidad 3 sets: **{sets_3/n_sims:.1%}**")