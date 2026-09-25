"""
Test verification script linking Geospatial Ingestion and Vision Inference.
"""

from src.app.pipeline.geospatial.ingestion import load_paired_raster_tensors, extract_village_bbox
from src.app.pipeline.vision.infer import run_flood_inference

def main():
    village_id = "VILLAGE_001"
    print(f"1. Extracting bounding box for village {village_id}:")
    bbox = extract_village_bbox(village_id)
    print(f"   BBox: {bbox}")

    print("\n2. Ingesting paired T1/T2 multi-band rasters:")
    paired = load_paired_raster_tensors(village_id=village_id)
    print(f"   Pre-disaster tensor shape: {paired.pre_disaster_tensor.shape}")
    print(f"   Post-disaster tensor shape: {paired.post_disaster_tensor.shape}")
    print(f"   Is mock: {paired.is_mock}")

    print("\n3. Running Vision Flood Inference:")
    flood_res = run_flood_inference(
        t1_tensor=paired.pre_disaster_tensor,
        t2_tensor=paired.post_disaster_tensor,
        village_id=village_id
    )

    print(f"   Inference Mode: {flood_res.inference_mode}")
    print(f"   Binary Mask Shape: {flood_res.binary_mask.shape}")
    print(f"   Flooded Pixels: {flood_res.flooded_pixel_count:,} / {flood_res.total_pixel_count:,}")
    print(f"   Flooded Area: {flood_res.flooded_area_hectares:.2f} hectares ({flood_res.flood_percentage:.2f}%)")
    print("\n--- Pipeline integration verified successfully ---")

if __name__ == "__main__":
    main()
