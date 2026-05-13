# ============================================================
# TENNIS IA - v23.15 WTA Dynamic Over Guard
# Archivo: app_v23_15_wta_dynamic_over_guard.py
#
# Objetivo de esta version:
# - Mantener el flujo de analisis por Excel/lista.
# - Leer archivos generados por versiones anteriores.
# - Aplicar WTA Dynamic Over Guard sobre WTA Clay.
# - Penalizar Over 18.5 solo cuando hay riesgo real de paliza.
# - Permitir Over 18.5 cuando el partido esta igualado.
# - Exportar Excel limpio con nuevas columnas de guard.
# ============================================================

import re
import io
from datetime import datetime
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st


APP_VERSION = "v23.15 WTA Dynamic Over Guard"
OUTPUT_FILE_NAME = "analisis_lista_tennis_ia_v23_15.xlsx"


# ============================================================
# CONFIG STREAMLIT
# ============================================================

st.set_page_config(
    page_title="Tennis IA v23.15",
    page_icon="🎾",
    layout="wide",
)


# ============================================================
# UTILIDADES GENERALES
# ============================================================

def normalizar_texto(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def to_float(x, default: float = 0.0) -> float:
    """Convierte porcentajes y numeros con coma a float."""
    if x is None or pd.isna(x):
        return default
    if isinstance(x, (int, float, np.integer, np.floating)):
        return float(x)
    txt = str(x).strip().replace("%", "").replace(",", ".")
    txt = re.sub(r"[^0-9.\-]", "", txt)
    if txt in ("", ".", "-", "-."):
        return default
    try:
        return float(txt)
    except Exception:
        return default


def pct(x) -> str:
    try:
        return f"{float(x):.1f}%"
    except Exception:
        return ""


def detectar_circuito(df: pd.DataFrame, circuito_default: str) -> pd.Series:
    """Devuelve serie circuito. Si existe columna Circuito, la usa; si no, usa default."""
    if "Circuito" in df.columns:
        return df["Circuito"].fillna(circuito_default).astype(str)
    if "Torneo" in df.columns:
        torneo = df["Torneo"].astype(str).str.upper()
        return np.select(
            [torneo.str.contains("CHALL", na=False), torneo.str.contains("WTA", na=False), torneo.str.contains("ATP", na=False)],
            ["Challenger", "WTA", "ATP"],
            default=circuito_default,
        )
    return pd.Series([circuito_default] * len(df), index=df.index)


def detectar_superficie(df: pd.DataFrame, superficie_default: str) -> pd.Series:
    if "Superficie" in df.columns:
        return df["Superficie"].fillna(superficie_default).astype(str)
    if "surface" in df.columns:
        return df["surface"].fillna(superficie_default).astype(str)
    return pd.Series([superficie_default] * len(df), index=df.index)


def detectar_columna(df: pd.DataFrame, posibles: list[str]) -> Optional[str]:
    cols_lower = {c.lower().strip(): c for c in df.columns}
    for p in posibles:
        key = p.lower().strip()
        if key in cols_lower:
            return cols_lower[key]
    return None


# ============================================================
# PARSERS BASICOS DE LISTA
# ============================================================

def parsear_lista_simple(texto: str) -> pd.DataFrame:
    """
    Parser sencillo para listas tipo:
    Jugador A vs Jugador B
    Jugador A - Jugador B

    Si pegas una lista de casa/Sofascore sin cuotas, crea partidos basicos.
    El analisis real necesitara probabilidades si no estan en Excel.
    """
    filas = []
    for raw in texto.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"\s+", " ", line)
        if " vs " in line.lower():
            parts = re.split(r"\s+vs\s+", line, flags=re.I)
        elif " - " in line:
            parts = line.split(" - ", 1)
        else:
            continue
        if len(parts) == 2:
            j1, j2 = parts[0].strip(), parts[1].strip()
            if j1 and j2:
                filas.append({"Partido": f"{j1} vs {j2}", "Jugador 1": j1, "Jugador 2": j2})
    return pd.DataFrame(filas)


# ============================================================
# v23.15 - WTA DYNAMIC OVER GUARD
# ============================================================

