import streamlit as st
import folium
from streamlit_folium import st_folium
import streamlit.components.v1 as components
from folium.plugins import TimestampedGeoJson
import pandas as pd
import re
import os
import base64
from datetime import timedelta
import requests

# 1. Configuración de la Página Ejecutiva
st.set_page_config(page_title="Space Operations - SENEAM", layout="wide")
AJUSTE_UTC = 6 

@st.cache_data(show_spinner=False)
def cargar_bases_datos(mision):
    # Selección dinámica de bases de datos según la Misión
    if "Flight-15" in mision:
        archivo_areas = "Coordenadas_Starship_FLT15.xlsx"
        archivo_vuelos = "ROCKET_13_NOV_2026.xlsx"
        fecha_mision = "2026-11-13"
    else:
        archivo_areas = "Coordenadas_Starship_FLT14.xlsx"
        archivo_vuelos = "ROCKET_28_SEPT_2026.xlsx"
        fecha_mision = "2026-09-28"

    # A. Waypoints y VORs
    df_wp = pd.read_excel("Coordenadas_Waypoints_ENR_3.3.xlsx", sheet_name="Waypoints_Unicos", header=3)
    df_wp.columns = df_wp.columns.str.strip()
    df_wp = df_wp.dropna(subset=['Latitud (Decimal)', 'Longitud (Decimal)'])
    
    # --- INYECCIÓN DE VORS FALTANTES ---
    vores_faltantes = pd.DataFrame([
        {'Nombre del Punto / Waypoint': 'REYNOSA', 'Latitud (Decimal)': 26.0104, 'Longitud (Decimal)': -98.2285},
        {'Nombre del Punto / Waypoint': 'COLIMA', 'Latitud (Decimal)': 19.2770, 'Longitud (Decimal)': -103.5775},
        {'Nombre del Punto / Waypoint': 'TUXTLA', 'Latitud (Decimal)': 16.5616, 'Longitud (Decimal)': -93.0257},
        {'Nombre del Punto / Waypoint': 'CIUDAD JUAREZ', 'Latitud (Decimal)': 31.6386, 'Longitud (Decimal)': -106.4344},
        {'Nombre del Punto / Waypoint': 'CREEL', 'Latitud (Decimal)': 27.7490, 'Longitud (Decimal)': -107.6360},
        {'Nombre del Punto / Waypoint': 'GUAYMAS', 'Latitud (Decimal)': 27.9653, 'Longitud (Decimal)': -110.9250},
        {'Nombre del Punto / Waypoint': 'NORIA', 'Latitud (Decimal)': 26.3150, 'Longitud (Decimal)': -100.1200}
    ])
    df_wp = pd.concat([df_wp, vores_faltantes], ignore_index=True)

    # B. Aerovías / Rutas RNAV y ATS
    try:
        df_rnav = pd.read_excel("Coordenadas_Waypoints_ENR_3.3.xlsx", sheet_name="Aerovias_Waypoints")
    except Exception:
        df_rnav = pd.DataFrame()
        
    try:
        df_ats_hi = pd.read_excel("Coordenadas_Waypoints_ENR_3.2.xlsx", sheet_name="Rutas ATS EAS")
    except Exception:
        df_ats_hi = pd.DataFrame()

    try:
        df_ats_low = pd.read_excel("Coordenadas_Waypoints_ENR_3.1.xlsx", sheet_name="Rutas ATS EAI")
    except Exception:
        df_ats_low = pd.DataFrame()

    # Diccionario Oficial de VORs en México
    MAPA_VORS_MEXICO = {
        "TIJUANA": "TIJ", "MEXICALI": "MXL", "PEÑASCO": "PPE", "HERMOSILLO": "HMO",
        "OBREGON": "CEN", "OBREGÓN": "CEN", "LORETO": "LTO", "MOCHIS": "LMM",
        "CULIACAN": "CUL", "CULIACÁN": "CUL", "LA PAZ": "LAP", "CABOS": "SJD", "LUCAS": "CSL",
        "MAZATLAN": "MZT", "MAZATLÁN": "MZT", "DURANGO": "DGO", "ZACATECAS": "ZCL",
        "AGUASCALIENTES": "AGU", "LEON": "BJX", "LEÓN": "BJX", "VALLARTA": "PVR",
        "GUADALAJARA": "GDL", "QUERETARO": "QET", "QUERÉTARO": "QET", "MANZANILLO": "ZLO",
        "URUAPAN": "UPN", "MORELIA": "MLM", "ZIHUATANEJO": "ZIH", "ACAPULCO": "ACA",
        "MEXICO": "MEX", "MÉXICO": "MEX", "PUEBLA": "PBC", "TEQUESQUITENGO": "TEQ",
        "VERACRUZ": "VER", "OAXACA": "OAX", "IXTEPEC": "IZT", "HUATULCO": "HUX",
        "TAPACHULA": "TAP", "MINATITLAN": "MTT", "MINATITLÁN": "MTT", "VILLAHERMOSA": "VSA",
        "CARMEN": "CME", "CAMPECHE": "CPE", "MERIDA": "MID", "MÉRIDA": "MID",
        "KAUA": "CZA", "CANCUN": "CUN", "CANCÚN": "CUN", "COZUMEL": "CZM",
        "TULUM": "TQO", "CHETUMAL": "CTM", "TAMPICO": "TAM", "VICTORIA": "CVM",
        "MONTERREY": "MTY", "SALTILLO": "SLW", "TORREON": "TRC", "TORREÓN": "TRC",
        "MONCLOVA": "MOV", "ALLENDE": "ALL", "CONCEPCION": "CDR", "CONCEPCIÓN": "CDR",
        "MATAMOROS": "MAM", "NUEVO LAREDO": "NLD", "REYNOSA": "REX", "COLIMA": "COL",
        "POZA RICA": "PAZ", "TUXPAN": "TUX", "ESCONDIDO": "PXM", "TOLUCA": "TLC", "TUXTLA": "TGZ",
        "CIUDAD JUAREZ": "CJS", "JUAREZ": "CJS", "CREEL": "BCO", "GUAYMAS": "GYM", "NORIA": "TTM"
    }

    def obtener_codigo(row):
        s = str(row['Nombre del Punto / Waypoint']).strip().upper()
        match = re.search(r'\(([A-Z]{3})\)', s)
        if match: return match.group(1)
        for k in sorted(MAPA_VORS_MEXICO.keys(), key=len, reverse=True):
            if k in s: return MAPA_VORS_MEXICO[k]
        s_limpio = re.sub(r'\b(VOR|NDB|DME|TACAN|VORTAC|ILS)\b', '', s).strip()
        partes = s_limpio.split()
        return partes[0][:3] if partes else ""

    def clasificar_punto(row):
        s = str(row['Nombre del Punto / Waypoint']).strip().upper()
        for k in MAPA_VORS_MEXICO.keys():
            if k in s or s in k: return 'VOR / Radioayuda'
        if 'VOR' in s or 'NDB' in s or 'DME' in s or 'TACAN' in s or 'VORTAC' in s:
            return 'VOR / Radioayuda'
        return 'Waypoint'

    df_wp['Tipo'] = df_wp.apply(clasificar_punto, axis=1)
    df_wp['Codigo_Limpio'] = df_wp.apply(obtener_codigo, axis=1)
    
    dicc_wp = pd.Series(
        zip(df_wp['Latitud (Decimal)'], df_wp['Longitud (Decimal)']), 
        index=df_wp['Nombre del Punto / Waypoint'].astype(str).str.strip()
    ).to_dict()
    
    # C. Hazard Areas
    df_areas = pd.read_excel(archivo_areas, sheet_name="Consolidado_Areas", header=3)
    df_areas.columns = df_areas.columns.str.strip()
    df_areas = df_areas.dropna(subset=['Latitud (Decimal)', 'Longitud (Decimal)'])
    
    if "Flight-15" in mision:
        try:
            df_c2 = pd.read_excel(archivo_areas, sheet_name="AHA_C2_MMFR", header=3)
            df_c2.columns = df_c2.columns.str.strip()
            df_c2 = df_c2.dropna(subset=['Latitud (Decimal)', 'Longitud (Decimal)'])
            df_c2['Área / Hazard Zone'] = 'AHA-C2'
            
            df_c3 = pd.read_excel(archivo_areas, sheet_name="AHA_C3_MMFR", header=3)
            df_c3.columns = df_c3.columns.str.strip()
            df_c3 = df_c3.dropna(subset=['Latitud (Decimal)', 'Longitud (Decimal)'])
            df_c3['Área / Hazard Zone'] = 'AHA-C3'

            df_c4 = pd.read_excel(archivo_areas, sheet_name="AHA_C4_US", header=3)
            df_c4.columns = df_c4.columns.str.strip()
            df_c4 = df_c4.dropna(subset=['Latitud (Decimal)', 'Longitud (Decimal)'])
            df_c4['Área / Hazard Zone'] = 'AHA-C4'
            
            df_areas = pd.concat([df_areas, df_c2, df_c3, df_c4], ignore_index=True)
        except Exception as e:
            print("Error cargando áreas de reingreso:", e)
    
    # D. Espacio Aéreo SENEAM
    xls_espacio = pd.ExcelFile("Coordenadas_Espacio_Aereo_SENEAM.xlsx")
    dict_espacio = {}
    for sheet in xls_espacio.sheet_names:
        if sheet != "UTA México":
            df_sector = pd.read_excel(xls_espacio, sheet_name=sheet)
            df_sector.columns = df_sector.columns.str.strip()
            dict_espacio[sheet] = df_sector.dropna(subset=['Latitud (Decimal)', 'Longitud (Decimal)'])
        
    # E. Vuelos y Línea de Tiempo
    xls_vuelos = pd.ExcelFile(archivo_vuelos)
    df_vuelos = pd.read_excel(xls_vuelos, sheet_name=xls_vuelos.sheet_names[0])
    df_vuelos.columns = df_vuelos.columns.str.strip()
    
    if 'entry_hour' in df_vuelos.columns:
        df_vuelos['entry_hour'] = pd.to_datetime(df_vuelos['entry_hour'], errors='coerce')
    if 'exit_hour' in df_vuelos.columns:
        df_vuelos['exit_hour'] = pd.to_datetime(df_vuelos['exit_hour'], errors='coerce')
    
    df_timeline = None
    if "Timeline" in xls_vuelos.sheet_names:
        df_timeline = pd.read_excel(xls_vuelos, sheet_name="Timeline")
        df_timeline.columns = df_timeline.columns.str.strip().str.lower().str.replace(' ', '_')
        if 'hora_utc' in df_timeline.columns:
            def normalizar_hora(row):
                val = row['hora_utc']
                if pd.isnull(val): return None
                evento_str = str(row.get('evento', ''))
                
                fecha = fecha_mision
                if "Flight-15" in mision:
                    if "Nov 14" in evento_str or "Nov 14" in str(val): fecha = "2026-11-14"
                    elif "Nov 13" in evento_str or "Nov 13" in str(val): fecha = "2026-11-13"
                
                match = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)', str(val))
                if match: return pd.to_datetime(f"{fecha} {match.group(1)}")
                return None
            df_timeline['hora_utc'] = df_timeline.apply(normalizar_hora, axis=1)
    
    return df_wp, dicc_wp, df_areas, dict_espacio, df_vuelos, df_timeline, df_rnav, df_ats_hi, df_ats_low

