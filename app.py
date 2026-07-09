import json
import pandas as pd
import streamlit as st
import unicodedata
import re
import math

# Configuración de la página web
st.set_page_config(page_title="Tennis Predictor V6 - Tipo de Partido v5.7", page_icon="🎾", layout="wide")

# Ruta del archivo JSON del caché
RUTA_JSON = "ta_profile_cache.json"

def cargar_datos_json_sin_cache(ruta_archivo):
    """Carga el JSON directamente sin caché de Streamlit."""
    try:
        with open(ruta_archivo, 'r', encoding='utf-8') as f:
            datos = json.load(f)
        entries = datos.get("entries", {})
        
        lista_jugadores = {}
        for k, v in entries.items():
            nombre_legible = v.get("player", k)
            lista_jugadores[nombre_legible] = k
            
        return datos, lista_jugadores
    except FileNotFoundError:
        st.error(f"❌ No se encontró el archivo '{ruta_archivo}' en la misma carpeta.")
        return None, {}

def guardar_datos_json(datos, ruta_archivo):
    """Guarda la estructura actualizada de vuelta en el archivo físico."""
    try:
        with open(ruta_archivo, 'w', encoding='utf-8') as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.error(f"Error al escribir en el JSON: {e}")
        return False

def obtener_hold_percentage(raw_text, superficie):
    """Encuentra de forma exacta la columna 'Hold%' leyendo los encabezados de Tennis Abstract."""
    superficies_map = {
        "Dura 🔵": "Hard",
        "Tierra Batida 🟤": "Clay",
        "Hierba 🟢": "Grass"
    }
    sup_ingles = superficies_map.get(superficie, "Hard")
    lineas = raw_text.split('\n')
    indice_hold = None
    
    for linea in lineas:
        partes = [p.strip() for p in linea.split('\t')]
        if "Hold%" in partes or "Hold" in partes:
            try:
                indice_hold = partes.index("Hold%") if "Hold%" in partes else partes.index("Hold")
                break
            except ValueError:
                pass
                
    if indice_hold is not None:
        for linea in lineas:
            partes = [p.strip() for p in linea.split('\t')]
            if partes and partes[0] == sup_ingles:
                if len(partes) > indice_hold and '%' in partes[indice_hold]:
                    try:
                        return float(partes[indice_hold].replace('%', '').strip())
                    except:
                        pass
                        
        for linea in lineas:
            partes = [p.strip() for p in linea.split('\t')]
            if partes and any(x in partes[0] for x in ["Overall", "52 Weeks", "Total"]):
                if len(partes) > indice_hold and '%' in partes[indice_hold]:
                    try:
                        return float(partes[indice_hold].replace('%', '').strip())
                    except:
                        pass

    for linea in lineas:
        if any(x in linea for x in ["52 Weeks", "Overall", sup_ingles]):
            partes = [p.strip() for p in linea.split('\t')]
            porcentajes = [x for x in partes if '%' in x]
            if len(porcentajes) >= 4:
                try:
                    for p_candidato in reversed(porcentajes):
                        valor = float(p_candidato.replace('%', '').strip())
                        if 68.0 <= valor <= 96.0:
                            return valor
                except:
                    pass

    return 79.5


def obtener_hold_percentage_con_calidad(raw_text, superficie, entry=None):
    """Devuelve Hold% + calidad de lectura usando primero los datos estructurados del caché TA.

    Mejora v5.4:
    - El JSON que usas ya trae campos limpios: ta_best_hard / ta_best_clay / ta_best_grass,
      last52_stats y career_stats. Esta versión los usa antes que el raw_text.
    - TennisAbstract llama a la columna de saque "Hld%", no siempre "Hold%". El parser
      ahora reconoce Hld%, Hld, Hold% y Hold.
    - Así evitamos muchísimos "DUDOSA heurística" y el motor trabaja con Hold% real.
    """
    superficies_map = {
        "Dura 🔵": "Hard",
        "Tierra Batida 🟤": "Clay",
        "Hierba 🟢": "Grass",
        "hard": "Hard",
        "clay": "Clay",
        "grass": "Grass",
    }
    sup_txt = str(superficie).strip()
    sup_ingles = superficies_map.get(sup_txt, None)
    if sup_ingles is None:
        low = sup_txt.lower()
        if "tierra" in low or "clay" in low or "🟤" in sup_txt:
            sup_ingles = "Clay"
        elif "hierba" in low or "grass" in low or "🟢" in sup_txt:
            sup_ingles = "Grass"
        else:
            sup_ingles = "Hard"

    def parse_pct(valor):
        try:
            if valor is None:
                return None
            s = str(valor).replace("%", "").replace(",", ".").strip()
            if not s or s in {"-", "None", "nan"}:
                return None
            v = float(s)
            if 0.45 <= v <= 0.98:
                v *= 100.0
            if 45.0 <= v <= 98.0:
                return round(v, 1)
        except Exception:
            return None
        return None

    def leer_hold_de_stats(stats):
        if not isinstance(stats, dict):
            return None, None
        v = parse_pct(stats.get("hold_pct"))
        if v is None:
            # Por si alguna ficha lo guarda con otro nombre.
            for k in ("hld_pct", "hld%", "Hld%", "Hold%", "hold"):
                if k in stats:
                    v = parse_pct(stats.get(k))
                    if v is not None:
                        break
        matches = stats.get("matches", stats.get("M", stats.get("ms", None)))
        try:
            matches = int(matches) if matches is not None else None
        except Exception:
            matches = None
        return v, matches

    # ------------------------------------------------------------------
    # 0) Fuente más fiable para tu caché: campos estructurados ya guardados
    # ------------------------------------------------------------------
    if isinstance(entry, dict):
        campo_superficie = {
            "Hard": "ta_best_hard",
            "Clay": "ta_best_clay",
            "Grass": "ta_best_grass",
        }.get(sup_ingles)

        candidatos = []
        if campo_superficie:
            candidatos.append((entry.get(campo_superficie), "OK superficie", f"Hold% leído del campo estructurado {campo_superficie}."))

        # last52_stats suele ser la mejor foto reciente si no existe ta_best_...
        last52 = entry.get("last52_stats")
        if isinstance(last52, dict):
            candidatos.append((last52.get(sup_ingles), "OK superficie", f"Hold% leído de Last 52 Weeks en {sup_ingles}."))

        # career_stats como respaldo si no hay muestra reciente por superficie.
        career = entry.get("career_stats")
        if isinstance(career, dict):
            candidatos.append((career.get(sup_ingles), "OK general", f"Hold% leído de Career Splits en {sup_ingles}."))

        # Respaldos generales del año/circuito. No son por superficie, pero son mejores que inventar 79.5.
        for campo in ("tour_2026", "challenger_2026_full"):
            stats = entry.get(campo)
            if isinstance(stats, dict) and stats:
                candidatos.append((stats, "OK general", f"Hold% leído del resumen {campo}."))

        for stats, calidad, motivo in candidatos:
            v, matches = leer_hold_de_stats(stats)
            if v is not None:
                if matches is not None and matches < 3:
                    return v, "DUDOSA heurística", motivo + f" Muestra baja: {matches} partidos."
                return v, calidad, motivo + (f" Muestra: {matches} partidos." if matches is not None else "")

    if not raw_text or not str(raw_text).strip():
        return None, "NO encontrado", "No hay raw_text ni campos estructurados útiles en la ficha TA."

    texto = str(raw_text)
    texto = texto.replace("\r", "\n").replace("\xa0", " ")
    lineas = [l.strip() for l in texto.split("\n") if l.strip()]

    def tokenizar(linea):
        """Tokeniza respetando tablas pegadas con tabs o espacios amplios."""
        if "\t" in linea:
            toks = [t.strip() for t in linea.split("\t") if t.strip()]
        else:
            toks = [t.strip() for t in re.split(r"\s{2,}", linea) if t.strip()]
            if len(toks) <= 3:
                toks = [t.strip() for t in linea.split() if t.strip()]
        return toks

    def normaliza_col(t):
        return re.sub(r"[^a-z0-9%]", "", str(t).lower())

    def extraer_porcentajes(linea):
        vals = []
        for m in re.finditer(r"(?<![\w.-])(?:\d{1,3}(?:[\.,]\d+)?|\.\d{2,3})\s*%", linea):
            v = parse_pct(m.group(0))
            if v is not None:
                vals.append(v)
        return vals

    def empieza_por_label(linea, labels):
        limpio = linea.strip().lower()
        limpio = re.sub(r"\s+", " ", limpio)
        for label in labels:
            lab = label.lower()
            if limpio == lab or limpio.startswith(lab + "\t") or limpio.startswith(lab + " "):
                return True
        return False

    labels_superficie = [sup_ingles]
    labels_generales = ["Overall", "52 Weeks", "Last 52 Weeks", "Total", "All", "Career"]
    nombres_hold = {"hold%", "hold", "hld%", "hld"}

    # ------------------------------------------------------------------
    # 1) Parser tabular. Reconoce Hld% de TennisAbstract.
    # ------------------------------------------------------------------
    for i, linea_header in enumerate(lineas):
        header_norm = normaliza_col(linea_header)
        if not any(x in header_norm for x in ("hold", "hld")):
            continue

        cols = tokenizar(linea_header)
        cols_norm = [normaliza_col(c) for c in cols]

        idx_hold_col = None
        for idx, c in enumerate(cols_norm):
            if c in nombres_hold:
                idx_hold_col = idx
                break

        pct_cols = [c for c in cols_norm if "%" in c or c in {"win", "set", "game", "tb", "hld", "hold", "brk", "a", "df", "1stin", "1st", "2nd", "spw", "rpw", "tpw"}]
        idx_hold_pct = None
        for idx, c in enumerate(pct_cols):
            if c in nombres_hold:
                idx_hold_pct = idx
                break

        if idx_hold_col is None and idx_hold_pct is None:
            continue

        for labels, calidad, motivo in [
            (labels_superficie, "OK superficie", f"Hold% leído en fila {sup_ingles} mediante cabecera TA Hld%/Hold%."),
            (labels_generales, "OK general", "Hold% leído en fila general mediante cabecera TA Hld%/Hold%."),
        ]:
            for linea in lineas[i + 1:i + 120]:
                if not empieza_por_label(linea, labels):
                    continue

                toks = tokenizar(linea)
                if toks and toks[0].lower() == "52" and len(toks) > 1 and toks[1].lower().startswith("weeks"):
                    toks = ["52 Weeks"] + toks[2:]

                if idx_hold_col is not None and idx_hold_col < len(toks):
                    v = parse_pct(toks[idx_hold_col])
                    if v is not None:
                        return v, calidad, motivo

                if idx_hold_pct is not None:
                    porcentajes = extraer_porcentajes(linea)
                    if idx_hold_pct < len(porcentajes):
                        v = porcentajes[idx_hold_pct]
                        if v is not None:
                            return v, calidad, motivo

    # ------------------------------------------------------------------
    # 2) Fallback por filas conocidas: solo si hay muchos porcentajes.
    # ------------------------------------------------------------------
    for labels, texto_motivo in [
        (labels_superficie, f"Hold% estimado en fila {sup_ingles} sin cabecera clara."),
        (labels_generales, "Hold% estimado en fila general sin cabecera clara."),
    ]:
        for linea in lineas:
            if empieza_por_label(linea, labels):
                porcentajes = extraer_porcentajes(linea)
                if len(porcentajes) >= 4:
                    candidatos = list(reversed(porcentajes[:-1] if len(porcentajes) >= 2 else porcentajes))
                    for v in candidatos:
                        if 60.0 <= v <= 96.0:
                            return v, "DUDOSA heurística", texto_motivo

    return None, "NO encontrado", "No se pudo localizar Hold% fiable."

def hold_valido_para_modelo(hold, calidad):
    """Decide si una lectura de Hold% puede entrar en el motor.

    v5 era demasiado estricta: si TennisAbstract no venía tabulado con encabezado
    claro, muchos jugadores quedaban como "DUDOSA heurística" y el validador
    bloqueaba prácticamente todo.

    En v5.1 dejamos entrar la lectura heurística para poder analizar Over/Under,
    pero luego se rebaja la acción y se bloquea el Tie-Break Sí si la calidad no
    es limpia.
    """
    if hold is None:
        return False
    return calidad in {"OK superficie", "OK general", "DUDOSA heurística"}


def depurar_sets_duplicados(sets, formato_sets=""):
    """Limpia marcadores duplicados pegados desde SofaScore.

    Ejemplo detectado: 7-6 7-5 7-6 7-5. Eso suele ser el mismo marcador repetido
    al copiar la tabla; para ATP/Challenger/WTA al mejor de 3 debe quedar 7-6 7-5.
    """
    if not sets:
        return []

    sets = list(sets)

    # Si la segunda mitad repite exactamente la primera, dejamos solo la primera mitad.
    if len(sets) % 2 == 0 and len(sets) >= 4:
        mitad = len(sets) // 2
        if sets[:mitad] == sets[mitad:]:
            sets = sets[:mitad]

    es_5_sets = "Grand Slam" in str(formato_sets) or "5 sets" in str(formato_sets).lower()
    max_sets = 5 if es_5_sets else 3

    if len(sets) > max_sets:
        # Cortamos cuando alguien gana el partido.
        objetivo = 3 if es_5_sets else 2
        limpios = []
        g1 = g2 = 0
        for a, b in sets:
            limpios.append((a, b))
            if a > b:
                g1 += 1
            elif b > a:
                g2 += 1
            if g1 == objetivo or g2 == objetivo:
                return limpios
        return sets[:max_sets]

    return sets

