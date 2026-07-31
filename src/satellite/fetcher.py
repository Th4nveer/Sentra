"""
Satellite Imagery Fetcher Facade Module.
Coordinates real satellite image retrieval via Esri World Imagery Wayback & high-res multispectral providers.
"""
import os
from datetime import datetime, timedelta
import numpy as np
from PIL import Image
from typing import Dict, Any, Tuple, Optional

from src.satellite.wayback_api import EsriWaybackClient
from src.satellite.synthetic_provider import SyntheticSatelliteProvider


class SatelliteFetcher:
    def __init__(self, cache_dir: str = "./data/satellite_cache"):
        self.cache_dir = cache_dir
        self.synthetic_provider = SyntheticSatelliteProvider()
        self.wayback_client = EsriWaybackClient()
        os.makedirs(self.cache_dir, exist_ok=True)

    def fetch_dual_temporal_imagery(
        self,
        tender_id: str,
        bounding_box: list,
        start_date: str,
        completion_date: str,
        project_type: str = "road_resurfacing",
        scenario_override: Optional[str] = None,
        buffer_months: int = 3
    ) -> Dict[str, Any]:
        """
        Retrieves pre-project (Before) and post-project (After) dual-temporal satellite arrays.
        Uses real historical high-resolution satellite imagery crops from Esri World Imagery Wayback
        (livingatlas.arcgis.com/wayback).
        
        The 'after' image is fetched at completion_date + buffer_months to account for
        realistic construction timelines and verification delays.
        """
        tender_cache_dir = os.path.join(self.cache_dir, tender_id)
        os.makedirs(tender_cache_dir, exist_ok=True)

        # Calculate buffered after-date (completion + 2-3 months)
        try:
            completion_dt = datetime.strptime(completion_date, "%Y-%m-%d")
            buffered_after_dt = completion_dt + timedelta(days=buffer_months * 30)
            buffered_after_date = buffered_after_dt.strftime("%Y-%m-%d")
        except ValueError:
            buffered_after_date = completion_date

        if scenario_override is not None:
            # Demo mode simulation
            before_arr, after_arr = self.synthetic_provider.generate_pair(
                project_type=project_type,
                scenario=scenario_override,
                image_size=(256, 256),
                seed=abs(hash(tender_id)) % 100000
            )
            before_img = Image.fromarray((before_arr[:, :, :3] * 255).astype(np.uint8))
            after_img = Image.fromarray((after_arr[:, :, :3] * 255).astype(np.uint8))
            source_name = "PlanetScope-Synthetic Multispectral Baseline"
        else:
            # Real satellite imagery query via Esri World Imagery Wayback (Floor date for start, Ceiling date for completion)
            print(f"[SatelliteFetcher] Fetching 'before' satellite crop for start date: {start_date} (using closest floor release <= {start_date})")
            before_crop = self.wayback_client.fetch_satellite_crop(bounding_box, start_date, is_start_date=True)

            print(f"[SatelliteFetcher] Fetching 'after' satellite crop for date: {buffered_after_date} (completion {completion_date} + {buffer_months}mo buffer)")
            after_crop = self.wayback_client.fetch_satellite_crop(bounding_box, buffered_after_date, is_start_date=False, zoom_level=15)

            before_arr = before_crop["array_4band"]
            after_arr = after_crop["array_4band"]
            before_img = before_crop["rgb_image"]
            after_img = after_crop["rgb_image"]
            before_date = before_crop.get("date", start_date)
            after_date = after_crop.get("date", buffered_after_date)
            source_name = f"Esri Wayback ({before_date} vs {after_date})"

        # Save local cached artifacts
        before_npy_path = os.path.join(tender_cache_dir, "before_4band.npy")
        after_npy_path = os.path.join(tender_cache_dir, "after_4band.npy")
        before_png_path = os.path.join(tender_cache_dir, "before_rgb.png")
        after_png_path = os.path.join(tender_cache_dir, "after_rgb.png")

        np.save(before_npy_path, before_arr)
        np.save(after_npy_path, after_arr)

        before_img.save(before_png_path)
        after_img.save(after_png_path)

        return {
            "tender_id": tender_id,
            "source": source_name,
            "bounding_box": bounding_box,
            "start_date": start_date,
            "completion_date": completion_date,
            "buffered_after_date": buffered_after_date,
            "before_date": before_date if not scenario_override else start_date,
            "after_date": after_date if not scenario_override else buffered_after_date,
            "buffer_months": buffer_months,
            "before_npy_path": before_npy_path,
            "after_npy_path": after_npy_path,
            "before_png_path": before_png_path,
            "after_png_path": after_png_path,
            "before_array": before_arr,
            "after_array": after_arr,
            "spatial_resolution": "Sub-5m/pixel"
        }