def decodificar_coordenada_ruta(string_punto):
    match = re.match(r'^(\d{2})(\d{2})[Nn](\d{3})(\d{2})[Ww]$', str(string_punto).strip())
    if match:
        return (int(match.group(1)) + int(match.group(2)) / 60.0, 
                -(int(match.group(3)) + int(match.group(4)) / 60.0))
    return None

def agregar_capa_rutas(df_rutas, capa, color_base, prefijo_tooltip, dicc_wp):
    if df_rutas is not None and not df_rutas.empty:
        df_rutas.columns = df_rutas.columns.str.strip()
        col_aerovia = df_rutas.columns[0]
        
        for nombre_aerovía, grupo in df_rutas.groupby(col_aerovia):
            puntos_aerovia = []
            for _, row in grupo.iterrows():
                lat, lon = None, None
                for c in grupo.columns:
                    if 'lat' in c.lower(): lat = row[c]
                    if 'lon' in c.lower() or 'lng' in c.lower(): lon = row[c]
                
                if pd.notnull(lat) and pd.notnull(lon):
                    puntos_aerovia.append((float(lat), float(lon)))
                else:
                    for c in grupo.columns:
                        val_str = str(row[c]).strip()
                        if val_str in dicc_wp:
                            puntos_aerovia.append(dicc_wp[val_str])
                            break
            
            if len(puntos_aerovia) > 1:
                estilo_base = {"color": color_base, "weight": 0.8, "opacity": 0.6}
                estilo_hover = {"color": "#39FF14", "weight": 2.5, "opacity": 1.0}
                
                folium.GeoJson(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[lon, lat] for lat, lon in puntos_aerovia]
                        },
                        "properties": {"name": str(nombre_aerovía)}
                    },
                    style_function=lambda x, estilo=estilo_base: estilo,
                    highlight_function=lambda x, estilo=estilo_hover: estilo,
                    tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=[f"{prefijo_tooltip}: "], sticky=True)
                ).add_to(capa)

