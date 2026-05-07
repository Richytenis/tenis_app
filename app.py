import streamlit as st
import pandas as pd
import numpy as np
import random
import re
import os
import unicodedata

# =========================================================
# MOTOR v9.0 - THE STRATEGIST (Calibrated & Realistic)
# =========================================================
st.set_page_config(page_title="Tennis IA Predictor v9.0", page_icon="🎾", layout="wide")

st.markdown("""
<style>
    .metric-card {
        background: #1e1e2e;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
        border: 1px solid #313244;
    }
    .metric-label { color: #a6adc8; font-size: 0.8rem; margin-bottom: 4px; }
    .metric-value { color: #cdd6f4; font-size: 1.6rem; font-weight: bold; }
    .metric-sub { color: #6c7086; font-size: 0.75rem; margin-top: 4px; }
    .prob-bar-container {
        background: #313244; border-radius: 8px; height: 28px;
        overflow: hidden; margin: 8px 0;
    }
    .prob-bar-fill {
        height: 100%; border-radius: 8px;
        display: flex; align-items: center; justify-content: center;
        font-weight: bold; font-size: 0.9rem; color: white;
        transition: width 0.5s ease;
    }
    .insight-box {
        padding: 12px 16px; border-radius: 8px;
        margin: 8px 0; font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────
def limpieza_extrema(texto):
    if pd.isna(texto): return ""
    t = unicodedata.normalize('NFKD', str(texto)).encode('ascii', 'ignore').decode('ascii')
    t = re.sub(r'\[.*?\]|\(.*?\)', '', t)
    return re.sub(r'[^A-Z0-9]', '', t.upper())

def elo_to_prob(elo1, elo2):
    """Probabilidad logística estándar Elo. Sin mezclas arbitrarias."""
    return 1.0 / (1.0 + 10 ** ((elo2 - elo1) / 400.0))


# ─────────────────────────────────────────────
# CARGA DE DATOS
# ─────────────────────────────────────────────
@st.cache_data
def cargar_todo():
    base_datos = {}
    stats_detalladas = {}

    if os.path.exists('atp_completa.xlsx'):
        df_s = pd.read_excel('atp_completa.xlsx')
        for _, row in df_s.iterrows():
            nid = limpieza_extrema(row.get('Player'))
            try:
                stats_detalladas[nid] = {
                    "ace":  float(str(row.get('Ace%', '5')).replace('%', '')) / 100,
                    "df":   float(str(row.get('DF%',  '3')).replace('%', '')) / 100,
                    "1in":  float(str(row.get('1stIn','62')).replace('%', '')) / 100,
                    "1w":   float(str(row.get('1st%', '72')).replace('%', '')) / 100,
                    "2w":   float(str(row.get('2nd%', '50')).replace('%', '')) / 100,
                    # Forma reciente (0-100 si existe en el Excel)
                    "form": float(str(row.get('Form', '50')).replace('%', ''))
                }
            except:
                pass

    if os.path.exists('atp_elo.xlsx'):
        df_elo = pd.read_excel('atp_elo.xlsx')
        df_elo.columns = [limpieza_extrema(c) for c in df_elo.columns]
        for _, row in df_elo.iterrows():
            nombre_raw = str(row.get('PLAYER', 'Unknown')).replace('\xa0', ' ').strip()
            nid = limpieza_extrema(nombre_raw)
            s = stats_detalladas.get(nid, {})

            elos_raw = [row.get('HELO'), row.get('CELO'), row.get('GELO'), row.get('ELO')]
            elos_val = [float(e) for e in elos_raw
                        if e is not None and str(e).replace('.', '').replace('-', '').isdigit()]
            max_e = max(elos_val) if elos_val else 1500

            # Intentar leer ranking ATP para ajuste de forma
            try:
                atp_rank = int(float(str(row.get('ATPRANK', 100))))
            except:
                atp_rank = 100

            base_datos[nombre_raw] = {
                "Player":  nombre_raw,
                "Rank":    str(row.get('ATPRANK', 'N/A')).replace('.0', ''),
                "RankNum": atp_rank,
                "Hard":    row.get('HELO') or row.get('ELO'),
                "Clay":    row.get('CELO') or row.get('ELO'),
                "Grass":   row.get('GELO') or row.get('ELO'),
                "General": row.get('ELO', 1500),
                "MaxElo":  max_e,
                "Stats":   s
            }
    return base_datos


# ─────────────────────────────────────────────
# MOTOR DE SIMULACIÓN MEJORADO
# ─────────────────────────────────────────────

# Factores de superficie calibrados con histórico ATP
SURFACE_ACE_MOD  = {"Hard": 1.0,  "Clay": 0.70, "Grass": 1.30}
SURFACE_DF_MOD   = {"Hard": 1.0,  "Clay": 0.85, "Grass": 1.10}
SURFACE_1W_MOD   = {"Hard": 1.0,  "Clay": 0.95, "Grass": 1.05}
# En clay los sets duran más → penalización de fatiga más agresiva
SURFACE_FATIGUE  = {"Hard": 0.97, "Clay": 0.94, "Grass": 0.98}

def prob_punto_saque(stats, elo_adj, surface):
    """
    Probabilidad de que el sacador gane el punto.
    Devuelve p_ganar_con_primer, p_ganar_con_segundo, p_primer_dentro, p_doble_falta
    """
    surf_ace = SURFACE_ACE_MOD[surface]
    surf_df  = SURFACE_DF_MOD[surface]
    surf_1w  = SURFACE_1W_MOD[surface]

    p_ace = np.clip(stats.get('ace', 0.05) * surf_ace, 0.0, 0.25)
    p_df  = np.clip(stats.get('df',  0.03) * surf_df,  0.0, 0.10)
    p_in  = np.clip(stats.get('1in', 0.62),             0.40, 0.80)
    p_w1  = np.clip(stats.get('1w',  0.70) * surf_1w + elo_adj, 0.20, 0.95)
    p_w2  = np.clip(stats.get('2w',  0.50)            + elo_adj * 0.6, 0.15, 0.88)

    return p_ace, p_df, p_in, p_w1, p_w2


def sim_game(serve_stats, return_stats, elo_adj, surface):
    """Simula un juego completo punto a punto. Devuelve 1 si gana sacador."""
    p_ace, p_df, p_in, p_w1, p_w2 = prob_punto_saque(serve_stats, elo_adj, surface)

    sp = rp = 0  # puntos sacador / restador
    while True:
        r = random.random()
        if r < p_ace:
            sp += 1
        elif r < p_ace + p_df:
            rp += 1
        else:
            r2 = random.random()
            if r2 < p_in:   # primer servicio dentro
                sp += 1 if random.random() < p_w1 else None
                if r2 < p_in:
                    if random.random() < p_w1: sp += 1
                    else: rp += 1
            else:            # segundo servicio
                if random.random() < p_w2: sp += 1
                else: rp += 1

        # Condición de victoria (deuce)
        if sp >= 4 and sp - rp >= 2: return 1
        if rp >= 4 and rp - sp >= 2: return 0


def calc_momentum(breaks_concedidos, sets_perdidos, is_decisive_set, surface):
    """
    Momentum más rico:
    - Fatiga por breaks consecutivos concedidos
    - Penalización mayor si se va perdiendo de sets
    - Presión extra en set decisivo
    """
    fatigue_base = SURFACE_FATIGUE[surface]
    fatigue = fatigue_base ** breaks_concedidos   # cada break pesa
    set_penalty = 0.96 ** sets_perdidos           # ir perdiendo sets acumula presión
    decisive_bonus = 0.97 if is_decisive_set else 1.0
    return np.clip(fatigue * set_penalty * decisive_bonus, 0.5, 1.0)


def sim_set(d1, d2, elo_diff_base, surface, sets1, sets2, sets_to_win):
    """
    Simula un set completo.
    Devuelve (games_j1, games_j2)
    """
    g1 = g2 = 0
    breaks1 = breaks2 = 0   # breaks concedidos por cada jugador en este set
    sacador = 1 if random.random() > 0.5 else 2

    is_decisive = (sets1 + 1 == sets_to_win and sets2 + 1 == sets_to_win)

    while True:
        mom1 = calc_momentum(breaks1, sets2, is_decisive, surface)  # presión sobre j1
        mom2 = calc_momentum(breaks2, sets1, is_decisive, surface)

        # elo_adj varía con momentum relativo
        elo_adj = (elo_diff_base / 4200) * (mom1 / mom2)

        if sacador == 1:
            resultado = sim_game(d1.get('Stats', {}), d2.get('Stats', {}),  elo_adj, surface)
            if resultado: g1 += 1
            else:         g2 += 1; breaks1 += 1
        else:
            resultado = sim_game(d2.get('Stats', {}), d1.get('Stats', {}), -elo_adj, surface)
            if resultado: g2 += 1
            else:         g1 += 1; breaks2 += 1

        sacador = 3 - sacador

        # Condición set normal o tie-break (7-6)
        if g1 >= 6 and g1 - g2 >= 2: return g1, g2
        if g2 >= 6 and g2 - g1 >= 2: return g1, g2
        if g1 == 6 and g2 == 6:
            # Tie-break: resultado rápido por Elo
            p_tb = elo_to_prob(
                d1.get('General', 1500) + elo_diff_base * 0.5,
                d2.get('General', 1500)
            )
            if random.random() < p_tb: return 7, 6
            else:                      return 6, 7


def sim_partido(d1, d2, e1, e2, superficie, sets_to_win, n=10000):
    """
    Simulación Monte Carlo completa.
    Devuelve diccionario de resultados.
    """
    elo_diff = e1 - e2

    # Ajuste por forma reciente (columna Form si existe)
    form1 = d1.get('Stats', {}).get('form', 50)
    form2 = d2.get('Stats', {}).get('form', 50)
    form_adj = (form1 - form2) / 1000.0  # impacto suave

    # Ajuste por diferencia de ranking (proxy de forma si no hay Form)
    rank1 = d1.get('RankNum', 50)
    rank2 = d2.get('RankNum', 50)
    rank_adj = np.clip((rank2 - rank1) / 2000.0, -0.05, 0.05)

    elo_diff_final = elo_diff + (form_adj + rank_adj) * 400  # escalar a unidades Elo

    res = {
        "j1_w": 0, "j2_w": 0,
        "j1_s1": 0, "j2_s1": 0,
        "j1_any": 0, "j2_any": 0,
        "set3": 0, "set5": 0,
        "over18": 0, "over19": 0, "over20": 0, "over21": 0,
        "gms": [],
        "scores": {}   # distribución de marcadores
    }

    for _ in range(n):
        s1 = s2 = gt = 0
        set_n = 0

        while s1 < sets_to_win and s2 < sets_to_win:
            g1, g2 = sim_set(d1, d2, elo_diff_final, superficie, s1, s2, sets_to_win)
            gt += g1 + g2
            if set_n == 0:
                if g1 > g2: res["j1_s1"] += 1
                else:       res["j2_s1"] += 1
            if g1 > g2: s1 += 1
            else:        s2 += 1
            set_n += 1

        score_str = f"{s1}-{s2}"
        res["scores"][score_str] = res["scores"].get(score_str, 0) + 1

        if s1 == sets_to_win: res["j1_w"] += 1
        else:                  res["j2_w"] += 1
        if s1 >= 1: res["j1_any"] += 1
        if s2 >= 1: res["j2_any"] += 1
        if gt > 18.5: res["over18"] += 1
        if gt > 19.5: res["over19"] += 1
        if gt > 20.5: res["over20"] += 1
        if gt > 21.5: res["over21"] += 1
        if set_n >= 3: res["set3"] += 1
        if set_n >= 5: res["set5"] += 1
        res["gms"].append(gt)

    return res


# ─────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────
base_datos = cargar_todo()

with st.sidebar:
    st.header("🎾 Tennis IA v9.0")
    st.caption("Motor Monte Carlo calibrado con Elo por superficie")
    lista = sorted(list(base_datos.keys()))
    superficie = st.selectbox("Superficie", ["Hard", "Clay", "Grass"])
    formato    = st.radio("Formato", ["Tour (3 sets)", "Grand Slam (5 sets)"])
    n_sims     = st.select_slider("Simulaciones", [5000, 10000, 20000], value=10000)
    st.divider()
    st.caption("v9.0 · Mejoras: Elo calibrado, momentum multifactor, form reciente, mercados recalibrados")

if not lista:
    st.error("No se encontraron datos. Asegúrate de tener atp_elo.xlsx en el directorio.")
    st.stop()

c1, c2 = st.columns(2)
with c1: j1_n = st.selectbox("Jugador 1", lista)
with c2: j2_n = st.selectbox("Jugador 2", lista, index=min(1, len(lista)-1))

if st.button("🚀 ANALIZAR PARTIDO", use_container_width=True, type="primary"):

    d1 = base_datos[j1_n]
    d2 = base_datos[j2_n]
    e1 = float(d1.get(superficie) or d1.get("General") or 1500)
    e2 = float(d2.get(superficie) or d2.get("General") or 1500)
    sets_to_win = 3 if "5 sets" in formato else 2

    # ── Insights previos ─────────────────────────────
    a1 = (d1['MaxElo'] - e1) > 85
    a2 = (d2['MaxElo'] - e2) > 85

    with st.container():
        if a1 and a2:
            st.warning("⚠️ **Doble riesgo de colapso:** Ambos jugadores rinden por debajo de su techo histórico en esta superficie. Partido impredecible.")
        elif a1:
            st.warning(f"⚠️ **Riesgo:** {d1['Player']} rinde históricamente peor en {superficie} "
                       f"({e1:.0f} Elo vs máximo {d1['MaxElo']:.0f}). Vulnerable si pierde el primer set.")
        elif a2:
            st.warning(f"⚠️ **Riesgo:** {d2['Player']} rinde históricamente peor en {superficie} "
                       f"({e2:.0f} Elo vs máximo {d2['MaxElo']:.0f}). Vulnerable si pierde el primer set.")
        else:
            st.info(f"💡 **Duelo de especialistas en {superficie}:** Ambos rinden cerca de su techo histórico. "
                    "Se espera partido competitivo con games largos.")

        # Diferencia de ranking como indicador de forma
        r1, r2 = d1.get('RankNum', 999), d2.get('RankNum', 999)
        if abs(r1 - r2) > 30:
            mejor = d1['Player'] if r1 < r2 else d2['Player']
            st.info(f"📈 **Diferencia de ranking notable** (#{r1} vs #{r2}): {mejor} llega con mejor forma reciente según ranking ATP.")

    # ── Simulación ───────────────────────────────────
    with st.spinner(f"Simulando {n_sims:,} partidos..."):
        res = sim_partido(d1, d2, e1, e2, superficie, sets_to_win, n=n_sims)

    # Probabilidad final: puramente Elo calibrado (sin mezcla arbitraria)
    p1 = res["j1_w"] / n_sims
    p2 = res["j2_w"] / n_sims

    # ── Probabilidad de Victoria ──────────────────────
    st.divider()
    st.subheader("🏆 Probabilidad de Victoria")

    col1, col2 = st.columns(2)
    elo_ref = elo_to_prob(e1, e2)

    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{d1['Player']}</div>
            <div class="metric-value">{p1:.1%}</div>
            <div class="metric-sub">Rank ATP #{d1['Rank']} · Elo {superficie}: {e1:.0f}</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{d2['Player']}</div>
            <div class="metric-value">{p2:.1%}</div>
            <div class="metric-sub">Rank ATP #{d2['Rank']} · Elo {superficie}: {e2:.0f}</div>
        </div>
        """, unsafe_allow_html=True)

    # Barra visual de probabilidad
    pct = int(p1 * 100)
    color1 = "#89b4fa"; color2 = "#f38ba8"
    st.markdown(f"""
    <div style="margin: 12px 0 4px 0; font-size: 0.8rem; color: #a6adc8;">
        {d1['Player']} {pct}% ←→ {100-pct}% {d2['Player']}
    </div>
    <div class="prob-bar-container">
        <div class="prob-bar-fill" style="width:{pct}%; background: linear-gradient(90deg, {color1}, {color2}); justify-content: flex-start; padding-left: 8px;">
            {'◀' if pct > 15 else ''}
        </div>
    </div>
    <div style="font-size:0.75rem; color:#6c7086; margin-top:4px;">
        Referencia Elo puro: {elo_ref:.1%} / {1-elo_ref:.1%}
    </div>
    """, unsafe_allow_html=True)

    # ── Distribución de Marcadores ────────────────────
    st.divider()
    st.subheader("📋 Distribución de Marcadores")
    scores_sorted = sorted(res["scores"].items(), key=lambda x: -x[1])
    cols = st.columns(min(len(scores_sorted), 4))
    for i, (score, count) in enumerate(scores_sorted[:4]):
        with cols[i]:
            winner = d1['Player'] if score.split('-')[0] > score.split('-')[1] else d2['Player']
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{winner}</div>
                <div class="metric-value">{score}</div>
                <div class="metric-sub">{count/n_sims:.1%} de partidos</div>
            </div>
            """, unsafe_allow_html=True)

    # ── Sets ──────────────────────────────────────────
    st.divider()
    st.subheader("🎾 Análisis de Sets")
    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    metrics_sets = [
        ("3er Set", f"{res['set3']/n_sims:.1%}", "Prob. de llegar al 3er set", sc1),
        ("1er Set →P1", f"{res['j1_s1']/n_sims:.1%}", f"Gana {d1['Player']}", sc2),
        ("1er Set →P2", f"{res['j2_s1']/n_sims:.1%}", f"Gana {d2['Player']}", sc3),
        ("P1 gana 1 set", f"{res['j1_any']/n_sims:.1%}", "Al menos 1 set", sc4),
        ("P2 gana 1 set", f"{res['j2_any']/n_sims:.1%}", "Al menos 1 set", sc5),
    ]
    for label, value, sub, col in metrics_sets:
        with col:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-value">{value}</div>
                <div class="metric-sub">{sub}</div>
            </div>
            """, unsafe_allow_html=True)

    if "5 sets" in formato:
        st.caption(f"5º Set: {res['set5']/n_sims:.1%} de probabilidad")

    # ── Mercados de Games ─────────────────────────────
    st.divider()
    st.subheader("📊 Mercados de Games Totales")

    avg_games = np.mean(res["gms"])
    med_games = np.median(res["gms"])
    std_games = np.std(res["gms"])

    gm1, gm2, gm3, gm4, gm5, gm6 = st.columns(6)
    mercados = [
        ("Over 18.5", res["over18"]/n_sims, gm1),
        ("Over 19.5", res["over19"]/n_sims, gm2),
        ("Over 20.5", res["over20"]/n_sims, gm3),
        ("Over 21.5", res["over21"]/n_sims, gm4),
        (f"Media games", f"{avg_games:.1f}", gm5),
        (f"Mediana", f"{med_games:.0f}", gm6),
    ]
    for label, value, col in mercados:
        with col:
            display = f"{value:.1%}" if isinstance(value, float) and value <= 1.0 else str(value)
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-value">{display}</div>
            </div>
            """, unsafe_allow_html=True)

    # Interpretación automática de mercados
    if avg_games < 19:
        st.caption(f"📉 Media de {avg_games:.1f} games → partido esperado **corto**. Favorece Under 19.5.")
    elif avg_games > 21:
        st.caption(f"📈 Media de {avg_games:.1f} games → partido esperado **largo**. Favorece Over 20.5 / Over 21.5.")
    else:
        st.caption(f"⚖️ Media de {avg_games:.1f} games → partido de **duración media**. Línea 19.5 equilibrada.")

    # ── Nota de fiabilidad ────────────────────────────
    st.divider()
    st.caption(
        f"🔬 Basado en {n_sims:,} simulaciones Monte Carlo · "
        f"Elo {superficie}: {d1['Player']} {e1:.0f} vs {d2['Player']} {e2:.0f} · "
        f"Dispersión games: σ={std_games:.1f}"
    )
