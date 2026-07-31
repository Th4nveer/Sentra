"""
Geocoding module using OpenStreetMap Nominatim API with fallback offline registry.
"""
import os
import re
import requests
from typing import Dict, Tuple, Optional
from dotenv import load_dotenv

from src.parser.models import GeocodingResult

load_dotenv()

# Built-in fallback registry for municipal wards, landmarks, and city locations
LOCAL_GEO_REGISTRY: Dict[str, Dict[str, float]] = {
    "bellandur lake": {"lat": 12.9333, "lon": 77.6637, "address": "Bellandur Lake, Bengaluru, Karnataka 560103"},
    "bellandur": {"lat": 12.9333, "lon": 77.6637, "address": "Bellandur Lake, Bengaluru, Karnataka 560103"},
    "ward 12 main connector road": {"lat": 12.9333, "lon": 77.6637, "address": "Bellandur Lake, Bengaluru, Karnataka 560103"},
    "bellandur outer ring road": {"lat": 12.9333, "lon": 77.6637, "address": "Bellandur Lake, Bengaluru, Karnataka 560103"},
    "bengaluru ward 12": {"lat": 12.9333, "lon": 77.6637, "address": "Bellandur Lake, Bengaluru, Karnataka 560103"},
    "sector 4 civic park": {"lat": 28.5355, "lon": 77.3910, "address": "Sector 4 Civic Park, Noida, Uttar Pradesh 201301"},
    "noida sector 4": {"lat": 28.5355, "lon": 77.3910, "address": "Sector 4, Noida, Uttar Pradesh"},
    "hosur main road drainage": {"lat": 12.9116, "lon": 77.6389, "address": "Hosur Main Road, Kudlu Gate Signal, Bengaluru, Karnataka 560068"},
    "mumbai bkc connector": {"lat": 19.0657, "lon": 72.8687, "address": "Bandra Kurla Complex, Mumbai, Maharashtra"},
    "gachibowli flyover": {"lat": 17.4401, "lon": 78.3489, "address": "Gachibowli, Hyderabad, Telangana"},
}

DEFAULT_LAT = 12.9333
DEFAULT_LON = 77.6637


