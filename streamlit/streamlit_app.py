
import itertools
import math
import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import requests
import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup

st.set_page_config(page_title="40K Team Pairings V13", page_icon="⚔️", layout="wide")

st.title("⚔️ 40K Team Pairings — V13 Data-Driven")
st.caption("6 vs 6 · Win rates empíricos de facciones y disposiciones · 720 combinaciones")

DEFAULT_MY = [
    ("Álvaro", "Aeldari", "Reconnaissance (R)"),
    ("Jugador 2", "Orks", "Purge the Foe (PF)"),
    ("Jugador 3", "Tau Empire", "Reconnaissance (R)"),
    ("Jugador 4", "Adeptus Custodes", "Disruption (D)"),
    ("Jugador 5", "Necrons", "Priority Assets (PA)"),
    ("Jugador 6", "Black Templars", "Take and Hold (TH)"),
]
DEFAULT_OPP = [
    ("Rival 1", "Space Marines", "Purge the Foe (PF)"),
    ("Rival 2", "Orks", "Reconnaissance (R)"),
    ("Rival 3", "Tau Empire", "Disruption (D)"),
    ("Rival 4", "Aeldari", "Priority Assets (PA)"),
    ("Rival 5", "Chaos Space Marines", "Take and Hold (TH)"),
    ("Rival 6", "Imperial Knights", "Reconnaissance (R)"),
]


# ============================================================
# GUARDAR / CARGAR EQUIPO
# ============================================================

with st.sidebar:
    st.header("💾 Mi equipo")
    st.caption("Guarda tus 6 jugadores para reutilizarlos en otro torneo o sesión.")
    uploaded_team = st.file_uploader("📂 Cargar equipo guardado", type=["json"], key="team_upload")
    if uploaded_team is not None and st.session_state.get("loaded_upload_name") != uploaded_team.name:
        try:
            payload = json.load(uploaded_team)
            players = payload.get("players", [])
            if len(players) != 6:
                st.error("El archivo no contiene exactamente 6 jugadores.")
            else:
                for i, pl in enumerate(players):
                    st.session_state[f"my_name_{i}"] = pl.get("name", f"Jugador {i+1}")
                    st.session_state[f"my_army_{i}"] = pl.get("army", DEFAULT_MY[i][1])
                    st.session_state[f"my_disp_{i}"] = pl.get("disposition", DEFAULT_MY[i][2])
                st.session_state["team_name"] = payload.get("team_name", "Mi equipo")
                st.session_state["loaded_upload_name"] = uploaded_team.name
                st.rerun()
        except Exception:
            st.error("No he podido leer ese archivo de equipo.")
    team_name = st.text_input("Nombre del equipo", value=st.session_state.get("team_name", "Mi equipo"), key="team_name")

    team_payload = {
        "team_name": team_name,
        "players": [
            {
                "name": st.session_state.get(f"my_name_{i}", DEFAULT_MY[i][0]),
                "army": st.session_state.get(f"my_army_{i}", DEFAULT_MY[i][1]),
                "disposition": st.session_state.get(f"my_disp_{i}", DEFAULT_MY[i][2]),
            } for i in range(6)
        ]
    }
    st.download_button(
        "💾 Guardar mi equipo",
        data=json.dumps(team_payload, ensure_ascii=False, indent=2),
        file_name=f"{team_name.strip() or 'mi_equipo'}.json",
        mime="application/json",
        use_container_width=True,
        help="Descarga un archivo con los 6 jugadores, armies y disposiciones para poder cargarlo otro día."
    )


# ============================================================
# CONFIGURACIÓN FIJA
# ============================================================

DISPOSITIONS = [
    "Take and Hold (TH)",
    "Purge the Foe (PF)",
    "Reconnaissance (R)",
    "Priority Assets (PA)",
    "Disruption (D)",
]


ARMY_GROUPS = {
    "CHAOS": [
        "Chaos Daemons", "Chaos Knights", "Chaos Space Marines",
        "Death Guard", "Emperor's Children", "Thousand Sons", "World Eaters",
    ],
    "IMPERIUM": [
        "Adepta Sororitas", "Adeptus Custodes", "Adeptus Mechanicus",
        "Adeptus Titanicus", "Astra Militarum", "Grey Knights",
        "Imperial Agents", "Imperial Knights",
    ],
    "SPACE MARINES": [
        "Black Templars", "Blood Angels", "Dark Angels", "Deathwatch",
        "Imperial Fists", "Iron Hands", "Raven Guard", "Salamanders",
        "Space Marines", "Space Wolves", "Ultramarines", "White Scars",
    ],
    "XENOS": [
        "Aeldari", "Drukhari", "Genestealer Cults", "Leagues of Votann",
        "Necrons", "Orks", "Tau Empire", "Tyranids",
    ],
}
ALL_ARMIES = [a for group in ARMY_GROUPS.values() for a in group]

# ============================================================
# FUENTE AUTOMÁTICA DE ESTADÍSTICAS: MINIHEADQUARTERS
# ============================================================

MHQ_STATS_URL = "https://miniheadquarters.com/meta/solo/warhammer-40000/stats/"
MHQ_METHOD_URL = "https://miniheadquarters.com/meta/warhammer-40000/methodology/"
DATA_CACHE_SECONDS = 6 * 60 * 60
DISPOSITION_EFFECT_WEIGHT = 0.75
FACTION_PRIOR_GAMES = 12
DISPOSITION_PRIOR_GAMES = 10

# Los nombres visibles en la app se conservan. Aquí se relacionan con los nombres
# usados por MiniHeadQuarters; se permite recurrir a una categoría genérica cuando
# no hay suficientes datos recientes de un capítulo concreto.
ARMY_SOURCE_CANDIDATES = {
    "Chaos Daemons": ["Chaos - Daemons"],
    "Chaos Knights": ["Chaos - Chaos Knights"],
    "Chaos Space Marines": ["Chaos - Chaos Space Marines"],
    "Death Guard": ["Chaos - Death Guard"],
    "Emperor's Children": ["Chaos - Emperor's Children"],
    "Thousand Sons": ["Chaos - Thousand Sons"],
    "World Eaters": ["Chaos - World Eaters"],
    "Adepta Sororitas": ["Imperium - Adepta Sororitas"],
    "Adeptus Custodes": ["Imperium - Adeptus Custodes"],
    "Adeptus Mechanicus": ["Imperium - Adeptus Mechanicus"],
    # No existe un registro competitivo 40K verificable para Adeptus Titanicus.
    "Adeptus Titanicus": [],
    "Astra Militarum": ["Imperium - Astra Militarum"],
    "Grey Knights": ["Imperium - Grey Knights"],
    # Imperial Agents no se sustituye por Inquisition: no son equivalentes exactos.
    "Imperial Agents": [],
    "Imperial Knights": ["Imperium - Imperial Knights"],
    "Black Templars": ["Imperium - Adeptus Astartes - Black Templars", "Imperium - Adeptus Astartes"],
    "Blood Angels": ["Imperium - Adeptus Astartes - Blood Angels", "Imperium - Adeptus Astartes"],
    "Dark Angels": ["Imperium - Adeptus Astartes - Dark Angels", "Imperium - Adeptus Astartes"],
    "Deathwatch": ["Imperium - Adeptus Astartes - Deathwatch", "Imperium - Adeptus Astartes"],
    "Imperial Fists": ["Imperium - Adeptus Astartes - Imperial Fists", "Imperium - Adeptus Astartes"],
    "Iron Hands": ["Imperium - Adeptus Astartes - Iron Hands", "Imperium - Adeptus Astartes"],
    "Raven Guard": ["Imperium - Adeptus Astartes - Raven Guard", "Imperium - Adeptus Astartes"],
    "Salamanders": ["Imperium - Adeptus Astartes - Salamanders", "Imperium - Adeptus Astartes"],
    "Space Marines": ["Imperium - Adeptus Astartes"],
    "Space Wolves": ["Imperium - Adeptus Astartes - Space Wolves", "Imperium - Adeptus Astartes"],
    "Ultramarines": ["Imperium - Adeptus Astartes - Ultramarines", "Imperium - Adeptus Astartes"],
    "White Scars": ["Imperium - Adeptus Astartes - White Scars", "Imperium - Adeptus Astartes"],
    "Aeldari": ["Aeldari - Craftworlds", "Aeldari"],
    "Drukhari": ["Aeldari - Drukhari"],
    "Genestealer Cults": ["Tyranids - Genestealers Cult", "Tyranids - Genestealer Cults", "Genestealer Cults"],
    "Leagues of Votann": ["Leagues of Votann"],
    "Necrons": ["Necrons"],
    "Orks": ["Orks"],
    "Tau Empire": ["T'au Empire", "T’au Empire", "Tau Empire"],
    "Tyranids": ["Tyranids"],
}