def calcular_analisis_multimercado(hold_j1, hold_j2, formato_sets, n1, n2, superficie):
    """
    MOTOR UNIFICADO AVANZADO: Implementa filtros de dominancia, 
    módulo específico de hierba y penalizaciones por igualdad.
    """
    suma_saques = hold_j1 + hold_j2
    diferencia_saque = abs(hold_j1 - hold_j2)
    es_grand_slam = "Grand Slam" in formato_sets or "5 sets" in formato_sets.lower()
    es_challenger = "Challenger" in formato_sets or "challenger" in formato_sets.lower()
    
    es_tierra = "tierra" in superficie.lower() or "clay" in superficie.lower() or "🟤" in superficie
    es_hierba = "hierba" in superficie.lower() or "grass" in superficie.lower() or "🟢" in superficie
    
    multiplicador_superficie = 0.90 if es_tierra else 1.0
    if es_hierba: multiplicador_superficie = 0.85 # Penaliza hándicaps exagerados en hierba
    
    # -------------------------------------------------------------------------
    # MERCADO 1: HÁNDICAP / GANADOR (CON MÓDULO HIERBA)
    # -------------------------------------------------------------------------
    favorito = n1 if hold_j1 > hold_j2 else n2
    
    # Exigimos más diferencia en Hierba para dar un hándicap fuerte
    umbral_fuerte = 8.5 if es_hierba else 7.5
    umbral_mod = 4.5 if es_hierba else 3.5
    
    if diferencia_saque >= umbral_fuerte:
        tipo_handicap = "Fuerte"
        pron_handicap = f"👤 {favorito} (Hándicap Fuerte)"
        # Recorte de líneas exageradas en hierba
        # v5.7: la validación mostró que -3.5 baja mucho el acierto.
        # Dejamos la lectura de dominancia, pero la línea práctica recomendada es conservadora.
        linea_handicap = "-1.5 Juegos" if not es_grand_slam else "-2.5 Juegos"
        fia_handicap = min(97.0, (65.0 + ((diferencia_saque - umbral_fuerte) * 3.0)) * multiplicador_superficie)
    elif diferencia_saque >= umbral_mod:
        tipo_handicap = "Moderado"
        pron_handicap = f"👤 {favorito} (Hándicap Moderado)"
        # v5.7: también en moderado se valida/propone la línea más segura.
        linea_handicap = "-1.5 Juegos" if not es_grand_slam else "-2.5 Juegos"
        fia_handicap = min(88.0, (60.0 + ((diferencia_saque - umbral_mod) * 4.0)) * multiplicador_superficie)
    else:
        tipo_handicap = "Igualado"
        pron_handicap = "⚖️ Partido Igualado (Evitar Hándicap)"
        linea_handicap = "N/A"
        fia_handicap = 50.0

    # -------------------------------------------------------------------------
    # MERCADO 2: MERCADO DE SETS
    # -------------------------------------------------------------------------
    if diferencia_saque >= 8.0:
        pron_sets = "📉 UNDER SETS (Vía Rápida)"
        linea_sets = "Menos de 3.5 Sets" if es_grand_slam else "Menos de 2.5 Sets"
        fia_sets = min(96.0, 70.0 + ((diferencia_saque - 8.0) * 3.5))
    elif diferencia_saque <= 2.5 and suma_saques >= (163.0 - 5 if es_grand_slam else 156.0 - 5 if es_challenger else 164.0 - 5):
        pron_sets = "📊 OVER SETS (Partido Largo)"
        linea_sets = "Más de 4.5 Sets" if es_grand_slam else "Más de 2.5 Sets"
        umbral_ref = 163.0 if es_grand_slam else 156.0 if es_challenger else 164.0
        fia_sets = min(94.0, 68.0 + ((2.5 - diferencia_saque) * 4.0) + ((suma_saques - umbral_ref + 5) * 0.5))
    else:
        pron_sets = "🟡 Incierto"
        linea_sets = "N/A"
        fia_sets = 50.0

    # -------------------------------------------------------------------------
    # MERCADO 3: OVER/UNDER JUEGOS RECALIBRADO + FILTRO DE DOMINANCIA
    # -------------------------------------------------------------------------
    if es_grand_slam:
        umbral_over, umbral_under = 163.0, 145.0
        linea_base_over = "Más de 38.5 / 39.5"
        linea_base_under = "Menos de 36.5 / 37.5" if suma_saques <= 139.0 else "Menos de 39.5 / 40.5"
    elif es_challenger:
        umbral_over, umbral_under = 156.0, 146.0
        linea_base_over = "Más de 21.5 / 22.5"
        linea_base_under = "Menos de 20.5 / 21.5"
    else:
        umbral_over, umbral_under = 164.0, 151.0
        linea_base_over = "Más de 22.5"
        linea_base_under = "Menos de 21.5"
        
    if suma_saques >= umbral_over:
        pron_juegos = "🟢 OVER JUEGOS"
        linea_juegos = linea_base_over
        dist = suma_saques - umbral_over
        fia_juegos = min(98.0, 65.0 + (dist * 2.8))
        score_orden = dist
        
        if tipo_handicap in ["Fuerte", "Moderado"] and pron_sets == "📉 UNDER SETS (Vía Rápida)":
            pron_juegos = "🟡 PASAR LARGO"
            linea_juegos = "N/A"
            fia_juegos = 50.0
            score_orden = -1.0
            
    elif suma_saques <= umbral_under:
        # ---> NUEVA REGLA: FILTRO DE DOMINANCIA PARA UNDERS <---
        if diferencia_saque < 4.5:
            pron_juegos = "🟡 PASAR (Riesgo por Igualdad)"
            linea_juegos = "N/A"
            fia_juegos = 50.0
            score_orden = -2.0
        else:
            pron_juegos = "🔴 UNDER JUEGOS"
            linea_juegos = linea_base_under
            dist = umbral_under - suma_saques
            fia_juegos = min(98.0, 65.0 + (dist * 2.8))
            score_orden = dist
            
            if es_grand_slam and tipo_handicap in ["Igualado", "Moderado"]:
                fia_juegos -= 25.0
                if fia_juegos < 65.0:
                    pron_juegos = "🟡 PASAR LARGO"
                    linea_juegos = "N/A"
                    fia_juegos = 50.0
                    score_orden = -5.0
    else:
        pron_juegos = "🟡 PASAR LARGO"
        linea_juegos = "N/A"
        fia_juegos = 50.0
        score_orden = -abs(suma_saques - ((umbral_over + umbral_under) / 2))

    # -------------------------------------------------------------------------
    # MERCADO 4: TIE-BREAK EN EL PARTIDO (MÓDULOS ESPECIALES)
    # -------------------------------------------------------------------------
    if es_hierba:
        # MÓDULO HIERBA: Máxima propensión al Tie-Break
        min_saque_requerido = 78.0
        umbral_tb_si = 156.0
        if hold_j1 >= min_saque_requerido and hold_j2 >= min_saque_requerido and suma_saques >= umbral_tb_si:
            pron_tb = "🎾 TIE-BREAK: SÍ"
            margen = suma_saques - umbral_tb_si
            fia_tb = min(96.0, 75.0 + (margen * 3.0))
        elif suma_saques <= 145.0 and diferencia_saque > 5.0:
            pron_tb = "❌ TIE-BREAK: NO"
            fia_tb = min(90.0, 70.0 + ((145.0 - suma_saques) * 1.5))
        else:
            pron_tb = "🎾 TIE-BREAK: SÍ (Tendencia Hierba)"
            fia_tb = 65.0
    else:
        # SUPERFICIES ESTÁNDAR
        min_saque_requerido = 83.5 if es_grand_slam else 81.5
        if hold_j1 >= min_saque_requerido and hold_j2 >= min_saque_requerido and suma_saques >= (umbral_over + 2):
            pron_tb = "🎾 TIE-BREAK: SÍ"
            margen = (hold_j1 + hold_j2) - (min_saque_requerido * 2)
            fia_tb = min(96.0, 70.0 + (margen * 3.5))
        elif hold_j1 <= 75.5 or hold_j2 <= 75.5 or (not es_grand_slam and suma_saques <= 154.0):
            # ---> NUEVA REGLA: FILTRO DE IGUALDAD PARA NO-TIEBREAK <---
            if diferencia_saque < 3.0:
                pron_tb = "🟡 SIN TENDENCIA (Riesgo TB por Igualdad)"
                fia_tb = 50.0
            else:
                pron_tb = "❌ TIE-BREAK: NO"
                umbral_referencia_tb = 154.0 if not es_grand_slam else 160.0
                fia_tb = min(95.0, 70.0 + (max(0.0, umbral_referencia_tb - suma_saques) * 1.2))
        else:
            if es_grand_slam and tipo_handicap == "Igualado":
                pron_tb = "🎾 TIE-BREAK: SÍ"
                fia_tb = 62.0
            else:
                pron_tb = "🟡 SIN TENDENCIA"
                fia_tb = 50.0

    # -------------------------------------------------------------------------
    # SISTEMA EXPERTO DE EVALUACIÓN INDIVIDUAL (VEREDICTO MAESTRO)
    # -------------------------------------------------------------------------
    opciones_validas = []
    if "PASAR" not in pron_juegos:
        opciones_validas.append(("Juegos Totales", pron_juegos, fia_juegos, linea_juegos))
    if "SIN TENDENCIA" not in pron_tb:
        opciones_validas.append(("Tie-Break", pron_tb, fia_tb, "N/A"))
    if "Evitar Hándicap" not in pron_handicap:
        opciones_validas.append(("Hándicap / Ganador", pron_handicap, fia_handicap, linea_handicap))
    if "Incierto" not in pron_sets:
        opciones_validas.append(("Duración en Sets", pron_sets, fia_sets, linea_sets))

    if opciones_validas:
        opciones_ordenadas = sorted(opciones_validas, key=lambda x: x[2], reverse=True)
        mejor = opciones_ordenadas[0]
        if mejor[2] >= 60.0:
            veredicto = f"🎯 PRONÓSTICO MÁS FIABLE: En '{mejor[0]}' se proyecta '{mejor[1]}' con una fiabilidad del {mejor[2]:.1f}%"
            if mejor[3] != "N/A": veredicto += f" (Línea: {mejor[3]})"
        else:
            veredicto = "🟡 VEREDICTO: PASAR LARGO (Ningún mercado supera el umbral mínimo de confianza estadística)"
    else:
        veredicto = "🟡 VEREDICTO: PASAR LARGO (Contradicción o riesgos detectados por filtros de seguridad)"

    return {
        "Juegos_Pron": pron_juegos, "Juegos_Lin": linea_juegos, "Juegos_Fia": fia_juegos,
        "TB_Pron": pron_tb, "TB_Fia": fia_tb,
        "Hand_Pron": pron_handicap, "Hand_Lin": linea_handicap, "Hand_Fia": fia_handicap,
        "Sets_Pron": pron_sets, "Sets_Lin": linea_sets, "Sets_Fia": fia_sets,
        "Veredicto_Global": veredicto, "_score_orden": score_orden, "Suma": suma_saques,
        "Diferencia": diferencia_saque, "Tipo_Handicap": tipo_handicap
    }

def buscar_jugador_flexible(nombre_buscado, diccionario_jugadores):
    def limpiar(texto):
        return "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn').lower().strip()
    nb = limpiar(nombre_buscado)
    if not nb or len(nb) < 2: return None
    for nombre_real in diccionario_jugadores.keys():
        nr = limpiar(nombre_real)
        if nr == nb or nb in nr or nr in nb: return nombre_real
    if "." in nb:
        partes_b = nb.split(".", 1)
        inicial = partes_b[0].strip()
        apellido = partes_b[1].strip()
        if apellido:
            for nombre_real in diccionario_jugadores.keys():
                nr = limpiar(nombre_real)
                if apellido in nr:
                    if nr.startswith(inicial) or any(p.startswith(inicial) for p in nr.split()): return nombre_real
    palabras_b = nb.split()
    if palabras_b:
        ultimo_apellido = palabras_b[-1]
        if len(ultimo_apellido) > 2:
            for nombre_real in diccionario_jugadores.keys():
                if ultimo_apellido in limpiar(nombre_real): return nombre_real
    return None

