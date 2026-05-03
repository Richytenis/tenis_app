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
st.set_page_config(page_title="Tennis IA: Auditoría Total", page_icon="🎯", layout="wide")

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
# 2. MOTOR LÓGICO (RECUPERADO Y MEJORADO)
# =================================================================

def normalizar_nombre(n):
    if pd.isna(n): return ""
    n = str(n).upper().strip()
    # Mantenemos letras y espacios, pero permitimos nombres cortos
    n = re.sub(r'[^A-Z\s]', '', n)
    return " ".join(n.split())

@st.cache_data
def cargar_big_data():
    ruta_base = 'datos'
    stats_jugador = {} 
    if not os.path.exists(ruta_base): return {}
    
    for root, _, files in os.walk(ruta_base):
        folder_name = os.path.basename(root).upper()
        # Peso por nivel de torneo
        peso = 2.5 if 'ATP' in folder_name else (2.0 if 'WTA' in folder_name else 1.5)
        
        for f in files:
            if not (f.endswith('.xlsx') or f.endswith('.csv')): continue
            try:
                path = os.path.join(root, f)
                df = pd.read_csv(path, engine='python', on_bad_lines='skip') if f.endswith('.csv') else pd.read_excel(path)
                df.columns = df.columns.str.lower().str.strip()
                
                w_col = next((c for c in df.columns if 'winner' in c), None)
                l_col = next((c for c in df.columns if 'loser' in c), None)
                surf_col = next((c for c in df.columns if 'surface' in c), 'surface')

                if w_col and l_col:
                    for _, row in df.iterrows():
                        w = normalizar_nombre(row[w_col])
                        l = normalizar_nombre(row[l_col])
                        if not w or not l: continue
                        
                        # Superficie
                        s_raw = str(row.get(surf_col, 'Hard')).upper()
                        surf = 'Clay' if 'CLAY' in s_raw or 'TIERRA' in s_raw else ('Grass' if 'GRASS' in s_raw or 'HIERBA' in s_raw else 'Hard')

                        for p in [w, l]:
                            if p not in stats_jugador: 
                                stats_jugador[p] = {'power': 0, 'surf_stats': {}}
                            
                            if surf not in stats_jugador[p]['surf_stats']:
                                stats_jugador[p]['surf_stats'][surf] = {'w': 0, 't': 0}
                            
                            stats_jugador[p]['surf_stats'][surf]['t'] += 1
                            if p == w:
                                stats_jugador[p]['power'] += (10 * peso)
                                stats_jugador[p]['surf_stats'][surf]['w'] += 1
                            else:
                                stats_jugador[p]['power'] -= (6 / peso)
            except: continue
    return stats_jugador

def calcular_poder_real(nombre, superficie, circuito, stats_ia):
    stats = stats_ia.get(nombre, {'power': 0, 'surf_stats': {}})
    s_stats = stats['surf_stats'].get(superficie, {'w': 0, 't': 0})
    surf_bonus = (s_stats['w'] / s_stats['t'] - 0.5) * 400 if s_stats['t'] > 0 else 0
    base = 1750 if circuito in ['ATP', 'WTA'] else 1400
    return max(1200 + stats['power'] + surf_bonus, base)

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
# 3. INTERFAZ (Pestañas y Selectores)
# =================================================================
inicializar_db()
stats_ia = cargar_big_data()
# Permite nombres de al menos 3 letras para no perder a nadie
jugadores = sorted([j for j in stats_ia.keys() if len(j) >= 3])

tab1, tab2 = st.tabs(["🚀 SIMULADOR", "📊 MI FIABILIDAD"])