SOURCE_DISPOSITION_NAMES = {
    "take and hold": "Take and Hold (TH)",
    "purge the foe": "Purge the Foe (PF)",
    "reconnaissance": "Reconnaissance (R)",
    "priority assets": "Priority Assets (PA)",
    "disruption": "Disruption (D)",
}

class DataSourceError(RuntimeError):
    """Error de descarga o interpretación de la fuente estadística."""


def normalize_label(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def parse_percentage(value):
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", str(value))
    return (float(match.group(1).replace(",", ".")) / 100.0) if match else None


def parse_game_count(value):
    text = str(value or "")
    match = re.search(r"\b(\d+)\s*games?\b", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"\b(\d+)\b", text)
    return int(match.group(1)) if match else 0


def parse_confidence_interval(value):
    """Extract 95% CI from either '(50.6 – 66.2)' or '43.9% – 100.0%'."""
    text = str(value or "").replace(",", ".")
    match = re.search(r"\(\s*(\d+(?:\.\d+)?)\s*[–—-]\s*(\d+(?:\.\d+)?)\s*\)", text)
    if match:
        return (float(match.group(1)) / 100.0, float(match.group(2)) / 100.0)
    values = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
    if len(values) >= 2:
        return (float(values[0]) / 100.0, float(values[1]) / 100.0)
    return (None, None)


def format_confidence_interval(record):
    if not record or record.get("ci_low") is None or record.get("ci_high") is None:
        return "IC 95% no disponible"
    return f"IC 95% {record['ci_low']*100:.1f}–{record['ci_high']*100:.1f}%"


def _table_header(table):
    for row in table.find_all("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        vals = [normalize_label(c.get_text(" ", strip=True)) for c in cells]
        if vals and any(v in ("faction", "opponent", "force disposition") for v in vals):
            return row, cells, vals
    return None, [], []


def _find_table(soup, required_headers):
    for table in soup.find_all("table"):
        row, cells, headers = _table_header(table)
        if not row:
            continue
        if all(any(req == h or req in h for h in headers) for req in required_headers):
            return table, row, cells, headers
    return None, None, [], []


def _new_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; 40KTeamPairings/13.0; tournament-statistics)",
        "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
    })
    return session


def _selected_option(select):
    selected = select.find("option", selected=True)
    if selected is None:
        selected = select.find("option")
    if selected is None:
        return None
    return selected.get("value", selected.get_text(" ", strip=True))


def _option_value_for_weeks(select, weeks):
    for option in select.find_all("option"):
        value = str(option.get("value", "")).strip()
        label = option.get_text(" ", strip=True)
        if value == str(weeks):
            return value
        if re.fullmatch(rf"\s*{weeks}\s*(?:weeks?|wks?)?\s*", label, re.IGNORECASE):
            return value or label
    return None


def _fetch_with_window(session, url, weeks):
    """GET a page and submit its own time-window selector, preserving the other controls."""
    try:
        response = session.get(url, timeout=18)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise DataSourceError(f"No se pudo abrir MiniHeadQuarters: {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")
    candidates = []
    for select in soup.find_all("select"):
        target_value = _option_value_for_weeks(select, weeks)
        if target_value is not None:
            options = [str(o.get("value", o.get_text(" ", strip=True))).strip() for o in select.find_all("option")]
            numeric_options = {re.sub(r"\D", "", x) for x in options}
            selector_hint = normalize_label((select.get("name") or "") + " " + (select.get("id") or ""))
            looks_like_window = any(word in selector_hint for word in ("week", "time", "period", "window"))
            if {"1", "2", "4", "8", "12", "26"}.issubset(numeric_options) or looks_like_window or target_value == str(weeks):
                target_option = next((o for o in select.find_all("option") if str(o.get("value", "")).strip() == target_value or o.get_text(" ", strip=True) == target_value), None)
                target_label = target_option.get_text(" ", strip=True) if target_option else str(target_value)
                candidates.append((select, target_value, target_label))

    if not candidates:
        raise DataSourceError(
            f"No he encontrado en MiniHeadQuarters el selector de ventana de {weeks} semanas. "
            "La estructura de la web puede haber cambiado; no voy a usar silenciosamente un periodo distinto."
        )

    select, target_value, target_label = candidates[0]
    form = select.find_parent("form")
    action = urljoin(response.url, form.get("action") or response.url) if form else response.url
    method = (form.get("method", "get").lower() if form else "get")
    fields = {}
    if form:
        for control in form.find_all(["input", "select", "textarea"]):
            name = control.get("name")
            if not name:
                continue
            if control.name == "input":
                typ = (control.get("type") or "text").lower()
                if typ in ("submit", "button", "image", "file", "reset"):
                    continue
                if typ in ("checkbox", "radio") and not control.has_attr("checked"):
                    continue
                fields[name] = control.get("value", "on" if typ in ("checkbox", "radio") else "")
            elif control.name == "select":
                fields[name] = _selected_option(control) or ""
            else:
                fields[name] = control.get_text()
        select_name = select.get("name")
        if not select_name:
            # Common convention: selector's id usually describes its query parameter.
            select_name = select.get("id") or "weeks"
        fields[select_name] = target_value
    else:
        select_name = select.get("name") or select.get("id") or "weeks"
        fields[select_name] = target_value

    try:
        if method == "post":
            selected_response = session.post(action, data=fields, timeout=18)
        else:
            selected_response = session.get(action, params=fields, timeout=18)
        selected_response.raise_for_status()
    except requests.RequestException as exc:
        raise DataSourceError(f"No se pudo seleccionar la ventana de {weeks} semanas: {exc}") from exc

    final_soup = BeautifulSoup(selected_response.text, "html.parser")
    # Verifica la ventana final para no analizar silenciosamente el periodo por defecto.
    final_select = None
    if select.get("name"):
        final_select = final_soup.find("select", attrs={"name": select.get("name")})
    if final_select is None and select.get("id"):
        final_select = final_soup.find("select", attrs={"id": select.get("id")})
    if final_select is not None:
        selected_option = final_select.find("option", selected=True) or final_select.find("option")
        if selected_option is not None:
            selected_value = str(selected_option.get("value", selected_option.get_text(" ", strip=True))).strip()
            selected_label = selected_option.get_text(" ", strip=True)
            window_confirmed = (
                selected_value == str(target_value)
                or normalize_label(selected_label) == normalize_label(target_label)
                or re.fullmatch(rf"\s*{weeks}\s*(?:weeks?|wks?)?\s*", selected_label, re.IGNORECASE) is not None
            )
            if not window_confirmed:
                raise DataSourceError(f"La web no confirmó la ventana seleccionada de {weeks} semanas (seleccionó: {selected_label}).")
    return final_soup, selected_response.url


