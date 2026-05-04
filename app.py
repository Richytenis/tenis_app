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
    # Eliminar espacios especiales de Excel (\xa0) y normalizar a espacio estándar
    n = str(n).replace('\xa0', ' ').replace('\u00a0', ' ')
    n = n.upper()
    n = re.sub(r'[^A-Z\s]', '', n)
    return " ".join(n.split()).strip()

def mapear_superficie(s):
    s = s.upper()
    if any(x in s for x in ["TIERRA", "CLAY", "ARCILLA"]): return "Clay"
    if any(x in s for x in ["HIERBA", "GRASS", "CESPED"]): return "Grass"
    return "Hard"

@st.cache_data
def cargar_base_elos():
    """Carga Elos específicos de archivos Excel y unifica la base de datos."""
    elos = {}
    # Rutas de los archivos proporcionados
    archivos = {"ATP": "atp_elo.xlsx", "WTA": "wta_elo.xlsx"}
    
    for circuito, ruta in archivos.items():
        if os.path.exists(ruta):
            try:
                df = pd.read_excel(ruta)
                # Limpiar nombres de columnas por si tienen espacios
                df.columns = df.columns.str.strip()
                
                for _, row in df.iterrows():
                    nombre_limpio = normalizar(row['Player'])
                    if nombre_limpio:
                        elos[nombre_limpio] = {
                            "Hard": row.get('hElo'),
                            "Clay": row.get('cElo'),
                            "Grass": row.get('gElo'),
                            "General": row.get('Elo'),
                            "Circuito": circuito
                        }
            except Exception as e:
                st.error(f"Error cargando {circuito}: {e}")
    return elos

# =========================================================
# MOTOR DE PROBABILIDAD Y SIMULACIÓN
# =========================================================
def calcular_probabilidad_base(j1, j2, superficie, elos):
    """Calcula la probabilidad de victoria usando la fórmula ELO oficial."""
    d1 = elos.get(j1, {"General": 1500})
    d2 = elos.get(j2, {"General": 1500})
    
    # Prioridad: ELO de superficie -> ELO General -> 1500 (base neutral)
    e1 = d1.get(superficie) or d1.get("General") or 1500
    e2 = d2.get(superficie) or d2.get("General") or 1500
    
    # Fórmula ELO: Prob = 1 / (1 + 10^((Elo2 - Elo1) / 400))
    prob_j1 = 1 / (1 + 10**((e2 - e1) / 400))
    return prob_j1, e1, e2

def obtener_hold_rate(e1, e2, circuito, superficie):
    """Determina la probabilidad de mantener el saque basándose en nivel y entorno."""
    # Bases estadísticas reales: ATP saca mejor que WTA; Clay tiene más quiebres.
    base = 0.81 if circuito == "ATP" else 0.66
    if superficie == "Clay": 
        base -= 0.07
    
    # Ajuste por diferencia de calidad entre jugadores
    diff = (e1 - e2) / 1200
    p1_hold = np.clip(base + diff, 0.35, 0.94)
    p2_hold = np.clip(base - diff, 0.35, 0.94)
    return p1_hold, p2_hold

def sim_set_profesional(p1_hold, p2_hold):
    """Simula un set completo alternando el servicio juego a juego."""
    g1 = g2 = 0
    sacador = 1 # Empieza sacando el Jugador 1
    
    while True:
        # Probabilidad de ganar el juego actual
        prob_ganar_juego = p1_hold if sacador == 1 else (1 - p2_hold)
        
        if random.random() < prob_ganar_juego:
            g1 += 1
        else:
            g2 += 1
        
        # Lógica de set: ganar por 2 (6-4) o llegar a 7 (7-5, 7-6)
        if (g1 >= 6 and g1-g2 >= 2) or g1 == 7: return g1, g2
        if (g2 >= 6 and g2-g1 >= 2) or g2 == 7: return g1, g2
        
        sacador = 3 - sacador # Cambia el turno de saque

# =========================================================
# INTERFAZ DE USUARIO (STREAMLIT)
# =========================================================
st.title("🎾 Tennis IA Predictor Ultra")
st.markdown("---")

# Carga de datos
base_elos = cargar_base_elos()
lista_jugadores = sorted(list(base_elos.keys()))

if not lista_jugadores:
    st.error("No se han podido cargar los jugadores. Verifica que 'atp_elo.xlsx' y 'wta_elo.xlsx' estén en el directorio.")
else:
    # Sidebar de configuración
    with st.sidebar:
        st.header("Ajustes de Simulación")
        superficie_ui = st.selectbox("Superficie", ["Tierra (Clay)", "Dura (Hard)", "Hierba (Grass)"])
        surf_key = mapear_superficie(superficie_ui)
        
        n_sims = st.select_slider("Número de Simulaciones", options=[5000, 10000, 20000], value=10000)
        linea_ou = st.number_input("Línea de Over/Under Juegos", value=21.5, step=0.5)

    # Selección de Jugadores
    col_a, col_b = st.columns(2)
    with col_a:
        j1 = st.selectbox("Jugador 1", lista_jugadores)
    with col_b:
        # Intentar seleccionar un segundo jugador distinto por defecto
        idx_j2 = 1 if len(lista_jugadores) > 1 else 0
        j2 = st.selectbox("Jugador 2", lista_jugadores, index=idx_j2)

    if st.button("🚀 CALCULAR PREDICCIÓN", use_container_width=True):
        # 1. Obtener datos base
        p_win_base, elo1, elo2 = calcular_probabilidad_base(j1, j2, surf_key, base_elos)
        circuito = base_elos[j1]["Circuito"]
        
        # 2. Calcular probabilidades de servicio
        h1, h2 = obtener_hold_rate(elo1, elo2, circuito, surf_key)
        
        # 3. Ejecutar Monte Carlo
        j1_wins = 0
        juegos_totales = []
        tres_sets = 0
        
        for _ in range(n_sims):
            s1 = s2 = 0
            games_in_match = 0
            while s1 < 2 and s2 < 2:
                g1, g2 = sim_set_profesional(h1, h2)
                games_in_match += (g1 + g2)
                if g1 > g2: s1 += 1
                else: s2 += 1
            
            if s1 == 2: j1_wins += 1
            if (s1 + s2) == 3: tres_sets += 1
            juegos_totales.append(games_in_match)

        # 4. Mostrar Resultados
        p_final_j1 = j1_wins / n_sims
        p_over = sum(g > linea_ou for g in juegos_totales) / n_sims
        
        st.divider()
        res1, res2, res3 = st.columns(3)
        
        with res1:
            st.metric(f"Victoria {j1}", f"{p_final_j1:.1%}")
            st.caption(f"Elo en {surf_key}: **{elo1:.0f}**")
            
        with res2:
            st.metric(f"Victoria {j2}", f"{1 - p_final_j1:.1%}")
            st.caption(f"Elo en {surf_key}: **{elo2:.0f}**")
            
        with res3:
            st.metric(f"Over {linea_ou} Juegos", f"{p_over:.1%}")
            st.progress(p_over)

        # Información Adicional
        st.write("---")
        info1, info2 = st.columns(2)
        with info1:
            st.write(f"**Probabilidad de 3 sets:** {tres_sets / n_sims:.1%}")
        with info2:
            promedio_juegos = sum(juegos_totales) / n_sims
            st.write(f"**Promedio de juegos estimado:** {promedio_juegos:.1f}")