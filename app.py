import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
from datetime import datetime

# =================================================================
# 1. CONFIGURACIÓN Y PERSISTENCIA
# =================================================================
st.set_page_config(page_title="Tennis IA: Auditoría y Simulación", page_icon="🎾", layout="wide")

FILE_REGISTRO = "auditoria_tenis.csv"

def inicializar_db():
    if not os.path.exists(FILE_REGISTRO):
        pd.DataFrame(columns=["ID", "Fecha", "Partido", "Apuesta", "Prob_IA", "Resultado"]).to_csv(FILE_REGISTRO, index=False)

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
# 2. MOTOR LÓGICO (Power Score + Limpieza)
# =================================================================

def limpiar_nombre(n):
    if pd.isna(n): return ""
    n = str(n).upper().strip()
    # Quitar números iniciales y símbolos
    n = re.sub(r'^[0-9\-\.\s]+', '', n)
    n = re.sub(r'[^A-Z\s]', '', n)
    return " ".join(n.split())

@st.cache_data
def cargar_todo():
    ruta_base = 'datos'
    stats_jugador = {} 
    archivos_ok = 0
    if not os.path.exists(ruta_base): return {}, 0

    for root, _, files in os.walk(ruta_base):
        for f in files:
            if f.endswith(('.csv', '.xlsx', '.xls')):
                try:
                    path = os.path.join(root, f)
                    peso = 2.5 if 'ATP' in root.upper() else (2.0 if 'WTA' in root.upper() else 1.5)
                    
                    df = pd.read_csv(path, engine='python', on_bad_lines='skip', encoding_errors='ignore') if f.endswith('.csv') else pd.read_excel(path)
                    df.columns = [str(c).lower().strip() for c in df.columns]
                    
                    w_col = next((c for c in df.columns if 'winner' in c or 'ganador' in c), None)
                    l_col = next((c for c in df.columns if 'loser' in c or 'perdedor' in c), None)
                    surf_col = next((c for c in df.columns if 'surface' in c), 'surface')

                    if w_col and l_col:
                        archivos_ok += 1
                        for _, row in df.iterrows():
                            w, l = limpiar_nombre(row[w_col]), limpiar_nombre(row[l_col])
                            if len(w) < 2 or len(l) < 2: continue
                            
                            s_raw = str(row.get(surf_col, 'Hard')).upper()
                            surf = 'Clay' if 'CLAY' in s_raw or 'TIERRA' in s_raw else ('Grass' if 'GRASS' in s_raw or 'HIERBA' in s_raw else 'Hard')

                            for p in [w, l]:
                                if p not in stats_jugador: stats_jugador[p] = {'pwr': 0, 'surf': {}}
                                if surf not in stats_jugador[p]['surf']: stats_jugador[p]['surf'][surf] = {'w': 0, 't': 0}
                                stats_jugador[p]['surf'][surf]['t'] += 1
                                if p == w:
                                    stats_jugador[p]['pwr'] += (10 * peso)
                                    stats_jugador[p]['surf'][surf]['w'] += 1
                                else:
                                    stats_jugador[p]['pwr'] -= (6 / peso)
                except: continue
    return stats_jugador, archivos_ok

def calcular_pwr_real(nombre, superficie, circuito, stats_ia):
    s = stats_ia.get(nombre, {'pwr': 0, 'surf': {}})
    s_stats = s['surf'].get(superficie, {'w': 0, 't': 0})
    bonus = (s_stats['w']/s_stats['t'] - 0.5) * 400 if s_stats['t'] > 0 else 0
    base = 1750 if circuito in ['ATP', 'WTA'] else 1400
    return max(1200 + s['pwr'] + bonus, base)

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
# 3. INTERFAZ STREAMLIT
# =================================================================
inicializar_db()
stats_ia, n_archivos = cargar_todo()
jugadores = sorted(list(stats_ia.keys()))

tab1, tab2 = st.tabs(["🚀 SIMULADOR IA", "📊 AUDITORÍA DE ACIERTOS"])