def parse_faction_table(soup, page_url):
    table, header_row, header_cells, headers = _find_table(soup, ["faction", "win rate", "games played"])
    if table is None:
        raise DataSourceError("No he encontrado la tabla de win rates globales de facciones en MiniHeadQuarters.")
    ix_faction = next(i for i, h in enumerate(headers) if h == "faction")
    ix_rate = next(i for i, h in enumerate(headers) if "win rate" in h)
    ix_games = next(i for i, h in enumerate(headers) if "games played" in h)
    factions = {}
    for row in table.find_all("tr"):
        if row is header_row:
            continue
        cells = row.find_all(["th", "td"], recursive=False)
        if max(ix_faction, ix_rate, ix_games) >= len(cells):
            continue
        a = cells[ix_faction].find("a", href=True)
        label = a.get_text(" ", strip=True) if a else cells[ix_faction].get_text(" ", strip=True)
        label = re.sub(r"\s+Small sample\s*$", "", label, flags=re.IGNORECASE).strip()
        rate_text = cells[ix_rate].get_text(" ", strip=True)
        p = parse_percentage(rate_text)
        ci_low, ci_high = parse_confidence_interval(rate_text)
        n = parse_game_count(cells[ix_games].get_text(" ", strip=True))
        if label and p is not None:
            href = urljoin(page_url, a.get("href")) if a else None
            factions[normalize_label(label)] = {"label": label, "p": p, "n": n, "ci_low": ci_low, "ci_high": ci_high, "url": href}
    if not factions:
        raise DataSourceError("La tabla de facciones se encontró, pero no pude extraer ninguna fila válida.")
    return factions


def parse_disposition_tables(soup):
    table, header_row, header_cells, headers = _find_table(soup, ["force disposition", "global win rate"])
    if table is None:
        raise DataSourceError("No he encontrado la matriz de win rates entre disposiciones.")
    ix_disp = next(i for i, h in enumerate(headers) if h == "force disposition")
    ix_global = next(i for i, h in enumerate(headers) if "global win rate" in h)
    globals_by_disp = {}
    matchups = {}
    header_dispositions = {}
    for i, header in enumerate(headers):
        cleaned = re.sub(r"^vs\s+", "", header).strip()
        disp = SOURCE_DISPOSITION_NAMES.get(cleaned)
        if disp and i != ix_disp:
            header_dispositions[i] = disp
    for row in table.find_all("tr"):
        if row is header_row:
            continue
        cells = row.find_all(["th", "td"], recursive=False)
        if max([ix_disp, ix_global] + list(header_dispositions.keys())) >= len(cells):
            continue
        row_source_disp = normalize_label(cells[ix_disp].get_text(" ", strip=True))
        row_disp = SOURCE_DISPOSITION_NAMES.get(row_source_disp)
        if not row_disp:
            continue
        global_text = cells[ix_global].get_text(" ", strip=True)
        gp = parse_percentage(global_text)
        gci_low, gci_high = parse_confidence_interval(global_text)
        gn = parse_game_count(global_text)
        if gp is not None:
            globals_by_disp[row_disp] = {"p": gp, "n": gn, "ci_low": gci_low, "ci_high": gci_high}
        for col_index, col_disp in header_dispositions.items():
            cell_text = cells[col_index].get_text(" ", strip=True)
            cp = parse_percentage(cell_text)
            ci_low, ci_high = parse_confidence_interval(cell_text)
            cn = parse_game_count(cell_text)
            # Mirrors show '-', and deliberately contribute no modifier.
            if cp is not None:
                matchups[(row_disp, col_disp)] = {"p": cp, "n": cn, "ci_low": ci_low, "ci_high": ci_high}
    if not matchups:
        raise DataSourceError("La matriz de disposiciones no contiene cruces con win rates válidos.")
    return globals_by_disp, matchups


@st.cache_data(ttl=DATA_CACHE_SECONDS, show_spinner=False)
def load_mhq_index(weeks):
    session = _new_session()
    soup, page_url = _fetch_with_window(session, MHQ_STATS_URL, int(weeks))
    factions = parse_faction_table(soup, page_url)
    disposition_globals, disposition_matchups = parse_disposition_tables(soup)
    return {
        "weeks": int(weeks),
        "source_url": page_url,
        "factions": factions,
        "disposition_globals": disposition_globals,
        "disposition_matchups": disposition_matchups,
    }


@st.cache_data(ttl=DATA_CACHE_SECONDS, show_spinner=False)
def load_mhq_profile(source_label_norm, profile_url, weeks, all_faction_labels_norm):
    session = _new_session()
    soup, page_url = _fetch_with_window(session, profile_url, int(weeks))
    table, header_row, header_cells, headers = _find_table(soup, ["opponent", "games played", "win rate"])
    if table is None:
        raise DataSourceError(f"No he encontrado la tabla de matchups de {source_label_norm}.")
    ix_opponent = next(i for i, h in enumerate(headers) if h == "opponent")
    ix_games = next(i for i, h in enumerate(headers) if "games played" in h)
    ix_rate = next(i for i, h in enumerate(headers) if "win rate" in h)
    ix_ci = next((i for i, h in enumerate(headers) if "estimated range" in h), None)
    rows = {}
    for row in table.find_all("tr"):
        if row is header_row:
            continue
        cells = row.find_all(["th", "td"], recursive=False)
        if max(ix_opponent, ix_games, ix_rate) >= len(cells):
            continue
        link = cells[ix_opponent].find("a", href=True)
        opponent_label = link.get_text(" ", strip=True) if link else cells[ix_opponent].get_text(" ", strip=True)
        opponent_label = re.sub(r"\s+Small sample\s*$", "", opponent_label, flags=re.IGNORECASE).strip()
        opponent_norm = normalize_label(opponent_label)
        rate_text = cells[ix_rate].get_text(" ", strip=True)
        p = parse_percentage(rate_text)
        if ix_ci is not None and ix_ci < len(cells):
            ci_low, ci_high = parse_confidence_interval(cells[ix_ci].get_text(" ", strip=True))
        else:
            ci_low, ci_high = parse_confidence_interval(rate_text)
        n = parse_game_count(cells[ix_games].get_text(" ", strip=True))
        if opponent_norm and p is not None:
            rows[opponent_norm] = {"p": p, "n": n, "ci_low": ci_low, "ci_high": ci_high, "label": opponent_label}
    return rows


def resolve_source_label(army, factions):
    candidates = ARMY_SOURCE_CANDIDATES.get(army, [army])
    for candidate in candidates:
        key = normalize_label(candidate)
        if key in factions:
            return key
    # Last chance: exact normalized match with the label as shown in the app.
    exact = normalize_label(army)
    return exact if exact in factions else None


