import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
from difflib import get_close_matches

# Configuración para que se vea bien en móviles
st.set_page_config(page_title="Tennis IA", page_icon="🎾", layout="centered")

# Estilos visuales rápidos
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 10px; height: 3.5em; background-color: #2e7d32; color: white; font-weight: bold; }
    .main { background-color: #f8f9fa; }
    </style>
    """, unsafe_allow_html=True)

# --- TUS FUNCIONES LÓGICAS (Normalizar, Cargar, Calcular...) ---
# (Pega aquí tus funciones: normalizar, mapear_superficie, cargar_big_data, etc.)
# Nota: Asegúrate de añadir @st.cache_data antes de cargar_big_data para que vaya rápido.

@st.cache_data
def cargar_datos_app():
    # Aquí va tu función cargar_big_data() original
    # ...
    return stats_ia

# --- INTERFAZ DE LA APP ---
st.title("🎾 Tennis IA Predictor")

stats_ia = cargar_datos_app()

if not stats_ia:
    st.error("⚠️ No se encontraron datos en la carpeta /datos")
else:
    # Selectores adaptados a móvil
    circuito = st.selectbox("🏆 Circuito", ["ATP", "WTA", "CHALLENGER"])
    superficie_ui = st.selectbox("🏟️ Superficie", ["Tierra", "Dura", "Hierba"])
    
    lista_jugadores = sorted(list(stats_ia.keys()))
    p1 = st.selectbox("👤 Jugador 1", lista_jugadores)
    p2 = st.selectbox("👤 Jugador 2", lista_jugadores)

    if st.button("🚀 SIMULAR PARTIDO"):
        # Realizamos la simulación (tu lógica de 10,000 ciclos)
        with st.spinner('Calculando probabilidades...'):
            # (Aquí va tu bloque de simulación de 10.000 ciclos)
            # ...
            
            # MOSTRAR RESULTADOS
            st.divider()
            ganador = p1 if prob_p1 > 0.5 else p2
            st.success(f"### Ganador Estimado: {ganador}")
            
            c1, c2 = st.columns(2)
            c1.metric("Confianza", f"{p_win:.1%}")
            c2.metric("Prob. 3 Sets", f"{p3s:.1%}")
            
            st.metric("🎯 Over 18.5 Juegos", f"{o18:.1%}")

            if p_win > 0.85: st.info("🔥 PRONÓSTICO PREMIUM: Victoria clara")