with tab1:
    with st.sidebar:
        st.header("⚙️ Ajustes")
        n_sims = st.slider("Simulaciones", 5000, 20000, 10000, step=1000)
        circ = st.selectbox("Circuito", ["ATP", "WTA", "CHALLENGER"])
        surf_in = st.selectbox("Superficie", ["Dura", "Tierra", "Hierba"])
        linea_ou = st.number_input("Línea Over/Under", value=22.5, step=0.5)

    c1, c2 = st.columns(2)
    p1_name = c1.selectbox("Jugador 1", jugadores, index=0)
    p2_name = c2.selectbox("Jugador 2", jugadores, index=min(1, len(jugadores)-1))

    if st.button("🔥 EJECUTAR ANÁLISIS"):
        surf_map = {'Dura': 'Hard', 'Tierra': 'Clay', 'Hierba': 'Grass'}[surf_in]
        pow1 = calcular_poder_real(p1_name, surf_map, circ, stats_ia)
        pow2 = calcular_poder_real(p2_name, surf_map, circ, stats_ia)
        
        # Probabilidades de saque basadas en Power Score
        diff = (pow1 - pow2) / 25
        base_s = 0.65 if circ == 'WTA' else 0.74
        p1_h = np.clip(base_s + (diff * 0.05), 0.50, 0.95)
        p2_h = np.clip(base_s - (diff * 0.05), 0.50, 0.95)

        j_tot, s1_win, t_sets = [], 0, 0
        bar = st.progress(0)
        for i in range(n_sims):
            if i % 1000 == 0: bar.progress(i/n_sims)
            s1, s2, jt = 0, 0, 0
            while s1 < 2 and s2 < 2:
                r1, r2 = simular_set(p1_h, p2_h)
                jt += (r1 + r2)
                if r1 > r2: s1 += 1
                else: s2 += 1
            if s1 > s2: s1_win += 1
            if (s1 + s2) == 3: t_sets += 1
            j_tot.append(jt)
        bar.empty()

        st.session_state.res = {
            'partido': f"{p1_name} vs {p2_name}",
            'p1': p1_name, 'p2': p2_name,
            'prob1': s1_win/n_sims, 'prob2': 1-(s1_win/n_sims),
            'over': sum(1 for j in j_tot if j > linea_ou)/n_sims,
            'under': sum(1 for j in j_tot if j < linea_ou)/n_sims,
            'sets': t_sets/n_sims, 'linea': linea_ou
        }

    if 'res' in st.session_state:
        r = st.session_state.res
        st.divider()
        col_res = st.columns(4)
        col_res[0].metric(f"Gana {r['p1']}", f"{r['prob1']:.1%}")
        col_res[1].metric(f"Gana {r['p2']}", f"{r['prob2']:.1%}")
        col_res[2].metric(f"Over {r['linea']}", f"{r['over']:.1%}")
        col_res[3].metric("3 Sets", f"{r['sets']:.1%}")

        with st.expander("📌 REGISTRAR APUESTA REALIZADA"):
            opc = {f"Gana {r['p1']}": r['prob1'], f"Gana {r['p2']}": r['prob2'], 
                   f"Over {r['linea']}": r['over'], f"Under {r['linea']}": r['under'], "3 Sets": r['sets']}
            pick = st.selectbox("Mercado:", list(opc.keys()))
            if st.button("GUARDAR EN AUDITORÍA"):
                guardar_seleccion(r['partido'], pick, opc[pick])
                st.toast("Guardado!")

with tab2:
    st.header("📊 Auditoría de Aciertos")
    df = pd.read_csv(FILE_REGISTRO)
    if df.empty: st.info("Sin registros.")
    else:
        pendientes = df[df["Resultado"] == "Pendiente"]
        if not pendientes.empty:
            with st.form("cierre"):
                id_s = st.selectbox("ID Pick", pendientes["ID"])
                res = st.radio("¿Resultado?", ["✅ ACERTADA", "❌ FALLADA"], horizontal=True)
                if st.form_submit_button("Cerrar Pick"):
                    df.loc[df["ID"] == id_s, "Resultado"] = res
                    df.to_csv(FILE_REGISTRO, index=False)
                    st.rerun()

        finalizadas = df[df["Resultado"] != "Pendiente"]
        if not finalizadas.empty:
            ok = len(finalizadas[finalizadas["Resultado"] == "✅ ACERTADA"])
            st.metric("FIABILIDAD REAL", f"{(ok/len(finalizadas))*100:.1f}%", f"{ok}/{len(finalizadas)}")
        st.dataframe(df.sort_values("ID", ascending=False), use_container_width=True)