def build_winrate_data(army_names, weeks):
    index = load_mhq_index(int(weeks))
    resolved = {army: resolve_source_label(army, index["factions"]) for army in set(army_names)}
    needed = sorted({label for label in resolved.values() if label and index["factions"].get(label, {}).get("url")})
    profile_matchups = {}
    profile_errors = {}
    labels_json = tuple(sorted(index["factions"].keys()))
    if needed:
        def load_one(label):
            url = index["factions"][label]["url"]
            return label, load_mhq_profile(label, url, int(weeks), labels_json)
        with ThreadPoolExecutor(max_workers=min(4, len(needed))) as executor:
            futures = {executor.submit(load_one, label): label for label in needed}
            for future in as_completed(futures):
                label = futures[future]
                try:
                    profile_label, rows = future.result()
                    for opponent_norm, row in rows.items():
                        profile_matchups[(profile_label, opponent_norm)] = row
                except Exception as exc:
                    profile_errors[label] = str(exc)
    return {
        **index,
        "resolved_armies": resolved,
        "faction_matchups": profile_matchups,
        "profile_errors": profile_errors,
    }


# ============================================================
# MODELO ESTADÍSTICO Y OPTIMIZADOR
# ============================================================

def _clamp_probability(p):
    return max(0.02, min(0.98, float(p)))


def logit(p):
    p = _clamp_probability(p)
    return math.log(p / (1.0 - p))


def sigmoid(value):
    value = max(-8.0, min(8.0, float(value)))
    return 1.0 / (1.0 + math.exp(-value))


def shrink_probability(observed_p, observed_games, prior_p, prior_games):
    """Promedio ponderado con una muestra previa equivalente para evitar extremos con N pequeño."""
    n = max(0, int(observed_games or 0))
    if n == 0:
        return _clamp_probability(prior_p)
    return _clamp_probability((float(observed_p) * n + float(prior_p) * prior_games) / (n + prior_games))


def _faction_prior_probability(my_label, opp_label, data):
    my_stats = data["factions"].get(my_label) if my_label else None
    opp_stats = data["factions"].get(opp_label) if opp_label else None
    if not my_stats or not opp_stats:
        return 0.5
    if my_label == opp_label:
        return 0.5
    # Las tasas globales también reflejan fortaleza de jugadores/metajuego; se reduce
    # su diferencia log-odds a la mitad cuando no hay un dato directo entre facciones.
    return sigmoid(0.5 * (logit(my_stats["p"]) - logit(opp_stats["p"])))


def _get_faction_matchup(my_label, opp_label, data):
    if not my_label or not opp_label or my_label == opp_label:
        return None
    rec = data["faction_matchups"].get((my_label, opp_label))
    if rec:
        return {**rec, "direction": "directa"}
    reverse = data["faction_matchups"].get((opp_label, my_label))
    if reverse:
        ci_low = reverse.get("ci_low")
        ci_high = reverse.get("ci_high")
        return {
            "p": 1.0 - reverse["p"],
            "n": reverse["n"],
            "ci_low": (1.0 - ci_high) if ci_high is not None else None,
            "ci_high": (1.0 - ci_low) if ci_low is not None else None,
            "label": reverse.get("label", ""),
            "direction": "inversa",
        }
    return None


def calculate_pairing(me, opp, winrate_data):
    my_label = winrate_data["resolved_armies"].get(me["army"])
    opp_label = winrate_data["resolved_armies"].get(opp["army"])
    faction_prior = _faction_prior_probability(my_label, opp_label, winrate_data)
    faction_matchup = _get_faction_matchup(my_label, opp_label, winrate_data)
    if faction_matchup:
        faction_p = shrink_probability(
            faction_matchup["p"], faction_matchup["n"], faction_prior, FACTION_PRIOR_GAMES
        )
        faction_games = faction_matchup["n"]
        faction_raw = faction_matchup["p"]
        faction_quality = f"Matchup {faction_matchup['direction']} · N={faction_games}"
    else:
        faction_p = faction_prior
        faction_games = 0
        faction_raw = None
        if my_label and opp_label and my_label != opp_label and winrate_data["factions"].get(my_label) and winrate_data["factions"].get(opp_label):
            faction_quality = "Estimación por tasas globales"
        else:
            faction_quality = "Sin datos de facción; prior neutral"

    # Para disposiciones comparamos su win rate empírico con lo que cabría esperar
    # por su win rate global. Solo añadimos el efecto específico del cruce, reduciendo
    # el doble conteo de la fortaleza general de cada disposición.
    my_disp_stats = winrate_data["disposition_globals"].get(me["disposition"])
    opp_disp_stats = winrate_data["disposition_globals"].get(opp["disposition"])
    if my_disp_stats and opp_disp_stats and me["disposition"] != opp["disposition"]:
        disp_baseline = sigmoid(logit(my_disp_stats["p"]) - logit(opp_disp_stats["p"]))
    else:
        disp_baseline = 0.5

    disp_record = winrate_data["disposition_matchups"].get((me["disposition"], opp["disposition"]))
    if disp_record:
        disp_p = shrink_probability(disp_record["p"], disp_record["n"], disp_baseline, DISPOSITION_PRIOR_GAMES)
        disp_raw = disp_record["p"]
        disp_games = disp_record["n"]
        disp_effect_log_odds = logit(disp_p) - logit(disp_baseline)
    else:
        disp_p = disp_baseline
        disp_raw = None
        disp_games = 0
        disp_effect_log_odds = 0.0

    # No existe una tabla pública conjunta facción×facción×disposición. Esta suma
    # log-odds ponderada es una estimación transparente de ambos efectos empíricos.
    probability = sigmoid(logit(faction_p) + DISPOSITION_EFFECT_WEIGHT * disp_effect_log_odds)
    return {
        "probability": probability,
        "faction_probability": faction_p,
        "faction_raw_probability": faction_raw,
        "faction_games": faction_games,
        "faction_quality": faction_quality,
        "my_source_faction": my_label,
        "opp_source_faction": opp_label,
        "faction_prior": faction_prior,
        "disposition_probability": disp_p,
        "disposition_raw_probability": disp_raw,
        "disposition_games": disp_games,
        "disposition_baseline": disp_baseline,
        "disposition_effect_log_odds": disp_effect_log_odds,
        "data_quality": faction_quality + (f" · disposición N={disp_games}" if disp_games else " · disposición sin cruce directo"),
    }


def result_distribution(probabilities):
    dp = [1.0] + [0.0] * 6
    for p in probabilities:
        new = [0.0] * 7
        for wins in range(7):
            if dp[wins] == 0:
                continue
            new[wins] += dp[wins] * (1 - p)
            if wins < 6:
                new[wins + 1] += dp[wins] * p
        dp = new
    return dp