def aplicar_wta_dynamic_over_guard(
    circuito,
    superficie,
    prob_ml_favorita,
    prob_over_18_5,
    mejor_senal_actual=None,
) -> Tuple[float, str, str]:
    """
    Guard dinamico para WTA Clay.

    Devuelve:
    - prob_over_ajustada
    - etiqueta_guard
    - recomendacion_over_guard
    """
    circuito = str(circuito).upper().strip()
    superficie = str(superficie).lower().strip()

    prob_ml_favorita = to_float(prob_ml_favorita)
    prob_over_18_5 = to_float(prob_over_18_5)
    prob_over_original = prob_over_18_5

    etiqueta_guard = ""
    recomendacion_over = "NORMAL"

    # Solo WTA Clay
    if circuito != "WTA" or "clay" not in superficie:
        return round(prob_over_18_5, 1), etiqueta_guard, recomendacion_over

    # Favorita muy fuerte: riesgo alto de 2-0 corto
    if prob_ml_favorita >= 72:
        prob_over_18_5 -= 12
        etiqueta_guard = "🛡️ WTA Guard fuerte: favorita muy superior, Over penalizado"
        recomendacion_over = "BLOQUEAR_OVER"

    # Favorita clara
    elif prob_ml_favorita >= 68:
        prob_over_18_5 -= 8
        etiqueta_guard = "🛡️ WTA Guard medio: favorita clara, Over rebajado"
        recomendacion_over = "OVER_CON_CUIDADO"

    # Favorita moderada
    elif prob_ml_favorita >= 65:
        prob_over_18_5 -= 4
        etiqueta_guard = "🟡 WTA Guard suave: favorita moderada, Over ligeramente rebajado"
        recomendacion_over = "OVER_PERMITIDO_SI_ALTO"

    # Partido igualado
    else:
        etiqueta_guard = "✅ WTA Dynamic Guard: partido igualado, Over permitido"
        recomendacion_over = "OVER_PERMITIDO"

    prob_over_18_5 = max(0, min(100, prob_over_18_5))

    # Extra: Over alto con partido igualado se mantiene valido
    if prob_ml_favorita < 65 and prob_over_original >= 66:
        recomendacion_over = "OVER_VALIDO"
        etiqueta_guard = "✅ WTA Dynamic Guard: Over alto con partido igualado"

    return round(prob_over_18_5, 1), etiqueta_guard, recomendacion_over


# ============================================================
# DECISION FINAL v23.15
# ============================================================