def extraer_partidos_sofascore_por_bloques(texto):
    lineas = [l.strip() for l in texto.split('\n') if l.strip()]
    paises_lista_negra = {
        "france", "france,", "japan", "japan,", "usa", "usa,", "argentina", "argentina,", 
        "switzerland", "switzerland,", "spain", "spain,", "italy", "germany", "australia",
        "brazil", "chile", "canada", "united states", "great britain", "uk", "serbia",
        "croatia", "belgium", "netherlands", "czech republic", "slovakia", "austria",
        "hungary", "hungary,", "romania", "romania,", "algeria", "bolivia", 
        "bosnia & herzegovina", "bulgaria", "chinese taipei", "czechia", "denmark", 
        "ecuador", "georgia", "india", "iran", "ireland", "israel", "kazakhstan", 
        "latvia", "lebanon", "mexico", "moldova", "north macedonia", "norway", "poland", 
        "russia", "south korea", "sweden", "ukraine", "united kingdom", "uruguay", 
        "uzbekistan", "zimbabwe", "colombia", "peru", "portugal", "greece", "china"
    }
    partidos_finales = []
    superficie_actual = "Dura 🔵"
    bloques = []
    bloque_actual = []
    
    for l in lineas:
        l_lower = l.lower()
        if "tierra batida" in l_lower or "clay" in l_lower: superficie_actual = "Tierra Batida 🟤"
        elif "hierba" in l_lower or "grass" in l_lower: superficie_actual = "Hierba 🟢"
        elif "dura" in l_lower or "hard" in l_lower: superficie_actual = "Dura 🔵"
            
        if re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', l) or re.search(r'\d{1,2}:\d{2}$', l):
            if bloque_actual: bloques.append(bloque_actual)
            bloque_actual = [l, superficie_actual]
        else:
            if bloque_actual: bloque_actual.append(l)
    if bloque_actual: bloques.append(bloque_actual)
        
    for b in bloques:
        sup_del_bloque = b[1]
        lineas_datos = b[2:]
        hora_partido = "N/A"
        for linea in b:
            match = re.search(r'\d{1,2}:\d{2}', linea)
            if match:
                hora_partido = match.group()
                break
        
        jugadores = []
        for item in lineas_datos:
            item_limpio = item.strip()
            item_lower = item_limpio.lower()
            if item_lower in paises_lista_negra: continue
            if any(x in item_lower for x in ["wimbledon", "grand slam", "hierba", "dura", "atp", "wta", "challenger", "outdoor", "indoor", "tierra batida", "clay", "grass", "hard"]): continue
            if item_limpio == "-" or item_limpio.isdigit() or ":" in item_limpio or "/" in item_limpio: continue
            if len(item_limpio) > 2: jugadores.append(item_limpio)
                
        if len(jugadores) >= 2:
            partidos_finales.append((jugadores[0], jugadores[1], sup_del_bloque, hora_partido))
            
    return partidos_finales


def limpiar_nombre_base(texto):
    """Normaliza nombres para comparar partidos entre pronóstico y resultados."""
    if texto is None:
        return ""
    texto = str(texto)
    texto = "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    texto = re.sub(r'[^a-zA-Z0-9\s]', ' ', texto).lower()
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto


def es_linea_pais_o_ruido(linea):
    """Filtra países, cabeceras y líneas que no son jugadores en bloques de SofaScore."""
    if not linea:
        return True
    l = limpiar_nombre_base(linea)
    paises = {
        "france", "japan", "usa", "argentina", "switzerland", "spain", "italy", "germany", "australia",
        "brazil", "chile", "canada", "united states", "great britain", "uk", "serbia", "croatia",
        "belgium", "netherlands", "czech republic", "slovakia", "austria", "hungary", "romania",
        "algeria", "bolivia", "bosnia herzegovina", "bulgaria", "chinese taipei", "czechia", "denmark",
        "ecuador", "georgia", "india", "iran", "ireland", "israel", "kazakhstan", "latvia", "lebanon",
        "mexico", "moldova", "north macedonia", "norway", "poland", "russia", "south korea", "sweden",
        "ukraine", "united kingdom", "uruguay", "uzbekistan", "zimbabwe", "colombia", "peru",
        "portugal", "greece", "china", "turkey", "finland", "lithuania", "slovenia", "thailand",
        "new zealand", "south africa", "austria", "montenegro", "dominican republic", "estonia"
    }
    palabras_ruido = [
        "atp", "wta", "challenger", "itf", "grand slam", "wimbledon", "roland garros", "us open",
        "australian open", "dura", "hard", "clay", "grass", "hierba", "tierra", "batida", "indoor",
        "outdoor", "round", "qualification", "qualifying", "final", "semifinal", "quarterfinal",
        "sofascore", "ranking", "scheduled", "postponed", "cancelled"
    ]
    if l in paises:
        return True
    if any(p in l for p in palabras_ruido):
        return True
    if re.fullmatch(r'[\d\s:\-/.,]+', linea.strip()):
        return True
    if len(l) <= 1:
        return True
    return False


def marcador_set_valido(a, b):
    """Comprueba si una pareja de juegos parece un set real de tenis terminado.

    Importante:
    - No aceptamos marcadores tipo 10-8, 11-9, 12-10 como sets.
      Normalmente son puntos de tie-break que SofaScore puede pegar junto al marcador.
    - Contarlos como sets infla los juegos totales y falsea el Over/Under.
    """
    try:
        a, b = int(a), int(b)
    except Exception:
        return False
    if a < 0 or b < 0 or a > 7 or b > 7:
        return False
    # Sets normales: 6-0 a 6-4, 7-5, 7-6 y viceversa.
    if a == 6 and 0 <= b <= 4:
        return True
    if b == 6 and 0 <= a <= 4:
        return True
    if a == 7 and b in (5, 6):
        return True
    if b == 7 and a in (5, 6):
        return True
    return False


def parsear_marcador_sets_desde_texto(texto):
    """Extrae sets tipo 6-4 7-6 desde una línea simplificada."""
    if not texto:
        return []
    pares = re.findall(r'(\d{1,2})\s*[-–]\s*(\d{1,2})', texto)
    sets = []
    for a, b in pares:
        if marcador_set_valido(a, b):
            sets.append((int(a), int(b)))
    return sets


def limpiar_numeros_tiebreak_sofascore(nums):
    """Elimina pares que parecen puntos de tie-break pegados como si fueran sets.

    Ejemplo típico al copiar SofaScore:
    7-6 11-9 6-3  -> el 11-9 son puntos del tie-break, no juegos.
    """
    nums = list(nums)
    variantes = [nums]
    limpia = []
    i = 0
    while i < len(nums):
        if i + 1 < len(nums):
            a, b = nums[i], nums[i + 1]
            if max(a, b) >= 8 and abs(a - b) >= 2:
                i += 2
                continue
        limpia.append(nums[i])
        i += 1
    if limpia != nums:
        variantes.append(limpia)
    return variantes


def inferir_sets_desde_numeros(numeros):
    """Intenta reconstruir sets cuando SofaScore pega los números en columnas sueltas."""
    nums_base = []
    for n in numeros:
        try:
            nums_base.append(int(n))
        except Exception:
            pass
    if len(nums_base) < 4:
        return []

    candidatos = []

    for nums in limpiar_numeros_tiebreak_sofascore(nums_base):
        # Formato habitual al copiar tabla: J1 set1,set2,set3 + J2 set1,set2,set3.
        for k in [5, 4, 3, 2]:
            if len(nums) >= 2 * k:
                p1 = nums[:k]
                p2 = nums[k:2*k]
                sets = list(zip(p1, p2))
                if all(marcador_set_valido(a, b) for a, b in sets):
                    sets_ganados_1 = sum(1 for a, b in sets if a > b)
                    sets_ganados_2 = sum(1 for a, b in sets if b > a)
                    if sets_ganados_1 != sets_ganados_2:
                        candidatos.append(sets)

        # Formato alternativo: set1 J1, set1 J2, set2 J1, set2 J2...
        for k in [5, 4, 3, 2]:
            if len(nums) >= 2 * k:
                sets = [(nums[i], nums[i+1]) for i in range(0, 2*k, 2)]
                if all(marcador_set_valido(a, b) for a, b in sets):
                    sets_ganados_1 = sum(1 for a, b in sets if a > b)
                    sets_ganados_2 = sum(1 for a, b in sets if b > a)
                    if sets_ganados_1 != sets_ganados_2:
                        candidatos.append(sets)

    if not candidatos:
        return []

    # Preferimos candidatos razonables. Si hay empate, gana el de más sets reales.
    candidatos = sorted(candidatos, key=lambda x: (len(x), sum(a + b for a, b in x)), reverse=True)
    return candidatos[0]


