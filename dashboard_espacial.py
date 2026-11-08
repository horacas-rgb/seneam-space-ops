import streamlit as st
import folium
from streamlit_folium import st_folium
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

@st.cache_data
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

    # B. Aerovías
    try:
        df_aerovias = pd.read_excel("Coordenadas_Waypoints_ENR_3.3.xlsx", sheet_name="Aerovias_Waypoints")
        df_aerovias.columns = df_aerovias.columns.str.strip()
    except Exception:
        df_aerovias = pd.DataFrame()

    # Diccionario Oficial de VORs en México (Actualizado)
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
    
    # B. Hazard Areas
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
            
            df_areas = pd.concat([df_areas, df_c2, df_c3], ignore_index=True)
        except Exception:
            pass
    
    # C. Espacio Aéreo SENEAM
    xls_espacio = pd.ExcelFile("Coordenadas_Espacio_Aereo_SENEAM.xlsx")
    dict_espacio = {}
    for sheet in xls_espacio.sheet_names:
        if sheet != "UTA México":
            df_sector = pd.read_excel(xls_espacio, sheet_name=sheet)
            df_sector.columns = df_sector.columns.str.strip()
            dict_espacio[sheet] = df_sector.dropna(subset=['Latitud (Decimal)', 'Longitud (Decimal)'])
        
    # D. Vuelos y Línea de Tiempo
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
    
    return df_wp, dicc_wp, df_areas, dict_espacio, df_vuelos, df_timeline, df_aerovias

def decodificar_coordenada_ruta(string_punto):
    match = re.match(r'^(\d{2})(\d{2})[Nn](\d{3})(\d{2})[Ww]$', str(string_punto).strip())
    if match:
        return (int(match.group(1)) + int(match.group(2)) / 60.0, 
                -(int(match.group(3)) + int(match.group(4)) / 60.0))
    return None

# --- MAIN INTERFACE HEADER ---
col1, col2 = st.columns([5, 1])
with col1:
    st.title("🛰️ Operational Monitoring: Space Launches")
    st.markdown("Tactical visualization of trajectories and air traffic control (Time displayed in UTC format).")
with col2:
    if os.path.exists("Seneam_Logo.png"): st.image("Seneam_Logo.png", use_container_width=True)

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

# --- CARGA DINÁMICA DE DATOS ---
df_waypoints, dicc_waypoints, df_riesgo, dict_espacio, df_vuelos, df_timeline, df_aerovias = cargar_bases_datos(operacion)

st.sidebar.title("🎛️ Map Control Panel")
st.sidebar.markdown("### Capas de Espacio Aéreo")
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
    mostrar_aha_reentry = st.sidebar.checkbox("Reentry Hazard Areas (AHA-C2 & AHA-C3)", value=True)
else:
    mostrar_aha_reentry = False

mostrar_10_7 = st.sidebar.checkbox("10^-7 Area MMFR", value=True)

st.sidebar.markdown("### Flight Data & Navigation")
mostrar_aerovias = st.sidebar.checkbox("Airways", value=False)
mostrar_rutas = st.sidebar.checkbox("Historical Flight Trajectories", value=False)
mostrar_vors = st.sidebar.checkbox("Mostrar VORs / Radioayudas", value=True)
mostrar_waypoints = st.sidebar.checkbox("Mostrar Waypoints (Fijos)", value=False)

if df_timeline is not None and not df_timeline.empty and 'hora_utc' in df_timeline.columns:
    st.markdown("""<div style="background-color: #1F2937; padding: 15px; border-radius: 10px; border: 1px solid #374151; margin-bottom: 20px;"><h4 style="color: #39FF14; margin-top: 0;">⏱️ Critical Timeline Events (UTC)</h4><ul style="color: #E5E7EB; font-size: 0.95rem; margin-bottom: 0;">""", unsafe_allow_html=True)
    for _, fila in df_timeline.iterrows():
        if 'evento' in df_timeline.columns and pd.notnull(fila['hora_utc']):
            st.markdown(f"<li><b>{fila['hora_utc'].strftime('%Y-%m-%d %H:%M:%S')}</b> - {fila['evento']}</li>", unsafe_allow_html=True)
    st.markdown("</ul></div>", unsafe_allow_html=True)