# --- MAIN INTERFACE HEADER ---
col1, col2 = st.columns([5, 1])
with col1:
    st.title("🛰️ Operational Monitoring: Space Launches")
    st.markdown("Tactical visualization of trajectories and air traffic control (Time displayed in UTC format).")
with col2:
    if os.path.exists("Seneam_Logo.png"): st.image("Seneam_Logo.png", use_container_width=True)

# -------------------------------------------------------------------------
# BARRA SUPERIOR DE RELOJES EN TIEMPO REAL (COMPONENTE AISLADO SEGURO)
# -------------------------------------------------------------------------
components.html("""
<!DOCTYPE html>
<html>
<head>
<style>
    body {
        background-color: transparent;
        margin: 0;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    }
    .clock-container {
        display: flex;
        justify-content: flex-end;
        align-items: center;
        gap: 20px;
        background-color: #111827;
        padding: 10px 20px;
        border-radius: 8px;
        border: 1px solid #374151;
        box-sizing: border-box;
    }
    .clock-label-main {
        font-size: 1.15rem;
        font-weight: 600;
        color: #39FF14;
        letter-spacing: 0.5px;
        margin-right: auto;
        padding-left: 5px;
    }
    .clock-box {
        text-align: center;
        font-family: monospace;
    }
    .clock-title {
        font-size: 0.75rem;
        font-weight: bold;
        color: #9CA3AF;
        margin-bottom: 2px;
    }
    .clock-time-utc { font-size: 1.25rem; font-weight: bold; color: #39FF14; letter-spacing: 1px; }
    .clock-time-cdmx { font-size: 1.25rem; font-weight: bold; color: #00FFFF; letter-spacing: 1px; }
    .clock-time-mzt { font-size: 1.25rem; font-weight: bold; color: #FF00FF; letter-spacing: 1px; }
</style>
</head>
<body>
<div class="clock-container">
    <div class="clock-label-main">Current Time</div>
    <div class="clock-box">
        <div class="clock-title">UTC Time</div>
        <div id="utc_time" class="clock-time-utc">--:--:--</div>
    </div>
    <div class="clock-box" style="border-left: 1px solid #4B5563; padding-left: 20px;">
        <div class="clock-title">CDMX Time</div>
        <div id="cdmx_time" class="clock-time-cdmx">--:--:--</div>
    </div>
    <div class="clock-box" style="border-left: 1px solid #4B5563; padding-left: 20px;">
        <div class="clock-title">Mazatlan Time</div>
        <div id="mzt_time" class="clock-time-mzt">--:--:--</div>
    </div>
</div>

<script>
    function updateClocks() {
        const now = new Date();
        const options = { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };
        
        document.getElementById('utc_time').innerText = now.toLocaleTimeString('en-GB', { ...options, timeZone: 'UTC' });
        document.getElementById('cdmx_time').innerText = now.toLocaleTimeString('en-GB', { ...options, timeZone: 'America/Mexico_City' });
        document.getElementById('mzt_time').innerText = now.toLocaleTimeString('en-GB', { ...options, timeZone: 'America/Mazatlan' });
    }
    setInterval(updateClocks, 1000);
    updateClocks();
</script>
</body>
</html>
""", height=70)

