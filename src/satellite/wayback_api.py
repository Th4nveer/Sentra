"""
Esri World Imagery Wayback API Client.
Fetches historical high-resolution satellite imagery tiles from https://livingatlas.arcgis.com/wayback/
using the official Wayback configuration index.
Stitches multi-tile $3 \times 3$ mosaics for high-definition wide-area coverage.
"""
import time
import math
import io
import datetime
import requests
import numpy as np
from PIL import Image
from typing import Dict, Any, Optional, Tuple, List

WAYBACK_CONFIG_URL = "https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json"


class EsriWaybackClient:
    """
    Client for Esri World Imagery Wayback historical satellite basemaps.
    Converts lat/lon ROI and dates into exact historical Wayback tile releases.
    Downloads multi-tile $3 \times 3$ mosaics for high-definition wide-area coverage.
    """

    def __init__(self):
        self.releases: List[Tuple[datetime.datetime, str, Dict[str, Any]]] = []
        self._load_release_index()

    def _load_release_index(self) -> None:
        """Loads and parses all available historical Wayback releases from Esri config."""
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Sentra-Satellite-Audit/1.0"}
            resp = requests.get(WAYBACK_CONFIG_URL, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for key, item in data.items():
                    title = item.get("itemTitle", "")
                    if "Wayback" in title:
                        d_str = title.split("Wayback")[-1].strip("() ")
                        try:
                            dt = datetime.datetime.strptime(d_str, "%Y-%m-%d")
                            self.releases.append((dt, key, item))
                        except ValueError:
                            continue
                self.releases.sort(key=lambda x: x[0])
                print(f"[EsriWaybackClient] Successfully loaded {len(self.releases)} historical satellite releases from Esri Wayback.")
        except Exception as e:
            print(f"[EsriWaybackClient] Failed to load Wayback index: {e}")

    def get_closest_release(self, date_str: str) -> Optional[Tuple[datetime.datetime, str, Dict[str, Any]]]:
        """Finds the closest historical satellite release for a given YYYY-MM-DD date."""
        if not self.releases:
            return None
        try:
            target_dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            target_dt = datetime.datetime.now()

        closest = min(self.releases, key=lambda x: abs((x[0] - target_dt).total_seconds()))
        return closest

    def fetch_satellite_crop(
        self,
        bounding_box: list,
        date_str: str,
        zoom_level: int = 16,
        grid_size: int = 3
    ) -> Dict[str, Any]:
        """
        Fetches a high-definition multi-tile ($3 \\times 3$ grid) satellite mosaic from Esri World Imagery Wayback
        for the given lat/lon bounding box & date at Zoom Level 16 (~2.3m/pixel resolution).
        """
        min_lat, min_lon, max_lat, max_lon = bounding_box
        center_lat = (min_lat + max_lat) / 2.0
        center_lon = (min_lon + max_lon) / 2.0

        x_center, y_center = self.latlon_to_tile(center_lat, center_lon, zoom_level)

        release_info = self.get_closest_release(date_str)
        if release_info:
            rel_dt, rel_id, rel_item = release_info
            actual_date_str = rel_dt.strftime("%Y-%m-%d")
            item_url = rel_item.get("itemURL", "")

            mosaic_data = self._download_tile_grid(
                item_url=item_url,
                release_id=rel_id,
                x_center=x_center,
                y_center=y_center,
                zoom=zoom_level,
                grid_size=grid_size
            )

            if mosaic_data is not None:
                return {
                    "source": f"Esri World Imagery Wayback ({actual_date_str})",
                    "date": actual_date_str,
                    "target_date": date_str,
                    "center": (center_lat, center_lon),
                    "rgb_image": mosaic_data["image"],
                    "array_4band": mosaic_data["array_4band"],
                    "is_live_planet": False,
                    "is_wayback": True
                }

        # Fallback to standard Esri tile grid if release query fails
        crop_data = self._fetch_standard_esri_grid(x_center, y_center, zoom_level, grid_size)
        return {
            "source": "Esri World Imagery Basemap (Sub-5m)",
            "date": date_str,
            "center": (center_lat, center_lon),
            "rgb_image": crop_data["image"],
            "array_4band": crop_data["array_4band"],
            "is_live_planet": False,
            "is_wayback": False
        }

    def _download_tile_grid(
        self,
        item_url: str,
        release_id: str,
        x_center: int,
        y_center: int,
        zoom: int,
        grid_size: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Downloads a grid_size x grid_size tile matrix around x_center, y_center
        and stitches them into a seamless high-resolution composite canvas.
        """
        half = grid_size // 2
        tile_width = 256
        mosaic_size = grid_size * tile_width
        canvas = Image.new("RGB", (mosaic_size, mosaic_size))

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://livingatlas.arcgis.com/wayback/",
            "Connection": "close"
        }

        downloaded_count = 0

        for row_idx, dy in enumerate(range(-half, half + 1)):
            for col_idx, dx in enumerate(range(-half, half + 1)):
                tile_x = x_center + dx
                tile_y = y_center + dy

                if item_url:
                    url = item_url.replace("{level}", str(zoom))\
                                  .replace("{row}", str(tile_y))\
                                  .replace("{col}", str(tile_x))\
                                  .replace("{z}", str(zoom))\
                                  .replace("{y}", str(tile_y))\
                                  .replace("{x}", str(tile_x))
                else:
                    url = f"https://wayback.maptiles.arcgis.com/arcgis/rest/services/world_imagery/wmts/1.0.0/default028mm/mapserver/tile/{release_id}/{zoom}/{tile_y}/{tile_x}"

                url = url.replace("World_Imagery", "world_imagery").replace("MapServer", "mapserver")

                tile_img = self._download_single_tile(url, headers)
                if tile_img is not None:
                    canvas.paste(tile_img, (col_idx * tile_width, row_idx * tile_width))
                    downloaded_count += 1
                else:
                    # Fill with neutral placeholder tile if individual tile fails
                    placeholder = Image.new("RGB", (tile_width, tile_width), (100, 100, 100))
                    canvas.paste(placeholder, (col_idx * tile_width, row_idx * tile_width))

        if downloaded_count > 0:
            # Resize mosaic to standard 512x512 array for Change Detection engine
            high_res_img = canvas.resize((512, 512), Image.Resampling.LANCZOS)
            rgb_arr = np.array(high_res_img, dtype=np.float32) / 255.0

            # Estimate Near-Infrared (NIR) channel from green/red reflectance
            nir_channel = np.clip(rgb_arr[:, :, 1] * 1.3 - rgb_arr[:, :, 0] * 0.3, 0.0, 1.0)
            arr_4band = np.dstack((rgb_arr, nir_channel)).astype(np.float32)

            return {"image": high_res_img, "array_4band": arr_4band}

        return None

    def _download_single_tile(self, tile_url: str, headers: dict, retries: int = 2) -> Optional[Image.Image]:
        """Downloads a single tile with retry logic and manual 301/302 redirect handling."""
        for attempt in range(retries + 1):
            try:
                resp = requests.get(tile_url, headers=headers, timeout=8, allow_redirects=False)

                if resp.status_code in (301, 302, 307, 308) and "Location" in resp.headers:
                    loc = resp.headers["Location"]
                    redirect_url = "https://wayback.maptiles.arcgis.com" + loc if loc.startswith("/") else loc
                    resp = requests.get(redirect_url, headers=headers, timeout=8, allow_redirects=False)

                if resp.status_code == 200 and len(resp.content) > 500:
                    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                    return img
            except Exception as e:
                pass
            time.sleep(0.15)
        return None

    def _fetch_standard_esri_grid(self, x_center: int, y_center: int, z: int, grid_size: int = 3) -> Dict[str, Any]:
        """Fallback standard Esri tile grid fetcher."""
        half = grid_size // 2
        tile_width = 256
        canvas = Image.new("RGB", (grid_size * tile_width, grid_size * tile_width))

        headers = {"User-Agent": "Mozilla/5.0", "Connection": "close"}

        for row_idx, dy in enumerate(range(-half, half + 1)):
            for col_idx, dx in enumerate(range(-half, half + 1)):
                url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y_center + dy}/{x_center + dx}"
                try:
                    resp = requests.get(url, headers=headers, timeout=5)
                    if resp.status_code == 200:
                        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                        canvas.paste(img, (col_idx * tile_width, row_idx * tile_width))
                except Exception:
                    pass

        high_res_img = canvas.resize((512, 512), Image.Resampling.LANCZOS)
        rgb_arr = np.array(high_res_img, dtype=np.float32) / 255.0
        nir_channel = np.clip(rgb_arr[:, :, 1] * 1.25 - rgb_arr[:, :, 0] * 0.25, 0.0, 1.0)
        arr_4band = np.dstack((rgb_arr, nir_channel)).astype(np.float32)
        return {"image": high_res_img, "array_4band": arr_4band}

    @staticmethod
    def latlon_to_tile(lat: float, lon: float, zoom: int) -> Tuple[int, int]:
        """Converts latitude, longitude to Web Mercator tile numbers (X, Y) at given zoom level."""
        lat_rad = math.radians(lat)
        n = 2.0 ** zoom
        x_tile = int((lon + 180.0) / 360.0 * n)
        y_tile = int((1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
        return x_tile, y_tile
