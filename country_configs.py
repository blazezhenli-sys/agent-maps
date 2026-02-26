
COUNTRY_CONFIGS = {
    "Taiwan": {
        "city_admin_level": "6",   # immediate subareas (cities/counties)
        "district_levels": ["7", "8"],  # level 7 primary, fallback to 8
        "default_district_level": "7",
        "map_center": [23.7, 121],       # default lat/lng for map start
        "map_zoom": 7,                    # default zoom
    },
    "Japan": {
        "city_admin_level": "3",         # prefectures
        "district_levels": ["7", "8"],   # wards inside prefectures
        "default_district_level": "7",
        "map_center": [36.0, 138.0],     # central Japan
        "map_zoom": 5,
    }
}