def evaluate_all_pairings(my_players, opp_players, winrate_data):
    results = []
    for permutation in itertools.permutations(opp_players):
        pairs = []
        probabilities = []
        for me, opp in zip(my_players, permutation):
            result = calculate_pairing(me, opp, winrate_data)
            p = result["probability"]
            probabilities.append(p)
            raw_disp = result["disposition_raw_probability"]
            pairs.append({
                "Nuestro jugador": me["name"],
                "Nuestro army": me["army"],
                "Nuestra disposición": me["disposition"],
                "Rival": opp["name"],
                "Rival army": opp["army"],
                "Rival disposición": opp["disposition"],
                "WR facción ajustado %": round(result["faction_probability"] * 100, 1),
                "WR facción observado %": round(result["faction_raw_probability"] * 100, 1) if result["faction_raw_probability"] is not None else None,
                "IC95 facción": format_confidence_interval(_get_faction_matchup(result["my_source_faction"], result["opp_source_faction"], winrate_data)) if _get_faction_matchup(result["my_source_faction"], result["opp_source_faction"], winrate_data) else "No hay cruce directo",
                "N matchup facción": result["faction_games"],
                "Fuente facción": result["faction_quality"],
                "WR disposición observado %": round(raw_disp * 100, 1) if raw_disp is not None else None,
                "IC95 disposición": format_confidence_interval(winrate_data["disposition_matchups"].get((me["disposition"], opp["disposition"]))) if winrate_data["disposition_matchups"].get((me["disposition"], opp["disposition"])) else "Sin cruce directo",
                "N matchup disposición": result["disposition_games"],
                "Victoria %": round(p * 100, 1),
                "Confianza de datos": result["data_quality"],
            })
        distribution = result_distribution(probabilities)
        results.append({
            "pairs": pairs,
            "expected_wins": sum(probabilities),
            "p_3plus": sum(distribution[3:]),
            "p_4plus": sum(distribution[4:]),
            "p_5plus": sum(distribution[5:]),
        })
    return results


def sort_results(results, objective):
    if objective == "Maximizar victorias esperadas":
        return sorted(results, key=lambda x: (x["expected_wins"], x["p_3plus"], x["p_4plus"]), reverse=True)
    if objective == "Maximizar 4-2 o mejor":
        return sorted(results, key=lambda x: (x["p_4plus"], x["expected_wins"], x["p_3plus"]), reverse=True)
    return sorted(results, key=lambda x: (x["p_3plus"], x["expected_wins"], x["p_4plus"]), reverse=True)


# ============================================================
# ASISTENTE DE PAIRING POR CARTAS
# ============================================================

def assistant_probability(me, opp, winrate_data):
    return calculate_pairing(me, opp, winrate_data)["probability"]


def assistant_best_completion(ours, rivals, winrate_data):
    if not ours or not rivals:
        return {"expected_wins": 0.0, "p_3plus": 0.0, "p_4plus": 0.0}
    best = None
    for perm in itertools.permutations(rivals):
        probs = [assistant_probability(me, op, winrate_data) for me, op in zip(ours, perm)]
        dist = result_distribution(probs)
        cand = (sum(probs), sum(dist[3:]), sum(dist[4:]))
        if best is None or cand > best[0]:
            best = (cand, list(zip(ours, perm)))
    return {"expected_wins": best[0][0], "p_3plus": best[0][1], "p_4plus": best[0][2], "pairs": best[1]}


def assistant_choose_opening(ours, rivals, winrate_data):
    out = []
    for me in ours:
        worst = min(max(assistant_probability(me, a, winrate_data), assistant_probability(me, b, winrate_data)) for a, b in itertools.combinations(rivals, 2))
        out.append((worst, me))
    return sorted(out, key=lambda x: x[0], reverse=True)


def assistant_counter_options(ours, rival_card, remaining_rivals, winrate_data):
    out = []
    for pair in itertools.combinations(ours, 2):
        immediate = min(assistant_probability(pair[0], rival_card, winrate_data), assistant_probability(pair[1], rival_card, winrate_data))
        rest = [p for p in ours if p not in pair]
        completion = assistant_best_completion(rest, remaining_rivals, winrate_data)
        out.append((immediate + completion["expected_wins"], immediate, completion, pair))
    return sorted(out, reverse=True, key=lambda x: (x[0], x[2]["p_3plus"], x[2]["p_4plus"]))


def assistant_choose_rival_for_offered(our_offered, rival_pair, our_counter_pair, received_rival, remaining_ours_after_round, remaining_rivals_after_round, winrate_data):
    """Recomienda cuál de las 2 cartas rivales elegir usando el resultado global estimado."""
    out = []
    for chosen_rival in rival_pair:
        other_rival = rival_pair[1] if chosen_rival is rival_pair[0] else rival_pair[0]
        p_offered = assistant_probability(our_offered, chosen_rival, winrate_data)
        rivals_after = list(remaining_rivals_after_round) + [other_rival]
        p_second = min(
            assistant_probability(our_counter_pair[0], received_rival, winrate_data),
            assistant_probability(our_counter_pair[1], received_rival, winrate_data)
        )
        continuation_candidates = []
        for chosen_our in our_counter_pair:
            other_our = our_counter_pair[1] if chosen_our is our_counter_pair[0] else our_counter_pair[0]
            ours_after = list(remaining_ours_after_round) + [other_our]
            continuation_candidates.append(assistant_best_completion(ours_after, rivals_after, winrate_data))
        best_cont = max(continuation_candidates, key=lambda c: (c["expected_wins"], c["p_3plus"], c["p_4plus"]))
        total = p_offered + p_second + best_cont["expected_wins"]
        out.append((total, p_offered, p_second, best_cont, chosen_rival))
    return sorted(out, reverse=True, key=lambda x: (x[0], x[1], x[3]["p_3plus"], x[3]["p_4plus"]))

def army_select(label, key, default):
    index = ALL_ARMIES.index(default) if default in ALL_ARMIES else 0
    return st.selectbox(label, ALL_ARMIES, index=index, key=key)

# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.header("📡 Datos estadísticos")
    data_weeks = st.selectbox("Ventana de win rates", [1, 2, 4, 8, 12, 26], index=4, format_func=lambda n: f"Últimas {n} semanas")
    st.caption("Fuente: MiniHeadQuarters · datos competitivos actualizados por la web · caché de 6 horas.")
    if st.button("🔄 Actualizar estadísticas ahora", use_container_width=True):
        load_mhq_index.clear()
        load_mhq_profile.clear()
        st.session_state.pop("results", None)
        st.session_state.pop("result_fingerprint", None)
        st.rerun()

    st.divider()
    st.header("⚙️ Objetivo del algoritmo")
    objective = st.selectbox(
        "Ordenar resultados por",
        [
            "Maximizar victorias esperadas",
            "Maximizar 4-2 o mejor",
            "Maximizar 3-3 o mejor",
        ]
    )
    st.divider()
    st.caption("Las probabilidades combinadas son estimaciones a partir de tasas empíricas de facciones y disposiciones, no una tabla conjunta observada para cada combinación exacta.")

# ============================================================
# NUESTRO EQUIPO
# ============================================================

st.header("1️⃣ Nuestro equipo — 6 jugadores")

my_players = []
cols = st.columns(2)

for i, default in enumerate(DEFAULT_MY):
    with cols[i % 2]:
        st.subheader(f"Jugador {i + 1}")

        name = st.text_input(
            "Nombre",
            default[0],
            key=f"my_name_{i}"
        )

        army = army_select(
            "Army",
            f"my_army_{i}",
            default[1]
        )

        disposition = st.selectbox(
            "Disposición",
            DISPOSITIONS,
            index=DISPOSITIONS.index(default[2]),
            key=f"my_disp_{i}"
        )

        my_players.append({
            "name": name,
            "army": army,
            "disposition": disposition,
        })

# ============================================================
# RIVAL
# ============================================================

st.header("2️⃣ Equipo rival — 6 jugadores")

opp_players = []
cols = st.columns(2)

for i, default in enumerate(DEFAULT_OPP):
    with cols[i % 2]:
        st.subheader(f"Rival {i + 1}")

        name = st.text_input(
            "Nombre",
            default[0],
            key=f"opp_name_{i}"
        )

        army = army_select(
            "Army",
            f"opp_army_{i}",
            default[1]
        )

        disposition = st.selectbox(
            "Disposición",
            DISPOSITIONS,
            index=DISPOSITIONS.index(default[2]),
            key=f"opp_disp_{i}"
        )

        opp_players.append({
            "name": name,
            "army": army,
            "disposition": disposition,
        })

