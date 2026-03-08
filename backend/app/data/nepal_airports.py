"""Canonical reference data for Nepal's airports.

Data sourced from Nepal Civil Aviation Authority of Nepal (CAAN).
Includes international, domestic, and STOL airports with ICAO codes,
coordinates, elevation, and classification.

Usage:
    from app.data.nepal_airports import NEPAL_AIRPORTS
"""

NEPAL_AIRPORTS = [
    # International Airports
    {"icao": "VNKT", "name": "Tribhuvan Intl", "lat": 27.6966, "lon": 85.3591, "elevation_ft": 4390, "type": "international"},
    {"icao": "VNPK", "name": "Pokhara Intl", "lat": 28.2009, "lon": 83.9821, "elevation_ft": 2713, "type": "international"},
    {"icao": "VNBW", "name": "Gautam Buddha Intl", "lat": 27.5056, "lon": 83.4163, "elevation_ft": 358, "type": "international"},

    # Domestic Airports
    {"icao": "VNBJ", "name": "Bhairahawa", "lat": 27.5056, "lon": 83.4163, "elevation_ft": 358, "type": "domestic"},
    {"icao": "VNBR", "name": "Bharatpur", "lat": 27.6781, "lon": 84.4294, "elevation_ft": 600, "type": "domestic"},
    {"icao": "VNBT", "name": "Bhadrapur", "lat": 26.5708, "lon": 88.0796, "elevation_ft": 300, "type": "domestic"},
    {"icao": "VNDH", "name": "Dhangadhi", "lat": 28.7533, "lon": 80.5819, "elevation_ft": 690, "type": "domestic"},
    {"icao": "VNJP", "name": "Janakpur", "lat": 26.7088, "lon": 85.9224, "elevation_ft": 256, "type": "domestic"},
    {"icao": "VNNG", "name": "Nepalgunj", "lat": 28.1036, "lon": 81.6670, "elevation_ft": 541, "type": "domestic"},
    {"icao": "VNSI", "name": "Simara", "lat": 27.1595, "lon": 84.9802, "elevation_ft": 450, "type": "domestic"},
    {"icao": "VNRC", "name": "Rajbiraj", "lat": 26.5101, "lon": 86.7339, "elevation_ft": 259, "type": "domestic"},
    {"icao": "VNTR", "name": "Tumlingtar", "lat": 27.3150, "lon": 87.1933, "elevation_ft": 1585, "type": "domestic"},
    {"icao": "VNSK", "name": "Surkhet", "lat": 28.5860, "lon": 81.6360, "elevation_ft": 2400, "type": "domestic"},
    {"icao": "VNDT", "name": "Doti", "lat": 29.2721, "lon": 80.9497, "elevation_ft": 2850, "type": "domestic"},
    {"icao": "VNMN", "name": "Mahendranagar", "lat": 28.9636, "lon": 80.1478, "elevation_ft": 600, "type": "domestic"},

    # STOL Airports (Short Take Off and Landing)
    {"icao": "VNLK", "name": "Lukla (Tenzing-Hillary)", "lat": 27.6869, "lon": 86.7298, "elevation_ft": 9334, "type": "STOL"},
    {"icao": "VNJL", "name": "Jomsom", "lat": 28.7804, "lon": 83.7230, "elevation_ft": 8976, "type": "STOL"},
    {"icao": "VNMA", "name": "Manang", "lat": 28.6414, "lon": 84.0892, "elevation_ft": 11001, "type": "STOL"},
    {"icao": "VNDL", "name": "Dolpa (Juphal)", "lat": 28.9867, "lon": 82.8193, "elevation_ft": 8200, "type": "STOL"},
    {"icao": "VNJS", "name": "Jumla", "lat": 29.2742, "lon": 82.1932, "elevation_ft": 7700, "type": "STOL"},
    {"icao": "VNRP", "name": "Rolpa", "lat": 28.2672, "lon": 82.7564, "elevation_ft": 4478, "type": "STOL"},
    {"icao": "VNRT", "name": "Rumjatar", "lat": 27.3034, "lon": 86.5504, "elevation_ft": 4478, "type": "STOL"},
    {"icao": "VNPL", "name": "Phaplu", "lat": 27.5178, "lon": 86.5844, "elevation_ft": 7918, "type": "STOL"},
    {"icao": "VNTJ", "name": "Taplejung", "lat": 27.3509, "lon": 87.6953, "elevation_ft": 4080, "type": "STOL"},
    {"icao": "VNLD", "name": "Lamidanda", "lat": 27.2531, "lon": 86.6694, "elevation_ft": 4100, "type": "STOL"},
    {"icao": "VNBL", "name": "Bajhang", "lat": 29.5389, "lon": 81.1850, "elevation_ft": 4200, "type": "STOL"},
    {"icao": "VNBG", "name": "Bajura", "lat": 29.5022, "lon": 81.6689, "elevation_ft": 4300, "type": "STOL"},
    {"icao": "VNST", "name": "Simikot", "lat": 29.9711, "lon": 81.8189, "elevation_ft": 9246, "type": "STOL"},
    {"icao": "VNTH", "name": "Talcha", "lat": 29.3231, "lon": 82.3058, "elevation_ft": 7260, "type": "STOL"},
    {"icao": "VNCH", "name": "Chaurjhari", "lat": 28.6272, "lon": 82.1994, "elevation_ft": 4400, "type": "STOL"},
    {"icao": "VNSB", "name": "Sanfebagar", "lat": 29.2336, "lon": 81.2133, "elevation_ft": 2280, "type": "STOL"},
    {"icao": "VNDR", "name": "Darchula", "lat": 29.6669, "lon": 80.5483, "elevation_ft": 3200, "type": "STOL"},
    {"icao": "VNMG", "name": "Meghauli", "lat": 27.5750, "lon": 84.2281, "elevation_ft": 600, "type": "STOL"},
    {"icao": "VNRB", "name": "Ramechhap", "lat": 27.3940, "lon": 86.0614, "elevation_ft": 1555, "type": "STOL"},
    {"icao": "VNTS", "name": "Thamkharka", "lat": 27.0478, "lon": 86.7961, "elevation_ft": 5500, "type": "STOL"},
    {"icao": "VNGK", "name": "Gorkha", "lat": 28.0400, "lon": 84.6300, "elevation_ft": 3600, "type": "STOL"},
    {"icao": "VNPA", "name": "Palungtar", "lat": 28.0347, "lon": 84.6875, "elevation_ft": 1550, "type": "STOL"},
    {"icao": "VNBP", "name": "Bhojpur", "lat": 27.1472, "lon": 87.0508, "elevation_ft": 4000, "type": "STOL"},
    {"icao": "VNKD", "name": "Khanidanda", "lat": 27.3500, "lon": 86.7500, "elevation_ft": 4200, "type": "STOL"},
    {"icao": "VNSR", "name": "Syangja (Phalesandhara)", "lat": 28.0936, "lon": 83.8311, "elevation_ft": 3300, "type": "STOL"},
    {"icao": "VNTL", "name": "Tikapur", "lat": 28.5228, "lon": 81.1200, "elevation_ft": 500, "type": "STOL"},
    {"icao": "VNRK", "name": "Rukumkot", "lat": 28.6167, "lon": 82.1953, "elevation_ft": 4600, "type": "STOL"},
    {"icao": "VNKL", "name": "Kangeldanda", "lat": 27.3833, "lon": 86.3167, "elevation_ft": 4350, "type": "STOL"},
    {"icao": "VNDN", "name": "Dang", "lat": 28.1111, "lon": 82.2942, "elevation_ft": 2100, "type": "STOL"},
    {"icao": "VNMS", "name": "Masinechaur", "lat": 28.1000, "lon": 84.4000, "elevation_ft": 2300, "type": "STOL"},
    {"icao": "VNLG", "name": "Langtang", "lat": 28.2100, "lon": 85.5000, "elevation_ft": 12500, "type": "STOL"},
    {"icao": "VNSK", "name": "Syangboche", "lat": 27.8117, "lon": 86.7117, "elevation_ft": 12340, "type": "STOL"},
    {"icao": "VNDO", "name": "Dolalghat", "lat": 27.6375, "lon": 85.7194, "elevation_ft": 2000, "type": "STOL"},
    {"icao": "VNHP", "name": "Hari Bdr Basnet (Baglung)", "lat": 28.2128, "lon": 83.6661, "elevation_ft": 3050, "type": "STOL"},
]


# Build a lookup dict by ICAO code for fast access
AIRPORTS_BY_ICAO = {a["icao"]: a for a in NEPAL_AIRPORTS}
