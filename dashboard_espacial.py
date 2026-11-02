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
        
    # D. Flights
    df_vuelos = pd.read_excel("ROCKET_28_SEPT_2026.xlsx")
    df_vuelos.columns = df_vuelos.columns.str.strip()
    df_vuelos['entry_hour'] = pd.to_datetime(df_vuelos['entry_hour'])
    df_vuelos['exit_hour'] = pd.to_datetime(df_vuelos['exit_hour'])
    
    return df_wp, dicc_wp, df_areas, dict_espacio, df_vuelos

def decodificar_coordenada_ruta(string_punto):
    match = re.match(r'^(\d{2})(\d{2})[Nn](\d{3})(\d{2})[Ww]$', str(string_punto).strip())
    if match:
        lat = int(match.group(1)) + int(match.group(2)) / 60.0
        lon = -(int(match.group(3)) + int(match.group(4)) / 60.0)
        return lat, lon
    return None

df_waypoints, dicc_waypoints, df_riesgo, dict_espacio, df_vuelos = cargar_bases_datos()

# --- MAIN INTERFACE HEADER ---
col1, col2 = st.columns([5, 1])
with col1:
    st.title("🛰️ Operational Monitoring: Space Launches")
    st.markdown("Tactical visualization of trajectories and air traffic control (Time displayed in UTC format).")
with col2:
    if os.path.exists("Seneam_Logo.png"):
        st.image("Seneam_Logo.png", use_container_width=True)

# Dropdown Menu Selector
operacion = st.selectbox(
    "Select the Space Launch to visualize:",
    [
        "SpaceX Starship Super Heavy Flight-14 Sept 28th, 2026", 
        "Upcoming launches..."
    ]
)

