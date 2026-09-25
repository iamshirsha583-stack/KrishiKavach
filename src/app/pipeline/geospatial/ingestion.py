"""
KrishiKavach Geospatial Data Ingestion Module.

This module provides tools to:
1. Ingest polygon boundaries from GeoJSON files (e.g., village_grids.geojson) using GeoPandas.
2. Extract bounding box coordinates (minx, miny, maxx, maxy) for specific village IDs.
3. Load paired pre-disaster (T1) and post-disaster (T2) GeoTIFF satellite tiles from cache using Rasterio,
   with robust fallback mock data generation when tiles are missing.
4. Normalize multi-band raster arrays (B2, B3, B4, B8) into 0.0 - 1.0 float32 PyTorch tensors resized to (512, 512).
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

# Optional / conditional imports with graceful fallbacks
try:
    import geopandas as gpd
    from shapely.geometry import Polygon, box
    GEOPANDAS_AVAILABLE = True
except ImportError:
    gpd = None  # type: ignore
    Polygon = None  # type: ignore
    box = None  # type: ignore
    GEOPANDAS_AVAILABLE = False

try:
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds
    RASTERIO_AVAILABLE = True
except ImportError:
    rasterio = None  # type: ignore
    Resampling = None  # type: ignore
    from_bounds = None  # type: ignore
    RASTERIO_AVAILABLE = False

try:
    import torch
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore
    F = None  # type: ignore
    TORCH_AVAILABLE = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("KrishiKavach.GeospatialIngestion")

# Type alias for bounding box: (minx, miny, maxx, maxy)
BoundingBox = Tuple[float, float, float, float]

# Expected Sentinel-2 Band Ordering
BAND_NAMES: List[str] = ["B2", "B3", "B4", "B8"]  # Blue, Green, Red, NIR (10m resolution)
TARGET_CHANNELS: int = 4
TARGET_IMAGE_SIZE: Tuple[int, int] = (512, 512)
DEFAULT_MAX_REFLECTANCE: float = 10000.0  # Sentinel-2 L2A BOA reflectance scale factor


@dataclass
class PairedRasterData:
    """Dataclass encapsulating paired pre- and post-disaster normalized satellite tensors and metadata."""
    village_id: str
    bbox: BoundingBox
    pre_disaster_tensor: Any  # torch.Tensor of shape (4, 512, 512) or np.ndarray if torch not installed
    post_disaster_tensor: Any  # torch.Tensor of shape (4, 512, 512) or np.ndarray if torch not installed
    band_names: List[str] = field(default_factory=lambda: list(BAND_NAMES))
    is_mock: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> Dict[str, Any]:
        """Returns a concise summary dictionary of the paired raster data."""
        pre_shape = tuple(self.pre_disaster_tensor.shape) if hasattr(self.pre_disaster_tensor, "shape") else None
        post_shape = tuple(self.post_disaster_tensor.shape) if hasattr(self.post_disaster_tensor, "shape") else None
        return {
            "village_id": self.village_id,
            "bbox": self.bbox,
            "pre_shape": pre_shape,
            "post_shape": post_shape,
            "bands": self.band_names,
            "is_mock": self.is_mock,
            "metadata": self.metadata,
        }


class GeospatialIngestionPipeline:
    """
    Ingestion pipeline for reading village boundaries, extracting coordinate extents,
    and loading/normalizing paired multi-spectral satellite imagery for AI inference.
    """

    def __init__(
        self,
        geojson_path: Union[str, Path] = "data/geojson/village_grids.geojson",
        cache_dir: Union[str, Path] = "data/cache/demo",
        target_size: Tuple[int, int] = TARGET_IMAGE_SIZE,
        max_reflectance: float = DEFAULT_MAX_REFLECTANCE,
        force_mock: bool = False,
    ):
        """
        Initialize the Geospatial Ingestion Pipeline.

        :param geojson_path: Path to the GeoJSON file containing village polygon boundaries.
        :param cache_dir: Directory where T1 (pre) and T2 (post) GeoTIFF tiles are stored.
        :param target_size: Output spatial dimensions (height, width), default is (512, 512).
        :param max_reflectance: Value used to scale Digital Numbers (DN) to 0.0 - 1.0 (default: 10000.0).
        :param force_mock: If True, bypasses disk reading and generates mock tensors directly.
        """
        self.geojson_path = Path(geojson_path)
        self.cache_dir = Path(cache_dir)
        self.target_size = target_size
        self.max_reflectance = max_reflectance
        self.force_mock = force_mock
        self._gdf_cache: Optional[Any] = None

    # =========================================================================
    # 1. GeoPandas Polygon Boundary Reading
    # =========================================================================

    def load_boundaries(self) -> Any:
        """
        Loads the polygon boundaries GeoDataFrame from the specified GeoJSON file.
        Caches the loaded GeoDataFrame in memory.

        :return: GeoPandas GeoDataFrame (or mock dictionary structure if GeoPandas is unavailable).
        """
        if self._gdf_cache is not None:
            return self._gdf_cache

        if not self.geojson_path.exists():
            logger.warning(
                f"GeoJSON file not found at '{self.geojson_path}'. Operating in mock boundary fallback mode."
            )
            return self._generate_mock_geodataframe()

        if not GEOPANDAS_AVAILABLE:
            logger.warning(
                "GeoPandas is not installed. Loading GeoJSON using mock fallback structure."
            )
            return self._generate_mock_geodataframe()

        try:
            logger.info(f"Loading village boundary polygons from '{self.geojson_path}'...")
            gdf = gpd.read_file(self.geojson_path)
            self._gdf_cache = gdf
            logger.info(f"Successfully loaded {len(gdf)} village polygons.")
            return gdf
        except Exception as e:
            logger.error(f"Failed to read GeoJSON at '{self.geojson_path}': {e}. Using mock boundaries.")
            return self._generate_mock_geodataframe()

    def _generate_mock_geodataframe(self) -> Any:
        """Generates a synthetic GeoDataFrame with sample village boundaries."""
        sample_data = [
            {
                "village_id": "VILLAGE_001",
                "village_name": "Rampur",
                "district": "Cuttack",
                "state": "Odisha",
                "minx": 85.8200, "miny": 20.4600, "maxx": 85.8700, "maxy": 20.5100,
            },
            {
                "village_id": "VILLAGE_002",
                "village_name": "Kalyanpur",
                "district": "Puri",
                "state": "Odisha",
                "minx": 85.7800, "miny": 19.8000, "maxx": 85.8300, "maxy": 19.8500,
            },
            {
                "village_id": "DEMO_VILLAGE",
                "village_name": "KrishiKavach Demo Farm",
                "district": "Khordha",
                "state": "Odisha",
                "minx": 85.7000, "miny": 20.2000, "maxx": 85.7500, "maxy": 20.2500,
            },
        ]

        if GEOPANDAS_AVAILABLE and box is not None:
            geometries = [box(d["minx"], d["miny"], d["maxx"], d["maxy"]) for d in sample_data]
            gdf = gpd.GeoDataFrame(sample_data, geometry=geometries, crs="EPSG:4326")
            self._gdf_cache = gdf
            return gdf

        # Fallback dict container if GeoPandas is not installed
        return sample_data

    # =========================================================================
    # 2. Bounding Box Coordinates Extraction
    # =========================================================================

    def get_village_bbox(self, village_id: str) -> BoundingBox:
        """
        Extracts bounding box coordinates (minx, miny, maxx, maxy) for a given village_id.

        :param village_id: Identifier of the village (matches 'village_id', 'id', 'VILLAGE_ID', 'grid_id', etc.).
        :return: Tuple of floats (minx, miny, maxx, maxy).
        :raises ValueError: If the village is not found and mock fallback is disabled.
        """
        gdf = self.load_boundaries()

        if GEOPANDAS_AVAILABLE and isinstance(gdf, gpd.GeoDataFrame):
            # Attempt to match common ID column names
            id_col = None
            possible_cols = ["village_id", "id", "VILLAGE_ID", "grid_id", "GRID_ID", "village_name", "Name", "name"]
            for col in possible_cols:
                if col in gdf.columns:
                    id_col = col
                    break

            if id_col is not None:
                matches = gdf[gdf[id_col].astype(str).str.lower() == str(village_id).lower()]
                if not matches.empty:
                    bounds = matches.total_bounds  # (minx, miny, maxx, maxy)
                    bbox = (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
                    logger.info(f"Extracted bounding box for '{village_id}': {bbox}")
                    return bbox

            # If not matched by column, try index or fallback
            logger.warning(f"Village ID '{village_id}' not found in GeoDataFrame columns. Using mock bounding box.")
        elif isinstance(gdf, list):
            for item in gdf:
                if item.get("village_id", "").lower() == str(village_id).lower():
                    return (float(item["minx"]), float(item["miny"]), float(item["maxx"]), float(item["maxy"]))

        # Deterministic synthetic bounding box generation based on hash for unlisted IDs
        logger.info(f"Generating deterministic mock bounding box for '{village_id}'.")
        seed = sum(ord(c) for c in str(village_id))
        base_lon = 85.0 + (seed % 100) * 0.01
        base_lat = 20.0 + ((seed * 7) % 100) * 0.01
        delta = 0.045  # ~5km grid box
        return (round(base_lon, 4), round(base_lat, 4), round(base_lon + delta, 4), round(base_lat + delta, 4))

    # =========================================================================
    # 3. GeoTIFF Tile Loader (Rasterio with Mock Fallback)
    # =========================================================================

    def _resolve_tile_paths(self, village_id: str) -> Tuple[Optional[Path], Optional[Path]]:
        """
        Searches the cache directory for matching pre-disaster (T1) and post-disaster (T2) GeoTIFF files.

        :param village_id: Identifier of the village.
        :return: Tuple of (t1_path, t2_path), either of which can be None if not found.
        """
        vid_clean = str(village_id).lower().replace(" ", "_")
        
        # Candidate file naming conventions for T1 (pre) and T2 (post)
        t1_patterns = [
            f"village_{vid_clean}_t1.tif",
            f"village_{vid_clean}_t1.tiff",
            f"{vid_clean}_t1.tif",
            f"{vid_clean}_pre.tif",
            f"{vid_clean}_pre_disaster.tif",
            f"t1_{vid_clean}.tif",
            "t1_demo.tif",
            "pre_disaster_demo.tif",
        ]
        t2_patterns = [
            f"village_{vid_clean}_t2.tif",
            f"village_{vid_clean}_t2.tiff",
            f"{vid_clean}_t2.tif",
            f"{vid_clean}_post.tif",
            f"{vid_clean}_post_disaster.tif",
            f"t2_{vid_clean}.tif",
            "t2_demo.tif",
            "post_disaster_demo.tif",
        ]

        t1_path: Optional[Path] = None
        t2_path: Optional[Path] = None

        if self.cache_dir.exists():
            for pat in t1_patterns:
                p = self.cache_dir / pat
                if p.is_file():
                    t1_path = p
                    break

            for pat in t2_patterns:
                p = self.cache_dir / pat
                if p.is_file():
                    t2_path = p
                    break

        return t1_path, t2_path

    def _read_geotiff_raster(self, file_path: Path) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Reads a multi-band GeoTIFF raster using Rasterio.

        :param file_path: Absolute or relative path to the GeoTIFF file.
        :return: Tuple of (numpy array of shape [C, H, W], metadata dictionary).
        """
        if not RASTERIO_AVAILABLE:
            raise ImportError("Rasterio is required to read GeoTIFF files directly.")

        with rasterio.open(file_path) as src:
            data = src.read()  # Shape: (count, height, width)
            meta = src.meta.copy()
            meta.update({
                "crs": str(src.crs),
                "transform": src.transform,
                "bounds": src.bounds,
                "count": src.count,
            })
            return data, meta

    def _generate_mock_raster_pair(
        self,
        village_id: str,
        bbox: BoundingBox
    ) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
        """
        Generates realistic synthetic 4-band Sentinel-2 reflectance arrays for T1 (pre) and T2 (post).
        
        Bands:
        - B2 (Blue): ~490 nm (water higher, vegetation low)
        - B3 (Green): ~560 nm (vegetation peak in visible)
        - B4 (Red): ~665 nm (chlorophyll absorption)
        - B8 (NIR): ~842 nm (healthy canopy high reflectance)

        Pre-disaster (T1): Healthy lush agricultural vegetation (High NIR B8, Low Red B4).
        Post-disaster (T2): Inundated / damaged agricultural land (Water attenuation in NIR, sediment shift in Red).
        """
        h, w = self.target_size
        rng = np.random.RandomState(seed=abs(hash(village_id)) % (2**31 - 1))

        # Base spatial gradient (terrain / field structure)
        x = np.linspace(0, 1, w)
        y = np.linspace(0, 1, h)
        xx, yy = np.meshgrid(x, y)
        field_pattern = np.sin(xx * 8 * np.pi) * np.cos(yy * 8 * np.pi) * 0.15 + 0.5

        # --- T1: Pre-disaster (Healthy Crops & Fields) ---
        # Sentinel-2 Digital Numbers (DN) typically 0 - 10000
        t1_b2 = np.clip((0.04 + 0.03 * field_pattern + rng.normal(0, 0.005, (h, w))) * self.max_reflectance, 0, self.max_reflectance)
        t1_b3 = np.clip((0.08 + 0.05 * field_pattern + rng.normal(0, 0.008, (h, w))) * self.max_reflectance, 0, self.max_reflectance)
        t1_b4 = np.clip((0.05 + 0.04 * field_pattern + rng.normal(0, 0.006, (h, w))) * self.max_reflectance, 0, self.max_reflectance)
        t1_b8 = np.clip((0.45 + 0.25 * field_pattern + rng.normal(0, 0.020, (h, w))) * self.max_reflectance, 0, self.max_reflectance)
        t1_array = np.stack([t1_b2, t1_b3, t1_b4, t1_b8], axis=0).astype(np.float32)

        # --- T2: Post-disaster (Simulated Flood / Cyclone / Drought Inundation) ---
        # Simulating flooded riverbed / inundated fields across the center
        flood_mask = ((yy - 0.5 * xx - 0.2) ** 2 < 0.03).astype(np.float32)
        damaged_fields = (1.0 - flood_mask) * field_pattern * 0.4  # reduced biomass

        t2_b2 = np.clip((0.08 * flood_mask + (0.05 + 0.03 * damaged_fields) * (1 - flood_mask) + rng.normal(0, 0.005, (h, w))) * self.max_reflectance, 0, self.max_reflectance)
        t2_b3 = np.clip((0.10 * flood_mask + (0.06 + 0.03 * damaged_fields) * (1 - flood_mask) + rng.normal(0, 0.008, (h, w))) * self.max_reflectance, 0, self.max_reflectance)
        t2_b4 = np.clip((0.07 * flood_mask + (0.12 + 0.05 * damaged_fields) * (1 - flood_mask) + rng.normal(0, 0.006, (h, w))) * self.max_reflectance, 0, self.max_reflectance)
        t2_b8 = np.clip((0.03 * flood_mask + (0.18 + 0.10 * damaged_fields) * (1 - flood_mask) + rng.normal(0, 0.015, (h, w))) * self.max_reflectance, 0, self.max_reflectance)
        t2_array = np.stack([t2_b2, t2_b3, t2_b4, t2_b8], axis=0).astype(np.float32)

        meta = {
            "driver": "MockGenerator",
            "dtype": "float32",
            "nodata": None,
            "width": w,
            "height": h,
            "count": TARGET_CHANNELS,
            "crs": "EPSG:4326",
            "bounds": bbox,
            "bands": BAND_NAMES,
            "simulation_note": "Synthetic Sentinel-2 pre/post disaster multi-spectral reflection pair",
        }

        return t1_array, t2_array, meta

    # =========================================================================
    # 4. Multi-Band Normalization & Resizing for PyTorch Inference
    # =========================================================================

    def normalize_and_resize_raster(
        self,
        raster_data: Union[np.ndarray, Any],
        target_size: Optional[Tuple[int, int]] = None
    ) -> Any:
        """
        Normalizes multi-band raster arrays (B2, B3, B4, B8) into 0.0 - 1.0 float32 tensors
        resized to (512, 512) for PyTorch inference.

        :param raster_data: Numpy array or PyTorch tensor of shape (C, H, W) or (H, W, C).
        :param target_size: Desired spatial dimension (height, width), default is self.target_size.
        :return: Normalized float32 PyTorch Tensor of shape (4, target_h, target_w).
                 If PyTorch is not available, returns normalized float32 numpy.ndarray.
        """
        target_size = target_size or self.target_size

        # Convert input to numpy array if it isn't already
        if hasattr(raster_data, "detach"):
            arr = raster_data.detach().cpu().numpy()
        elif isinstance(raster_data, np.ndarray):
            arr = raster_data.copy()
        else:
            arr = np.array(raster_data, dtype=np.float32)

        # Handle channel dimension: standard shape should be (C, H, W)
        if arr.ndim == 2:
            arr = np.expand_dims(arr, axis=0)  # (1, H, W)
        elif arr.ndim == 3:
            if arr.shape[0] not in (1, 3, 4, 8, 12, 13) and arr.shape[-1] in (1, 3, 4):
                # Shape is (H, W, C), transpose to (C, H, W)
                arr = np.transpose(arr, (2, 0, 1))

        # Ensure we have at least 4 bands (B2, B3, B4, B8)
        c, h, w = arr.shape
        if c < TARGET_CHANNELS:
            # Replicate channels to match 4
            pad_channels = np.repeat(arr[-1:], TARGET_CHANNELS - c, axis=0)
            arr = np.concatenate([arr, pad_channels], axis=0)
        elif c > TARGET_CHANNELS:
            # Slice first 4 channels
            arr = arr[:TARGET_CHANNELS, :, :]

        # Normalization: Sentinel-2 L2A BOA reflectance scaling (0 - 10000 -> 0.0 - 1.0)
        arr = arr.astype(np.float32)
        if np.nanmax(arr) > 1.0:
            arr = arr / float(self.max_reflectance)

        # Clip values strictly between 0.0 and 1.0 to eliminate extreme outliers / cloud glint
        arr = np.clip(arr, 0.0, 1.0)
        np.nan_to_num(arr, copy=False, nan=0.0, posinf=1.0, neginf=0.0)

        # Resizing and PyTorch Tensor conversion
        if TORCH_AVAILABLE and torch is not None:
            tensor = torch.from_numpy(arr).float()  # (C, H, W)
            if (h, w) != target_size:
                # Add batch dimension for interpolate: (1, C, H, W)
                tensor_batched = tensor.unsqueeze(0)
                resized_batched = F.interpolate(
                    tensor_batched,
                    size=target_size,
                    mode="bilinear",
                    align_corners=False
                )
                tensor = resized_batched.squeeze(0)  # (C, target_h, target_w)
            return tensor
        else:
            # Fallback bilinear resize using numpy if PyTorch is not present
            if (h, w) != target_size:
                resized_arr = self._numpy_resize_bilinear(arr, target_size)
                return resized_arr.astype(np.float32)
            return arr.astype(np.float32)

    @staticmethod
    def _numpy_resize_bilinear(arr: np.ndarray, target_size: Tuple[int, int]) -> np.ndarray:
        """Pure numpy fallback for bilinear interpolation across C channels."""
        c, h, w = arr.shape
        th, tw = target_size
        y_indices = np.linspace(0, h - 1, th)
        x_indices = np.linspace(0, w - 1, tw)

        y_low = np.floor(y_indices).astype(int)
        y_high = np.clip(y_low + 1, 0, h - 1)
        y_weight = (y_indices - y_low)[:, None]

        x_low = np.floor(x_indices).astype(int)
        x_high = np.clip(x_low + 1, 0, w - 1)
        x_weight = (x_indices - x_low)[None, :]

        resized = np.empty((c, th, tw), dtype=np.float32)
        for i in range(c):
            channel = arr[i]
            top = channel[y_low[:, None], x_low] * (1 - x_weight) + channel[y_low[:, None], x_high] * x_weight
            bottom = channel[y_high[:, None], x_low] * (1 - x_weight) + channel[y_high[:, None], x_high] * x_weight
            resized[i] = top * (1 - y_weight) + bottom * y_weight

        return resized

    # =========================================================================
    # 5. Paired Loader Orchestrator
    # =========================================================================

    def load_paired_satellite_imagery(
        self,
        village_id: str,
        mock_if_missing: bool = True
    ) -> PairedRasterData:
        """
        Loads paired pre-disaster (T1) and post-disaster (T2) GeoTIFF tiles from cache,
        normalizes multi-band arrays (B2, B3, B4, B8) into 0.0 - 1.0 float32 tensors resized to (512, 512).
        Falls back to mock mode if files do not exist or force_mock is active.

        :param village_id: Target village identifier.
        :param mock_if_missing: If True, falls back to generating mock data when GeoTIFFs are missing.
        :return: PairedRasterData object containing pre/post PyTorch tensors and spatial metadata.
        """
        bbox = self.get_village_bbox(village_id)

        if self.force_mock:
            logger.info(f"Force mock enabled. Generating mock paired rasters for village '{village_id}'.")
            t1_raw, t2_raw, meta = self._generate_mock_raster_pair(village_id, bbox)
            t1_tensor = self.normalize_and_resize_raster(t1_raw)
            t2_tensor = self.normalize_and_resize_raster(t2_raw)
            return PairedRasterData(
                village_id=village_id,
                bbox=bbox,
                pre_disaster_tensor=t1_tensor,
                post_disaster_tensor=t2_tensor,
                is_mock=True,
                metadata=meta,
            )

        t1_path, t2_path = self._resolve_tile_paths(village_id)
        both_exist = (t1_path is not None and t2_path is not None and RASTERIO_AVAILABLE)

        if both_exist and t1_path and t2_path:
            try:
                logger.info(f"Loading GeoTIFF T1 from '{t1_path}' and T2 from '{t2_path}'...")
                t1_raw, meta_t1 = self._read_geotiff_raster(t1_path)
                t2_raw, meta_t2 = self._read_geotiff_raster(t2_path)

                t1_tensor = self.normalize_and_resize_raster(t1_raw)
                t2_tensor = self.normalize_and_resize_raster(t2_raw)

                combined_meta = {
                    "t1_path": str(t1_path),
                    "t2_path": str(t2_path),
                    "t1_meta": meta_t1,
                    "t2_meta": meta_t2,
                }

                return PairedRasterData(
                    village_id=village_id,
                    bbox=bbox,
                    pre_disaster_tensor=t1_tensor,
                    post_disaster_tensor=t2_tensor,
                    is_mock=False,
                    metadata=combined_meta,
                )
            except Exception as err:
                logger.warning(f"Error loading GeoTIFF tiles ({err}). Falling back to mock data.")
                if not mock_if_missing:
                    raise

        if not mock_if_missing:
            raise FileNotFoundError(
                f"Could not find paired GeoTIFF tiles for village '{village_id}' in '{self.cache_dir}'."
            )

        logger.info(f"GeoTIFF tiles not found in cache. Generating mock paired rasters for village '{village_id}'.")
        t1_raw, t2_raw, meta = self._generate_mock_raster_pair(village_id, bbox)
        t1_tensor = self.normalize_and_resize_raster(t1_raw)
        t2_tensor = self.normalize_and_resize_raster(t2_raw)

        return PairedRasterData(
            village_id=village_id,
            bbox=bbox,
            pre_disaster_tensor=t1_tensor,
            post_disaster_tensor=t2_tensor,
            is_mock=True,
            metadata=meta,
        )