def decidir_recomendacion_v23_15(
    circuito,
    superficie,
    favorito_modelo,
    ml_favorito,
    over_18_5,
    mejor_senal_previa="",
    signal_trust_previo="",
) -> dict:
    """Aplica decision final compatible con WTA Dynamic Over Guard."""

    circuito_txt = str(circuito).upper().strip()
    superficie_txt = str(superficie).lower().strip()
    favorito_modelo = normalizar_texto(favorito_modelo)
    ml = to_float(ml_favorito)
    over = to_float(over_18_5)

    mejor_senal = normalizar_texto(mejor_senal_previa)
    signal_trust = normalizar_texto(signal_trust_previo)
    recomendacion = "NO BET"
    motivo_guard = ""

    over_ajustado, etiqueta_guard, rec_over_guard = aplicar_wta_dynamic_over_guard(
        circuito=circuito_txt,
        superficie=superficie_txt,
        prob_ml_favorita=ml,
        prob_over_18_5=over,
        mejor_senal_actual=mejor_senal,
    )

    # ========================================================
    # WTA CLAY - NUEVA LOGICA DINAMICA
    # ========================================================
    if circuito_txt == "WTA" and "clay" in superficie_txt:

        if ml >= 72:
            mejor_senal = f"ML {favorito_modelo}" if favorito_modelo else "ML favorita"
            recomendacion = "APTA" if ml >= 75 else "DUDOSA"
            signal_trust = "🔥 SPOT FUERTE" if ml >= 75 else "✅ Media-alta"
            motivo_guard = "Favorita muy fuerte. Se prioriza ML y se bloquea Over por riesgo de marcador corto."

        elif ml >= 68:
            if over_ajustado >= 68 and rec_over_guard != "BLOQUEAR_OVER":
                mejor_senal = "Over 18.5"
                recomendacion = "DUDOSA"
                signal_trust = "✅ Media-alta"
                motivo_guard = "Over permitido con cautela pese a favorita clara."
            else:
                mejor_senal = f"ML {favorito_modelo}" if favorito_modelo else "ML favorita"
                recomendacion = "DUDOSA"
                signal_trust = "✅ Media-alta"
                motivo_guard = "Favorita clara. ML tiene preferencia sobre Over."

        elif ml >= 65:
            if over_ajustado >= 66:
                mejor_senal = "Over 18.5"
                recomendacion = "DUDOSA"
                signal_trust = "✅ Media-alta"
                motivo_guard = "Over aceptable. Favorita moderada, sin bloqueo fuerte."
            else:
                mejor_senal = f"ML {favorito_modelo}" if favorito_modelo else "ML favorita"
                recomendacion = "DUDOSA"
                signal_trust = "⚖️ Ajustada"
                motivo_guard = "ML moderado. Over no suficientemente alto."

        else:
            if over_ajustado >= 66:
                mejor_senal = "Over 18.5"
                recomendacion = "DUDOSA"
                signal_trust = "✅ Media-alta"
                motivo_guard = "Partido igualado. Over permitido por Dynamic Guard."
            else:
                mejor_senal = "NO BET"
                recomendacion = "NO BET"
                signal_trust = "⚠️ Baja"
                motivo_guard = "Partido igualado pero sin probabilidad Over suficiente."

    # ========================================================
    # RESTO DE CIRCUITOS - NO TOCAMOS DEMASIADO
    # ========================================================
    else:
        # Si ya venia recomendacion/senal, la respetamos bastante.
        if not mejor_senal:
            if ml >= 70:
                mejor_senal = f"ML {favorito_modelo}" if favorito_modelo else "ML favorita"
            elif over >= 68:
                mejor_senal = "Over 18.5"
            else:
                mejor_senal = "NO BET"

        if circuito_txt == "CHALLENGER":
            # Challenger Clay: desconfiar ML, priorizar Over si es alto.
            if "clay" in superficie_txt and over >= 68:
                mejor_senal = "Over 18.5"
                recomendacion = "DUDOSA"
                signal_trust = "✅ Over útil / ML débil Challenger"
            elif ml >= 75:
                recomendacion = "DUDOSA"
                signal_trust = "⚠️ ML Challenger con cautela"
            else:
                recomendacion = "NO BET"
                signal_trust = signal_trust or "⚠️ Baja"
        else:
            # ATP o default.
            if ml >= 75 or over >= 72:
                recomendacion = "APTA"
                signal_trust = signal_trust or "🔥 SPOT FUERTE"
            elif ml >= 65 or over >= 66:
                recomendacion = "DUDOSA"
                signal_trust = signal_trust or "✅ Media-alta"
            else:
                recomendacion = "NO BET"
                signal_trust = signal_trust or "⚠️ Baja"

    return {
        "Mejor señal v23.15": mejor_senal,
        "Recomendación v23.15": recomendacion,
        "Signal Trust v23.15": signal_trust,
        "Over 18.5 Ajustado": over_ajustado,
        "WTA Guard": etiqueta_guard,
        "Motivo Guard": motivo_guard,
        "Recomendacion Over Guard": rec_over_guard,
    }


# ============================================================
# ANALISIS DE DATAFRAME
# ============================================================