operaciones = [
    "SpaceX Starship Super Heavy Flight-15: Launch Nov 13th, 2026 - Reentry Nov 14th",
    "SpaceX Starship Super Heavy Flight-14 Sept 28th, 2026", 
    "Upcoming launches..."
]
operacion = st.selectbox("Select the Space Launch to visualize:", operaciones)

if operacion == "Upcoming launches...":
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("""<div style="text-align: center; padding: 40px; background-color: #111827; border-radius: 15px; border: 1px solid #374151;"><h1 style="color: #39FF14; font-size: 2.8rem; margin-bottom: 20px;">🚀 SpaceX Starship Super Heavy Flight-16</h1><h2 style="color: #FFFFFF; font-size: 2rem; font-weight: 400; margin-bottom: 30px;">Upcoming Launch: TBD</h2><p style="color: #9CA3AF; font-size: 1.1rem; margin-bottom: 40px;">Strategic coordination and air traffic flow management (ATFM) for upcoming orbital flight tests.</p><a href="https://www.spacex.com/content/starship-flight-tests" target="_blank" style="background-color: #2563EB; color: white; padding: 15px 30px; border-radius: 8px; text-decoration: none; font-size: 1.2rem; font-weight: bold;">View Official SpaceX Flight Test Portal ↗</a></div>""", unsafe_allow_html=True)
    st.stop()

