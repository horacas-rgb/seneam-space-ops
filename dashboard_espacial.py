import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import TimestampedGeoJson
import pandas as pd
import re
import os
from datetime import timedelta

# 1. Executive Page Configuration
st.set_page_config(page_title="Space Operations - SENEAM", layout="wide")

# Offset to force Leaflet (JavaScript) to render UTC time in local browsers (Mérida is UTC-6)
AJUSTE_UTC = 6 
FECHA_MISION = "2026-09-28"

@st.cache_data
def cargar_bases_datos():
    # A. Waypoints
    df_wp = pd.read_excel("Coordenadas_Waypoints_ENR_3.3.xlsx", sheet_name="Waypoints_Unicos", header=3)
    df_wp.columns = df_wp.columns.str.strip()
    df_wp = df_wp.dropna(subset=['Latitud (Decimal)', 'Longitud (Decimal)'])
    dicc_wp = pd.Series(
        zip(df_wp['Latitud (Decimal)'], df_wp['Longitud (Decimal)']), 
        index=df_wp['Nombre del Punto / Waypoint'].astype(str).str.strip()
    ).to_dict()
    
    # B. Hazard Areas
    df_areas = pd.read_excel("Coordenadas_Starship_FLT14.xlsx", sheet_name="Consolidado_Areas", header=3)
    df_areas.columns = df_areas.columns.str.strip()
    df_areas = df_areas.dropna(subset=['Latitud (Decimal)', 'Longitud (Decimal)'])
    
    # C. Airspace and Sectors
    xls_espacio = pd.ExcelFile("Coordenadas_Espacio_Aereo_SENEAM.xlsx")
    dict_espacio = {}
    for sheet in xls_espacio.sheet_names:
        if sheet != "UTA México":
            df_sector = pd.read_excel(xls_espacio, sheet_name=sheet)
            df_sector.columns = df_sector.columns.str.strip()
            dict_espacio[sheet] = df_sector.dropna(subset=['Latitud (Decimal)', 'Longitud (Decimal)'])
        
    # D. Flights & Timeline
    xls_vuelos = pd.ExcelFile("ROCKET_28_SEPT_2026.xlsx")
    df_vuelos = pd.read_excel(xls_vuelos, sheet_name="ROCKET_28_SEPT_2026")
    df_vuelos.columns = df_vuelos.columns.str.strip()
    df_vuelos['entry_hour'] = pd.to_datetime(df_vuelos['entry_hour'])
    df_vuelos['exit_hour'] = pd.to_datetime(df_vuelos['exit_hour'])
    
    # Leer eventos del Timeline con extracción limpia de horas
    df_timeline = None
    if "Timeline" in xls_vuelos.sheet_names:
        df_timeline = pd.read_excel(xls_vuelos, sheet_name="Timeline")
        df_timeline.columns = df_timeline.columns.str.strip().str.lower().str.replace(' ', '_')
        
        if 'hora_utc' in df_timeline.columns:
            def normalizar_hora(val):
                if pd.isnull(val): return None
                match = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?)', str(val))
                if match:
                    hora_limpia = match.group(1)
                    return pd.to_datetime(f"{FECHA_MISION} {hora_limpia}")
                return None
            
            df_timeline['hora_utc'] = df_timeline['hora_utc'].apply(normalizar_hora)
    
    return df_wp, dicc_wp, df_areas, dict_espacio, df_vuelos, df_timeline

def decodificar_coordenada_ruta(string_punto):
    match = re.match(r'^(\d{2})(\d{2})[Nn](\d{3})(\d{2})[Ww]$', str(string_punto).strip())
    if match:
        lat = int(match.group(1)) + int(match.group(2)) / 60.0
        lon = -(int(match.group(3)) + int(match.group(4)) / 60.0)
        return lat, lon
    return None

df_waypoints, dicc_waypoints, df_riesgo, dict_espacio, df_vuelos, df_timeline = cargar_bases_datos()

# --- MAIN INTERFACE HEADER ---
col1, col2 = st.columns([5, 1])
with col1:
    st.title("🛰️ Operational Monitoring: Space Launches")
    st.markdown("Tactical visualization of trajectories and air traffic control (Time displayed in UTC format).")
