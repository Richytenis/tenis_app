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
st.set_page_config(page_title="Tennis IA: Auditoría", page_icon="🎯", layout="wide")

# Archivo donde se guardará tu histórico para que no se borre al refrescar
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
# 2. MOTOR LÓGICO (Tu motor matemático)
# =================================================================

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
                        w, l = str(row[w_col]).upper(), str(row[l_col]).upper()
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
# 3. INTERFAZ DE USUARIO (2 PESTAÑAS)
# =================================================================
inicializar_db()
stats_ia = cargar_big_data()
jugadores = sorted(list(stats_ia.keys()))

tab1, tab2 = st.tabs(["🚀 SIMULADOR", "📊 MI FIABILIDAD"])

with tab1:
    col1, col2 = st.columns(2)
    p1 = col1.selectbox("Jugador 1", jugadores, index=0)
    p2 = col2.selectbox("Jugador 2", jugadores, index=min(1, len(jugadores)-1))
    
    with st.sidebar:
        st.header("Ajustes")
        circ = st.selectbox("Nivel", ["ATP", "WTA", "CHALLENGER"])
        surf = st.selectbox("Pista", ["Dura", "Tierra", "Hierba"])
        linea_ou = st.number_input("Línea O/U", value=22.5, step=0.5)

    if st.button("CALCULAR PROBABILIDADES"):
        # Lógica de simulación rápida
        p1_h, p2_h = 0.75, 0.72 # Simplificado para el ejemplo
        j_tot, s1_win, t_sets = [], 0, 0
        for _ in range(5000):
            set1 = simular_set(p1_h, p2_h)
            set2 = simular_set(p1_h, p2_h)
            jt = (set1[0]+set1[1]+set2[0]+set2[1])
            s1, s2 = (1,0) if set1[0]>set1[1] else (0,1)
            if set2[0]>set2[1]: s1+=1
            else: s2+=1
            if s1==1 and s2==1:
                set3 = simular_set(p1_h, p2_h)
                jt += (set3[0]+set3[1])
                t_sets += 1
                if set3[0]>set3[1]: s1+=1
            if s1 > s2: s1_win += 1
            j_tot.append(jt)
        
        st.session_state.data = {
            'partido': f"{p1} vs {p2}",
            'p1': p1, 'p2': p2,
            'prob1': s1_win/5000, 'prob2': 1-(s1_win/5000),
            'over': sum(1 for j in j_tot if j > linea_ou)/5000,
            '3sets': t_sets/5000,
            'linea': linea_ou
        }

    if 'data' in st.session_state:
        d = st.session_state.data
        st.divider()
        c = st.columns(4)
        c[0].metric(f"Gana {d['p1']}", f"{d['prob1']:.1%}")
        c[1].metric(f"Gana {d['p2']}", f"{d['prob2']:.1%}")
        c[2].metric(f"Over {d['linea']}", f"{d['over']:.1%}")
        c[3].metric("3 Sets", f"{d['3sets']:.1%}")

        st.subheader("📌 ¿A qué vas a apostar?")
        opciones = {
            f"Victoria {d['p1']}": d['prob1'],
            f"Victoria {d['p2']}": d['prob2'],
            f"Over {d['linea']} juegos": d['over'],
            "Habrá 3 Sets": d['3sets']
        }
        eleccion = st.selectbox("Selecciona tu apuesta real:", list(opciones.keys()))
        if st.button("REGISTRAR APUESTA"):
            guardar_seleccion(d['partido'], eleccion, opciones[eleccion])
            st.success("Guardado en la pestaña de Auditoría.")

with tab2:
    st.header("📊 Control de Aciertos")
    df = pd.read_csv(FILE_REGISTRO)
    
    if df.empty:
        st.info("Aún no has registrado ninguna apuesta.")
    else:
        # SECCIÓN PARA INTRODUCIR RESULTADOS
        pendientes = df[df["Resultado"] == "Pendiente"]
        if not pendientes.empty:
            with st.expander("📝 MARCAR RESULTADOS PENDIENTES", expanded=True):
                id_a_corregir = st.selectbox("ID de Apuesta", pendientes["ID"])
                res = st.radio("¿Qué ocurrió?", ["✅ ACERTADA", "❌ FALLADA"], horizontal=True)
                if st.button("ACTUALIZAR"):
                    df.loc[df["ID"] == id_a_corregir, "Resultado"] = res
                    df.to_csv(FILE_REGISTRO, index=False)
                    st.rerun()

        # ESTADÍSTICAS MÁSTRICAS
        finalizadas = df[df["Resultado"] != "Pendiente"]
        if not finalizadas.empty:
            aciertos = len(finalizadas[finalizadas["Resultado"] == "✅ ACERTADA"])
            total = len(finalizadas)
            st.metric("PORCENTAJE DE ACIERTO REAL", f"{(aciertos/total)*100:.1f}%", f"{aciertos} de {total} picks")
        
        st.subheader("Historial Completo")
        st.dataframe(df.sort_values("ID", ascending=False), use_container_width=True)

        if st.button("BORRAR TODO EL HISTORIAL"):
            os.remove(FILE_REGISTRO)
            st.rerun()