def aplicar_v23_15_a_dataframe(
    df: pd.DataFrame,
    circuito_default: str = "WTA",
    superficie_default: str = "Clay",
) -> pd.DataFrame:
    df = df.copy()

    # Detectar columnas principales.
    col_partido = detectar_columna(df, ["Partido", "match", "encuentro"])
    col_fav = detectar_columna(df, ["Favorito modelo", "Pick", "Ganador modelo", "Favorito"])
    col_ml = detectar_columna(df, ["ML favorito", "Prob ML", "Prob ganador", "Win %", "ML"])
    col_over = detectar_columna(df, ["Over 18.5", "Over18.5", "Over 18,5", "Prob Over 18.5"])
    col_senal = detectar_columna(df, ["Mejor señal", "Mejor senal", "Signal", "Señal"])
    col_trust = detectar_columna(df, ["Signal Trust", "Trust", "Confianza"])
    col_reco = detectar_columna(df, ["Recomendación", "Recomendacion"])

    if col_fav is None:
        df["Favorito modelo"] = ""
        col_fav = "Favorito modelo"
    if col_ml is None:
        df["ML favorito"] = 0.0
        col_ml = "ML favorito"
    if col_over is None:
        df["Over 18.5"] = 0.0
        col_over = "Over 18.5"
    if col_senal is None:
        df["Mejor señal"] = ""
        col_senal = "Mejor señal"
    if col_trust is None:
        df["Signal Trust"] = ""
        col_trust = "Signal Trust"
    if col_reco is None:
        df["Recomendación"] = ""
        col_reco = "Recomendación"

    df["Circuito v23.15"] = detectar_circuito(df, circuito_default)
    df["Superficie v23.15"] = detectar_superficie(df, superficie_default)

    nuevas = []
    for _, row in df.iterrows():
        nuevas.append(
            decidir_recomendacion_v23_15(
                circuito=row.get("Circuito v23.15", circuito_default),
                superficie=row.get("Superficie v23.15", superficie_default),
                favorito_modelo=row.get(col_fav, ""),
                ml_favorito=row.get(col_ml, 0),
                over_18_5=row.get(col_over, 0),
                mejor_senal_previa=row.get(col_senal, ""),
                signal_trust_previo=row.get(col_trust, ""),
            )
        )

    extra = pd.DataFrame(nuevas, index=df.index)
    out = pd.concat([df, extra], axis=1)

    # Para que sea comodo visualmente, colocamos columnas v23.15 cerca del inicio.
    preferidas = []
    for c in [
        col_reco,
        "Recomendación v23.15",
        "Fecha",
        "Hora",
        col_partido,
        col_fav,
        col_ml,
        col_senal,
        "Mejor señal v23.15",
        col_over,
        "Over 18.5 Ajustado",
        "Signal Trust v23.15",
        "WTA Guard",
        "Motivo Guard",
        "Recomendacion Over Guard",
        "Circuito v23.15",
        "Superficie v23.15",
    ]:
        if c and c in out.columns and c not in preferidas:
            preferidas.append(c)

    resto = [c for c in out.columns if c not in preferidas]
    out = out[preferidas + resto]
    return out


# ============================================================
# VALIDACION SI HAY RESULTADOS REALES
# ============================================================

def resumen_validacion(df: pd.DataFrame) -> dict:
    res = {}

    col_ml_ok = detectar_columna(df, ["Acierta ML modelo", "Acierta ML", "ML correcto"])
    col_over_ok = detectar_columna(df, ["Acierta Over 18.5", "Over 18.5 correcto", "Acierta Over"])
    col_reco = detectar_columna(df, ["Recomendación v23.15", "Recomendacion v23.15", "Recomendación"])

    if col_ml_ok:
        s = df[col_ml_ok].dropna().astype(str).str.upper()
        valid = s[s.isin(["TRUE", "FALSE", "1", "0", "SI", "SÍ", "NO", "✅", "❌"])]
        aciertos = valid.isin(["TRUE", "1", "SI", "SÍ", "✅"]).sum()
        total = len(valid)
        res["ML"] = (int(aciertos), int(total), float(aciertos / total * 100) if total else 0)

    if col_over_ok:
        s = df[col_over_ok].dropna().astype(str).str.upper()
        valid = s[s.isin(["TRUE", "FALSE", "1", "0", "SI", "SÍ", "NO", "✅", "❌"])]
        aciertos = valid.isin(["TRUE", "1", "SI", "SÍ", "✅"]).sum()
        total = len(valid)
        res["Over 18.5"] = (int(aciertos), int(total), float(aciertos / total * 100) if total else 0)

    if col_reco:
        res["Recomendaciones"] = df[col_reco].astype(str).value_counts().to_dict()

    return res


# ============================================================
# EXPORT EXCEL
# ============================================================

def dataframe_to_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, data in sheets.items():
            safe_name = str(name)[:31] or "Analisis"
            data.to_excel(writer, sheet_name=safe_name, index=False)

            ws = writer.book[safe_name]
            ws.freeze_panes = "A2"
            for col_cells in ws.columns:
                max_len = 0
                col_letter = col_cells[0].column_letter
                for cell in col_cells:
                    try:
                        val = "" if cell.value is None else str(cell.value)
                        max_len = max(max_len, len(val))
                    except Exception:
                        pass
                ws.column_dimensions[col_letter].width = min(max_len + 2, 45)
    return output.getvalue()


# ============================================================
# INTERFAZ
# ============================================================

st.title("🎾 Tennis IA - v23.15 WTA Dynamic Over Guard")
st.caption(APP_VERSION)