def extraer_resultados_tenis(texto, superficie_defecto="Dura 🔵"):
    """
    Extrae resultados desde dos formatos:
    1) Recomendado: Jugador 1 vs Jugador 2 | 6-4 7-6 | Hierba
    2) Pegado bruto de SofaScore con FT y números en líneas separadas.
    """
    resultados = []
    if not texto or not texto.strip():
        return resultados

    superficie_actual = superficie_defecto
    lineas = [l.strip() for l in texto.split('\n') if l.strip()]

    # 1) Formato simplificado por línea.
    for linea in lineas:
        l_low = linea.lower()
        if "tierra" in l_low or "clay" in l_low:
            sup_linea = "Tierra Batida 🟤"
        elif "hierba" in l_low or "grass" in l_low:
            sup_linea = "Hierba 🟢"
        elif "dura" in l_low or "hard" in l_low:
            sup_linea = "Dura 🔵"
        else:
            sup_linea = superficie_actual

        sets = parsear_marcador_sets_desde_texto(linea)
        if sets and re.search(r'\b(vs|v\.|contra)\b', linea, flags=re.I):
            antes_marcador = re.split(r'\d{1,2}\s*[-–]\s*\d{1,2}', linea, maxsplit=1)[0]
            partes = re.split(r'\bvs\b|\bv\.\b|\bcontra\b', antes_marcador, flags=re.I)
            if len(partes) >= 2:
                j1 = partes[0].replace('|', ' ').strip(' -—|')
                j2 = partes[1].replace('|', ' ').strip(' -—|')
                if j1 and j2:
                    resultados.append({"Jugador 1": j1, "Jugador 2": j2, "Sets": sets, "Superficie": sup_linea, "Fuente": "Línea"})

    if resultados:
        return resultados

    # 2) Pegado bruto SofaScore.
    bloques = []
    bloque = []
    for l in lineas:
        l_low = l.lower()
        if "tierra batida" in l_low or l_low == "clay" or " clay" in l_low:
            superficie_actual = "Tierra Batida 🟤"
        elif "hierba" in l_low or l_low == "grass" or " grass" in l_low:
            superficie_actual = "Hierba 🟢"
        elif "dura" in l_low or l_low == "hard" or " hard" in l_low:
            superficie_actual = "Dura 🔵"

        es_inicio = bool(re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', l)) or l.upper() in {"FT", "RET", "W/O", "WO"}
        if es_inicio and bloque:
            bloques.append(bloque)
            bloque = []
        if es_inicio:
            bloque = [{"linea": l, "superficie": superficie_actual}]
        elif bloque:
            bloque.append({"linea": l, "superficie": superficie_actual})
    if bloque:
        bloques.append(bloque)

    for b in bloques:
        sup_bloque = b[0].get("superficie", superficie_defecto)
        crudas = [x["linea"] for x in b]
        if any(x.upper() in {"RET", "W/O", "WO"} for x in crudas):
            estado = "RET/WO"
        else:
            estado = "FT"

        candidatos_jug = []
        numeros = []
        for x in crudas:
            x_limpia = x.strip()
            if re.fullmatch(r'\d{1,2}', x_limpia):
                numeros.append(int(x_limpia))
            elif not es_linea_pais_o_ruido(x_limpia) and not re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', x_limpia) and x_limpia.upper() not in {"FT", "RET", "W/O", "WO"}:
                candidatos_jug.append(x_limpia)

        if len(candidatos_jug) >= 2:
            sets = inferir_sets_desde_numeros(numeros)
            if sets:
                resultados.append({
                    "Jugador 1": candidatos_jug[0],
                    "Jugador 2": candidatos_jug[1],
                    "Sets": sets,
                    "Superficie": sup_bloque,
                    "Fuente": f"SofaScore {estado}"
                })

    return resultados


def total_juegos_sets(sets):
    return sum(a + b for a, b in sets)


def sets_ganados(sets):
    j1 = sum(1 for a, b in sets if a > b)
    j2 = sum(1 for a, b in sets if b > a)
    return j1, j2


def hay_tiebreak(sets):
    return any((a == 7 and b == 6) or (a == 6 and b == 7) for a, b in sets)


def extraer_primera_linea_numerica(texto):
    nums = re.findall(r'\d+(?:\.\d+)?', str(texto))
    if not nums:
        return None
    return float(nums[0])


def evaluar_over_under(pronostico, linea_texto, juegos_totales):
    """
    Valida la APUESTA REAL del usuario, no la línea exacta que recomienda el motor.

    Regla práctica:
    - Si el motor da señal OVER JUEGOS, se valida como Over 18.5.
    - Si el motor da señal UNDER JUEGOS, se valida como Under 24.5.

    Ejemplo: aunque el motor recomiende Más de 21.5 / 22.5, el histórico se mide
    contra Over 18.5 porque esa es la apuesta real que está usando Richy.
    """
    if juegos_totales is None:
        return None, None, None
    p = str(pronostico).lower()
    if "over" in p or "más" in p or "mas" in p:
        linea_real = 18.5
        return juegos_totales > linea_real, "Over Juegos", linea_real
    if "under" in p or "menos" in p:
        linea_real = 24.5
        return juegos_totales < linea_real, "Under Juegos", linea_real
    return None, None, None


def evaluar_sets(pronostico, linea_texto, num_sets):
    linea = extraer_primera_linea_numerica(linea_texto)
    if linea is None:
        return None, None, None
    p = str(pronostico).lower()
    if "over" in p or "más" in p or "mas" in p:
        return num_sets > linea, "Over Sets", linea
    if "under" in p or "menos" in p:
        return num_sets < linea, "Under Sets", linea
    return None, None, None


def evaluar_tiebreak(pronostico, tuvo_tb):
    """Valida solo señales reales de Tie-Break Sí / No.

    Corrección importante:
    - Antes, "SIN TENDENCIA" podía entrar como Tie-Break Sí porque contiene "si".
    - Ahora las señales neutras no se validan como apuesta.
    """
    p_original = str(pronostico)
    p = "".join(c for c in unicodedata.normalize("NFD", p_original) if unicodedata.category(c) != "Mn").lower()

    if "sin tendencia" in p or "faltan datos" in p or "n/a" in p:
        return None, None, None

    if ("tie-break: si" in p or "tiebreak: si" in p or "tie break: si" in p):
        return bool(tuvo_tb), "Tie-Break Sí", "Sí"

    if ("tie-break: no" in p or "tiebreak: no" in p or "tie break: no" in p):
        return not bool(tuvo_tb), "Tie-Break No", "No"

    return None, None, None


def evaluar_handicap(pronostico, linea_texto, sets, jugador1, jugador2):
    linea = extraer_primera_linea_numerica(linea_texto)
    if linea is None or not sets:
        return None, None, None
    p = limpiar_nombre_base(pronostico)
    j1 = limpiar_nombre_base(jugador1)
    j2 = limpiar_nombre_base(jugador2)
    juegos_j1 = sum(a for a, _ in sets)
    juegos_j2 = sum(b for _, b in sets)
    margen_requerido = abs(linea)

    if j1 and j1 in p:
        return (juegos_j1 - juegos_j2) > margen_requerido, "Hándicap Favorito", f"-{margen_requerido}"
    if j2 and j2 in p:
        return (juegos_j2 - juegos_j1) > margen_requerido, "Hándicap Favorito", f"-{margen_requerido}"
    return None, None, None


def construir_resumen_validacion(df_detalle):
    """Resumen limpio por mercado.

    En versiones anteriores el Hándicap salía separado por jugador, creando muchas
    filas de 1 pick y haciendo difícil ver si el mercado funciona. Ahora se agrupa
    por mercado + línea real para que el resumen sea práctico.
    """
    if df_detalle is None or df_detalle.empty:
        return pd.DataFrame()
    df_val = df_detalle[df_detalle["Resultado"].isin(["✅ Acierto", "❌ Fallo"])].copy()
    if df_val.empty:
        return pd.DataFrame()

    df_val["Pronóstico Resumen"] = df_val["Pronóstico"].astype(str)
    mask_hand = df_val["Mercado"].eq("Hándicap Favorito")
    df_val.loc[mask_hand, "Pronóstico Resumen"] = "Favorito " + df_val.loc[mask_hand, "Línea Validada"].astype(str)

    df_val["Acierto_num"] = (df_val["Resultado"] == "✅ Acierto").astype(int)
    resumen = (
        df_val.groupby(["Mercado", "Pronóstico Resumen", "Línea Validada"], dropna=False)
        .agg(Picks=("Resultado", "count"), Aciertos=("Acierto_num", "sum"))
        .reset_index()
        .rename(columns={"Pronóstico Resumen": "Pronóstico"})
    )
    resumen["Fallos"] = resumen["Picks"] - resumen["Aciertos"]
    resumen["% Acierto"] = (resumen["Aciertos"] / resumen["Picks"] * 100).round(1).astype(str) + "%"
    resumen = resumen.sort_values(by=["Aciertos", "Picks"], ascending=False)
    return resumen


def construir_control_dia(df_detectados, df_detalle):
    """Crea un control rápido del día para no sobrevalorar señales por el contexto.

    Ejemplo: si casi todos los partidos del día fueron sin tie-break, un 94% de
    acierto en Tie-Break No puede ser bueno, pero la ventaja real contra la base
    del día puede ser pequeña.
    """
    filas = []
    if df_detectados is not None and not df_detectados.empty:
        total = int(len(df_detectados))
        tb_no = int((df_detectados["Tie-Break"].astype(str) == "No").sum()) if "Tie-Break" in df_detectados.columns else 0
        tb_si = int((df_detectados["Tie-Break"].astype(str) == "Sí").sum()) if "Tie-Break" in df_detectados.columns else 0
        pct_no = round(tb_no / total * 100, 1) if total else 0.0
        faltan_ta = int(df_detectados["Match TA"].astype(str).str.contains("NO ENCONTRADO", na=False).sum()) if "Match TA" in df_detectados.columns else 0
        filas.extend([
            {"Métrica": "Partidos detectados", "Valor": total, "Detalle": "Total leído del bloque de resultados"},
            {"Métrica": "Partidos con Match TA incompleto", "Valor": faltan_ta, "Detalle": "Al menos un jugador aparece como NO ENCONTRADO"},
            {"Métrica": "Tie-Break real: No", "Valor": tb_no, "Detalle": f"Base del día sin tie-break: {pct_no}%"},
            {"Métrica": "Tie-Break real: Sí", "Valor": tb_si, "Detalle": f"Base del día con tie-break: {round(tb_si / total * 100, 1) if total else 0.0}%"},
        ])

    if df_detalle is not None and not df_detalle.empty:
        df_val = df_detalle[df_detalle["Resultado"].isin(["✅ Acierto", "❌ Fallo"])].copy()
        filas.append({"Métrica": "Picks validados", "Valor": int(len(df_val)), "Detalle": "Filas con acierto/fallo real"})
        if "Mercado" in df_val.columns:
            tb_no_rows = df_val[df_val["Mercado"].eq("Tie-Break No")]
            if not tb_no_rows.empty:
                ac = int((tb_no_rows["Resultado"] == "✅ Acierto").sum())
                picks = int(len(tb_no_rows))
                filas.append({"Métrica": "Picks Tie-Break No", "Valor": picks, "Detalle": f"{ac}/{picks} = {round(ac / picks * 100, 1)}%"})

        if "Mercado" in df_detalle.columns:
            datos_dudosos = int(df_detalle["Mercado"].eq("Datos dudosos").sum())
            sin_pick = int(df_detalle["Mercado"].eq("Sin pick validable").sum())
            filas.append({"Métrica": "Filas Datos dudosos", "Valor": datos_dudosos, "Detalle": "Bloqueadas por Hold% no encontrado"})
            filas.append({"Métrica": "Filas sin pick validable", "Valor": sin_pick, "Detalle": "El motor no dio señal clara"})

    return pd.DataFrame(filas)


def etiqueta_linea_real_juegos(pronostico):
    """Devuelve la línea segura que realmente está usando Richy para juegos totales.

    La línea del motor funciona como DISPARADOR:
    - Si el motor ve un Over 21.5/22.5, se juega más conservador: Over 18.5.
    - Si el motor ve un Under 21.5/22.5, se juega más conservador: Under 24.5/25.5.

    En validación se mide Under 24.5 como referencia conservadora; la hoja de estudio
    de líneas muestra también Under 25.5 y 26.5.
    """
    p = str(pronostico).lower()
    if "over" in p or "más" in p or "mas" in p:
        return "Over 18.5"
    if "under" in p or "menos" in p:
        return "Under 24.5 / 25.5"
    return "N/A"


def diagnosticar_tipo_partido(res, hold_j1=None, hold_j2=None, superficie=""):
    """V6: primero diagnostica estructura del partido; después se elige mercado.

    Objetivo: evitar los dos fallos que vimos en directo:
    - Over 18.5/19.5 en partidos de paliza corta.
    - Under 24.5/25.5 en partidos con riesgo real de 3 sets/tie-break.
    """
    try:
        h1 = float(hold_j1) if hold_j1 is not None else None
        h2 = float(hold_j2) if hold_j2 is not None else None
    except Exception:
        h1 = h2 = None
    suma = float(res.get("Suma", (h1 or 0) + (h2 or 0)) or 0)
    diferencia = abs(h1 - h2) if h1 is not None and h2 is not None else float(res.get("Diferencia", 0) or 0)
    sets_pron = str(res.get("Sets_Pron", ""))
    hand_pron = str(res.get("Hand_Pron", ""))
    tb_pron = str(res.get("TB_Pron", ""))
    es_hierba = "hierba" in str(superficie).lower() or "grass" in str(superficie).lower() or "🟢" in str(superficie)
    es_tierra = "tierra" in str(superficie).lower() or "clay" in str(superficie).lower() or "🟤" in str(superficie)

    via_rapida = ("UNDER SETS" in sets_pron or "Vía Rápida" in sets_pron or "Via Rapida" in sets_pron or "Hándicap Fuerte" in hand_pron)
    riesgo_largo = ("OVER SETS" in sets_pron or "Partido Largo" in sets_pron)
    tb_si = "TIE-BREAK: SÍ" in tb_pron or "TIE-BREAK: SI" in tb_pron

    # 1) Paliza / 2-0 corto: el gran enemigo del Over 18.5.
    if diferencia >= 8.0 and via_rapida:
        return "PALIZA PROBABLE / 2-0 CORTO", "Bloquea Over. Solo estudiar Under alto o TB No si la línea es cómoda."
    if diferencia >= 9.5:
        return "DOMINANCIA CLARA", "Riesgo de 6-3 6-2 o similar. Over solo si hay saque muy alto de ambos."

    # 2) Igualdad larga: zona natural del Over 18.5.
    if diferencia <= 3.5 and (riesgo_largo or suma >= 156.0 or es_hierba):
        return "IGUALADO LARGO / OVER18", "Favorece Over 18.5. Evitar Under por riesgo de 3 sets/tie-break."

    # 3) Igualdad sin saque alto: partido caótico, puede ir a 3 sets aunque no haya TB.
    if diferencia <= 4.5 and suma < 156.0:
        return "IGUALADO CAÓTICO / RIESGO 3 SETS", "No jugar Under. Over 18.5 puede tener sentido si la cuota es buena."

    # 4) Dominio rápido: el único tipo donde el Under puede tener sentido.
    if diferencia >= 6.5 and suma <= 153.0 and via_rapida and not es_hierba:
        return "DOMINIO RÁPIDO / UNDER POSIBLE", "Under alto válido si la línea real es 24.5/25.5/26.5."

    # 5) Saque alto: no forzar Under.
    if suma >= 160.0 or tb_si:
        return "SAQUE ALTO / POSIBLE OVER", "No jugar Under. Over 18.5 puede ser la lectura segura."

    if es_tierra and suma <= 150.0 and diferencia >= 5.5:
        return "TIERRA DE BREAKS / TB NO", "Mejor mirar TB No o Under alto con mucha prudencia."

    return "SIN VENTAJA CLARA", "Pasar o stake mínimo; el modelo no identifica estructura fiable."


def clasificar_accion_juegos(res, hold_j1=None, hold_j2=None, superficie=""):
    """V6: Over/Under no decide por suma simple; decide por tipo de partido.

    Reglas base:
    - Over seguro = el motor ve partido largo, pero bloqueamos si hay paliza probable.
    - Under seguro = solo dominio rápido/vía rápida.
    - Si hay riesgo de 3 sets, nunca Under.
    """
    pron = str(res.get("Juegos_Pron", ""))
    linea_motor_txt = str(res.get("Juegos_Lin", ""))
    fia = float(res.get("Juegos_Fia", 50.0) or 50.0)
    diferencia = abs(float(hold_j1) - float(hold_j2)) if hold_j1 is not None and hold_j2 is not None else None
    tipo, alerta = diagnosticar_tipo_partido(res, hold_j1, hold_j2, superficie)
    sets_pron = str(res.get("Sets_Pron", ""))
    es_hierba = "hierba" in str(superficie).lower() or "grass" in str(superficie).lower() or "🟢" in str(superficie)

    if "OVER JUEGOS" in pron:
        pick = "Over 18.5"
        if "PALIZA" in tipo or "DOMINANCIA CLARA" in tipo:
            return "NO Over / posible Under", "PASAR", f"Bloqueado V6: {tipo}. {alerta}"
        if "IGUALADO LARGO" in tipo and fia >= 70:
            return pick, "JUGAR", f"V6: {tipo}. Motor proyecta línea más alta; se usa Over 18.5 como línea segura."
        if "SAQUE ALTO" in tipo and fia >= 72:
            return pick, "JUGAR BAJO STAKE", f"V6: {tipo}. Over válido, pero sin subir línea."
        if fia >= 68 and (diferencia is None or diferencia <= 6.0):
            return pick, "OBSERVAR", f"Over posible, pero falta confirmación total de estructura. {tipo}: {alerta}"
        return pick, "PASAR", f"Over no limpio. {tipo}: {alerta}"

    if "UNDER JUEGOS" in pron:
        linea_motor = extraer_primera_linea_numerica(linea_motor_txt)
        colchon = (24.5 - linea_motor) if linea_motor is not None else None
        pick = "Under 24.5 / 25.5"

        if es_hierba:
            return "Revisar Over 18.5 / NO Under", "PASAR", "Bloqueado V6: Under en hierba. Un 7-6 o tercer set rompe la línea."
        if "IGUALADO" in tipo or "RIESGO 3 SETS" in tipo or "SAQUE ALTO" in tipo:
            return "Revisar Over 18.5 / NO Under", "PASAR", f"Bloqueado V6: {tipo}. {alerta}"
        if "DOMINIO RÁPIDO" in tipo and fia >= 70:
            detalle = f" Colchón aprox: +{colchon:.1f} juegos." if colchon is not None else ""
            return pick, "JUGAR BAJO STAKE", f"V6: Under solo permitido por dominio/vía rápida.{detalle}"
        if "TIERRA DE BREAKS" in tipo and fia >= 74:
            return pick, "OBSERVAR", f"V6: Under posible, pero mejor TB No si hay mercado. {alerta}"
        return pick, "PASAR", f"Under no tiene estructura suficiente. {tipo}: {alerta}"

    return "N/A", "PASAR", f"Sin señal de juegos. {tipo}: {alerta}"

def etiqueta_pick_tiebreak(pronostico_tb):
    """Traduce la señal del motor de tie-break a un mercado real y limpio."""
    p = str(pronostico_tb).lower()
    if "sin tendencia" in p or "faltan datos" in p or "n/a" in p:
        return "N/A"
    if "tie-break" in p and ("sí" in p or "si" in p):
        return "Tie-Break Sí"
    if "tie-break" in p and "no" in p:
        return "Tie-Break No"
    return "N/A"


def ranking_accion(accion):
    """Convierte acciones en prioridad para ordenar sin depender del texto exacto."""
    a = str(accion).upper()
    if "JUGAR SI HAY MERCADO" in a or a.strip() == "JUGAR":
        return 4
    if "JUGAR BAJO STAKE" in a:
        return 3
    if "OBSERVAR" in a:
        return 2
    return 1


def clasificar_accion_tiebreak(res, superficie=""):
    """Clasifica el mercado tie-break como JUGAR SI HAY MERCADO / OBSERVAR / PASAR.

    v5.7:
    - Tie-Break Sí sigue bloqueado.
    - Tie-Break No en hierba queda bloqueado: la muestra reciente fue mala y la superficie
      aumenta el riesgo de 7-6.
    - Tie-Break No solo puede ser premium con fiabilidad alta; después se exige también
      calidad Hold OK superficie en ambos jugadores.
    """
    pron = str(res.get("TB_Pron", ""))
    pick = etiqueta_pick_tiebreak(pron)
    try:
        fia = float(res.get("TB_Fia", 50.0) or 50.0)
    except Exception:
        fia = 50.0

    es_hierba = "hierba" in str(superficie).lower() or "grass" in str(superficie).lower() or "🟢" in str(superficie)
    es_tierra = "tierra" in str(superficie).lower() or "clay" in str(superficie).lower() or "🟤" in str(superficie)

    if pick == "Tie-Break Sí":
        return pick, "PASAR", "Bloqueado temporalmente: el Tie-Break Sí salió muy flojo en las validaciones recientes."

    if pick == "Tie-Break No":
        if es_hierba:
            return pick, "PASAR", "Bloqueado en hierba: la superficie aumenta el riesgo de tie-break y la última muestra falló esta señal."
        if fia >= 88:
            extra = " Tierra/dura favorece esta lectura cuando el Hold es limpio." if (es_tierra or not es_hierba) else ""
            return pick, "JUGAR SI HAY MERCADO", "Señal fuerte de no tie-break con filtro v5.7." + extra
        if fia >= 72:
            return pick, "OBSERVAR", "No tie-break interesante, pero no suficientemente fuerte para automático."
        return pick, "PASAR", "Tie-break no con fiabilidad insuficiente."

    return "N/A", "PASAR", "El motor no da señal clara de tie-break."


def elegir_mejor_pick(juegos_pick, juegos_accion, juegos_motivo, juegos_fia, tb_pick, tb_accion, tb_motivo, tb_fia):
    """Elige el pick más práctico entre Juegos y Tie-Break sin perder el alternativo."""
    prio_j = ranking_accion(juegos_accion)
    prio_tb = ranking_accion(tb_accion)
    try:
        juegos_fia = float(juegos_fia or 50.0)
    except Exception:
        juegos_fia = 50.0
    try:
        tb_fia = float(tb_fia or 50.0)
    except Exception:
        tb_fia = 50.0

    if tb_pick != "N/A" and (prio_tb > prio_j or (prio_tb == prio_j and tb_fia >= juegos_fia + 4.0)):
        return tb_pick, tb_accion, tb_motivo, juegos_pick

    return juegos_pick, juegos_accion, juegos_motivo, tb_pick




def ajustar_acciones_por_calidad_hold(
    pick_juegos, accion_juegos, motivo_juegos,
    pick_tb, accion_tb, motivo_tb,
    calidad_j1, calidad_j2
):
    """Rebaja señales cuando el Hold% no es limpio.

    v5.7:
    - Under seguro puede quedar como JUGAR si la línea motor es baja y no hay riesgo de 3 sets.
    - Tie-Break Sí queda bloqueado siempre.
    - Tie-Break No solo queda como JUGAR SI HAY MERCADO cuando ambos Hold son OK superficie.
      Con OK general o heurística baja a OBSERVAR.
    """
    c1, c2 = str(calidad_j1), str(calidad_j2)
    calidades = {c1, c2}
    hay_dudosa = any("DUDOSA" in c or "heurística" in c.lower() or "heuristica" in c.lower() for c in calidades)
    ambos_ok_superficie = all("OK superficie" in c for c in (c1, c2))
    ambos_ok_limpio = all("OK" in c for c in (c1, c2))

    if hay_dudosa:
        aviso = " Hold% estimado/heurístico: señal válida para estudiar, pero no premium."
        if str(accion_juegos).upper() == "JUGAR":
            accion_juegos = "OBSERVAR"
            motivo_juegos = str(motivo_juegos) + aviso
        elif "OBSERVAR" in str(accion_juegos).upper():
            motivo_juegos = str(motivo_juegos) + aviso

    if pick_tb == "Tie-Break Sí":
        accion_tb = "PASAR"
        motivo_tb = "Bloqueado: Tie-Break Sí queda fuera hasta que el histórico vuelva a validarlo."

    elif pick_tb == "Tie-Break No":
        if not ambos_ok_superficie:
            if "JUGAR" in str(accion_tb).upper():
                accion_tb = "OBSERVAR"
            if hay_dudosa:
                motivo_tb = str(motivo_tb) + " Hold% estimado/heurístico: revisar, no entrar automático."
            elif ambos_ok_limpio:
                motivo_tb = str(motivo_tb) + " Hold% limpio, pero no ambos por superficie exacta: observar antes de jugar."
            else:
                motivo_tb = str(motivo_tb) + " Hold% incompleto: no automático."
        else:
            motivo_tb = str(motivo_tb) + " Ambos Hold son OK superficie: señal TB No premium."

    return pick_juegos, accion_juegos, motivo_juegos, pick_tb, accion_tb, motivo_tb


def etiqueta_ficha_por_calidad(calidad):
    c = str(calidad)
    if "OK" in c:
        return "✅"
    if "DUDOSA" in c or "heurística" in c.lower() or "heuristica" in c.lower():
        return "⚠️ Estimada"
    return "⚠️ Hold dudoso"


def construir_resumen_tiebreak(df_detalle, df_detectados=None):
    """Resumen específico para controlar el rendimiento real de Tie-Break Sí / No.

    Añade una comparación contra la base real del día por superficie. Esto evita
    sobrevalorar Tie-Break No en jornadas donde casi todo ya fue No-TB.
    """
    if df_detalle is None or df_detalle.empty:
        return pd.DataFrame()
    df_tb = df_detalle[df_detalle["Mercado"].isin(["Tie-Break Sí", "Tie-Break No"])].copy()
    if df_tb.empty:
        return pd.DataFrame()
    df_tb = df_tb[df_tb["Resultado"].isin(["✅ Acierto", "❌ Fallo"])].copy()
    if df_tb.empty:
        return pd.DataFrame()
    df_tb["Acierto_num"] = (df_tb["Resultado"] == "✅ Acierto").astype(int)
    resumen = (
        df_tb.groupby(["Mercado", "Superficie"], dropna=False)
        .agg(Picks=("Resultado", "count"), Aciertos=("Acierto_num", "sum"))
        .reset_index()
    )
    resumen["Fallos"] = resumen["Picks"] - resumen["Aciertos"]
    resumen["% Acierto Num"] = (resumen["Aciertos"] / resumen["Picks"] * 100).round(1)

    if df_detectados is not None and not df_detectados.empty and "Tie-Break" in df_detectados.columns:
        base = df_detectados.groupby("Superficie", dropna=False).agg(
            Partidos_Base=("Tie-Break", "count"),
            TB_No_Base=("Tie-Break", lambda x: int((x.astype(str) == "No").sum())),
            TB_Si_Base=("Tie-Break", lambda x: int((x.astype(str) == "Sí").sum()))
        ).reset_index()
        resumen = resumen.merge(base, on="Superficie", how="left")

        def pct_base(row):
            total = row.get("Partidos_Base", 0) or 0
            if total == 0:
                return None
            if row.get("Mercado") == "Tie-Break No":
                return round(row.get("TB_No_Base", 0) / total * 100, 1)
            return round(row.get("TB_Si_Base", 0) / total * 100, 1)

        resumen["Base Superficie"] = resumen.apply(pct_base, axis=1)
        resumen["Ventaja vs Base"] = (resumen["% Acierto Num"] - resumen["Base Superficie"]).round(1)
        resumen["Base Superficie"] = resumen["Base Superficie"].apply(lambda x: "N/A" if pd.isna(x) else f"{x}%")
        resumen["Ventaja vs Base"] = resumen["Ventaja vs Base"].apply(lambda x: "N/A" if pd.isna(x) else f"{x:+.1f} pp")

    resumen["% Acierto"] = resumen["% Acierto Num"].astype(str) + "%"
    cols = [c for c in ["Mercado", "Superficie", "Picks", "Aciertos", "Fallos", "% Acierto", "Partidos_Base", "Base Superficie", "Ventaja vs Base"] if c in resumen.columns]
    return resumen[cols].sort_values(by=["Mercado", "Aciertos", "Picks"], ascending=[True, False, False])


def superar_lineas_juegos(juegos_totales):
    """Devuelve columnas booleanas útiles para estudiar si los Over van sobrados."""
    if juegos_totales is None or pd.isna(juegos_totales):
        return {}
    lineas = [18.5, 19.5, 20.5, 21.5, 22.5, 23.5, 24.5]
    datos = {}
    for linea in lineas:
        datos[f"Over {linea}"] = "✅" if juegos_totales > linea else "❌"
    for linea in [24.5, 23.5, 22.5, 21.5, 20.5]:
        datos[f"Under {linea}"] = "✅" if juegos_totales < linea else "❌"
    return datos




def alerta_3sets_over18(juegos_totales, num_sets, tb_real, superficie):
    """Etiqueta de control para detectar fallos tipo Under que en realidad eran Over 18.5 por 3 sets."""
    if juegos_totales is None or pd.isna(juegos_totales):
        return "N/A"
    es_hierba = "hierba" in str(superficie).lower() or "grass" in str(superficie).lower() or "🟢" in str(superficie)
    if int(num_sets or 0) >= 3 and float(juegos_totales) > 18.5:
        return "⚠️ 3 sets = Over 18.5"
    if bool(tb_real) and float(juegos_totales) > 18.5:
        return "⚠️ TB = cuidado Under"
    if es_hierba:
        return "⚠️ Hierba: cuidado Under"
    return "OK"

def tipo_over_largo(juegos_totales):
    if juegos_totales is None or pd.isna(juegos_totales):
        return "N/A"
    if juegos_totales >= 25:
        return "Over larguísimo"
    if juegos_totales >= 23:
        return "Over largo claro"
    if juegos_totales >= 21:
        return "Over medio"
    if juegos_totales >= 19:
        return "Over justo"
    return "No llegó al over real"


def construir_resumen_superficie(df_detalle):
    if df_detalle is None or df_detalle.empty or "Superficie" not in df_detalle.columns:
        return pd.DataFrame()
    df_val = df_detalle[df_detalle["Resultado"].isin(["✅ Acierto", "❌ Fallo"])].copy()
    if df_val.empty:
        return pd.DataFrame()
    df_val["Acierto_num"] = (df_val["Resultado"] == "✅ Acierto").astype(int)
    resumen = (
        df_val.groupby(["Mercado", "Línea Validada", "Superficie"], dropna=False)
        .agg(Picks=("Resultado", "count"), Aciertos=("Acierto_num", "sum"))
        .reset_index()
    )
    resumen["Fallos"] = resumen["Picks"] - resumen["Aciertos"]
    resumen["% Acierto"] = (resumen["Aciertos"] / resumen["Picks"] * 100).round(1).astype(str) + "%"
    return resumen.sort_values(by=["Mercado", "Línea Validada", "% Acierto"], ascending=[True, True, False])


def construir_resumen_lineas_juegos(df_detalle):
    """Estudia cuánto habrían acertado líneas alternativas en señales OVER/UNDER de juegos."""
    if df_detalle is None or df_detalle.empty or "Juegos Reales" not in df_detalle.columns:
        return pd.DataFrame()
    df_j = df_detalle[df_detalle["Mercado"].isin(["Over Juegos", "Under Juegos"])].copy()
    if df_j.empty:
        return pd.DataFrame()

    filas = []
    over_lineas = [18.5, 19.5, 20.5, 21.5, 22.5, 23.5, 24.5]
    under_lineas = [26.5, 25.5, 24.5, 23.5, 22.5, 21.5, 20.5]

    for mercado, grupo in df_j.groupby("Mercado"):
        juegos = pd.to_numeric(grupo["Juegos Reales"], errors="coerce").dropna()
        if juegos.empty:
            continue
        if mercado == "Over Juegos":
            for linea in over_lineas:
                aciertos = int((juegos > linea).sum())
                picks = int(len(juegos))
                filas.append({
                    "Señal Motor": mercado,
                    "Línea estudiada": f"Over {linea}",
                    "Picks": picks,
                    "Aciertos": aciertos,
                    "Fallos": picks - aciertos,
                    "% Acierto": f"{round(aciertos / picks * 100, 1)}%"
                })
        elif mercado == "Under Juegos":
            for linea in under_lineas:
                aciertos = int((juegos < linea).sum())
                picks = int(len(juegos))
                filas.append({
                    "Señal Motor": mercado,
                    "Línea estudiada": f"Under {linea}",
                    "Picks": picks,
                    "Aciertos": aciertos,
                    "Fallos": picks - aciertos,
                    "% Acierto": f"{round(aciertos / picks * 100, 1)}%"
                })
    return pd.DataFrame(filas)


def construir_over_largo(df_detalle):
    """Tabla específica para estudiar si los picks Over 18.5 permiten subir a 20.5/21.5/22.5."""
    if df_detalle is None or df_detalle.empty:
        return pd.DataFrame()
    df_over = df_detalle[df_detalle["Mercado"].eq("Over Juegos")].copy()
    if df_over.empty:
        return pd.DataFrame()
    cols_base = [c for c in ["Partido", "Superficie", "Pronóstico", "Línea Motor", "Línea Validada", "Resultado", "Marcador", "Juegos Reales", "Suma Saques", "Fiabilidad"] if c in df_over.columns]
    df_over = df_over[cols_base].copy()
    df_over["Tipo Over"] = df_over["Juegos Reales"].apply(tipo_over_largo)
    for linea in [18.5, 19.5, 20.5, 21.5, 22.5, 23.5, 24.5]:
        df_over[f"Supera {linea}"] = df_over["Juegos Reales"].apply(lambda x, l=linea: "✅" if pd.notnull(x) and x > l else "❌")
    return df_over.sort_values(by="Juegos Reales", ascending=False)

# --- INICIO DE LA APLICACIÓN WEB ---
if "lista_faltantes" not in st.session_state: st.session_state.lista_faltantes = []

json_data, diccionario_jugadores = cargar_datos_json_sin_cache(RUTA_JSON)

if json_data:
    entries = json_data.get("entries", {})
    tab1, tab2, tab3 = st.tabs(["👤 Análisis Individual", "📋 Cuadro de Mandos Multi-Mercado (Lote)", "✅ Validador Resultados"])
    
    with tab1:
        st.subheader("Configuración de Partido Único Completo")
        nombres_ordenados = sorted(list(diccionario_jugadores.keys()))
        col1, col2 = st.columns(2)
        with col1: j1_elegido = st.selectbox("Selecciona el Jugador 1:", nombres_ordenados, index=0, key="sb_j1")
        with col2:
            idx_j2 = 1 if len(nombres_ordenados) > 1 else 0
            j2_elegido = st.selectbox("Selecciona el Jugador 2:", nombres_ordenados, index=idx_j2, key="sb_j2")
        col_sup, col_sets = st.columns(2)
        with col_sup: superficie = st.radio("Superficie:", ["Dura 🔵", "Tierra Batida 🟤", "Hierba 🟢"], horizontal=True, key="r_sup1")
        with col_sets: formato_sets = st.radio("Formato/Categoría:", ["Al mejor de 3 sets (ATP Estándar)", "Al mejor de 3 sets (Circuito Challenger)", "Al mejor de 5 sets (Grand Slam)"], key="r_set1")
        
        if st.button("🚀 ESCANEAR TODOS LOS MERCADOS", width="stretch"):
            if j1_elegido == j2_elegido: st.warning("⚠️ Selecciona dos jugadores diferentes.")
            else:
                ids = []
                for j in [j1_elegido, j2_elegido]:
                    id_j = diccionario_jugadores[j]
                    if "raw_text" not in entries[id_j] and "alias_to" in entries[id_j]: id_j = entries[id_j]["alias_to"]
                    ids.append(id_j)
                h1, h1_calidad, h1_motivo = obtener_hold_percentage_con_calidad(entries[ids[0]].get("raw_text", ""), superficie, entries[ids[0]])
                h2, h2_calidad, h2_motivo = obtener_hold_percentage_con_calidad(entries[ids[1]].get("raw_text", ""), superficie, entries[ids[1]])

                if not hold_valido_para_modelo(h1, h1_calidad) or not hold_valido_para_modelo(h2, h2_calidad):
                    st.error("⚠️ Hold% no encontrado de forma fiable. No genero pronóstico para evitar señales falsas.")
                    st.caption(f"{j1_elegido}: {h1_calidad} — {h1_motivo}")
                    st.caption(f"{j2_elegido}: {h2_calidad} — {h2_motivo}")
                    st.stop()

                res = calcular_analisis_multimercado(h1, h2, formato_sets, j1_elegido, j2_elegido, superficie)
                
                st.write("")
                if "PASAR LARGO" in res["Veredicto_Global"]: st.warning(res["Veredicto_Global"], icon="🟡")
                else: st.success(res["Veredicto_Global"], icon="🎯")
                st.write("---")

                st.subheader("📊 Métricas Base")
                m1, m2, m3 = st.columns(3)
                m1.metric(j1_elegido, f"{h1}% Saque")
                m2.metric(j2_elegido, f"{h2}% Saque")
                m3.metric("Suma combinada", f"{res['Suma']:.1f}%")
                
                st.subheader("🎯 Proyecciones por Mercado")
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.metric("Juegos Totales", res["Juegos_Pron"], f"Fiabilidad: {res['Juegos_Fia']:.1f}%" if res["Juegos_Lin"] != "N/A" else "")
                    st.caption(f"Línea recomendada: {res['Juegos_Lin']}")
                with c2:
                    st.metric("¿Habrá Tie-Break?", res["TB_Pron"], f"Fiabilidad: {res['TB_Fia']:.1f}%" if "🟡" not in res["TB_Pron"] else "")
                with c3:
                    st.metric("Hándicap / Ganador", res["Hand_Pron"], f"Fiabilidad: {res['Hand_Fia']:.1f}%" if "⚖️" not in res["Hand_Pron"] else "")
                    st.caption(f"Línea sugerida: {res['Hand_Lin']}")
                with c4:
                    st.metric("Duración en Sets", res["Sets_Pron"], f"Fiabilidad: {res['Sets_Fia']:.1f}%" if "🟡" not in res["Sets_Pron"] else "")
                    st.caption(f"Línea sugerida: {res['Sets_Lin']}")

    with tab2:
        st.subheader("Análisis de Cartelera Completa Inteligente (V6 Tipo de Partido)")
        st.info("V6: primero clasifica el partido: paliza probable, igualado largo, riesgo 3 sets, dominio rápido o sin ventaja. Después decide Over/Under/TB.")
        texto_copiado = st.text_area("Pega tu bloque mixto de Sofascore aquí:", height=200, placeholder="Pega los partidos de Dura, Tierra o Hierba juntos...", key="input_sofascore")
        formato_sets2 = st.radio("Formato base para los partidos del lote:", ["Al mejor de 3 sets (ATP Estándar)", "Al mejor de 3 sets (Circuito Challenger)", "Al mejor de 5 sets (Grand Slam)"], key="r_set2")
            
        if st.button("⚡ INICIAR ESCANEO GLOBAL MIXTO", width="stretch"):
            if not texto_copiado.strip():
                st.warning("⚠️ El cuadro de texto está vacío.")
            else:
                partidos_extraidos = extraer_partidos_sofascore_por_bloques(texto_copiado)
                if not partidos_extraidos:
                    st.error("❌ No se detectaron partidos ni estructuras válidas en el texto.")
                else:
                    st.info(f"📋 **Control de lectura:** Se han detectado **{len(partidos_extraidos)}** partidos con sus respectivas superficies automáticas.")
                    
                    resultados_bulk = []
                    faltantes_detectados = set()
                    
                    for j1_raw, j2_raw, sup_detectada, hora_partido in partidos_extraidos:
                        j1_match = buscar_jugador_flexible(j1_raw, diccionario_jugadores)
                        j2_match = buscar_jugador_flexible(j2_raw, diccionario_jugadores)
                        
                        if not j1_match: faltantes_detectados.add(j1_raw)
                        if not j2_match: faltantes_detectados.add(j2_raw)
                        
                        if j1_match and j2_match:
                            id_j1 = diccionario_jugadores[j1_match]
                            if "raw_text" not in entries[id_j1] and "alias_to" in entries[id_j1]: id_j1 = entries[id_j1]["alias_to"]
                            id_j2 = diccionario_jugadores[j2_match]
                            if "raw_text" not in entries[id_j2] and "alias_to" in entries[id_j2]: id_j2 = entries[id_j2]["alias_to"]

                            h1, h1_calidad, h1_motivo = obtener_hold_percentage_con_calidad(entries[id_j1].get("raw_text", ""), sup_detectada, entries[id_j1])
                            h2, h2_calidad, h2_motivo = obtener_hold_percentage_con_calidad(entries[id_j2].get("raw_text", ""), sup_detectada, entries[id_j2])

                            if not hold_valido_para_modelo(h1, h1_calidad) or not hold_valido_para_modelo(h2, h2_calidad):
                                resultados_bulk.append({
                                    "Hora": hora_partido,
                                    "Partido": f"{j1_match} vs {j2_match}",
                                    "Superficie Auto": sup_detectada,
                                    "Ficha J1": "⚠️ Hold dudoso",
                                    "Ficha J2": "⚠️ Hold dudoso",
                                    "Hold J1": f"{h1:.1f}%" if h1 is not None else "N/A",
                                    "Hold J2": f"{h2:.1f}%" if h2 is not None else "N/A",
                                    "Calidad Hold J1": h1_calidad,
                                    "Calidad Hold J2": h2_calidad,
                                    "Suma Saques": None,
                                    "Diferencia Saque": "N/A",
                                    "Tipo Partido V6": "Datos dudosos",
                                    "Alerta Modelo V6": "No se diagnostica por Hold% no fiable.",
                                    "Pick Principal": "N/A",
                                    "Acción Principal": "PASAR",
                                    "Motivo Principal": f"Hold% no fiable: {j1_match}={h1_calidad}; {j2_match}={h2_calidad}.",
                                    "Pick Alternativo": "N/A",
                                    "Pick Juegos": "N/A",
                                    "Línea Real Juegos": "N/A",
                                    "Acción Juegos": "PASAR",
                                    "Motivo Juegos": "No se analiza por Hold% dudoso.",
                                    "Pick Tie-Break": "N/A",
                                    "Acción TB": "PASAR",
                                    "Motivo TB": "No se analiza por Hold% dudoso.",
                                    "Mercado TB Disponible": "No prioritario",
                                    "Pronóstico Juegos": "⚠️ Hold% dudoso",
                                    "Línea Motor Juegos": "N/A",
                                    "Fiabilidad Juegos": "N/A",
                                    "Mercado Tie-Break": "⚠️ Hold% dudoso",
                                    "Fiabilidad TB": "N/A",
                                    "Hándicap / Ganador": "⚠️ Hold% dudoso",
                                    "Línea Hándicap": "N/A",
                                    "Fiabilidad Hándicap": "N/A",
                                    "Mercado Sets": "⚠️ Hold% dudoso",
                                    "Línea Sets": "N/A",
                                    "Fiabilidad Sets": "N/A",
                                    "_orden": -998.0
                                })
                                continue

                            res = calcular_analisis_multimercado(h1, h2, formato_sets2, j1_raw, j2_raw, sup_detectada)
                            pick_juegos, accion_juegos, motivo_juegos = clasificar_accion_juegos(res, h1, h2, sup_detectada)
                            pick_tb, accion_tb, motivo_tb = clasificar_accion_tiebreak(res, sup_detectada)
                            pick_juegos, accion_juegos, motivo_juegos, pick_tb, accion_tb, motivo_tb = ajustar_acciones_por_calidad_hold(
                                pick_juegos, accion_juegos, motivo_juegos,
                                pick_tb, accion_tb, motivo_tb,
                                h1_calidad, h2_calidad
                            )
                            pick_principal, accion, motivo, pick_alternativo = elegir_mejor_pick(
                                pick_juegos, accion_juegos, motivo_juegos, res.get("Juegos_Fia", 50.0),
                                pick_tb, accion_tb, motivo_tb, res.get("TB_Fia", 50.0)
                            )
                            diferencia_saque = abs(h1 - h2)
                            orden_accion = ranking_accion(accion)
                            orden_final = (orden_accion * 1000) + max(float(res.get("Juegos_Fia", 50.0)), float(res.get("TB_Fia", 50.0))) + float(res.get("_score_orden", 0.0))
                            
                            resultados_bulk.append({
                                "Hora": hora_partido,
                                "Partido": f"{j1_match} vs {j2_match}",
                                "Superficie Auto": sup_detectada,
                                "Ficha J1": "✅",
                                "Ficha J2": "✅",
                                "Hold J1": f"{h1:.1f}%",
                                "Hold J2": f"{h2:.1f}%",
                                "Calidad Hold J1": h1_calidad,
                                "Calidad Hold J2": h2_calidad,
                                "Suma Saques": res["Suma"],
                                "Diferencia Saque": f"{diferencia_saque:.1f}%",
                                "Tipo Partido V6": diagnosticar_tipo_partido(res, h1, h2, sup_detectada)[0],
                                "Alerta Modelo V6": diagnosticar_tipo_partido(res, h1, h2, sup_detectada)[1],
                                "Pick Principal": pick_principal,
                                "Acción Principal": accion,
                                "Motivo Principal": motivo,
                                "Pick Alternativo": pick_alternativo,
                                "Pick Juegos": pick_juegos,
                                "Línea Real Juegos": etiqueta_linea_real_juegos(res["Juegos_Pron"]),
                                "Acción Juegos": accion_juegos,
                                "Motivo Juegos": motivo_juegos,
                                "Pick Tie-Break": pick_tb,
                                "Acción TB": accion_tb,
                                "Motivo TB": motivo_tb,
                                "Mercado TB Disponible": "Revisar casa" if "JUGAR" in accion_tb or "OBSERVAR" in accion_tb else "No prioritario",
                                "Pronóstico Juegos": res["Juegos_Pron"],
                                "Línea Motor Juegos": res["Juegos_Lin"],
                                "Fiabilidad Juegos": f"{res['Juegos_Fia']:.1f}%" if res["Juegos_Lin"] != "N/A" else "50.0%",
                                "Mercado Tie-Break": res["TB_Pron"],
                                "Fiabilidad TB": f"{res['TB_Fia']:.1f}%" if "🟡" not in res["TB_Pron"] else "N/A",
                                "Hándicap / Ganador": res["Hand_Pron"],
                                "Línea Hándicap": res["Hand_Lin"],
                                "Fiabilidad Hándicap": f"{res['Hand_Fia']:.1f}%" if "⚖️" not in res["Hand_Pron"] else "N/A",
                                "Mercado Sets": res["Sets_Pron"],
                                "Línea Sets": res["Sets_Lin"],
                                "Fiabilidad Sets": f"{res['Sets_Fia']:.1f}%" if "🟡" not in res["Sets_Pron"] else "N/A",
                                "_orden": orden_final
                            })
                        else:
                            p_name1 = j1_match if j1_match else j1_raw
                            p_name2 = j2_match if j2_match else j2_raw
                            resultados_bulk.append({
                                "Hora": hora_partido,
                                "Partido": f"{p_name1} vs {p_name2}", 
                                "Superficie Auto": sup_detectada,
                                "Ficha J1": "✅" if j1_match else "❌",
                                "Ficha J2": "✅" if j2_match else "❌",
                                "Hold J1": "N/A",
                                "Hold J2": "N/A",
                                "Suma Saques": None,
                                "Diferencia Saque": "N/A",
                                "Pick Principal": "N/A",
                                "Acción Principal": "PASAR",
                                "Motivo Principal": "Faltan datos TA de uno o ambos jugadores.",
                                "Pick Alternativo": "N/A",
                                "Pick Juegos": "N/A",
                                "Línea Real Juegos": "N/A",
                                "Acción Juegos": "PASAR",
                                "Motivo Juegos": "Faltan datos TA de uno o ambos jugadores.",
                                "Pick Tie-Break": "N/A",
                                "Acción TB": "PASAR",
                                "Motivo TB": "Faltan datos TA de uno o ambos jugadores.",
                                "Mercado TB Disponible": "No prioritario",
                                "Pronóstico Juegos": "⚠️ Faltan datos", "Línea Motor Juegos": "N/A", "Fiabilidad Juegos": "0%",
                                "Mercado Tie-Break": "⚠️ Faltan datos", "Fiabilidad TB": "N/A",
                                "Hándicap / Ganador": "⚠️ Faltan datos", "Línea Hándicap": "N/A", "Fiabilidad Hándicap": "N/A",
                                "Mercado Sets": "⚠️ Faltan datos", "Línea Sets": "N/A", "Fiabilidad Sets": "N/A",
                                "_orden": -999.0
                            })
                    
                    st.session_state.lista_faltantes = list(faltantes_detectados)
                    if resultados_bulk:
                        df = pd.DataFrame(resultados_bulk).sort_values(by="_orden", ascending=False)
                        st.session_state.df_multi = df.copy()

        if "df_multi" in st.session_state and not st.session_state.df_multi.empty:
            df_ui = st.session_state.df_multi.copy()
            df_ui["Suma Saques"] = df_ui["Suma Saques"].apply(lambda x: f"{x:.1f}%" if pd.notnull(x) else "N/A")
            df_ui_limpio = df_ui.drop(columns=["_orden"])
            
            st.subheader("🔥 Panel Completo Inteligente Multi-Mercado y Multi-Superficie")
            st.dataframe(df_ui_limpio, width="stretch")
            
            try:
                import io
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_ui_limpio.to_excel(writer, index=False, sheet_name='MultiMercado_Tenis')
                st.download_button(
                    label="📥 Descargar Informe Completo Automatizado en Excel (.xlsx)",
                    data=output.getvalue(),
                    file_name="informe_multimercado_mixto.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width="stretch"
                )
            except Exception as e:
                st.error(f"Falta librería excel: {e}")

        if st.session_state.lista_faltantes:
            st.write("---")
            st.warning(f"⚠️ Jugadores faltantes detectados: {len(st.session_state.lista_faltantes)}")
            with st.form("formulario_agregar_jugadores"):
                jugador_a_añadir = st.selectbox("Selecciona jugador:", st.session_state.lista_faltantes)
                nombre_oficial = st.text_input("Nombre Oficial:", value=jugador_a_añadir.replace(".", "").strip())
                raw_text_pasted = st.text_area("Perfil Tennis Abstract:", height=120)
                if st.form_submit_button("💾 Guardar y Actualizar"):
                    if raw_text_pasted.strip() and nombre_oficial.strip():
                        nuevo_id = nombre_oficial.lower().replace(" ", "-")
                        json_data["entries"][nuevo_id] = {"player": nombre_oficial, "raw_text": raw_text_pasted.strip()}
                        if jugador_a_añadir != nombre_oficial:
                            alias_id = jugador_a_añadir.lower().replace(" ", "-").replace(".", "")
                            if alias_id != nuevo_id:
                                json_data["entries"][alias_id] = {"player": jugador_a_añadir, "alias_to": nuevo_id}
                        if guardar_datos_json(json_data, RUTA_JSON):
                            st.session_state.lista_faltantes.remove(jugador_a_añadir)
                            st.rerun()

    with tab3:
        st.subheader("✅ Validador de Resultados por Mercado")
        st.caption("Pega resultados ya finalizados. La app recalcula los picks con el motor actual y mide aciertos/fallos por mercado.")
        st.info("📌 v5.8: Over/Under seguro + filtro 3 sets/Over18. Si el motor proyecta Over 21.5/22.5, la línea real es Over 18.5. Si proyecta Under 21.5/22.5, la línea real es Under 24.5/25.5. Tie-Break Sí sigue bloqueado y Tie-Break No queda como mercado premium separado. Los Under en hierba o con riesgo 3 sets quedan bloqueados y se marca alerta para revisar Over 18.5.")

        with st.expander("📌 Formato recomendado para máxima precisión"):
            st.markdown(
                """
                Puedes pegar el bloque bruto de SofaScore, pero el formato más limpio es una línea por partido:

                `Jugador 1 vs Jugador 2 | 6-4 7-6 | Hierba`

                También sirve:

                `N. Borges vs T. Atmane | 6-4 6-4 | Dura`
                """
            )

        col_val1, col_val2 = st.columns(2)
        with col_val1:
            formato_sets_val = st.radio(
                "Formato base para validar:",
                ["Al mejor de 3 sets (ATP Estándar)", "Al mejor de 3 sets (Circuito Challenger)", "Al mejor de 5 sets (Grand Slam)"],
                key="r_set_val"
            )
        with col_val2:
            superficie_defecto_val = st.radio(
                "Superficie por defecto si el texto no la trae:",
                ["Dura 🔵", "Tierra Batida 🟤", "Hierba 🟢"],
                horizontal=True,
                key="r_sup_val"
            )

        mercados_a_validar = st.multiselect(
            "Mercados a validar:",
            ["Juegos Totales", "Tie-Break", "Hándicap / Ganador", "Duración en Sets"],
            default=["Juegos Totales", "Tie-Break"],
            help="Juegos valida tu apuesta real. Tie-Break valida Sí/No por separado para comprobar si ese mercado mantiene el porcentaje alto."
        )

        texto_resultados = st.text_area(
            "Pega aquí la lista de partidos con resultados:",
            height=260,
            placeholder="Ejemplo:\nN. Borges vs T. Atmane | 6-4 6-4 | Dura\nB. Bonzi vs M. Rottgering | 6-4 6-4 | Hierba",
            key="input_resultados_val"
        )

        if st.button("📊 ANALIZAR ACIERTOS / FALLOS", width="stretch"):
            resultados_detectados = extraer_resultados_tenis(texto_resultados, superficie_defecto_val)
            if not resultados_detectados:
                st.error("❌ No he podido detectar resultados válidos. Prueba con el formato: Jugador 1 vs Jugador 2 | 6-4 7-6 | Superficie")
            else:
                filas_detalle = []
                filas_detectadas = []
                faltantes_val = set()

                for r in resultados_detectados:
                    j1_raw = r["Jugador 1"]
                    j2_raw = r["Jugador 2"]
                    sets = depurar_sets_duplicados(r["Sets"], formato_sets_val)
                    sup = r.get("Superficie", superficie_defecto_val)
                    marcador_txt = " ".join([f"{a}-{b}" for a, b in sets])
                    juegos_totales = total_juegos_sets(sets)
                    num_sets = len(sets)
                    tb_real = hay_tiebreak(sets)
                    sg1, sg2 = sets_ganados(sets)

                    j1_match = buscar_jugador_flexible(j1_raw, diccionario_jugadores)
                    j2_match = buscar_jugador_flexible(j2_raw, diccionario_jugadores)

                    filas_detectadas.append({
                        "Partido detectado": f"{j1_raw} vs {j2_raw}",
                        "Match TA": f"{j1_match or 'NO ENCONTRADO'} vs {j2_match or 'NO ENCONTRADO'}",
                        "Marcador": marcador_txt,
                        "Juegos Totales": juegos_totales,
                        "Sets": f"{sg1}-{sg2}",
                        "Tie-Break": "Sí" if tb_real else "No",
                        "Superficie": sup,
                        "Fuente": r.get("Fuente", "N/A")
                    })

                    if not j1_match:
                        faltantes_val.add(j1_raw)
                    if not j2_match:
                        faltantes_val.add(j2_raw)
                    if not j1_match or not j2_match:
                        continue

                    id_j1 = diccionario_jugadores[j1_match]
                    if "raw_text" not in entries[id_j1] and "alias_to" in entries[id_j1]:
                        id_j1 = entries[id_j1]["alias_to"]
                    id_j2 = diccionario_jugadores[j2_match]
                    if "raw_text" not in entries[id_j2] and "alias_to" in entries[id_j2]:
                        id_j2 = entries[id_j2]["alias_to"]

                    try:
                        h1, h1_calidad, h1_motivo = obtener_hold_percentage_con_calidad(entries[id_j1].get("raw_text", ""), sup, entries[id_j1])
                        h2, h2_calidad, h2_motivo = obtener_hold_percentage_con_calidad(entries[id_j2].get("raw_text", ""), sup, entries[id_j2])

                        if not hold_valido_para_modelo(h1, h1_calidad) or not hold_valido_para_modelo(h2, h2_calidad):
                            filas_detalle.append({
                                "Partido": f"{j1_match} vs {j2_match}",
                                "Mercado": "Datos dudosos",
                                "Pronóstico": "No validado",
                                "Línea Motor": "N/A",
                                "Línea Validada": "N/A",
                                "Pick Real": "N/A",
                                "Acción Motor": "PASAR",
                                "Motivo Motor": f"Hold% no fiable: {j1_match}={h1_calidad}; {j2_match}={h2_calidad}.",
                                "Pick Alternativo": "N/A",
                                "Pick Juegos": "N/A",
                                "Acción Juegos": "PASAR",
                                "Pick Tie-Break": "N/A",
                                "Acción TB": "PASAR",
                                "Resultado": "No validado",
                                "Marcador": marcador_txt,
                                "Juegos Reales": juegos_totales,
                                "Sets Reales": num_sets,
                                "Tie-Break Real": "Sí" if tb_real else "No",
                                "Superficie": sup,
                                "Hold J1": f"{h1:.1f}%" if h1 is not None else "N/A",
                                "Hold J2": f"{h2:.1f}%" if h2 is not None else "N/A",
                                "Calidad Hold J1": h1_calidad,
                                "Calidad Hold J2": h2_calidad,
                                "Suma Saques": "N/A",
                                "Fiabilidad": "N/A"
                            })
                            continue

                        res = calcular_analisis_multimercado(h1, h2, formato_sets_val, j1_match, j2_match, sup)
                        pick_juegos_val, accion_juegos_val, motivo_juegos_val = clasificar_accion_juegos(res, h1, h2, sup)
                        pick_tb_val, accion_tb_val, motivo_tb_val = clasificar_accion_tiebreak(res, sup)
                        pick_juegos_val, accion_juegos_val, motivo_juegos_val, pick_tb_val, accion_tb_val, motivo_tb_val = ajustar_acciones_por_calidad_hold(
                            pick_juegos_val, accion_juegos_val, motivo_juegos_val,
                            pick_tb_val, accion_tb_val, motivo_tb_val,
                            h1_calidad, h2_calidad
                        )
                        pick_principal_val, accion_val, motivo_val, pick_alternativo_val = elegir_mejor_pick(
                            pick_juegos_val, accion_juegos_val, motivo_juegos_val, res.get("Juegos_Fia", 50.0),
                            pick_tb_val, accion_tb_val, motivo_tb_val, res.get("TB_Fia", 50.0)
                        )
                        lineas_juegos_val = superar_lineas_juegos(juegos_totales)
                    except Exception as e:
                        filas_detalle.append({
                            "Partido": f"{j1_match} vs {j2_match}",
                            "Mercado": "Error",
                            "Pronóstico": "No calculado",
                            "Línea Motor": "N/A",
                            "Línea Validada": "N/A",
                            "Resultado": f"Error: {e}",
                            "Marcador": marcador_txt,
                            "Juegos Reales": juegos_totales,
                            "Superficie": sup,
                            "Fiabilidad": "N/A"
                        })
                        continue

                    evaluaciones = []
                    if "Juegos Totales" in mercados_a_validar:
                        hit, mercado, linea = evaluar_over_under(res["Juegos_Pron"], res["Juegos_Lin"], juegos_totales)
                        # v5.8: solo validamos como pick de juegos si la acción no es PASAR.
                        # Así los Under bloqueados por riesgo 3 sets/hierba no ensucian la estadística.
                        if mercado and str(accion_juegos_val).upper() != "PASAR":
                            evaluaciones.append((mercado, res["Juegos_Pron"], linea, hit, res["Juegos_Fia"], res["Juegos_Lin"]))

                    if "Tie-Break" in mercados_a_validar:
                        hit, mercado, linea = evaluar_tiebreak(res["TB_Pron"], tb_real)
                        if mercado and "PASAR" not in str(accion_tb_val).upper():
                            evaluaciones.append((mercado, res["TB_Pron"], linea, hit, res["TB_Fia"], "N/A"))

                    if "Hándicap / Ganador" in mercados_a_validar:
                        hit, mercado, linea = evaluar_handicap(res["Hand_Pron"], res["Hand_Lin"], sets, j1_match, j2_match)
                        if mercado:
                            evaluaciones.append((mercado, res["Hand_Pron"], linea, hit, res["Hand_Fia"], res["Hand_Lin"]))

                    if "Duración en Sets" in mercados_a_validar:
                        hit, mercado, linea = evaluar_sets(res["Sets_Pron"], res["Sets_Lin"], num_sets)
                        if mercado:
                            evaluaciones.append((mercado, res["Sets_Pron"], linea, hit, res["Sets_Fia"], res["Sets_Lin"]))

                    if not evaluaciones:
                        filas_detalle.append({
                            "Partido": f"{j1_match} vs {j2_match}",
                            "Mercado": "Sin pick validable",
                            "Pronóstico": res["Juegos_Pron"],
                            "Línea Motor": res["Juegos_Lin"],
                            "Línea Validada": "N/A",
                            "Pick Real": pick_principal_val,
                            "Acción Motor": accion_val,
                            "Motivo Motor": motivo_val,
                            "Pick Alternativo": pick_alternativo_val,
                            "Pick Juegos": pick_juegos_val,
                            "Acción Juegos": accion_juegos_val,
                            "Pick Tie-Break": pick_tb_val,
                            "Acción TB": accion_tb_val,
                            "Resultado": "🟡 Sin apuesta",
                            "Marcador": marcador_txt,
                            "Juegos Reales": juegos_totales,
                            "Sets Reales": num_sets,
                            "Tie-Break Real": "Sí" if tb_real else "No",
                            "Superficie": sup,
                            "Hold J1": f"{h1:.1f}%",
                            "Hold J2": f"{h2:.1f}%",
                            "Suma Saques": f"{res['Suma']:.1f}%",
                            "Fiabilidad": "N/A",
                            "Alerta 3 sets / Over18": alerta_3sets_over18(juegos_totales, num_sets, tb_real, sup),
                            **lineas_juegos_val
                        })
                    else:
                        for mercado, pron, linea, hit, fia, linea_motor in evaluaciones:
                            filas_detalle.append({
                                "Partido": f"{j1_match} vs {j2_match}",
                                "Mercado": mercado,
                                "Pronóstico": pron,
                                "Línea Motor": linea_motor,
                                "Línea Validada": linea,
                                "Pick Real": etiqueta_linea_real_juegos(pron) if mercado in ["Over Juegos", "Under Juegos"] else (pick_tb_val if mercado in ["Tie-Break Sí", "Tie-Break No"] else linea),
                                "Acción Motor": accion_juegos_val if mercado in ["Over Juegos", "Under Juegos"] else (accion_tb_val if mercado in ["Tie-Break Sí", "Tie-Break No"] else "N/A"),
                                "Motivo Motor": motivo_juegos_val if mercado in ["Over Juegos", "Under Juegos"] else (motivo_tb_val if mercado in ["Tie-Break Sí", "Tie-Break No"] else "N/A"),
                                "Pick Alternativo": pick_alternativo_val,
                                "Pick Juegos": pick_juegos_val,
                                "Acción Juegos": accion_juegos_val,
                                "Pick Tie-Break": pick_tb_val,
                                "Acción TB": accion_tb_val,
                                "Resultado": "✅ Acierto" if hit else "❌ Fallo",
                                "Marcador": marcador_txt,
                                "Juegos Reales": juegos_totales,
                                "Sets Reales": num_sets,
                                "Tie-Break Real": "Sí" if tb_real else "No",
                                "Superficie": sup,
                                "Hold J1": f"{h1:.1f}%",
                                "Hold J2": f"{h2:.1f}%",
                                "Calidad Hold J1": h1_calidad,
                                "Calidad Hold J2": h2_calidad,
                                "Suma Saques": f"{res['Suma']:.1f}%",
                                "Fiabilidad": f"{fia:.1f}%",
                                "Alerta 3 sets / Over18": alerta_3sets_over18(juegos_totales, num_sets, tb_real, sup),
                                **lineas_juegos_val
                            })

                df_detectados = pd.DataFrame(filas_detectadas)
                df_detalle = pd.DataFrame(filas_detalle)
                df_resumen = construir_resumen_validacion(df_detalle)
                df_resumen_superficie = construir_resumen_superficie(df_detalle)
                df_resumen_lineas = construir_resumen_lineas_juegos(df_detalle)
                df_over_largo = construir_over_largo(df_detalle)
                df_resumen_tiebreak = construir_resumen_tiebreak(df_detalle, df_detectados)
                df_control_dia = construir_control_dia(df_detectados, df_detalle)

                st.session_state.df_val_detectados = df_detectados
                st.session_state.df_val_detalle = df_detalle
                st.session_state.df_val_resumen = df_resumen
                st.session_state.df_val_resumen_superficie = df_resumen_superficie
                st.session_state.df_val_resumen_lineas = df_resumen_lineas
                st.session_state.df_val_over_largo = df_over_largo
                st.session_state.df_val_resumen_tiebreak = df_resumen_tiebreak
                st.session_state.df_val_control_dia = df_control_dia
                st.session_state.faltantes_val = sorted(list(faltantes_val))

        if "df_val_resumen" in st.session_state:
            st.write("---")
            st.subheader("📌 Resumen por mercado")
            if st.session_state.df_val_resumen.empty:
                st.warning("No hay picks validables con los mercados seleccionados.")
            else:
                total_picks = int(st.session_state.df_val_resumen["Picks"].sum())
                total_aciertos = int(st.session_state.df_val_resumen["Aciertos"].sum())
                total_fallos = int(st.session_state.df_val_resumen["Fallos"].sum())
                pct_global = round((total_aciertos / total_picks * 100), 1) if total_picks else 0.0
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Picks validados", total_picks)
                k2.metric("Aciertos", total_aciertos)
                k3.metric("Fallos", total_fallos)
                k4.metric("% Global", f"{pct_global}%")
                st.dataframe(st.session_state.df_val_resumen, width="stretch")

                if not st.session_state.get("df_val_control_dia", pd.DataFrame()).empty:
                    st.subheader("🧭 Control del día")
                    st.caption("Compara el rendimiento de las señales contra la base real de la jornada. Muy útil para Tie-Break No.")
                    st.dataframe(st.session_state.df_val_control_dia, width="stretch")

                if not st.session_state.get("df_val_resumen_superficie", pd.DataFrame()).empty:
                    st.subheader("🌍 Resumen por superficie")
                    st.dataframe(st.session_state.df_val_resumen_superficie, width="stretch")

                if not st.session_state.get("df_val_resumen_tiebreak", pd.DataFrame()).empty:
                    st.subheader("🎾 Resumen específico Tie-Break")
                    st.caption("Separa Tie-Break Sí / No por superficie para saber dónde merece la pena priorizarlo si la casa ofrece el mercado.")
                    st.dataframe(st.session_state.df_val_resumen_tiebreak, width="stretch")

                if not st.session_state.get("df_val_resumen_lineas", pd.DataFrame()).empty:
                    st.subheader("📏 Estudio de líneas alternativas")
                    st.caption("Sirve para saber si el Over 18.5 va sobrado y si compensa mirar 20.5 / 21.5 / 22.5, y qué línea Under segura funciona mejor: 24.5 / 25.5 / 26.5.")
                    st.dataframe(st.session_state.df_val_resumen_lineas, width="stretch")

                if not st.session_state.get("df_val_over_largo", pd.DataFrame()).empty:
                    st.subheader("🚀 Hoja Over Largo")
                    st.caption("Solo partidos donde el motor dio señal OVER. Aquí se ve si llegaron a 21+, 22+, 23+ o 24+ juegos.")
                    st.dataframe(st.session_state.df_val_over_largo, width="stretch")

            st.subheader("📋 Detalle pick a pick")
            st.dataframe(st.session_state.df_val_detalle, width="stretch")

            with st.expander("🔎 Resultados detectados antes de validar"):
                st.dataframe(st.session_state.df_val_detectados, width="stretch")

            if st.session_state.get("faltantes_val"):
                st.warning("⚠️ Jugadores sin ficha TA detectados: " + ", ".join(st.session_state.faltantes_val))

            try:
                import io
                output_val = io.BytesIO()
                with pd.ExcelWriter(output_val, engine='openpyxl') as writer:
                    st.session_state.df_val_resumen.to_excel(writer, index=False, sheet_name='Resumen_Mercados')
                    st.session_state.get('df_val_control_dia', pd.DataFrame()).to_excel(writer, index=False, sheet_name='Control_Dia')
                    st.session_state.get('df_val_resumen_superficie', pd.DataFrame()).to_excel(writer, index=False, sheet_name='Resumen_Superficie')
                    st.session_state.get('df_val_resumen_tiebreak', pd.DataFrame()).to_excel(writer, index=False, sheet_name='Resumen_TieBreak')
                    st.session_state.get('df_val_resumen_lineas', pd.DataFrame()).to_excel(writer, index=False, sheet_name='Estudio_Lineas')
                    st.session_state.get('df_val_over_largo', pd.DataFrame()).to_excel(writer, index=False, sheet_name='Over_Largo')
                    st.session_state.df_val_detalle.to_excel(writer, index=False, sheet_name='Detalle_Picks')
                    st.session_state.df_val_detectados.to_excel(writer, index=False, sheet_name='Resultados_Detectados')
                st.download_button(
                    label="📥 Descargar Validación en Excel (.xlsx)",
                    data=output_val.getvalue(),
                    file_name="validacion_resultados_tennis.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width="stretch"
                )
            except Exception as e:
                st.error(f"No se pudo crear el Excel de validación: {e}")
