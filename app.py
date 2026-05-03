import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
from datetime import datetime

# =================================================================
# 1. CONFIGURACIÓN E INICIALIZACIÓN
# =================================================================
st.set_page_config(page_title="Tennis IA: Auditoría Pro", page_icon="🎯", layout="wide")

FILE_REGISTRO = "auditoria_tenis.csv"

def inicializar_db():
    if not os.path.exists(FILE_REGISTRO):
        df = pd.DataFrame(columns=["ID", "Fecha", "Partido", "Apuesta", "Prob_IA", "Resultado"])
        df.to_csv(FILE_REGISTRO, index=False)

def guardar_seleccion(partido, apuesta, prob):
    df = pd.read_csv(FILE_REGISTRO)
    nueva_fila = pd.DataFrame([{
        "ID": len(df) + 1,
        "Fecha": datetime.now().strftime("%d/%m/%Y"),
        "Partido": partido,
        "Apuesta": apuesta,
        "Prob_IA": f"{prob:.1%}",
        "Resultado": "Pendiente"
    }])
    pd.concat([df, nueva_fila], ignore_index=True).to_csv(FILE_REGISTRO, index=False)

# =================================================================
# 2. MOTOR LÓGICO (Recuperando tu limpieza de nombres original)
# =================================================================

def normalizar_nombre(n):
    if pd.isna(n): return ""
    n = str(n).upper()
    # Elimina números y caracteres raros para que solo quede el nombre
    n = re.sub(r'[^A-Z\s]', '', n)
    return " ".join(n.split())

@st.cache_data
def cargar_big_data():
    ruta_base = 'datos'
    stats_jugador = {} 
    if not os.path.exists(ruta_base): return {}
    for root, _, files in os.walk(ruta_base):
        folder_name = os.path.basename(root).upper()
        peso = 2.5 if 'ATP' in folder_name else (2.0 if 'WTA' in folder_name else 1.5)
        for f in files:
            try:
                path = os.path.join(root, f)
                df = pd.read_csv(path, engine='python') if f.endswith('.csv') else pd.read_excel(path)
                df.columns = df.columns.str.lower().str.strip()
                w_col = next((c for c in df.columns if 'winner' in c), None)
                l_col = next((c for c in df.columns if 'loser' in c), None)
                if w_col and l_col:
                    for _, row in df.iterrows():
                        # AQUI ESTÁ EL ARREGLO DE LOS NOMBRES
                        w = normalizar_nombre(row[w_col])
                        l = normalizar_nombre(row[l_col])
                        if not w or not l: continue
                        for p in [w, l]:
                            if p not in stats_jugador: stats_jugador[p] = {'power': 0}
                            stats_jugador[p]['power'] += (10 * peso) if p == w else (-6 / peso)
            except: continue
    return stats_jugador

def simular_set(p1_h, p2_h):
    j1, j2 = 0, 0
    srv = 1 if random.random() > 0.5 else 2
    while True:
        prob = p1_h if srv == 1 else (1 - p2_h)
        if random.random() < prob: j1 += 1
        else: j2 += 1
        if (j1 >= 6 or j2 >= 6) and abs(j1 - j2) >= 2: return j1, j2
        if j1 == 7 or j2 == 7: return j1, j2
        srv = 3 - srv

# =================================================================
# 3. INTERFAZ DE USUARIO
# =================================================================
inicializar_db()
stats_ia = cargar_big_data()
# Filtramos para que no aparezcan nombres vacíos
jugadores = sorted([j for j in stats_ia.keys() if len(j) > 2])

tab1, tab2 = st.tabs(["🚀 SIMULADOR", "📊 MI FIABILIDAD"])