# ============================================================
# CARGA AUTOMÁTICA DE WIN RATES
# ============================================================

st.header("3️⃣ Win rates automáticos")
st.caption(
    "Ya no hay que introducir valoraciones Army vs Army. Se descargan win rates de facciones "
    "y de Force Dispositions desde MiniHeadQuarters; después el modelo combina ambas fuentes."
)
st.markdown("Fuente: [MiniHeadQuarters — Meta analysis](" + MHQ_STATS_URL + ") · [Metodología](" + MHQ_METHOD_URL + ")")

all_selected_armies = sorted({p["army"] for p in my_players + opp_players})
_data_fingerprint = (tuple(all_selected_armies), int(data_weeks))
try:
    with st.spinner(f"Consultando win rates de MiniHeadQuarters ({data_weeks} semanas)…"):
        winrate_data = build_winrate_data(all_selected_armies, data_weeks)
    st.session_state["mhq_last_good_data"] = winrate_data
    st.session_state["mhq_last_good_fingerprint"] = _data_fingerprint
except Exception as exc:
    cached_data = st.session_state.get("mhq_last_good_data")
    cached_fingerprint = st.session_state.get("mhq_last_good_fingerprint")
    if cached_data is not None and cached_fingerprint == _data_fingerprint:
        winrate_data = cached_data
        st.warning("No se pudo refrescar MiniHeadQuarters; continúo con los últimos datos válidos cargados en esta sesión. Pulsa «Actualizar estadísticas ahora» para reintentar.")
    else:
        st.error(f"No he podido cargar las estadísticas de MiniHeadQuarters: {exc}")
        st.info("Comprueba la conexión y pulsa «Actualizar estadísticas ahora». No utilizaré datos inventados ni una ventana temporal distinta sin avisarte.")
        st.stop()

# Resumen de cobertura para las facciones realmente seleccionadas.
summary_rows = []
missing_armies = []
for army in all_selected_armies:
    source_key = winrate_data["resolved_armies"].get(army)
    if source_key and source_key in winrate_data["factions"]:
        stat = winrate_data["factions"][source_key]
        summary_rows.append({
            "Army seleccionado": army,
            "Facción estadística usada": stat["label"],
            "Win rate global": f"{stat['p']*100:.1f}%",
            "IC 95%": format_confidence_interval(stat),
            "Partidas": stat["n"],
            "Uso": "Exacta" if normalize_label(army) == normalize_label(stat["label"]) else ("Alias estadístico" if ARMY_SOURCE_CANDIDATES.get(army) and normalize_label(stat["label"]) == normalize_label(ARMY_SOURCE_CANDIDATES[army][0]) else "Categoría genérica"),
        })
    else:
        missing_armies.append(army)
        summary_rows.append({
            "Army seleccionado": army,
            "Facción estadística usada": "Sin datos publicados detectados",
            "Win rate global": "50% neutral",
            "IC 95%": "No disponible",
            "Partidas": 0,
            "Uso": "Sin datos directos",
        })

with st.expander("📚 Ver cobertura de datos de las facciones seleccionadas", expanded=False):
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
    st.caption("Las muestras pequeñas se suavizan hacia una estimación previa para evitar que 1 partida al 100% se interprete como certeza.")
    if missing_armies:
        st.warning("Sin tasa directa disponible para: " + ", ".join(missing_armies) + ". En estos casos el componente de facción se mantiene neutral si no se puede estimar con las tasas globales. Las disposiciones sí siguen influyendo.")
    if winrate_data.get("profile_errors"):
        st.warning("No se pudieron leer algunos perfiles de facción; cuando falte el cruce directo se usará una estimación por tasas globales. Perfiles: " + ", ".join(winrate_data["profile_errors"].keys()))

st.subheader("Win rates entre disposiciones")
st.caption("Cada celda muestra el win rate publicado de la disposición de la fila contra la de la columna. Debajo puedes consultar el tamaño de cada muestra.")
_disp_pct = pd.DataFrame(index=DISPOSITIONS, columns=DISPOSITIONS, dtype=object)
_disp_n = pd.DataFrame(index=DISPOSITIONS, columns=DISPOSITIONS, dtype=object)
for _mine in DISPOSITIONS:
    for _theirs in DISPOSITIONS:
        _rec = winrate_data["disposition_matchups"].get((_mine, _theirs))
        _disp_pct.loc[_mine, _theirs] = f"{_rec['p']*100:.1f}%" if _rec else "—"
        _disp_n.loc[_mine, _theirs] = str(_rec["n"]) if _rec else "—"
st.dataframe(_disp_pct, use_container_width=True)
with st.expander("Ver número de partidas de cada cruce entre disposiciones"):
    st.dataframe(_disp_n, use_container_width=True)
with st.expander("Ver win rate global de cada disposición"):
    st.dataframe(pd.DataFrame([
        {
            "Disposición": disp,
            "Win rate global": f"{rec['p']*100:.1f}%",
            "IC 95%": format_confidence_interval(rec),
            "Partidas": rec["n"],
        }
        for disp, rec in winrate_data["disposition_globals"].items()
    ]), use_container_width=True, hide_index=True)

# ============================================================
# ASISTENTE — FLUJO REAL DE CARTAS (V8: RONDA 1 + RONDA 2)
# ============================================================

st.markdown("---")
st.header("🎴 Asistente de pairing por cartas")
st.info("El asistente acompaña el pairing real por rondas. Primero calcula la salida con 6 cartas; después registra lo que realmente ha ocurrido y recalcula desde las 4 cartas restantes. La recomendación de salida es conservadora: no puede conocer las decisiones ocultas del rival.")