with tab1:
    with st.sidebar:
        st.header("⚙️ Ajustes")
        st.info(f"📂 {n_archivos} archivos cargados.")
        n_sims = st.slider("Simulaciones", 5000, 20000, 10000, step=1000)
        circ = st.selectbox("Circuito", ["ATP", "WTA", "CHALLENGER"])
        surf_in = st.selectbox("Superficie", ["Dura", "Tierra", "Hierba"])
        linea_ou = st.number_input("Línea Over/Under", value=22.5, step=0.5)
        
        st.divider()
        busqueda = st.text_input("🔍 Buscar Jugador (ej: COULIBALY)")
        if busqueda:
            matches = [j for j in jugadores if busqueda.upper() in j]
            if matches: st.success(f"Encontrado: {matches[0]}")
            else: st.error("No encontrado")

    if not jugadores:
        st.warning("Sube archivos CSV/Excel a la carpeta 'datos'")
    else:
        # Lógica de pre-selección por búsqueda
        p1_idx = 0
        if busqueda:
            for i, j in enumerate(jugadores):
                if busqueda.upper() in j: 
                    p1_idx = i
                    break

        c1, c2 = st.columns(2)
        p1_sel = c1.selectbox("Jugador 1", jugadores, index=p1_idx)
        p2_sel = c2.selectbox("Jugador 2", jugadores, index=min(1, len(jugadores)-1))

        if st.button("🔥 EJECUTAR ANÁLISIS COMPLETO"):
            s_map = {'Dura': 'Hard', 'Tierra': 'Clay', 'Hierba': 'Grass'}[surf_in]
            pow1 = calcular_pwr_real(p1_sel, s_map, circ, stats_ia)
            pow2 = calcular_pwr_real(p2_sel, s_map, circ, stats_ia)
            
            # Cálculo de probabilidades de saque
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

            st.session_state.result = {
                'partido': f"{p1_sel} vs {p2_sel}",
                'p1': p1_sel, 'p2': p2_sel,
                'prob1': s1_win/n_sims, 'prob2': 1-(s1_win/n_sims),
                'over': sum(1 for j in j_tot if j > linea_ou)/n_sims,
                'under': sum(1 for j in j_tot if j < linea_ou)/n_sims,
                'sets': t_sets/n_sims, 'linea': linea_ou
            }

        if 'result' in st.session_state:
            res = st.session_state.result
            st.divider()
            m = st.columns(4)
            m[0].metric(f"Gana {res['p1']}", f"{res['prob1']:.1%}")
            m[1].metric(f"Gana {res['p2']}", f"{res['prob2']:.1%}")
            m[2].metric(f"Over {res['linea']}", f"{res['over']:.1%}")
            m[3].metric("3 Sets", f"{res['sets']:.1%}")

            with st.expander("📌 REGISTRAR PICK PARA AUDITORÍA"):
                opciones = {
                    f"Gana {res['p1']}": res['prob1'],
                    f"Gana {res['p2']}": res['prob2'],
                    f"Over {res['linea']}": res['over'],
                    f"Under {res['linea']}": res['under'],
                    "3 Sets": res['sets']
                }
                pick_sel = st.selectbox("Mercado apostado:", list(opciones.keys()))
                if st.button("GUARDAR EN HISTORIAL"):
                    guardar_seleccion(res['partido'], pick_sel, opciones[pick_sel])
                    st.toast("¡Pick registrado!")

with tab2:
    st.header("📊 Seguimiento de Fiabilidad")
    df_aud = pd.read_csv(FILE_REGISTRO)
    
    if df_aud.empty:
        st.info("No hay picks registrados para auditar.")
    else:
        # Cierre de picks
        pendientes = df_aud[df_aud["Resultado"] == "Pendiente"]
        if not pendientes.empty:
            with st.form("cierre_pick"):
                id_up = st.selectbox("ID del Pick", pendientes["ID"])
                status = st.radio("Resultado real:", ["✅ ACERTADA", "❌ FALLADA"], horizontal=True)
                if st.form_submit_button("ACTUALIZAR"):
                    df_aud.loc[df_aud["ID"] == id_up, "Resultado"] = status
                    df_aud.to_csv(FILE_REGISTRO, index=False)
                    st.rerun()

        # KPIs
        finalizados = df_aud[df_aud["Resultado"] != "Pendiente"]
        if not finalizados.empty:
            aciertos = len(finalizados[finalizados["Resultado"] == "✅ ACERTADA"])
            st.metric("TASA DE ACIERTO REAL", f"{(aciertos/len(finalizados))*100:.1%}", f"{aciertos} de {len(finalizados)}")
        
        st.dataframe(df_aud.sort_values("ID", ascending=False), use_container_width=True)
        
        if st.button("🗑️ Borrar Historial"):
            os.remove(FILE_REGISTRO)
            st.rerun()