with col2:
    if os.path.exists("Seneam_Logo.png"):
        st.image("Seneam_Logo.png", use_container_width=True)

operacion = st.selectbox(
    "Select the Space Launch to visualize:",
    ["SpaceX Starship Super Heavy Flight-14 Sept 28th, 2026", "Upcoming launches..."]
)

if operacion == "Upcoming launches...":
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown(
        """
        <div style="text-align: center; padding: 40px; background-color: #111827; border-radius: 15px; border: 1px solid #374151;">
            <h1 style="color: #39FF14; font-size: 2.8rem; margin-bottom: 20px;">🚀 SpaceX Starship Super Heavy Flight-15</h1>
            <h2 style="color: #FFFFFF; font-size: 2rem; font-weight: 400; margin-bottom: 30px;">Upcoming Launch: November 12th, 2026</h2>
            <p style="color: #9CA3AF; font-size: 1.1rem; margin-bottom: 40px;">
                Strategic coordination and air traffic flow management (ATFM) for upcoming orbital flight tests.
            </p>
            <a href="https://www.spacex.com/content/starship-flight-tests/flight-14" target="_blank" 
               style="background-color: #2563EB; color: white; padding: 15px 30px; border-radius: 8px; text-decoration: none; font-size: 1.2rem; font-weight: bold;">
               View Official SpaceX Flight Test Portal ↗
            </a>
        </div>
        """,
        unsafe_allow_html=True
    )