if len(my_players) == 6 and len(opp_players) == 6:
    # ---------- helpers de estado ----------
    def reset_assistant():
        for k in list(st.session_state.keys()):
            if k.startswith("pa_"):
                del st.session_state[k]
        st.session_state["pa_ours"] = list(range(6))
        st.session_state["pa_rivals"] = list(range(6))
        st.session_state["pa_round"] = 1
        st.session_state["pa_closed"] = []

    if "pa_ours" not in st.session_state or "pa_rivals" not in st.session_state:
        reset_assistant()

    if st.button("🔄 Reiniciar asistente de pairing", use_container_width=True):
        reset_assistant()
        st.rerun()

    def cards(indices, players):
        return [players[i] for i in indices]

    def choose_opening_for_indices(our_indices, rival_indices):
        ours = cards(our_indices, my_players)
        rivals = cards(rival_indices, opp_players)
        return assistant_choose_opening(ours, rivals, winrate_data)

    round_no = st.session_state["pa_round"]
    our_ids = st.session_state["pa_ours"]
    rival_ids = st.session_state["pa_rivals"]

    st.subheader(f"🃏 Ronda {round_no} — {len(our_ids)} cartas restantes")

    # Tras cerrar la ronda 2 quedan 2 cartas. V8 no simula la ronda final:
    # no intentamos calcular recomendaciones con una cantidad de cartas no soportada.
    if round_no > 2:
        st.success("### ✅ Rondas 1 y 2 completadas")
        st.write(f"**Nuestras 2 cartas restantes:** {', '.join(my_players[i]['name'] for i in st.session_state['pa_ours'])}")
        st.write(f"**Sus 2 cartas restantes:** {', '.join(opp_players[i]['army'] for i in st.session_state['pa_rivals'])}")
        st.info("La ronda final 2→1 se añadirá más adelante. Por ahora el asistente termina aquí sin mostrar errores ni recomendaciones adicionales.")
    else:
        # ==================== RONDA ACTIVA ====================
        opening = choose_opening_for_indices(our_ids, rival_ids)
        first = opening[0][1]
        first_idx = my_players.index(first)

        st.success(f"### 🎯 CARTA RECOMENDADA PARA SALIR: {first['name']} — {first['army']} · {first['disposition']}")
        with st.expander("Ver las cartas ordenadas para salir"):
            st.dataframe(pd.DataFrame([
                {"#": i+1, "Jugador": me["name"], "Army": me["army"], "Disposición": me["disposition"], "Peor caso": f"{score*100:.1f}%"}
                for i, (score, me) in enumerate(opening)
            ]), use_container_width=True, hide_index=True)

        # En la ronda 1 el ofrecido debe ser la recomendación; en la ronda 2 también se puede cambiar manualmente.
        offer_options = [i for i in our_ids]
        offer_idx = st.selectbox(
            "1️⃣ ¿Qué carta nuestra entregamos al rival?",
            offer_options,
            index=offer_options.index(first_idx) if first_idx in offer_options else 0,
            format_func=lambda i: f"{my_players[i]['name']} — {my_players[i]['army']} · {my_players[i]['disposition']}",
            key=f"pa_offer_{round_no}"
        )
        offered_ours = my_players[offer_idx]

        rival_labels = [f"{opp_players[i]['name']} — {opp_players[i]['army']} · {opp_players[i]['disposition']}" for i in rival_ids]
        receive_idx = st.selectbox(
            "2️⃣ ¿Qué carta nos entrega el rival?",
            rival_ids,
            format_func=lambda i: f"{opp_players[i]['name']} — {opp_players[i]['army']} · {opp_players[i]['disposition']}",
            key=f"pa_receive_{round_no}"
        )
        received_rival = opp_players[receive_idx]

        our_remaining = [i for i in our_ids if i != offer_idx]
        rival_remaining = [i for i in rival_ids if i != receive_idx]

        # El asistente recomienda las 2 mejores, pero NO las selecciona por nosotros.
        # El jugador debe introducir manualmente la decisión real tomada en mesa.
        st.subheader(f"3️⃣ Nuestras 2 cartas contra {received_rival['army']}")
        our_remaining_cards = cards(our_remaining, my_players)
        rival_remaining_cards = cards(rival_remaining, opp_players)
        options = assistant_counter_options(our_remaining_cards, received_rival, rival_remaining_cards, winrate_data)

        if options:
            recommended_pair = options[0][3]
            rec_names = " + ".join(c["name"] for c in recommended_pair)
            st.success(f"### 🎯 Te recomiendo poner: {rec_names}")
            st.caption("Es una recomendación del modelo. Tú debes seleccionar manualmente las 2 cartas que realmente vais a poner en mesa.")

        our_pair_indices = st.multiselect(
            "Selecciona manualmente exactamente 2 de nuestras cartas",
            our_remaining,
            max_selections=2,
            default=[],
            format_func=lambda i: f"{my_players[i]['name']} — {my_players[i]['army']} · {my_players[i]['disposition']}",
            key=f"pa_our_pair_{round_no}"
        )

        if len(our_pair_indices) < 2:
            st.info("👆 Selecciona las 2 cartas que habéis decidido poner para continuar.")
            st.stop()

        selected_pair = [my_players[i] for i in our_pair_indices]
        selected_key = frozenset(c['name'] for c in selected_pair)
        selected_option = next((o for o in options if frozenset(c['name'] for c in o[3]) == selected_key), None)

        if selected_option is not None:
            rank = next(i for i, o in enumerate(options, 1) if o is selected_option)
            if rank == 1:
                st.success("### ✅ Buena elección: tus 2 cartas son la opción mejor valorada por el asistente.")
            else:
                st.info(f"### 📊 Tu elección queda en la posición #{rank} de {len(options)} según el modelo.")
            st.caption(f"Resultado conservador de esta elección: {selected_option[1]*100:.1f}% en el cruce inmediato; continuación esperada: {selected_option[2]['expected_wins']:.2f} victorias.")
        else:
            st.warning("No se ha podido valorar la pareja seleccionada.")

        with st.expander("🔎 Comparar con las demás parejas posibles"):
            st.dataframe(pd.DataFrame([
                {"#": i+1, "Carta 1": o[3][0]["name"], "Carta 2": o[3][1]["name"], "Mínimo inmediato": f"{o[1]*100:.1f}%", "Equipo restante (esperado)": f"{o[2]['expected_wins']:.2f}"}
                for i, o in enumerate(options)
            ]), use_container_width=True, hide_index=True)

        st.subheader("4️⃣ Se revelan las 2 cartas que ellos han puesto contra nuestra carta ofrecida")
        if len(rival_remaining) >= 2:
            rival_pair_indices = st.multiselect(
                "Selecciona las 2 cartas RIVALES que han puesto contra nuestra carta",
                rival_remaining,
                max_selections=2,
                format_func=lambda i: f"{opp_players[i]['name']} — {opp_players[i]['army']} · {opp_players[i]['disposition']}",
                key=f"pa_rival_pair_{round_no}"
            )
        else:
            rival_pair_indices = rival_remaining
            st.info("Quedan 2 cartas rivales: ambas son las que se revelan.")

        if len(rival_pair_indices) == 2:
            rival_pair_cards = [opp_players[i] for i in rival_pair_indices]
            remaining_ours_after_round_base = [my_players[i] for i in our_remaining if i not in our_pair_indices]
            remaining_rivals_after_round_base = [opp_players[i] for i in rival_remaining if i not in rival_pair_indices]
            rival_choice_options = assistant_choose_rival_for_offered(
                offered_ours,
                rival_pair_cards,
                [my_players[i] for i in our_pair_indices],
                received_rival,
                remaining_ours_after_round_base,
                remaining_rivals_after_round_base,
                winrate_data
            )
            recommended_rival = rival_choice_options[0][4]
            recommended_rival_idx = rival_pair_indices[rival_pair_cards.index(recommended_rival)]

            st.subheader("5️⃣ Elegimos cuál de sus 2 cartas enfrenta a la nuestra")
            st.success(f"### 🎯 Te recomiendo elegir: {recommended_rival['name']} — {recommended_rival['army']} · {recommended_rival['disposition']}")
            st.caption("La recomendación busca el mejor resultado global del equipo, teniendo en cuenta las cartas que quedarían disponibles.")
            chosen_rival_idx = st.radio(
                "¿Cuál elegimos contra nuestra carta ofrecida?",
                rival_pair_indices,
                index=rival_pair_indices.index(recommended_rival_idx),
                format_func=lambda i: f"{opp_players[i]['name']} — {opp_players[i]['army']} · {opp_players[i]['disposition']}",
                key=f"pa_chosen_rival_{round_no}"
            )
            with st.expander("🔎 Comparar las 2 opciones"):
                st.dataframe(pd.DataFrame([
                    {
                        "Opción": "⭐ RECOMENDADA" if x[4] is recommended_rival else "Alternativa",
                        "Carta rival": x[4]["army"],
                        "Cruce ofrecida": f"{x[1]*100:.1f}%",
                        "Equipo proyectado": f"{x[0]:.2f} victorias esperadas"
                    } for x in rival_choice_options
                ]), use_container_width=True, hide_index=True)

            st.subheader("6️⃣ Registramos cuál de nuestras 2 han elegido ellos")
            chosen_our_idx = st.radio(
                "¿Cuál de nuestras 2 cartas han elegido contra su carta ofrecida?",
                our_pair_indices,
                format_func=lambda i: f"{my_players[i]['name']} — {my_players[i]['army']} · {my_players[i]['disposition']}",
                key=f"pa_chosen_our_{round_no}"
            )

            if st.button(f"⚔️ CERRAR RONDA {round_no} Y CALCULAR LA SIGUIENTE", type="primary", use_container_width=True, key=f"pa_close_{round_no}"):
                # Se cierran exactamente dos pairings: carta ofrecida vs carta rival elegida,
                # y carta nuestra elegida por ellos vs carta rival que recibimos.
                closed = [
                    (offered_ours, opp_players[chosen_rival_idx]),
                    (my_players[chosen_our_idx], received_rival)
                ]
                st.session_state["pa_closed"] = st.session_state.get("pa_closed", []) + closed

                # Las cartas que no fueron elegidas en los cruces vuelven a la mano.
                used_ours = {offer_idx, chosen_our_idx}
                used_rivals = {receive_idx, chosen_rival_idx}
                st.session_state["pa_ours"] = [i for i in our_ids if i not in used_ours]
                st.session_state["pa_rivals"] = [i for i in rival_ids if i not in used_rivals]
                st.session_state["pa_round"] = round_no + 1
                st.rerun()

    # ==================== HISTORIAL ====================
    if st.session_state.get("pa_closed"):
        st.markdown("---")
        st.subheader("📋 Pairings ya cerrados")
        for n, (me, op) in enumerate(st.session_state["pa_closed"], 1):
            st.write(f"**{n}. {me['name']}** ({me['army']} · {me['disposition']})  ⚔️  **{op['army']}** ({op['disposition']})")