# =============================================================================
# Functional Public API Helpers
# =============================================================================

def load_village_boundaries(
    geojson_path: Union[str, Path] = "data/geojson/village_grids.geojson"
) -> Any:
    """Convenience function to load polygon boundaries using GeoPandas."""
    pipeline = GeospatialIngestionPipeline(geojson_path=geojson_path)
    return pipeline.load_boundaries()


def extract_village_bbox(
    village_id: str,
    geojson_path: Union[str, Path] = "data/geojson/village_grids.geojson"
) -> BoundingBox:
    """Convenience function to extract (minx, miny, maxx, maxy) bounding box for a given village_id."""
    pipeline = GeospatialIngestionPipeline(geojson_path=geojson_path)
    return pipeline.get_village_bbox(village_id)


def load_paired_raster_tensors(
    village_id: str,
    geojson_path: Union[str, Path] = "data/geojson/village_grids.geojson",
    cache_dir: Union[str, Path] = "data/cache/demo",
    target_size: Tuple[int, int] = TARGET_IMAGE_SIZE,
    max_reflectance: float = DEFAULT_MAX_REFLECTANCE,
    force_mock: bool = False
) -> PairedRasterData:
    """
    Convenience function to ingest paired T1/T2 Sentinel-2 rasters normalized and resized to (512, 512).

    :param village_id: Unique identifier for the village.
    :param geojson_path: Path to village boundary polygons.
    :param cache_dir: Path to directory containing cached GeoTIFFs.
    :param target_size: Spatial shape (512, 512).
    :param max_reflectance: Scale factor for Sentinel-2 DN to float (10000.0).
    :param force_mock: Force mock data generation.
    :return: PairedRasterData containing pre- and post-disaster tensors and metadata.
    """
    pipeline = GeospatialIngestionPipeline(
        geojson_path=geojson_path,
        cache_dir=cache_dir,
        target_size=target_size,
        max_reflectance=max_reflectance,
        force_mock=force_mock,
    )
    return pipeline.load_paired_satellite_imagery(village_id=village_id)