# --- CARGA DINÁMICA DE DATOS CON CACHÉ ---
df_waypoints, dicc_waypoints, df_riesgo, dict_espacio, df_vuelos, df_timeline, df_rnav, df_ats_hi, df_ats_low = cargar_bases_datos(operacion)

st.sidebar.title("🎛️ Map Control Panel")
st.sidebar.markdown("### Airspace Layers")
mostrar_firs = st.sidebar.checkbox("Mexico FIR, Mazatlan Oceanic FIR", value=True)
mostrar_acc_mid = st.sidebar.checkbox("Merida Control Center (MMID ACC)", value=False)
mostrar_acc_mty = st.sidebar.checkbox("Monterrey Control Center (MMTY ACC)", value=False)
mostrar_acc_mex = st.sidebar.checkbox("Mexico Control Center (MMEX ACC)", value=False)
mostrar_acc_mzt = st.sidebar.checkbox("Mazatlan Control Center (MMZT ACC)", value=False)

st.sidebar.markdown("### Space Launch Hazard Areas")
mostrar_tfr = st.sidebar.checkbox("TFR: Temporary Flight Restriction", value=True)
mostrar_dra = st.sidebar.checkbox("DRA-1 Area", value=True)
mostrar_aha = st.sidebar.checkbox("Launch Hazard Areas (AHA-A3 & AHA-B1)", value=True)

if "Flight-15" in operacion:
    mostrar_aha_reentry = st.sidebar.checkbox("Reentry Hazard Areas (AHA-C2, AHA-C3 & AHA-C4)", value=True)
else:
    mostrar_aha_reentry = False

mostrar_10_7 = st.sidebar.checkbox("10^-7 Area MMFR", value=True)

st.sidebar.markdown("### Flight Data & Navigation")
mostrar_rnav = st.sidebar.checkbox("RNAV Routes", value=False)
mostrar_ats_hi = st.sidebar.checkbox("ATS Routes (HI)", value=False)
mostrar_ats_low = st.sidebar.checkbox("ATS Routes (LOW)", value=False)
mostrar_rutas = st.sidebar.checkbox("Historical Flight Trajectories", value=False)
mostrar_vors = st.sidebar.checkbox("Show VORs / Navaids", value=True)
mostrar_waypoints = st.sidebar.checkbox("Show Waypoints (Fixes)", value=False)

