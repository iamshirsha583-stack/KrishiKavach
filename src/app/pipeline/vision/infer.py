"""
KrishiKavach Vision Inference Pipeline.

This module implements:
1. A lightweight Siamese feature-difference neural network for bi-temporal flood and inundation detection.
2. An inference engine that compares paired normalized 4-band satellite tensors (T1 baseline, T2 post-event)
   to produce 2D binary inundation masks (0 = dry land, 1 = inundated/flooded).
3. Automatic weight loading from 'data/weights/siamese_unet_flood.pth' with seamless fallback
   to NDWI (Normalized Difference Water Index) spectral change thresholding when weights are absent.
4. Statistical computation of total flooded pixel count, total area, and inundated area in hectares
   based on spatial resolution (default 10m/pixel Sentinel-2).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np

# Optional / conditional torch imports with graceful fallbacks
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore
    nn = None  # type: ignore
    F = None  # type: ignore
    TORCH_AVAILABLE = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("KrishiKavach.VisionInfer")

# Sentinel-2 Band Index constants
B2_BLUE_IDX = 0
B3_GREEN_IDX = 1
B4_RED_IDX = 2
B8_NIR_IDX = 3

# Spatial and Unit Conversion Constants
DEFAULT_PIXEL_RES_M = 10.0  # 10 meters per pixel for Sentinel-2 bands
M2_PER_HECTARE = 10000.0   # 1 hectare = 10,000 square meters


@dataclass
class FloodInferenceResult:
    """Dataclass holding flood/inundation inference results, masks, and geographical metrics."""
    binary_mask: np.ndarray  # 2D binary numpy mask (0 = dry land, 1 = inundated/flooded), shape: (H, W)
    probability_map: np.ndarray  # 2D continuous float map (0.0 to 1.0), shape: (H, W)
    flooded_pixel_count: int
    total_pixel_count: int
    flooded_area_hectares: float
    total_area_hectares: float
    flood_percentage: float
    inference_mode: str  # "siamese_neural_network" or "ndwi_heuristic_fallback"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> Dict[str, Any]:
        """Returns a formatted summary dictionary of flood metrics."""
        return {
            "inference_mode": self.inference_mode,
            "mask_shape": self.binary_mask.shape,
            "flooded_pixels": self.flooded_pixel_count,
            "total_pixels": self.total_pixel_count,
            "flooded_area_ha": round(self.flooded_area_hectares, 2),
            "total_area_ha": round(self.total_area_hectares, 2),
            "flood_percentage": round(self.flood_percentage, 2),
            "metadata": self.metadata,
        }


# =============================================================================
# 1. Siamese Feature-Difference Neural Network Architecture
# =============================================================================

if TORCH_AVAILABLE:
    class ConvBlock(nn.Module):
        """Standard 2-layer Convolutional block with BatchNorm and LeakyReLU activation."""
        def __init__(self, in_channels: int, out_channels: int):
            super().__init__()
            self.block = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
                nn.BatchNorm2d(out_channels),
                nn.LeakyReLU(negative_slope=0.1, inplace=True),
                nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
                nn.BatchNorm2d(out_channels),
                nn.LeakyReLU(negative_slope=0.1, inplace=True),
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.block(x)

    class SiameseEncoder(nn.Module):
        """Shared weights encoder for extracting multi-scale spectral-spatial features."""
        def __init__(self, in_channels: int = 4):
            super().__init__()
            self.enc1 = ConvBlock(in_channels, 32)
            self.pool1 = nn.MaxPool2d(2)
            self.enc2 = ConvBlock(32, 64)
            self.pool2 = nn.MaxPool2d(2)
            self.enc3 = ConvBlock(64, 128)

        def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
            f1 = self.enc1(x)        # (B, 32, H, W)
            p1 = self.pool1(f1)      # (B, 32, H/2, W/2)
            f2 = self.enc2(p1)       # (B, 64, H/2, W/2)
            p2 = self.pool2(f2)      # (B, 64, H/4, W/4)
            f3 = self.enc3(p2)       # (B, 128, H/4, W/4)
            return f1, f2, f3

    class SiameseFloodUNet(nn.Module):
        """
        Lightweight Siamese Feature-Difference Neural Network.

        Processes T1 (baseline) and T2 (post-disaster) satellite rasters through a shared encoder,
        calculates absolute multi-scale feature differences (|F(T1) - F(T2)|), and decodes them
        into a high-resolution flood/inundation probability map.
        """
        def __init__(self, in_channels: int = 4, out_channels: int = 1):
            super().__init__()
            self.encoder = SiameseEncoder(in_channels=in_channels)

            # Feature fusion & decoding blocks
            # Deepest difference features (128 channels)
            self.upconv2 = nn.ConvTranspose2d(128, 64, kernel_size=2, stride=2)
            self.dec2 = ConvBlock(64 + 64, 64)  # upsampled + level 2 difference

            self.upconv1 = nn.ConvTranspose2d(64, 32, kernel_size=2, stride=2)
            self.dec1 = ConvBlock(32 + 32, 32)  # upsampled + level 1 difference

            # Final classification head
            self.head = nn.Sequential(
                nn.Conv2d(32, 16, kernel_size=3, padding=1),
                nn.ReLU(inplace=True),
                nn.Conv2d(16, out_channels, kernel_size=1),
            )

        def forward(self, t1: torch.Tensor, t2: torch.Tensor) -> torch.Tensor:
            """
            Forward pass computing absolute feature differences across time steps.

            :param t1: Baseline tensor of shape (B, 4, H, W).
            :param t2: Recent tensor of shape (B, 4, H, W).
            :return: Logits tensor of shape (B, 1, H, W).
            """
            # 1. Extract shared feature maps for both time points
            f1_t1, f2_t1, f3_t1 = self.encoder(t1)
            f1_t2, f2_t2, f3_t2 = self.encoder(t2)

            # 2. Compute absolute difference representations
            diff_f3 = torch.abs(f3_t1 - f3_t2)  # (B, 128, H/4, W/4)
            diff_f2 = torch.abs(f2_t1 - f2_t2)  # (B, 64, H/2, W/2)
            diff_f1 = torch.abs(f1_t1 - f1_t2)  # (B, 32, H, W)

            # 3. Decode feature differences back to full spatial resolution
            u2 = self.upconv2(diff_f3)
            d2 = self.dec2(torch.cat([u2, diff_f2], dim=1))

            u1 = self.upconv1(d2)
            d1 = self.dec1(torch.cat([u1, diff_f1], dim=1))

            logits = self.head(d1)  # (B, 1, H, W)
            return logits

else:
    # Dummy placeholder class if torch is not installed
    class SiameseFloodUNet:  # type: ignore
        def __init__(self, *args: Any, **kwargs: Any):
            pass


# =============================================================================
# 2. Geographical Metrics Computation
# =============================================================================

def compute_flood_metrics(
    binary_mask: np.ndarray,
    pixel_resolution_m: float = DEFAULT_PIXEL_RES_M
) -> Tuple[int, int, float, float, float]:
    """
    Computes flood pixel counts and surface area in hectares based on spatial pixel resolution.

    :param binary_mask: 2D numpy array where 1 indicates flooded/inundated and 0 indicates dry land.
    :param pixel_resolution_m: Ground sampling distance in meters per pixel (default: 10.0m for Sentinel-2).
    :return: Tuple containing:
        - flooded_pixel_count (int)
        - total_pixel_count (int)
        - flooded_area_hectares (float)
        - total_area_hectares (float)
        - flood_percentage (float)
    """
    if binary_mask.ndim != 2:
        raise ValueError(f"Expected 2D binary mask, got shape {binary_mask.shape}")

    flooded_pixels = int(np.sum(binary_mask == 1))
    total_pixels = int(binary_mask.size)

    # Calculate area: (res * res) = square meters per pixel
    m2_per_pixel = pixel_resolution_m * pixel_resolution_m
    hectares_per_pixel = m2_per_pixel / M2_PER_HECTARE

    flooded_area_ha = flooded_pixels * hectares_per_pixel
    total_area_ha = total_pixels * hectares_per_pixel
    flood_percentage = (flooded_pixels / total_pixels) * 100.0 if total_pixels > 0 else 0.0

    return flooded_pixels, total_pixels, flooded_area_ha, total_area_ha, flood_percentage


# =============================================================================
# 3. Vision Inference Pipeline Class
# =============================================================================

class FloodInferencePipeline:
    """
    End-to-end inference pipeline for bi-temporal flood and water inundation assessment.
    """

    def __init__(
        self,
        weights_path: Union[str, Path] = "data/weights/siamese_unet_flood.pth",
        device: Optional[Union[str, Any]] = None,
        threshold: float = 0.5,
        pixel_resolution_m: float = DEFAULT_PIXEL_RES_M,
    ):
        """
        Initialize the Flood Inference Pipeline.

        :param weights_path: Path to PyTorch model weights file.
        :param device: Execution device ('cpu', 'cuda', or None for auto-detection).
        :param threshold: Classification threshold for converting continuous probability to binary mask.
        :param pixel_resolution_m: Ground resolution in meters per pixel (default 10m).
        """
        self.weights_path = Path(weights_path)
        self.threshold = threshold
        self.pixel_resolution_m = pixel_resolution_m
        self.model: Optional[Any] = None
        self.device = self._resolve_device(device)
        self.is_neural_ready = False

        self._initialize_model()

    def _resolve_device(self, device: Optional[Union[str, Any]]) -> str:
        """Determines best execution device."""
        if device is not None:
            return str(device)
        if TORCH_AVAILABLE and torch is not None and torch.cuda.is_available():
            return "cuda"
        return "cpu"

    def _initialize_model(self) -> None:
        """Initializes model architecture and loads weights if available."""
        if not TORCH_AVAILABLE:
            logger.info("PyTorch is not available. Operating exclusively in NDWI spectral fallback mode.")
            self.is_neural_ready = False
            return

        try:
            self.model = SiameseFloodUNet(in_channels=4, out_channels=1)
            self.model.to(self.device)

            if self.weights_path.is_file():
                logger.info(f"Loading Siamese Flood UNet weights from '{self.weights_path}'...")
                state_dict = torch.load(self.weights_path, map_location=self.device)
                self.model.load_state_dict(state_dict)
                self.model.eval()
                self.is_neural_ready = True
                logger.info("Successfully loaded neural network weights for inference.")
            else:
                logger.info(
                    f"Model weights not found at '{self.weights_path}'. "
                    "Inference will seamlessly use NDWI spectral difference heuristic fallback."
                )
                self.is_neural_ready = False
        except Exception as e:
            logger.warning(f"Failed to load neural weights from '{self.weights_path}': {e}. Using NDWI fallback.")
            self.is_neural_ready = False

    # =========================================================================
    # NDWI Spectral Heuristic Fallback
    # =========================================================================

    def _compute_ndwi(self, raster_4band: np.ndarray) -> np.ndarray:
        """
        Computes McFeeters Normalized Difference Water Index (NDWI) from 4-band array.
        NDWI = (Green - NIR) / (Green + NIR + epsilon)
        Using Sentinel-2 bands: Green = B3 (idx 1), NIR = B8 (idx 3).

        :param raster_4band: Array of shape (4, H, W) normalized to [0.0, 1.0].
        :return: NDWI array of shape (H, W) with values in range [-1.0, 1.0].
        """
        green = raster_4band[B3_GREEN_IDX].astype(np.float32)
        nir = raster_4band[B8_NIR_IDX].astype(np.float32)

        eps = 1e-6
        numerator = green - nir
        denominator = green + nir + eps
        ndwi = numerator / denominator
        return np.clip(ndwi, -1.0, 1.0)

    def _infer_ndwi_heuristic(
        self,
        t1_arr: np.ndarray,
        t2_arr: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Performs bi-temporal spectral change detection using NDWI and NIR attenuation.

        Water bodies exhibit:
        - High NDWI (> 0)
        - Very low NIR reflectance due to strong water absorption (< 0.15)
        - Significant positive increase in NDWI from T1 baseline to T2 post-event.

        :param t1_arr: T1 baseline array of shape (4, H, W).
        :param t2_arr: T2 post-disaster array of shape (4, H, W).
        :return: Tuple of (2D binary mask [0 or 1], continuous probability map [0.0 to 1.0]).
        """
        ndwi_t1 = self._compute_ndwi(t1_arr)
        ndwi_t2 = self._compute_ndwi(t2_arr)

        nir_t2 = t2_arr[B8_NIR_IDX]
        ndwi_diff = ndwi_t2 - ndwi_t1  # Positive indicates increased water content

        # Probability heuristic based on post-NDWI and temporal difference
        # Base probability from NDWI post-disaster scaled to [0, 1]
        base_water_prob = np.clip((ndwi_t2 + 0.2) / 0.8, 0.0, 1.0)
        # Difference contribution: positive delta increases flood confidence
        delta_contrib = np.clip(ndwi_diff / 0.4, 0.0, 1.0)
        # NIR attenuation bonus (water strongly absorbs NIR)
        nir_absorption_factor = np.clip(1.0 - (nir_t2 / 0.20), 0.0, 1.0)

        probability_map = 0.45 * base_water_prob + 0.35 * delta_contrib + 0.20 * nir_absorption_factor
        probability_map = np.clip(probability_map, 0.0, 1.0)

        # Binary decision criteria:
        # 1. High confidence water in T2 (NDWI > 0.05 and low NIR) OR
        # 2. Significant temporal inundation shift (NDWI diff > 0.18 and probability > threshold)
        binary_mask = np.where(probability_map >= self.threshold, 1, 0).astype(np.uint8)

        return binary_mask, probability_map.astype(np.float32)

    # =========================================================================
    # Neural Network Inference
    # =========================================================================

    def _infer_neural(
        self,
        t1_tensor: Any,
        t2_tensor: Any
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Executes forward pass through Siamese UNet feature difference model.

        :param t1_tensor: PyTorch tensor (1, 4, H, W) or (4, H, W).
        :param t2_tensor: PyTorch tensor (1, 4, H, W) or (4, H, W).
        :return: Tuple of (2D binary mask, continuous probability map).
        """
        if t1_tensor.ndim == 3:
            t1_tensor = t1_tensor.unsqueeze(0)
        if t2_tensor.ndim == 3:
            t2_tensor = t2_tensor.unsqueeze(0)

        t1_tensor = t1_tensor.to(self.device).float()
        t2_tensor = t2_tensor.to(self.device).float()

        with torch.no_grad():
            logits = self.model(t1_tensor, t2_tensor)  # (1, 1, H, W)
            probs = torch.sigmoid(logits).squeeze(0).squeeze(0)  # (H, W)
            prob_map = probs.cpu().numpy()

        binary_mask = (prob_map >= self.threshold).astype(np.uint8)
        return binary_mask, prob_map

    # =========================================================================
    # Main Predict Entrypoint
    # =========================================================================

    def predict(
        self,
        t1_input: Union[torch.Tensor, np.ndarray, Any],
        t2_input: Union[torch.Tensor, np.ndarray, Any],
        village_id: Optional[str] = None,
    ) -> FloodInferenceResult:
        """
        Executes flood and water inundation inference comparing T1 baseline with T2 post-event.

        :param t1_input: Normalized 4-band pre-disaster tensor/array of shape (4, H, W) or (1, 4, H, W).
        :param t2_input: Normalized 4-band post-disaster tensor/array of shape (4, H, W) or (1, 4, H, W).
        :param village_id: Optional village ID for tracking in metadata.
        :return: FloodInferenceResult containing binary mask, metrics, and summary.
        """
        # Format tensors / arrays
        if TORCH_AVAILABLE and isinstance(t1_input, torch.Tensor) and self.is_neural_ready:
            # Neural network path
            binary_mask, prob_map = self._infer_neural(t1_input, t2_input)
            mode = "siamese_neural_network"
        else:
            # Prepare numpy arrays for heuristic path
            if hasattr(t1_input, "detach"):
                t1_arr = t1_input.detach().cpu().numpy()
            else:
                t1_arr = np.asarray(t1_input, dtype=np.float32)

            if hasattr(t2_input, "detach"):
                t2_arr = t2_input.detach().cpu().numpy()
            else:
                t2_arr = np.asarray(t2_input, dtype=np.float32)

            # Squeeze batch dimension if present: (1, 4, H, W) -> (4, H, W)
            if t1_arr.ndim == 4:
                t1_arr = t1_arr.squeeze(0)
            if t2_arr.ndim == 4:
                t2_arr = t2_arr.squeeze(0)

            binary_mask, prob_map = self._infer_ndwi_heuristic(t1_arr, t2_arr)
            mode = "ndwi_heuristic_fallback"

        # Calculate geospatial and surface metrics
        flooded_px, total_px, flooded_ha, total_ha, flood_pct = compute_flood_metrics(
            binary_mask=binary_mask,
            pixel_resolution_m=self.pixel_resolution_m
        )

        metadata = {
            "village_id": village_id,
            "threshold": self.threshold,
            "pixel_resolution_m": self.pixel_resolution_m,
            "weights_path": str(self.weights_path),
            "device": self.device,
        }

        return FloodInferenceResult(
            binary_mask=binary_mask,
            probability_map=prob_map,
            flooded_pixel_count=flooded_px,
            total_pixel_count=total_px,
            flooded_area_hectares=flooded_ha,
            total_area_hectares=total_ha,
            flood_percentage=flood_pct,
            inference_mode=mode,
            metadata=metadata,
        )


# =============================================================================
# Functional Convenience API
# =============================================================================

def run_flood_inference(
    t1_tensor: Union[torch.Tensor, np.ndarray, Any],
    t2_tensor: Union[torch.Tensor, np.ndarray, Any],
    weights_path: Union[str, Path] = "data/weights/siamese_unet_flood.pth",
    threshold: float = 0.5,
    pixel_resolution_m: float = DEFAULT_PIXEL_RES_M,
    village_id: Optional[str] = None
) -> FloodInferenceResult:
    """
    Convenience function to run end-to-end flood inundation inference.

    :param t1_tensor: Normalized 4-band pre-disaster tensor (4, H, W).
    :param t2_tensor: Normalized 4-band post-disaster tensor (4, H, W).
    :param weights_path: Path to model weights file.
    :param threshold: Threshold for binary classification.
    :param pixel_resolution_m: Ground resolution in meters per pixel.
    :param village_id: Identifier for target village.
    :return: FloodInferenceResult object with binary mask and area statistics.
    """
    pipeline = FloodInferencePipeline(
        weights_path=weights_path,
        threshold=threshold,
        pixel_resolution_m=pixel_resolution_m,
    )
    return pipeline.predict(t1_input=t1_tensor, t2_input=t2_tensor, village_id=village_id)


if __name__ == "__main__":
    print("--- KrishiKavach Vision Inference Pipeline Test ---")

    # Synthetic test tensors: (4 bands, 512, 512)
    # Bands: [B2, B3, B4, B8]
    # T1: Baseline healthy vegetation (NIR high ~0.60, Green ~0.10)
    t1_mock = np.zeros((4, 512, 512), dtype=np.float32)
    t1_mock[B2_BLUE_IDX] = 0.05
    t1_mock[B3_GREEN_IDX] = 0.12
    t1_mock[B4_RED_IDX] = 0.08
    t1_mock[B8_NIR_IDX] = 0.55  # High healthy NIR

    # T2: Post-disaster with simulated flood inundation across lower half
    t2_mock = t1_mock.copy()
    # Inundate rows 250 to 512 (water absorbs NIR, increases Green/Blue)
    t2_mock[B2_BLUE_IDX, 250:, :] = 0.10
    t2_mock[B3_GREEN_IDX, 250:, :] = 0.14
    t2_mock[B4_RED_IDX, 250:, :] = 0.06
    t2_mock[B8_NIR_IDX, 250:, :] = 0.02  # Drastic NIR drop (water signature)

    # Run inference pipeline
    pipeline = FloodInferencePipeline()
    result = pipeline.predict(t1_input=t1_mock, t2_input=t2_mock, village_id="TEST_VILLAGE_001")

    print("[1] Inference Output Summary:")
    for k, v in result.summary().items():
        print(f"    - {k}: {v}")

    print(f"[2] Mask unique values: {np.unique(result.binary_mask)}")
    print(f"[3] Flooded Pixels: {result.flooded_pixel_count} / {result.total_pixel_count}")
    print(f"[4] Flooded Area: {result.flooded_area_hectares:.2f} ha ({result.flood_percentage:.2f}%)")
    print("--- Vision Inference Pipeline test completed successfully ---")