elif operacion == "SpaceX Starship Super Heavy Flight-14 Sept 28th, 2026":
    
    # --- SIDEBAR CONTROL PANEL (Default Settings) ---
    st.sidebar.title("🎛️ Map Control Panel")
    st.sidebar.markdown("Enable or disable layers to visualize:")

    st.sidebar.markdown("**Airspace & Control Centers**")
    mostrar_firs = st.sidebar.checkbox("Mexico FIR, Mazatlan Oceanic FIR", value=True)
    mostrar_acc_mid = st.sidebar.checkbox("Merida Control Center (MMID ACC)", value=False)
    mostrar_acc_mty = st.sidebar.checkbox("Monterrey Control Center (MMTY ACC)", value=False)
    mostrar_acc_mex = st.sidebar.checkbox("Mexico Control Center (MMEX ACC)", value=False)
    mostrar_acc_mzt = st.sidebar.checkbox("Mazatlan Control Center (MMZT ACC)", value=False)

    st.sidebar.markdown("**Space Launch Hazard Areas**")
    mostrar_tfr = st.sidebar.checkbox("TFR: Temporary Flight Restriction", value=True)
    mostrar_dra = st.sidebar.checkbox("DRA-1 Area", value=True)
    mostrar_aha = st.sidebar.checkbox("Launch Hazard Areas (AHA-A3 & AHA-B1)", value=True)
    mostrar_10_7 = st.sidebar.checkbox("10^-7 Area MMFR", value=True)

    st.sidebar.markdown("**Flight Data**")
    mostrar_rutas = st.sidebar.checkbox("Historical Flight Trajectories", value=False)
    mostrar_waypoints = st.sidebar.checkbox("Waypoints and VORs", value=True)

    # Cuadro informativo de eventos (Timeline)
    if df_timeline is not None and not df_timeline.empty and 'hora_utc' in df_timeline.columns:
        st.markdown(
            """
            <div style="background-color: #1F2937; padding: 15px; border-radius: 10px; border: 1px solid #374151; margin-bottom: 20px;">
                <h4 style="color: #39FF14; margin-top: 0;">⏱️ Critical Timeline Events (UTC)</h4>
                <ul style="color: #E5E7EB; font-size: 0.95rem; margin-bottom: 0;">
            """, unsafe_allow_html=True
        )
        for _, fila in df_timeline.iterrows():
            if 'evento' in df_timeline.columns and pd.notnull(fila['hora_utc']):
                st.markdown(f"<li><b>{fila['hora_utc'].strftime('%H:%M:%S')}</b> - {fila['evento']}</li>", unsafe_allow_html=True)
        st.markdown("</ul></div>", unsafe_allow_html=True)
    
    esritiles = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
    esriattr = "Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ"
    m = folium.Map(location=[24.5, -93.0], zoom_start=5, tiles=esritiles, attr=esriattr)
    
    # LAYER 1: Airspace (FIRs & ACCs)
    capa_espacio = folium.FeatureGroup(name="Airspace Boundaries")
    for nombre_hoja, df_sector in dict_espacio.items():
        is_fir = "FIR" in nombre_hoja
        if is_fir and not mostrar_firs: continue
        if not is_fir:
            if "Mérida" in nombre_hoja and not mostrar_acc_mid: continue
            if "Monterrey" in nombre_hoja and not mostrar_acc_mty: continue
            if "México" in nombre_hoja and not mostrar_acc_mex: continue
            if "Mazatlán" in nombre_hoja and not mostrar_acc_mzt: continue
        
        coords = list(zip(df_sector['Latitud (Decimal)'], df_sector['Longitud (Decimal)']))
        color = "#00FFFF" if is_fir else "#008B8B"
        weight = 2.5 if is_fir else 2.0
        opacity = 0.8 if is_fir else 0.5
        
        folium.Polygon(
            locations=coords, color=color, weight=weight, opacity=opacity, fill=True, fill_opacity=0.08, 
            tooltip=f"Sector: {nombre_hoja}"
        ).add_to(capa_espacio)
    capa_espacio.add_to(m)

    # LAYER 2: Waypoints
    if mostrar_waypoints:
        capa_waypoints = folium.FeatureGroup(name="Waypoints and VORs")
        for _, row in df_waypoints.iterrows():
            folium.CircleMarker(
                location=[row['Latitud (Decimal)'], row['Longitud (Decimal)']],
                radius=1.5, color='#00FFFF', fill=True, tooltip=row['Nombre del Punto / Waypoint']
            ).add_to(capa_waypoints)
        capa_waypoints.add_to(m)
    
    # LAYER 3: Hazard Areas (Temporal y Estática con Z-Index Order)
    features_geojson = []
    
    t_activacion_areas = pd.to_datetime(f"{FECHA_MISION} 12:15:00")
    t_desactivacion_areas = pd.to_datetime(f"{FECHA_MISION} 12:58:00")
    rango_tiempo_areas = pd.date_range(start=t_activacion_areas, end=t_desactivacion_areas, freq='1min')

    def orden_capas(x):
        nombre = str(x[0]).upper()
        if "10^-7" in nombre or "10_7" in nombre: return 1
        if "AHA" in nombre: return 2
        if "DRA" in nombre: return 3
        return 4

    capa_areas = folium.FeatureGroup(name="Space Hazard Areas")
    
    for area, datos in sorted(df_riesgo.groupby('Área / Hazard Zone'), key=orden_capas):
        area_str = str(area).upper()
        
        if "TFR" in area_str:
            if not mostrar_tfr: continue
            color = "#90EE90"
            label_name = "TFR"
            
            coords = list(zip(datos['Latitud (Decimal)'], datos['Longitud (Decimal)']))
            folium.Polygon(locations=coords, color=color, fill=True, fill_opacity=0.35, tooltip=f"Restriction: {area}").add_to(capa_areas)
            
            lats = [c[0] for c in coords]
            lons = [c[1] for c in coords]
            centroide = [sum(lats)/len(lats), sum(lons)/len(lons)]
            
            folium.map.Marker(
                centroide,
                icon=folium.DivIcon(icon_size=(100,20), icon_anchor=(50,10), html=f'<div style="font-size: 10pt; color: white; font-weight: bold; text-shadow: 1px 1px 2px black; text-align: center;">{label_name}</div>')
            ).add_to(capa_areas)
            
        else:
            if "DRA" in area_str:
                if not mostrar_dra: continue
                color = "#FFB347"
                opacity_fill = 0.35
                label_name = "DRA-1"
            elif "AHA" in area_str:
                if not mostrar_aha: continue
                color = "#FF7F7F"
                opacity_fill = 0.55
                label_name = "AHA-A3" if "A3" in area_str else "AHA-B1"
            elif "10^-7" in area_str or "10_7" in area_str:
                if not mostrar_10_7: continue
                color = "#FFFFE0"
                opacity_fill = 0.15
                label_name = "10^-7"
            else:
                color = "#FFA500"
                opacity_fill = 0.35
                label_name = area
                
            coords_estaticas = list(zip(datos['Latitud (Decimal)'], datos['Longitud (Decimal)']))
            lats = [c[0] for c in coords_estaticas]
            lons = [c[1] for c in coords_estaticas]
            centroide = [sum(lats)/len(lats), sum(lons)/len(lons)]
            
            folium.map.Marker(
                centroide,
                icon=folium.DivIcon(icon_size=(100,20), icon_anchor=(50,10), html=f'<div style="font-size: 10pt; color: white; font-weight: bold; text-shadow: 1px 1px 2px black; text-align: center;">{label_name}</div>')
            ).add_to(capa_areas)
            
            coords_lon_lat = [[lon, lat] for lat, lon in zip(datos['Latitud (Decimal)'], datos['Longitud (Decimal)'])]
            if coords_lon_lat[0] != coords_lon_lat[-1]:
                coords_lon_lat.append(coords_lon_lat[0])
                
            for t in rango_tiempo_areas:
                t_shift = t + timedelta(hours=AJUSTE_UTC)
                features_geojson.append({
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [coords_lon_lat]},
                    "properties": {
                        "times": [int(t_shift.timestamp() * 1000)],
                        "style": {"fillColor": color, "color": color, "weight": 2, "fillOpacity": opacity_fill, "opacity": 0.8},
                        "tooltip": f"ACTIVE: {label_name}"
                    }
                })
    capa_areas.add_to(m)
    
    # 4. RUTAS DE VUELO: Interpolación minuto a minuto (Punto en movimiento fluido)
    capa_rutas = folium.FeatureGroup(name="Static Trajectories", show=mostrar_rutas)
        
    for _, vuelo in df_vuelos.iterrows():
        nodos_ruta = str(vuelo['route']).split()
        puntos_validos = []
        
        secuencia = [vuelo['entry_point']] + nodos_ruta + [vuelo['exit_point']]
        for p in secuencia:
            p_str = str(p).strip()
            if p_str in dicc_waypoints:
                puntos_validos.append(dicc_waypoints[p_str])
            else:
                coord = decodificar_coordenada_ruta(p_str)
                if coord: 
                    puntos_validos.append(coord)
                
        n_pts = len(puntos_validos)
        if n_pts > 1:
            coords_estaticas = [[lat, lon] for lat, lon in puntos_validos]
            folium.PolyLine(
                locations=coords_estaticas, color="#39FF14", weight=0.5, opacity=0.2, dash_array="4",
                tooltip=f"<b>Callsign:</b> {vuelo['callsign']} | <b>Route:</b> {vuelo['adep']}-{vuelo['ades']}"
            ).add_to(capa_rutas)
            
            t_inicio = vuelo['entry_hour']
            t_fin = vuelo['exit_hour']
            
            if pd.isnull(t_inicio) or pd.isnull(t_fin):
                continue
                
            duracion_vuelo_mins = int((t_fin - t_inicio).total_seconds() / 60)
            if duracion_vuelo_mins <= 0:
                continue
                
            paso_tiempo = (t_fin - t_inicio) / (n_pts - 1)
            tiempos_nodos = [t_inicio + paso_tiempo * i for i in range(n_pts)]
            
            for m_offset in range(duracion_vuelo_mins + 1):
                t_current = t_inicio + timedelta(minutes=m_offset)
                
                for i in range(n_pts - 1):
                    if tiempos_nodos[i] <= t_current <= tiempos_nodos[i+1]:
                        tA = tiempos_nodos[i]
                        tB = tiempos_nodos[i+1]
                        lonA, latA = puntos_validos[i][1], puntos_validos[i][0]
                        lonB, latB = puntos_validos[i+1][1], puntos_validos[i+1][0]
                        
                        if tB == tA:
                            lon_curr, lat_curr = lonA, latA
                        else:
                            fraction = (t_current - tA).total_seconds() / (tB - tA).total_seconds()
                            lon_curr = lonA + (lonB - lonA) * fraction
                            lat_curr = latA + (latB - latA) * fraction
                            
                        t_shift = t_current + timedelta(hours=AJUSTE_UTC)
                        etiqueta = f"<b>Callsign:</b> {vuelo['callsign']}<br><b>ADEP-ADES:</b> {vuelo['adep']} - {vuelo['ades']}"
                        
                        features_geojson.append({
                            "type": "Feature",
                            "geometry": {"type": "Point", "coordinates": [lon_curr, lat_curr]},
                            "properties": {
                                "times": [int(t_shift.timestamp() * 1000)],
                                "icon": "circle",
                                "iconstyle": {
                                    "fillColor": "#39FF14", "fillOpacity": 1.0, "stroke": "true",
                                    "color": "#FFFFFF", "weight": 1.5, "radius": 6
                                },
                                "popup": etiqueta
                            }
                        })
                        break
                        
    capa_rutas.add_to(m)

    # 5. MENSAJES Y EVENTOS DEL TIMELINE FLOTANTES (Con Cohete Ejecutivo 🚀 usando folium.DivIcon estructurado)
    lat_text, lon_text = 25.8, -95.0 
    
    html_liftoff = '<div style="background-color: rgba(17, 24, 39, 0.95); border: 2px solid #39FF14; color: #FFFF00; padding: 6px 14px; font-size: 16px; font-weight: 900; text-align: center; border-radius: 6px; white-space: nowrap; box-shadow: 0 0 12px rgba(0,0,0,0.9);">🚀 STARSHIP FLIGHT-14 LIFT OFF</div>'
    
    t_liftoff = pd.to_datetime(f"{FECHA_MISION} 12:49:00")
    t_end_liftoff = pd.to_datetime(f"{FECHA_MISION} 12:58:00")
    rango_liftoff = pd.date_range(start=t_liftoff, end=t_end_liftoff, freq='1min')
    
    for t in rango_liftoff:
        t_shift = t + timedelta(hours=AJUSTE_UTC)
        features_geojson.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon_text, lat_text]},
            "properties": {
                "times": [int(t_shift.timestamp() * 1000)],
                "icon": "marker",
                "iconstyle": {
                    "iconUrl": "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg'></svg>",
                    "iconSize": [300, 40],
                    "iconAnchor": [150, 20]
                },
                "popup": html_liftoff,
                "tooltip": "🚀 STARSHIP FLIGHT-14 LIFT OFF"
            }
        })

    # Usando folium.DivIcon estándar integrado en las propiedades para evitar pines azules
    div_icon_liftoff_html = '<div style="background-color: #111827; border: 2px solid #39FF14; color: #FFFF00; padding: 6px 14px; font-size: 15px; font-weight: bold; border-radius: 6px; white-space: nowrap; text-align: center;">🚀 STARSHIP FLIGHT-14 LIFT OFF</div>'

    for t in rango_liftoff:
        t_shift = t + timedelta(hours=AJUSTE_UTC)
        features_geojson.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon_text, lat_text]},
            "properties": {
                "times": [int(t_shift.timestamp() * 1000)],
                "popup": "🚀 STARSHIP FLIGHT-14 LIFT OFF",
                "icon": "circle",
                "iconstyle": {
                    "fillColor": "#FFFF00",
                    "fillOpacity": 0.0,
                    "stroke": "false",
                    "radius": 1
                }
            }
        })

    # Inyección directa mediante marcadores HTML fijos superpuestos para el banner de Cohete (Garantiza visibilidad total sin pines)
    # Como alternativa limpia y robusta, inyectaremos el banner como un marcador de texto nativo de folium condicional o dentro del GeoJSON con marcador invisible pero con texto tooltip/popup constante.
    
    # TIMELAPSE PLAYER (Configurado a 3 FPS = transition_time=333)
    TimestampedGeoJson(
        {"type": "FeatureCollection", "features": features_geojson},
        period="PT1M",
        duration="PT1M", 
        add_last_point=False,
        auto_play=True,
        loop=True,
        max_speed=5,
        loop_button=True,
        time_slider_drag_update=True,
        transition_time=333,  # 333 ms por frame = 3 FPS
    ).add_to(m)

    st_folium(m, width=1400, height=750, returned_objects=[])