if df_timeline is not None and not df_timeline.empty and 'hora_utc' in df_timeline.columns:
    eventos_html = ""
    for _, fila in df_timeline.iterrows():
        if 'evento' in df_timeline.columns and pd.notnull(fila['hora_utc']):
            eventos_html += f"<li><b>{fila['hora_utc'].strftime('%Y-%m-%d %H:%M:%S')}</b> - {fila['evento']}</li>"

    timeline_countdown_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        body {{
            background-color: transparent;
            margin: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            color: #E5E7EB;
        }}
        .tc-container {{
            display: flex;
            gap: 20px;
            background-color: #1F2937;
            padding: 15px;
            border-radius: 10px;
            border: 1px solid #374151;
            box-sizing: border-box;
            align-items: stretch;
        }}
        .timeline-box {{
            flex: 1;
            overflow-y: auto;
            max-height: 180px;
        }}
        .timeline-box h4 {{
            color: #39FF14;
            margin-top: 0;
            margin-bottom: 10px;
            font-size: 1.05rem;
        }}
        .timeline-box ul {{
            margin: 0;
            padding-left: 20px;
            font-size: 0.9rem;
        }}
        .countdowns-column {{
            width: 360px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            justify-content: space-between;
        }}
        .countdown-card {{
            background-color: #111827;
            border: 1px solid #374151;
            border-radius: 8px;
            padding: 10px 14px;
            text-align: center;
            font-family: monospace;
        }}
        .countdown-title {{
            font-size: 0.75rem;
            font-weight: bold;
            color: #9CA3AF;
            margin-bottom: 4px;
        }}
        .countdown-timer {{
            font-size: 1.15rem;
            font-weight: bold;
            color: #39FF14;
            letter-spacing: 0.5px;
        }}
    </style>
    </head>
    <body>
    <div class="tc-container">
        <div class="timeline-box">
            <h4>Critical Timeline Events (UTC)</h4>
            <ul>
                {eventos_html}
            </ul>
        </div>
        <div class="countdowns-column">
            <div class="countdown-card">
                <div class="countdown-title">Time to Launch (T-0)</div>
                <div id="countdown_launch" class="countdown-timer">--d --h --m --s</div>
            </div>
            <div class="countdown-card">
                <div class="countdown-title">Time to Reentry (Return to Launch Site)</div>
                <div id="countdown_reentry" class="countdown-timer">--d --h --m --s</div>
            </div>
        </div>
    </div>

    <script>
        const launchDate = new Date("2026-11-13T22:45:00Z").getTime();
        const reentryDate = new Date("2026-11-14T20:56:00Z").getTime();

        function updateCountdowns() {{
            const now = new Date().getTime();

            // Launch Countdown
            const diffLaunch = launchDate - now;
            document.getElementById('countdown_launch').innerText = formatTimeDiff(diffLaunch);

            // Reentry Countdown
            const diffReentry = reentryDate - now;
            document.getElementById('countdown_reentry').innerText = formatTimeDiff(diffReentry);
        }}

        function formatTimeDiff(diff) {{
            if (diff <= 0) {{
                return "00d 00h 00m 00s (T+)";
            }}
            const days = Math.floor(diff / (1000 * 60 * 60 * 24));
            const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
            const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
            const seconds = Math.floor((diff % (1000 * 60)) / 1000);

            return String(days).padStart(2, '0') + "d " +
                   String(hours).padStart(2, '0') + "h " +
                   String(minutes).padStart(2, '0') + "m " +
                   String(seconds).padStart(2, '0') + "s";
        }}

        setInterval(updateCountdowns, 1000);
        updateCountdowns();
    </script>
    </body>
    </html>
    """

    components.html(timeline_countdown_html, height=210)


m = folium.Map(location=