if __name__ == "__main__":
    print("--- KrishiKavach Geospatial Ingestion Test Run ---")
    test_village_id = "VILLAGE_001"
    
    # 1. Test Bounding Box extraction
    pipeline = GeospatialIngestionPipeline()
    bbox = pipeline.get_village_bbox(test_village_id)
    print(f"[1] Village ID: {test_village_id} -> Bounding Box (minx, miny, maxx, maxy): {bbox}")

    # 2. Test Paired Imagery Ingestion with Mock Fallback
    paired_data = pipeline.load_paired_satellite_imagery(test_village_id)
    print(f"[2] Ingestion Result Summary:")
    for k, v in paired_data.summary().items():
        print(f"    - {k}: {v}")

    # 3. Verify Tensor Properties
    t1 = paired_data.pre_disaster_tensor
    t2 = paired_data.post_disaster_tensor
    print(f"[3] Pre-disaster Tensor Type: {type(t1)}, Shape: {t1.shape}, Min: {float(t1.min()):.4f}, Max: {float(t1.max()):.4f}")
    print(f"    Post-disaster Tensor Type: {type(t2)}, Shape: {t2.shape}, Min: {float(t2.min()):.4f}, Max: {float(t2.max()):.4f}")
    print("--- Ingestion Pipeline executed successfully ---")
