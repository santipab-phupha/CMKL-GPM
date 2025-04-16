import streamlit as st
import folium
from streamlit_folium import st_folium
import math
import numpy as np
from folium.plugins import HeatMap

# ตั้งค่าให้แสดงผลแบบ Wide
st.set_page_config(layout="wide")
st.title("จำลองการกระจาย (Gaussian Plume Model) บนแผนที่กรุงเทพฯ")

st.markdown("""
**วิธีใช้งาน:**
1. คลิกบนแผนที่ด้านล่างเพื่อระบุจุด "ระเบิด"  
2. ปรับค่าพารามิเตอร์ Gaussian ใน Sidebar  
3. HeatMap จะแสดงโดยไล่สี "เหลือง→ส้ม→แดง" โดยเน้นให้เห็นส้มมากขึ้น  
""")

# ------------------------------------------------------------------------------
# Sidebar: ค่าพารามิเตอร์ของ Gaussian Plume
# ------------------------------------------------------------------------------
st.sidebar.header("ปรับพารามิเตอร์ Gaussian Plume Model")

event_name = st.sidebar.text_input("ชื่อเหตุการณ์", "Explosion #1")

Q = st.sidebar.number_input(
    "Emission rate (Q)",
    min_value=10.0, max_value=5000.0, value=100.0, step=10.0,
    help="ค่าปริมาณการปล่อยสาร (หน่วยสมมติ)"
)

u = st.sidebar.number_input(
    "Wind Speed (m/s)",
    min_value=0.0, max_value=30.0, value=5.0, step=0.5,
    help="ความเร็วลม (m/s)"
)

time_t = st.sidebar.number_input(
    "Time (t) (s)",
    min_value=0.1, max_value=100.0, value=1.0, step=0.1,
    help="ระยะเวลาที่ลมพัด (วินาที)"
)

wind_direction = st.sidebar.slider(
    "Wind Direction (°)",
    0, 360, 90, 1,
    help="ทิศทางลม (0° = เหนือ, 90° = ตะวันออก, เป็นต้น)"
)

sigma_m = st.sidebar.slider(
    "Dispersion Sigma (m)",
    500, 10000, 4000, 500,
    help="ควบคุมความกว้างของการกระจาย (Gaussian)"
)

max_range_km = st.sidebar.slider(
    "Max Range (km)",
    1, 50, 20, 1,
    help="ระยะครอบคลุมสำหรับการ sample (ยิ่งมาก กระจายไกล)"
)

# ------------------------------------------------------------------------------
# สร้างแผนที่กรุงเทพฯ ให้คลิกเลือกจุดระเบิด
# ------------------------------------------------------------------------------
BANGKOK_LAT, BANGKOK_LON = 13.7563, 100.5018
base_map = folium.Map(location=[BANGKOK_LAT, BANGKOK_LON], zoom_start=10)
folium.LatLngPopup().add_to(base_map)

map_data = st_folium(base_map, use_container_width=True, height=700)

# ------------------------------------------------------------------------------
# หากคลิกบนแผนที่ -> คำนวณการกระจายและแสดง HeatMap
# ------------------------------------------------------------------------------
if map_data["last_clicked"] is not None:
    bomb_lat = map_data["last_clicked"]["lat"]
    bomb_lon = map_data["last_clicked"]["lng"]
    
    st.subheader(f"เหตุการณ์: {event_name}")
    st.write(f"**ตำแหน่งระเบิด:** lat={bomb_lat:.4f}, lon={bomb_lon:.4f}")
    
    # 1) คำนวณศูนย์กลางการกระจายที่เลื่อนตามลม
    d = u * time_t  # ระยะลมพัด (เมตร)
    theta_w = math.radians(wind_direction)
    lat_m_factor = 111_000
    lon_m_factor = 111_000 * math.cos(math.radians(bomb_lat))
    
    center_lat = bomb_lat + (d * math.sin(theta_w)) / lat_m_factor
    center_lon = bomb_lon + (d * math.cos(theta_w)) / lon_m_factor
    
    st.write(f"**เลื่อนตามลม -> ศูนย์กลางการกระจาย:** lat={center_lat:.4f}, lon={center_lon:.4f}")
    
    # 2) สร้าง dataset (heat_data) แบบ polar รอบจุดระเบิด
    heat_data = []
    max_range_m = max_range_km * 1000
    
    num_r = 80
    num_theta = 150
    
    for i in range(num_r):
        r = (i / (num_r - 1)) * max_range_m
        for j in range(num_theta):
            theta = (j / num_theta) * 2 * math.pi
            
            offset_x = r * math.cos(theta)
            offset_y = r * math.sin(theta)
            sample_lat = bomb_lat + offset_y / lat_m_factor
            sample_lon = bomb_lon + offset_x / lon_m_factor
            
            # ระยะจาก (center_lat, center_lon)
            delta_lat = (sample_lat - center_lat) * lat_m_factor
            delta_lon = (sample_lon - center_lon) * lon_m_factor
            distance_m = math.sqrt(delta_lat**2 + delta_lon**2)
            
            # สูตร Gaussian 2D
            concentration = Q * math.exp(-(distance_m**2) / (2 * sigma_m**2))
            heat_data.append([sample_lat, sample_lon, concentration])
    
    # 3) Normalization ความเข้ม -> [0..1]
    max_conc = max(pt[2] for pt in heat_data)
    if max_conc > 0:
        for pt in heat_data:
            pt[2] = pt[2] / max_conc
    
    # 4) แผนที่ใหม่สำหรับ HeatMap
    explosion_map = folium.Map(location=[bomb_lat, bomb_lon], zoom_start=10)
    
    # ------------------------------------------------------------------------------
    # ปรับ gradient ให้สีแดง (Red) แคบลง และสีส้ม (Orange) กับสีเหลือง (Yellow) กว้างขึ้น
    #  - 0.0 - 0.2  : เหลือง
    #  - 0.2 - 0.6  : ส้ม
    #  - 0.6 - 1.0  : แดง
    # (ปรับตามต้องการ ถ้าอยากให้ส้มกว้างขึ้น/แดงแคบลงก็เพิ่มค่าระดับกลาง)
    # ------------------------------------------------------------------------------
    raw_gradient = {
        0.0: 'yellow',
        0.2: 'yellow',   # 0-20% = เหลือง
        0.21: 'orange',
        0.6: 'orange',   # 21-60% = ส้ม
        0.61: 'red',
        1.0: 'red'       # 61-100% = แดง
    }
    gradient = {str(k): v for k, v in raw_gradient.items()}
    
    HeatMap(
        heat_data,
        radius=30,
        blur=25,
        gradient=gradient,
        min_opacity=0.3,
        max_opacity=0.8,
        max_zoom=13
    ).add_to(explosion_map)
    
    st_folium(explosion_map, use_container_width=True, height=700)
else:
    st.info("คลิกบนแผนที่ด้านบนเพื่อเลือกจุดเกิดระเบิด แล้วผล HeatMap จะปรากฏที่นี่!")