st.markdown(
    """
Esta version cambia el antiguo bloqueo fijo de WTA Clay por un guard dinamico:
- Favorita muy fuerte: penaliza Over 18.5.
- Partido igualado: permite Over 18.5 si la probabilidad es alta.
- ATP y Challenger se dejan practicamente igual.
"""
)

with st.sidebar:
    st.header("Configuracion")
    circuito_default = st.selectbox("Circuito por defecto", ["WTA", "ATP", "Challenger"], index=0)
    superficie_default = st.selectbox("Superficie por defecto", ["Clay", "Hard", "Grass", "Indoor"], index=0)
    st.info("Si el Excel no trae columnas Circuito/Superficie, se usaran estos valores.")

modo = st.tabs(["📁 Analizar Excel", "📝 Pegar lista simple", "🧪 Test manual guard"])


with modo[0]:
    uploaded = st.file_uploader(
        "Sube tu Excel de analisis/lista",
        type=["xlsx", "xls"],
        help="Compatible con analisis_lista_tennis_ia.xlsx y hojas similares.",
    )

    if uploaded is not None:
        xls = pd.ExcelFile(uploaded)
        hoja = st.selectbox("Hoja a analizar", xls.sheet_names, index=0)
        df_in = pd.read_excel(uploaded, sheet_name=hoja)

        st.subheader("Vista previa original")
        st.dataframe(df_in, use_container_width=True)

        df_out = aplicar_v23_15_a_dataframe(
            df_in,
            circuito_default=circuito_default,
            superficie_default=superficie_default,
        )

        st.subheader("Resultado v23.15")
        st.dataframe(df_out, use_container_width=True)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Partidos", len(df_out))
        c2.metric("APTA v23.15", int((df_out["Recomendación v23.15"].astype(str).str.upper() == "APTA").sum()))
        c3.metric("DUDOSA v23.15", int((df_out["Recomendación v23.15"].astype(str).str.upper() == "DUDOSA").sum()))
        c4.metric("NO BET v23.15", int((df_out["Recomendación v23.15"].astype(str).str.upper() == "NO BET").sum()))

        resumen = resumen_validacion(df_out)
        if resumen:
            st.subheader("Resumen de validacion detectada")
            cols = st.columns(max(1, len(resumen)))
            i = 0
            for k, v in resumen.items():
                if isinstance(v, tuple):
                    ac, total, pr = v
                    cols[i % len(cols)].metric(k, f"{ac}/{total}", f"{pr:.1f}%")
                    i += 1
            if "Recomendaciones" in resumen:
                st.write("Recomendaciones:", resumen["Recomendaciones"])

        excel_bytes = dataframe_to_excel_bytes({"Analisis v23.15": df_out})
        st.download_button(
            "⬇️ Descargar Excel v23.15",
            data=excel_bytes,
            file_name=OUTPUT_FILE_NAME,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


with modo[1]:
    texto = st.text_area(
        "Pega partidos, uno por linea",
        height=220,
        placeholder="Elina Svitolina vs Elena Rybakina\nJessica Pegula vs Iga Swiatek",
    )
    if st.button("Parsear lista"):
        df_lista = parsear_lista_simple(texto)
        if df_lista.empty:
            st.warning("No he podido detectar partidos. Usa formato 'Jugador A vs Jugador B'.")
        else:
            st.dataframe(df_lista, use_container_width=True)
            st.info("Esta lista no trae probabilidades. Para aplicar recomendaciones reales, sube el Excel generado por el modelo.")


with modo[2]:
    st.subheader("Prueba rapida del Dynamic Over Guard")
    c1, c2, c3, c4 = st.columns(4)
    circuito_t = c1.selectbox("Circuito", ["WTA", "ATP", "Challenger"], index=0, key="test_circuito")
    superficie_t = c2.selectbox("Superficie", ["Clay", "Hard", "Grass", "Indoor"], index=0, key="test_superficie")
    ml_t = c3.number_input("ML favorita", min_value=0.0, max_value=100.0, value=68.0, step=0.1)
    over_t = c4.number_input("Over 18.5", min_value=0.0, max_value=100.0, value=72.0, step=0.1)

    test = decidir_recomendacion_v23_15(
        circuito=circuito_t,
        superficie=superficie_t,
        favorito_modelo="Favorita",
        ml_favorito=ml_t,
        over_18_5=over_t,
    )

    st.json(test)

st.divider()
st.caption("v23.15: WTA Dynamic Over Guard | Creada para comparar contra v23.14 WTA Over Guard")