if operacion == "Upcoming launches...":
    # --- EXECUTIVE UPCOMING LAUNCH SCREEN ---
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
    
    # --- SIDEBAR CONTROL PANEL ---
    st.sidebar.title("🎛️ Map Control Panel")
    st.sidebar.markdown("Enable or disable layers to visualize:")

    st.sidebar.markdown("**Airspace & Control Centers**")
    mostrar_firs = st.sidebar.checkbox("Mexico FIR, Mazatlan Oceanic FIR", value=True)
    mostrar_acc_mid = st.sidebar.checkbox("Merida Control Center (MMID ACC)", value=True)
    mostrar_acc_mty = st.sidebar.checkbox("Monterrey Control Center (MMTY ACC)", value=True)
    mostrar_acc_mex = st.sidebar.checkbox("Mexico Control Center (MMEX ACC)", value=True)
    mostrar_acc_mzt = st.sidebar.checkbox("Mazatlan Control Center (MMZT ACC)", value=True)

    st.sidebar.markdown("**Space Launch Hazard Areas**")
    mostrar_tfr = st.sidebar.checkbox("TFR: Temporary Flight Restriction", value=True)
    mostrar_dra = st.sidebar.checkbox("DRA-1 Area", value=True)
    mostrar_aha = st.sidebar.checkbox("Launch Hazard Areas (AHA-A3 & AHA-B1)", value=True)
    mostrar_10_7 = st.sidebar.checkbox("10^-7 Area MMFR", value=True)

    st.sidebar.markdown("**Flight Data**")
    mostrar_rutas = st.sidebar.checkbox("Historical Flight Trajectories", value=True)
    mostrar_waypoints = st.sidebar.checkbox("Waypoints and VORs", value=False)
    
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
    
    # LAYER 3: Hazard Areas (Custom Colors & White Text Labels)
    capa_areas = folium.FeatureGroup(name="Space Hazard Areas")
    for area, datos in df_riesgo.groupby('Área / Hazard Zone'):
        area_str = str(area).upper()
        label_name = area
        
        if "TFR" in area_str:
            if not mostrar_tfr: continue
            color = "#90EE90"
            label_name = "TFR"
        elif "DRA" in area_str:
            if not mostrar_dra: continue
            color = "#FFB347"
            label_name = "DRA-1"
        elif "AHA" in area_str:
            if not mostrar_aha: continue
            color = "#FF7F7F"
            label_name = "AHA-A3" if "A3" in area_str else "AHA-B1"
        elif "10^-7" in area_str or "10_7" in area_str:
            if not mostrar_10_7: continue
            color = "#FFFFE0"
            label_name = "10^-7"
        else:
            color = "#FFA500"
            
        coords = list(zip(datos['Latitud (Decimal)'], datos['Longitud (Decimal)']))
        
        folium.Polygon(
            locations=coords, color=color, fill=True, fill_opacity=0.35, tooltip=f"Restriction: {area}"
        ).add_to(capa_areas)
        
        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]
        centroide = [sum(lats)/len(lats), sum(lons)/len(lons)]
        
        folium.map.Marker(
            centroide,
            icon=folium.DivIcon(
                icon_size=(100,20),
                icon_anchor=(50,10),
                html=f'<div style="font-size: 10pt; color: white; font-weight: bold; text-shadow: 1px 1px 2px black; text-align: center;">{label_name}</div>',
            )
        ).add_to(capa_areas)
        
    capa_areas.add_to(m)
    
    # FLIGHT TRAJECTORY PROCESSING (With Aircraft Position Icons and Progressive Lines)
    features_vuelos = []
    
    if mostrar_rutas:
        capa_rutas = folium.FeatureGroup(name="Static Trajectories")
        
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
            # Static background route
            if mostrar_rutas:
                coords_estaticas = [[lat, lon] for lat, lon in puntos_validos]
                folium.PolyLine(
                    locations=coords_estaticas, color="#39FF14", weight=0.5, opacity=0.2, dash_array="4",
                    tooltip=f"<b>Callsign:</b> {vuelo['callsign']} | <b>Route:</b> {vuelo['adep']}-{vuelo['ades']}"
                ).add_to(capa_rutas)
            
            t_inicio = vuelo['entry_hour']
            t_fin = vuelo['exit_hour']
            paso_tiempo = (t_fin - t_inicio) / (n_pts - 1)
            
            for i in range(n_pts - 1):
                remaining_coords = [[lon, lat] for lat, lon in puntos_validos[i:]]
                
                t_current = t_inicio + paso_tiempo * i
                t_next = t_inicio + paso_tiempo * (i + 1)
                
                t1_shift = t_current + timedelta(hours=AJUSTE_UTC)
                t2_shift = t_next + timedelta(hours=AJUSTE_UTC)
                
                etiqueta_click = (
                    f"<b>Callsign:</b> {vuelo['callsign']}<br>"
                    f"<b>ADEP-ADES:</b> {vuelo['adep']} - {vuelo['ades']}<br>"
                    f"<b>Track Time:</b> {t_current.strftime('%H:%M')} UTC"
                )
                
                # 1. Progressive Line Feature (Present & Future)
                features_vuelos.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": remaining_coords
                    },
                    "properties": {
                        "times": [int(t1_shift.timestamp() * 1000), int(t2_shift.timestamp() * 1000)],
                        "style": {"color": "#39FF14", "weight": 1.5, "opacity": 0.9},
                        "popup": etiqueta_click
                    }
                })
                
                # 2. Small Aircraft Position Icon (Green Dot with White Border)
                lat_i, lon_i = puntos_validos[i]
                features_vuelos.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon_i, lat_i]
                    },
                    "properties": {
                        "times": [int(t1_shift.timestamp() * 1000), int(t2_shift.timestamp() * 1000)],
                        "icon": "circle",
                        "iconstyle": {
                            "fillColor": "#39FF14",
                            "fillOpacity": 1.0,
                            "stroke": "true",
                            "color": "#FFFFFF",
                            "weight": 1,
                            "radius": 5
                        },
                        "popup": etiqueta_click
                    }
                })
            
    if mostrar_rutas:
        capa_rutas.add_to(m)

    # TIMELAPSE PLAYER
    TimestampedGeoJson(
        {"type": "FeatureCollection", "features": features_vuelos},
        period="PT1M",
        add_last_point=False,
        auto_play=True,
        loop=True,
        max_speed=5,
        loop_button=True,
        time_slider_drag_update=True,
    ).add_to(m)

    st_folium(m, width=1400, height=750, returned_objects=[])