m = folium.Map(location=[24.5, -93.0], zoom_start=5, tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", attr="Tiles &copy; Esri")

# -------------------------------------------------------------------------
# FUSIÓN GEOGRÁFICA (LINESTRING EXACTO POR VECTORES)
# -------------------------------------------------------------------------
url_geojson = "https://raw.githubusercontent.com/johan/world.geo.json/master/countries/MEX.geo.json"
dict_espacio_procesado = {}

try:
    mexico_frontera = requests.get(url_geojson).json()
    coords_fisicas = []
    for feature in mexico_frontera['features']:
        geom = feature['geometry']
        if geom['type'] == 'MultiPolygon':
            coords_fisicas = max(geom['coordinates'], key=lambda poly: len(poly[0]))[0]
        elif geom['type'] == 'Polygon':
            coords_fisicas = geom['coordinates'][0]

    def distance_geo(p1, p2): return ((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)**0.5
    def find_closest_index(lon, lat, coords): return min(range(len(coords)), key=lambda i: distance_geo(coords[i], [lon, lat]))
    def get_path_length(indices, coords): return sum(distance_geo(coords[indices[i]], coords[indices[i+1]]) for i in range(len(indices)-1))

    def extract_line_string(idx_start, idx_end, coords):
        n = len(coords)
        sf = []; c = idx_start
        while True:
            sf.append(c)
            if c == idx_end or len(sf) > n: break
            c = (c + 1) % n
        sb = []; c = idx_start
        while True:
            sb.append(c)
            if c == idx_end or len(sb) > n: break
            c = (c - 1) % n
        return [coords[i] for i in (sf if get_path_length(sf, coords) < get_path_length(sb, coords) else sb)]

    idx_tj = find_closest_index(-117.12, 32.53, coords_fisicas)
    idx_mat = find_closest_index(-97.14, 25.95, coords_fisicas)
    usa_line = extract_line_string(idx_tj, idx_mat, coords_fisicas)

    idx_tap = find_closest_index(-92.21, 14.53, coords_fisicas)
    idx_xcalak = find_closest_index(-87.75, 18.15, coords_fisicas)
    south_line = extract_line_string(idx_tap, idx_xcalak, coords_fisicas)

    def is_on_line(lon, lat, line_coords, threshold=0.8):
        if not line_coords: return False
        return min(distance_geo([lon, lat], p) for p in line_coords) < threshold

    def get_subline(lon1, lat1, lon2, lat2, line_coords):
        i1, i2 = find_closest_index(lon1, lat1, line_coords), find_closest_index(lon2, lat2, line_coords)
        if i1 <= i2: return line_coords[i1:i2+1]
        else: return line_coords[i1:i2-1:-1] if i2 > 0 else line_coords[i1::-1]

    for nombre_hoja, df_sheet in dict_espacio.items():
        dict_espacio_procesado[nombre_hoja] = {}
        for sector_name, df_subsector in df_sheet.groupby('Área / Sector'):
            sector_coords = df_subsector[['Latitud (Decimal)', 'Longitud (Decimal)']].to_dict('records')
            new_coords = []
            num_pts = len(sector_coords)
            
            for i in range(num_pts):
                lat1, lon1 = sector_coords[i]['Latitud (Decimal)'], sector_coords[i]['Longitud (Decimal)']
                lat2, lon2 = sector_coords[(i + 1) % num_pts]['Latitud (Decimal)'], sector_coords[(i + 1) % num_pts]['Longitud (Decimal)']
                new_coords.append([lat1, lon1])
                
                if is_on_line(lon1, lat1, usa_line) and is_on_line(lon2, lat2, usa_line):
                    for p in get_subline(lon1, lat1, lon2, lat2, usa_line)[1:-1]: new_coords.append([p[1], p[0]])
                elif is_on_line(lon1, lat1, south_line) and is_on_line(lon2, lat2, south_line):
                    for p in get_subline(lon1, lat1, lon2, lat2, south_line)[1:-1]: new_coords.append([p[1], p[0]])

            dict_espacio_procesado[nombre_hoja][sector_name] = pd.DataFrame(new_coords, columns=['Latitud (Decimal)', 'Longitud (Decimal)'])
except Exception as e:
    for nombre_hoja, df_sheet in dict_espacio.items():
        if 'Área / Sector' in df_sheet.columns:
            dict_espacio_procesado[nombre_hoja] = {s: d for s, d in df_sheet.groupby('Área / Sector')}
        else:
            dict_espacio_procesado[nombre_hoja] = {'Sector': df_sheet}

# LAYER 1: Airspace Boundaries
capa_espacio = folium.FeatureGroup(name="Airspace Boundaries")
for nombre_hoja, sectores in dict_espacio_procesado.items():
    is_fir = "FIR" in nombre_hoja
    if is_fir and not mostrar_firs: continue
    if "UTA" in nombre_hoja.upper(): continue
    if not is_fir:
        if "Mérida" in nombre_hoja and not mostrar_acc_mid: continue
        if "Monterrey" in nombre_hoja and not mostrar_acc_mty: continue
        if "México" in nombre_hoja and not mostrar_acc_mex: continue
        if "Mazatlán" in nombre_hoja and not mostrar_acc_mzt: continue
    
    if "MÉXICO" in nombre_hoja.upper() and not is_fir: color_sector = "#2ECC71"
    elif "OCEÁNICA" in nombre_hoja.upper() or "OCEANICA" in nombre_hoja.upper(): color_sector = "#FF5555"
    elif is_fir: color_sector = "#00FFFF"
    else: color_sector = "#00E5FF"
    
    for sector_name, df_sector in sectores.items():
        coords = list(zip(df_sector['Latitud (Decimal)'], df_sector['Longitud (Decimal)']))
        if len(coords) < 3: continue
            
        es_perimetro = "PERIMETRO" in str(sector_name).upper()
        folium.Polygon(
            locations=coords, color=color_sector, weight=2.5 if es_perimetro else 1.2, opacity=0.7, fill=True, 
            fill_opacity=0.03 if es_perimetro else (0.06 if "OCEÁNICA" in nombre_hoja.upper() else 0.08), 
            interactive=False
        ).add_to(capa_espacio)
        
        if not es_perimetro and not is_fir:
            match = re.search(r'SEC\s*\d+', str(sector_name).upper())
            etiqueta_sector = match.group(0) if match else sector_name
            
            if "MERIDA SEC 1" in str(sector_name).upper():
                cent_lat, cent_lon = 17.50, -93.50
            else:
                cent_lat, cent_lon = sum([c[0] for c in coords])/len(coords), sum([c[1] for c in coords])/len(coords)
            
            folium.map.Marker(
                [cent_lat, cent_lon],
                icon=folium.DivIcon(
                    icon_size=(60, 20), icon_anchor=(30, 10),
                    html=f'<div style="font-size: 8pt; color: #E0FFFF; font-weight: bold; text-align: center; text-shadow: 1px 1px 2px black;">{etiqueta_sector}</div>'
                )
            ).add_to(capa_espacio)
capa_espacio.add_to(m)

# LAYER 1.5: AIRWAYS (Aerovias_Waypoints)
capa_aerovias = folium.FeatureGroup(name="Airways", show=mostrar_aerovias)
if mostrar_aerovias and not df_aerovias.empty:
    df_aerovias.columns = df_aerovias.columns.str.strip()
    # Identificar posibles nombres de columnas para aerovía y waypoints/coordenadas
    col_aerovia = next((c for c in df_aerovias.columns if 'aerov' in c.lower() or 'route' in c.lower() or 'designador' in c.lower() or 'id' in c.lower()), df_aerovias.columns[0])
    
    # Agrupamos por aerovía si existe una columna identificadora, de lo contrario trazamos por pares o segmentos
    for nombre_aerovía, grupo in df_aerovias.groupby(col_aerovia):
        puntos_aerovia = []
        for _, row in grupo.iterrows():
            # Buscar lat/lon directamente en el dataframe o buscar en dicc_wp si hay nombres de puntos
            lat = None
            lon = None
            for c in grupo.columns:
                if 'lat' in c.lower(): lat = row[c]
                if 'lon' in c.lower() or 'lng' in c.lower(): lon = row[c]
            
            if pd.notnull(lat) and pd.notnull(lon):
                puntos_aerovia.append((float(lat), float(lon)))
            else:
                # Buscar por nombre de waypoint en las columnas de texto
                for c in grupo.columns:
                    val_str = str(row[c]).strip()
                    if val_str in dicc_waypoints:
                        puntos_aerovia.append(dicc_waypoints[val_str])
                        break
        
        if len(puntos_aerovia) > 1:
            folium.PolyLine(
                locations=puntos_aerovia,
                color="#00FFFF",
                weight=0.8,
                opacity=0.6,
                tooltip=f"Airway: {nombre_aerovía}"
            ).add_to(capa_aerovias)
capa_aerovias.add_to(m)

# LAYER 2: VORs y Waypoints Separados
capa_navaids = folium.FeatureGroup(name="Waypoints & Radioayudas")

if not df_waypoints.empty:
    for _, row in df_waypoints.iterrows():
        lat = row['Latitud (Decimal)']
        lon = row['Longitud (Decimal)']
        tipo = row['Tipo']
        designador = row['Codigo_Limpio']
        nombre_completo = row['Nombre del Punto / Waypoint']
        
        if tipo == 'VOR / Radioayuda' and mostrar_vors:
            folium.CircleMarker(
                location=[lat, lon], radius=3.5, color="#FFC107", weight=1.5,
                fill=True, fill_color="#FFC107", fill_opacity=0.9, 
                tooltip=f"VOR: {designador}"
            ).add_to(capa_navaids)
            
            folium.map.Marker(
                [lat, lon],
                icon=folium.DivIcon(
                    icon_size=(40, 15), icon_anchor=(20, -7),
                    html=f'<div style="font-size: 8pt; color: #FFC107; font-weight: bold; text-shadow: 1px 1px 2px black, -1px -1px 2px black, 0px 0px 4px rgba(0,0,0,0.8); text-align: center;">{designador}</div>'
                )
            ).add_to(capa_navaids)
            
        elif tipo == 'Waypoint' and mostrar_waypoints:
            folium.CircleMarker(
                location=[lat, lon], radius=2.0, color="#00FFFF", weight=1.0,
                fill=True, fill_color="#00FFFF", fill_opacity=0.6, 
                tooltip=f"Waypoint: {nombre_completo}"
            ).add_to(capa_navaids)

capa_navaids.add_to(m)

# --- VENTANAS DE TIEMPO DINÁMICAS (Lanzamiento y Reingreso) ---
if "Flight-15" in operacion:
    rango_launch = list(pd.date_range(start=pd.to_datetime("2026-11-13 20:45:00"), end=pd.to_datetime("2026-11-14 00:40:00"), freq='1min'))
    rango_reentry = list(pd.date_range(start=pd.to_datetime("2026-11-14 20:56:00"), end=pd.to_datetime("2026-11-15 00:14:00"), freq='1min'))
    t_liftoff = pd.to_datetime("2026-11-13 22:45:00")
    t_end_liftoff = pd.to_datetime("2026-11-13 23:00:00")
    rango_liftoff = list(pd.date_range(start=t_liftoff, end=t_end_liftoff, freq='1min'))
    banner_text = "🚀 STARSHIP FLIGHT-15 LIFT OFF"
else:
    rango_launch = list(pd.date_range(start=pd.to_datetime("2026-09-28 12:15:00"), end=pd.to_datetime("2026-09-28 12:58:00"), freq='1min'))
    rango_reentry = []
    t_liftoff = pd.to_datetime("2026-09-28 12:49:00")
    t_end_liftoff = pd.to_datetime("2026-09-28 12:58:00")
    rango_liftoff = list(pd.date_range(start=t_liftoff, end=t_end_liftoff, freq='1min'))
    banner_text = "🚀 STARSHIP FLIGHT-14 LIFT OFF"

# LAYER 3: Hazard Areas Animadas
features_geojson = []

def orden_capas(x):
    nombre = str(x[0]).upper()
    if "10^-7" in nombre or "10_7" in nombre: return 1
    if "AHA" in nombre: return 2
    if "DRA" in nombre: return 3
    return 4

capa_areas = folium.FeatureGroup(name="Space Hazard Areas")
for area, datos in sorted(df_riesgo.groupby('Área / Hazard Zone'), key=orden_capas):
    area_str = str(area).upper()
    
    if "C2" in area_str or "C3" in area_str:
        if not mostrar_aha_reentry: continue
        color, opacity_fill, label_name = "#D500F9", 0.45, "AHA-C2" if "C2" in area_str else "AHA-C3"
        tiempos_activos = rango_reentry
    elif "TFR" in area_str:
        if not mostrar_tfr: continue
        color, opacity_fill, label_name = "#90EE90", 0.35, "TFR"
        tiempos_activos = rango_launch + rango_reentry
    elif "DRA" in area_str:
        if not mostrar_dra: continue
        color, opacity_fill, label_name = "#FFB347", 0.35, "DRA-1"
        tiempos_activos = rango_launch
    elif "AHA" in area_str:
        if not mostrar_aha: continue
        color, opacity_fill, label_name = "#FF7F7F", 0.55, "AHA-A3" if "A3" in area_str else "AHA-B1"
        tiempos_activos = rango_launch
    elif "10^-7" in area_str or "10_7" in area_str:
        if not mostrar_10_7: continue
        color, opacity_fill, label_name = "#FFFFE0", 0.15, "10^-7"
        tiempos_activos = rango_launch
    else:
        color, opacity_fill, label_name = "#FFA500", 0.35, area
        tiempos_activos = rango_launch
        
    coords_estaticas = list(zip(datos['Latitud (Decimal)'], datos['Longitud (Decimal)']))
    lats = [c[0] for c in coords_estaticas]
    lons = [c[1] for c in coords_estaticas]
    cent_lat = sum(lats)/len(lats)
    cent_lon = sum(lons)/len(lons)
    
    if "10^-7" in label_name:
        cent_lat -= 0.6  
        
    folium.map.Marker(
        [cent_lat, cent_lon], 
        icon=folium.DivIcon(icon_size=(100,20), icon_anchor=(50,10), html=f'<div style="font-size: 10pt; color: white; font-weight: bold; text-shadow: 1px 1px 2px black; text-align: center;">{label_name}</div>')
    ).add_to(capa_areas)
    
    coords_lon_lat = [[lon, lat] for lat, lon in zip(datos['Latitud (Decimal)'], datos['Longitud (Decimal)'])]
    if coords_lon_lat[0] != coords_lon_lat[-1]: coords_lon_lat.append(coords_lon_lat[0])
    
    for t in tiempos_activos:
        features_geojson.append({
            "type": "Feature", "geometry": {"type": "Polygon", "coordinates": [coords_lon_lat]},
            "properties": {"times": [int((t + timedelta(hours=AJUSTE_UTC)).timestamp() * 1000)], "style": {"fillColor": color, "color": color, "weight": 2, "fillOpacity": opacity_fill, "opacity": 0.8}, "tooltip": f"ACTIVE: {label_name}"}
        })
capa_areas.add_to(m)

# LAYER 4: RUTAS DE VUELO Y POPUP DE AERONAVES
capa_rutas = folium.FeatureGroup(name="Static Trajectories", show=mostrar_rutas)
for _, vuelo in df_vuelos.iterrows():
    puntos_validos = []
    
    entry_pt = vuelo.get('entry_point')
    exit_pt = vuelo.get('exit_point')
    route_str = str(vuelo.get('route', ''))
    if pd.isnull(entry_pt) or pd.isnull(exit_pt): continue
    
    for p in [entry_pt] + route_str.split() + [exit_pt]:
        p_str = str(p).strip()
        if p_str in dicc_waypoints: puntos_validos.append(dicc_waypoints[p_str])
        else:
            coord = decodificar_coordenada_ruta(p_str)
            if coord: puntos_validos.append(coord)
            
    n_pts = len(puntos_validos)
    if n_pts > 1:
        folium.PolyLine(locations=[[lat, lon] for lat, lon in puntos_validos], color="#39FF14", weight=0.5, opacity=0.2, dash_array="4", tooltip=f"<b>Callsign:</b> {vuelo['callsign']} | <b>Route:</b> {vuelo['adep']}-{vuelo['ades']}").add_to(capa_rutas)
        t_inicio, t_fin = vuelo['entry_hour'], vuelo['exit_hour']
        if pd.isnull(t_inicio) or pd.isnull(t_fin): continue
        duracion_vuelo_mins = int((t_fin - t_inicio).total_seconds() / 60)
        if duracion_vuelo_mins <= 0: continue
            
        paso_tiempo = (t_fin - t_inicio) / (n_pts - 1)
        tiempos_nodos = [t_inicio + paso_tiempo * i for i in range(n_pts)]
        
        callsign = vuelo.get('callsign', 'N/A')
        tipo_aeronave = vuelo.get('aircraft_type', 'N/A')
        adep = vuelo.get('adep', 'N/A')
        ades = vuelo.get('ades', 'N/A')
        nivel_vuelo = vuelo.get('entry_level', vuelo.get('rfl', 'N/A'))
        if pd.notna(nivel_vuelo):
            nivel_str = f"FL{int(float(nivel_vuelo))}" if str(nivel_vuelo).replace('.','',1).isdigit() else str(nivel_vuelo)
        else:
            nivel_str = "N/A"
        ruta_completa = vuelo.get('route', 'Directo / No especificada')

        popup_html = f"""
        <div style="font-family: Arial, sans-serif; font-size: 11px; width: 220px; color: #333;">
            <div style="background-color: #00FFFF; padding: 5px; text-align: center; font-weight: bold; color: #0c2340; border-radius: 3px 3px 0 0;">
                ✈️ {callsign}
            </div>
            <table style="width: 100%; border-collapse: collapse; margin-top: 5px;">
                <tr><td><b>Tipo Aeronave:</b></td><td>{tipo_aeronave}</td></tr>
                <tr><td><b>ADEP - ADES:</b></td><td>{adep} - {ades}</td></tr>
                <tr><td><b>Nivel de Vuelo:</b></td><td>{nivel_str}</td></tr>
            </table>
            <div style="margin-top: 6px; padding-top: 4px; border-top: 1px solid #ccc; font-size: 10px; word-wrap: break-word;">
                <b>Ruta:</b> <span style="color: #05508a;">{ruta_completa}</span>
            </div>
        </div>
        """

        for m_offset in range(duracion_vuelo_mins + 1):
            t_current = t_inicio + timedelta(minutes=m_offset)
            for i in range(n_pts - 1):
                if tiempos_nodos[i] <= t_current <= tiempos_nodos[i+1]:
                    tA, tB = tiempos_nodos[i], tiempos_nodos[i+1]
                    lonA, latA = puntos_validos[i][1], puntos_validos[i][0]
                    lonB, latB = puntos_validos[i+1][1], puntos_validos[i+1][0]
                    if tB == tA:
                        lon_curr, lat_curr = lonA, latA
                    else:
                        fraction = (t_current - tA).total_seconds() / (tB - tA).total_seconds()
                        lon_curr, lat_curr = lonA + (lonB - lonA) * fraction, latA + (latB - latA) * fraction
                        
                    features_geojson.append({
                        "type": "Feature", "geometry": {"type": "Point", "coordinates": [lon_curr, lat_curr]},
                        "properties": {
                            "times": [int((t_current + timedelta(hours=AJUSTE_UTC)).timestamp() * 1000)], 
                            "icon": "circle", 
                            "iconstyle": {"fillColor": "#39FF14", "fillOpacity": 1.0, "stroke": "true", "color": "#FFFFFF", "weight": 1.5, "radius": 6}, 
                            "popup": popup_html
                        }
                    })
                    break
capa_rutas.add_to(m)

# LAYER 5: LANZAMIENTO EN BOCA CHICA
lat_boca_chica, lon_boca_chica = 25.996, -97.154
icon_url_banner = f"data:image/svg+xml;base64,{base64.b64encode(f'<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"320\" height=\"45\"><rect width=\"320\" height=\"45\" rx=\"6\" fill=\"#111827\" stroke=\"#39FF14\" stroke-width=\"2\"/><text x=\"50%\" y=\"54%\" dominant-baseline=\"middle\" text-anchor=\"middle\" font-family=\"Arial, sans-serif\" font-size=\"15px\" font-weight=\"900\" fill=\"#FFFF00\">{banner_text}</text></svg>'.encode('utf-8')).decode('utf-8')}"

for t in rango_liftoff:
    t_shift = t + timedelta(hours=AJUSTE_UTC)
    features_geojson.append({
        "type": "Feature", "geometry": {"type": "Point", "coordinates": [lon_boca_chica, lat_boca_chica]},
        "properties": {"times": [int(t_shift.timestamp() * 1000)], "icon": "circle", "iconstyle": {"fillColor": "#FF4500", "fillOpacity": 1.0, "stroke": "true", "color": "#FFFFFF", "weight": 2.5, "radius": 10}, "popup": f"<b>Starbase Boca Chica, TX</b><br>{banner_text} Launch Site"}
    })
    features_geojson.append({
        "type": "Feature", "geometry": {"type": "Point", "coordinates": [lon_boca_chica, lat_boca_chica + 0.35]},
        "properties": {"times": [int(t_shift.timestamp() * 1000)], "icon": "marker", "iconstyle": {"iconUrl": icon_url_banner, "iconSize": [320, 45], "iconAnchor": [160, 22]}}
    })

TimestampedGeoJson(
    {"type": "FeatureCollection", "features": features_geojson},
    period="PT1M", duration="PT1M", add_last_point=False, auto_play=True,
    loop=True, max_speed=5, loop_button=True, time_slider_drag_update=True, transition_time=333,
).add_to(m)

folium.LayerControl().add_to(m)
st_folium(m, width=1400, height=750, returned_objects=[])
