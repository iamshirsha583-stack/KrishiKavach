"""Test script for GEE Sentinel-1 fetch pipeline."""

import os
import sys

# Ensure src is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.app.pipeline.geospatial.gee_client import fetch_sar_pair


def test_fetch_sar_pair_hooghly():
    """Verify pulling Sentinel-1 SAR pair for Hooghly basin bounding box for Sept 2024."""
    bbox = [87.5, 22.5, 88.5, 23.5]
    pre_dates = ("2024-09-01", "2024-09-15")
    post_dates = ("2024-09-16", "2024-09-30")
    out_dir = "data/cache"

    print(f"Testing fetch_sar_pair with bbox={bbox}, pre_dates={pre_dates}, post_dates={post_dates}...")
    pre_path, post_path = fetch_sar_pair(bbox, pre_dates, post_dates, out_dir=out_dir)

    print(f"Pre-SAR path: {pre_path}")
    print(f"Post-SAR path: {post_path}")

    assert os.path.exists(pre_path), f"File missing: {pre_path}"
    assert os.path.exists(post_path), f"File missing: {post_path}"

    pre_size = os.path.getsize(pre_path)
    post_size = os.path.getsize(post_path)

    print(f"Pre-SAR file size: {pre_size} bytes")
    print(f"Post-SAR file size: {post_size} bytes")

    assert pre_size > 0, f"File {pre_path} is empty (0 bytes)"
    assert post_size > 0, f"File {post_path} is empty (0 bytes)"

    print("SUCCESS: Both GeoTIFF files verified in data/cache/ with size > 0 bytes!")


if __name__ == "__main__":
    test_fetch_sar_pair_hooghly()