class Geocoder:
    def __init__(self, user_agent: Optional[str] = None):
        self.user_agent = user_agent or os.getenv("GEOLOCATION_USER_AGENT", "Sentra-Satellite-Audit/1.0")

    def geocode(self, location_text: str, radius_km: float = 0.5) -> GeocodingResult:
        """
        Geocodes a location text into lat, lon and bounding box.
        """
        # 1. Check if location_text has raw coordinates
        coord_match = re.search(r'(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)', location_text)
        if coord_match:
            lat = float(coord_match.group(1))
            lon = float(coord_match.group(2))
            bbox = self._calculate_bbox(lat, lon, radius_km)
            return GeocodingResult(
                latitude=lat,
                longitude=lon,
                bounding_box=bbox,
                confidence=1.0,
                formatted_address=f"Explicit Coordinates ({lat}, {lon})",
                geocoding_source="coordinates"
            )

        # 2. Check local registry match first for speed & offline reliability
        loc_lower = location_text.lower()
        sorted_keys = sorted(LOCAL_GEO_REGISTRY.keys(), key=len, reverse=True)
        for key in sorted_keys:
            info = LOCAL_GEO_REGISTRY[key]
            # Require the full key to appear in the text, or at least 2 distinctive words (3+ chars)
            if key in loc_lower:
                lat, lon = info["lat"], info["lon"]
                bbox = self._calculate_bbox(lat, lon, radius_km)
                return GeocodingResult(
                    latitude=lat,
                    longitude=lon,
                    bounding_box=bbox,
                    confidence=0.95,
                    formatted_address=info["address"],
                    geocoding_source="local_registry"
                )
            # Partial match: require at least 2 distinctive words (excluding generic geo terms) to match
            generic_words = {"road", "main", "ward", "sector", "park", "outer", "ring", "canal", "drainage", "bridge", "flyover", "connector"}
            key_words = [w for w in key.split() if len(w) >= 3 and w not in generic_words]
            matched_words = [w for w in key_words if w in loc_lower]
            if len(key_words) >= 2 and len(matched_words) >= 2 and len(matched_words) / len(key_words) >= 0.6:
                lat, lon = info["lat"], info["lon"]
                bbox = self._calculate_bbox(lat, lon, radius_km)
                return GeocodingResult(
                    latitude=lat,
                    longitude=lon,
                    bounding_box=bbox,
                    confidence=0.85,
                    formatted_address=info["address"],
                    geocoding_source="local_registry"
                )

        # 3. Query OpenStreetMap Nominatim API online — try full text first, landmark combinations, then simplified queries
        queries_to_try = [location_text]
        parts = [p.strip() for p in re.split(r'[,;/]', location_text) if p.strip()]

        city_match = re.search(r'(Mumbai|Delhi|Bengaluru|Bangalore|Chennai|Hyderabad|Kolkata|Pune|Ahmedabad|Noida|Lucknow|Jaipur|Surat|Nagpur|Indore|Thane|Bhopal|Patna|Vadodara|Kochi|Coimbatore)', location_text, re.IGNORECASE)
        city_name = city_match.group(1) if city_match else ""

        # Extract specific landmarks (e.g., Juhu-Versova, Barfiwala, JVPD, etc.)
        for part in parts:
            clean_part = re.sub(r'\b(road|rd|street|st|ward|k/w|junction|upto|construction|of|flyover)\b', '', part, flags=re.IGNORECASE).strip()
            if len(clean_part) >= 3:
                if city_name:
                    queries_to_try.append(f"{clean_part}, {city_name}")
                    if len(parts) >= 2:
                        queries_to_try.append(f"{clean_part}, {parts[-2]}, {city_name}")
                else:
                    queries_to_try.append(clean_part)

        if len(parts) >= 2:
            queries_to_try.append(", ".join(parts[-3:]) if len(parts) >= 3 else ", ".join(parts[-2:]))
            queries_to_try.append(", ".join(parts[-2:]))

        if city_name and parts:
            queries_to_try.insert(1, f"{parts[0]}, {city_name}")

        for query in queries_to_try:
            try:
                url = "https://nominatim.openstreetmap.org/search"
                headers = {"User-Agent": self.user_agent}
                params = {"q": query, "format": "json", "limit": 1}
                response = requests.get(url, headers=headers, params=params, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    if data and len(data) > 0:
                        lat = float(data[0]["lat"])
                        lon = float(data[0]["lon"])
                        bbox = self._calculate_bbox(lat, lon, radius_km)
                        return GeocodingResult(
                            latitude=lat,
                            longitude=lon,
                            bounding_box=bbox,
                            confidence=0.9 if query == location_text else 0.8,
                            formatted_address=data[0].get("display_name", location_text),
                            geocoding_source="nominatim"
                        )
            except Exception as e:
                print(f"[Geocoder] Nominatim lookup failed for '{query}': {e}")

        # 4. Final fallback default coordinate
        bbox = self._calculate_bbox(DEFAULT_LAT, DEFAULT_LON, radius_km)
        return GeocodingResult(
            latitude=DEFAULT_LAT,
            longitude=DEFAULT_LON,
            bounding_box=bbox,
            confidence=0.7,
            formatted_address=f"{location_text} (Estimated Coordinates)",
            geocoding_source="fallback"
        )

    def geocode_coordinates(self, lat: float, lon: float, radius_km: float = 0.5) -> GeocodingResult:
        """
        Creates a GeocodingResult directly from coordinates (e.g. from a user map pin).
        Attempts reverse geocoding via Nominatim for a human-readable address.
        """
        bbox = self._calculate_bbox(lat, lon, radius_km)
        formatted_address = f"({lat:.4f}, {lon:.4f})"

        # Attempt reverse geocode for a readable address
        try:
            url = "https://nominatim.openstreetmap.org/reverse"
            headers = {"User-Agent": self.user_agent}
            params = {"lat": lat, "lon": lon, "format": "json", "zoom": 16}
            response = requests.get(url, headers=headers, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if "display_name" in data:
                    formatted_address = data["display_name"]
        except Exception as e:
            print(f"[Geocoder] Reverse geocode failed for ({lat}, {lon}): {e}")

        return GeocodingResult(
            latitude=lat,
            longitude=lon,
            bounding_box=bbox,
            confidence=1.0,
            formatted_address=formatted_address,
            geocoding_source="community_pin"
        )

    def _calculate_bbox(self, lat: float, lon: float, radius_km: float = 0.5) -> list:
        """
        Calculates bounding box [min_lat, min_lon, max_lat, max_lon] around center coordinate.
        Approx 1 deg lat = 111 km, 1 deg lon = 111 * cos(lat) km.
        """
        lat_offset = radius_km / 111.0
        lon_offset = radius_km / (111.0 * max(0.1, abs(abs(lat) * 0.01745)))
        return [
            round(lat - lat_offset, 6),
            round(lon - lon_offset, 6),
            round(lat + lat_offset, 6),
            round(lon + lon_offset, 6)
        ]