with tab1:
    with st.sidebar:
        st.header("⚙️ Ajustes de Simulación")
        # HE RECUPERADO LAS SIMULACIONES
        n_sims = st.slider("Cantidad de simulaciones", 5000, 20000, 10000, step=1000)
        circ = st.selectbox("Nivel de Circuito", ["ATP", "WTA", "CHALLENGER"])
        surf = st.selectbox("Superficie", ["Dura", "Tierra", "Hierba"])
        linea_ou = st.number_input("Línea Over/Under", value=22.5, step=0.5)

    col1, col2 = st.columns(2)
    p1 = col1.selectbox("Elegir Jugador 1", jugadores, index=0)
    p2 = col2.selectbox("Elegir Jugador 2", jugadores, index=min(1, len(jugadores)-1))

    if st.button("🔥 EJECUTAR ANÁLISIS IA"):
        # Lógica de saque (puedes meter aquí tu fórmula de power_score)
        p1_h, p2_h = 0.72, 0.70 
        
        j_tot, s1_win, t_sets = [], 0, 0
        progreso = st.progress(0)
        
        for i in range(n_sims):
            if i % 1000 == 0: progreso.progress(i/n_sims)
            s1, s2, jt = 0, 0, 0
            while s1 < 2 and s2 < 2:
                res = simular_set(p1_h, p2_h)
                jt += (res[0] + res[1])
                if res[0] > res[1]: s1 += 1
                else: s2 += 1
            if s1 > s2: s1_win += 1
            if (s1 + s2) == 3: t_sets += 1
            j_tot.append(jt)
        
        progreso.empty()
        
        st.session_state.data = {
            'partido': f"{p1} vs {p2}",
            'p1': p1, 'p2': p2,
            'prob1': s1_win/n_sims, 'prob2': 1-(s1_win/n_sims),
            'over': sum(1 for j in j_tot if j > linea_ou)/n_sims,
            '3sets': t_sets/n_sims,
            'linea': linea_ou
        }

    if 'data' in st.session_state:
        d = st.session_state.data
        st.divider()
        c = st.columns(4)
        c[0].metric(f"Victoria {d['p1']}", f"{d['prob1']:.1%}")
        c[1].metric(f"Victoria {d['p2']}", f"{d['prob2']:.1%}")
        c[2].metric(f"Over {d['linea']}", f"{d['over']:.1%}")
        c[3].metric("Prob. 3 Sets", f"{d['3sets']:.1%}")

        st.subheader("📌 Registro de Auditoría")
        opciones = {
            f"Gana {d['p1']}": d['prob1'],
            f"Gana {d['p2']}": d['prob2'],
            f"Over {d['linea']}": d['over'],
            "Habrá 3 Sets": d['3sets']
        }
        eleccion = st.selectbox("¿Qué vas a apostar realmente?", list(opciones.keys()))
        if st.button("REGISTRAR PICK"):
            guardar_seleccion(d['partido'], eleccion, opciones[eleccion])
            st.success(f"Registrada apuesta a: {eleccion}")

with tab2:
    st.header("📊 Mi Historial de Aciertos")
    df = pd.read_csv(FILE_REGISTRO)
    
    if df.empty:
        st.info("No hay picks registrados.")
    else:
        # Panel para introducir el resultado
        pendientes = df[df["Resultado"] == "Pendiente"]
        if not pendientes.empty:
            with st.expander("✅ MARCAR RESULTADOS DE PARTIDOS TERMINADOS", expanded=True):
                id_sel = st.selectbox("ID de la apuesta", pendientes["ID"])
                res_final = st.radio("¿Se cumplió el pronóstico?", ["✅ ACERTADA", "❌ FALLADA"], horizontal=True)
                if st.button("ACTUALIZAR ESTADO"):
                    df.loc[df["ID"] == id_sel, "Resultado"] = res_final
                    df.to_csv(FILE_REGISTRO, index=False)
                    st.rerun()

        # KPIs de rendimiento
        finalizadas = df[df["Resultado"] != "Pendiente"]
        if not finalizadas.empty:
            aciertos = len(finalizadas[finalizadas["Resultado"] == "✅ ACERTADA"])
            ratio = (aciertos / len(finalizadas)) * 100
            
            k1, k2 = st.columns(2)
            k1.metric("TOTAL PRONÓSTICOS", len(finalizadas))
            k2.metric("FIABILIDAD IA", f"{ratio:.1f}%", f"{aciertos} aciertos")
        
        st.dataframe(df.sort_values("ID", ascending=False), use_container_width=True)