else:
    st.warning("Configura los 6 jugadores de cada equipo para activar el asistente.")


# Invalidar resultados previos si cambian los equipos o la ventana de datos.
_result_fingerprint = (
    tuple((p["name"], p["army"], p["disposition"]) for p in my_players),
    tuple((p["name"], p["army"], p["disposition"]) for p in opp_players),
    int(data_weeks),
)
if st.session_state.get("result_fingerprint") != _result_fingerprint:
    st.session_state.pop("results", None)
    st.session_state["result_fingerprint"] = _result_fingerprint

# ============================================================
# CALCULAR
# ============================================================

st.header("5️⃣ Buscar el pairing óptimo")

if st.button(
    "🚀 CALCULAR LOS 720 PAIRINGS",
    type="primary",
    use_container_width=True
):
    with st.spinner("Calculando 720 combinaciones..."):
        st.session_state["results"] = evaluate_all_pairings(
            my_players,
            opp_players,
            winrate_data
        )
        st.session_state["result_fingerprint"] = _result_fingerprint

if "results" in st.session_state:
    results = sort_results(st.session_state["results"], objective)
    best = results[0]

    # ========================================================
    # RESULTADO — FORMATO "HOJA DE PAIRING"
    # ========================================================
    st.markdown("---")
    st.header("🏆 Pairing recomendado")
    st.caption("La combinación que mejor encaja con el objetivo seleccionado.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Victorias esperadas", f'{best["expected_wins"]:.2f} / 6')
    c2.metric("3-3 o mejor", f'{best["p_3plus"] * 100:.1f}%')
    c3.metric("4-2 o mejor", f'{best["p_4plus"] * 100:.1f}%')

    st.markdown("### ⚔️ Los 6 enfrentamientos")

    # Tarjetas grandes, pensadas para leerlas rápidamente en una tablet.
    for i, p in enumerate(best["pairs"], 1):
        with st.container(border=True):
            left, mid, right = st.columns([4, 1, 4])
            with left:
                st.markdown(f"**{p['Nuestro jugador']}**")
                st.caption(f"{p['Nuestro army']} · {p['Nuestra disposición']}")
            with mid:
                st.markdown("### ⚔️")
            with right:
                st.markdown(f"**{p['Rival army']}**")
                st.caption(f"Disposición rival · {p['Rival disposición']}")

            st.progress(
                p["Victoria %"] / 100,
                text=f"Probabilidad de victoria: {p['Victoria %']:.1f}%"
            )
            _fmatch = (
                f"WR facción ajustado {p['WR facción ajustado %']:.1f}%"
                + (f" (cruce observado {p['WR facción observado %']:.1f}%, {p['IC95 facción']}, N={p['N matchup facción']})" if p["WR facción observado %"] is not None else f" ({p['Fuente facción']})")
            )
            _dmatch = (
                f"WR disposiciones observado {p['WR disposición observado %']:.1f}% ({p['IC95 disposición']}, N={p['N matchup disposición']})"
                if p["WR disposición observado %"] is not None else "Sin cruce directo de disposiciones"
            )
            st.caption(_fmatch + " · " + _dmatch)

    with st.expander("📋 Ver detalle numérico del pairing"):
        detail_df = pd.DataFrame(best["pairs"]).drop(columns=["Rival"], errors="ignore")
        st.dataframe(detail_df, use_container_width=True, hide_index=True)

    # ========================================================
    # ALTERNATIVAS
    # ========================================================
    st.markdown("### 🔄 Otras opciones fuertes")
    st.caption("No son simples números de combinación: aquí puedes ver exactamente qué cambia en cada pairing.")

    for rank, result in enumerate(results[1:4], 2):
        with st.expander(
            f"Opción {rank} · {result['expected_wins']:.2f} victorias esperadas · "
            f"{result['p_3plus'] * 100:.1f}% de 3-3+"
        ):
            for i, p in enumerate(result["pairs"], 1):
                st.write(
                    f"**{i}. {p['Nuestro jugador']} → {p['Rival army']}** "
                    f"· {p['Nuestro army']} vs {p['Rival army']} · "
                    f"**{p['Victoria %']:.1f}%**"
                )

    # ========================================================
    # MATRIZ — ANÁLISIS AVANZADO
    # ========================================================
    st.markdown("### 📊 Análisis avanzado")

    with st.expander("Ver matriz 6×6 de enfrentamientos"):
        matrix = pd.DataFrame(
            index=[
                f"{p['name']} — {p['army']} — {p['disposition']}"
                for p in my_players
            ],
            columns=[
                f"{p['army']} — {p['disposition']}"
                for p in opp_players
            ],
            dtype=float
        )

        for me in my_players:
            for opp in opp_players:
                r = calculate_pairing(me, opp, winrate_data)
                matrix.loc[
                    f"{me['name']} — {me['army']} — {me['disposition']}",
                    f"{opp['army']} — {opp['disposition']}"
                ] = round(r["probability"] * 100, 1)

        st.dataframe(matrix, use_container_width=True)

    with st.expander("ℹ️ Cómo interpretar los resultados"):
        st.info(
            "Los datos proceden de MiniHeadQuarters. Los win rates de facción se obtienen del cruce directo cuando existe muestra; "
            "si falta, se estima a partir de las tasas globales de ambas facciones y se indica en la tabla. "
            "La disposición aporta un ajuste basado en su win rate contra la otra disposición, centrado frente a las tasas globales de ambas. "
            "El sitio no publica una matriz conjunta para todas las combinaciones facción×facción×disposición, así que la probabilidad final es una estimación combinada, no una estadística observada exacta."
        )
