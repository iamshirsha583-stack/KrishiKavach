"""
KrishiKavach FastAPI Application Server.

Main API server providing:
1. POST /api/v1/scan-trigger:
   - Full orchestration: Geospatial ingestion -> Siamese Vision inference -> Risk assessment -> Gemini advisory -> Twilio SMS dispatch.
   - Returns flooded_hectares, risk_level, advisory_sms, and sms_sid.
2. GET /api/v1/maps/overlay/{village_id}:
   - Returns GeoJSON FeatureCollection containing village boundary polygon and flood inundation extent for MapLibre GL JS.
3. CORS middleware configured for frontend integration.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.app.pipeline.geospatial.ingestion import (
    GeospatialIngestionPipeline,
    extract_village_bbox,
    load_paired_raster_tensors,
)
from src.app.pipeline.vision.infer import run_flood_inference
from src.app.services.advisory import AdvisorySynthesizer
from src.app.services.notification import SMSDispatchService
from src.app.services.overlay import generate_map_overlay_geojson
from src.app.services.risk import calculate_flood_risk

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("KrishiKavach.API")

# Initialize FastAPI App
app = FastAPI(
    title="KrishiKavach API",
    description="AI-driven Satellite Geospatial Inundation Monitoring & Agricultural Disaster Advisory Engine",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# =============================================================================
# 3. CORS Middleware for Frontend & MapLibre Integration
# =============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for local dev and web clients
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],  # Allows all headers
)

# Service Singletons
advisory_service = AdvisorySynthesizer()
sms_service = SMSDispatchService()
ingestion_pipeline = GeospatialIngestionPipeline()


# =============================================================================
# Request & Response Schemas
# =============================================================================

class ScanTriggerRequest(BaseModel):
    village_id: str = Field(
        default="VILLAGE_001",
        description="Unique identifier of the village grid (e.g., VILLAGE_001, Rampur, DEMO_VILLAGE)",
        example="VILLAGE_001"
    )
    phone_number: str = Field(
        default="+919876543210",
        description="Recipient mobile number in E.164 format for SMS advisory dispatch",
        example="+919876543210"
    )
    language: str = Field(
        default="Bengali",
        description="Advisory language (e.g. Bengali, Odia, Hindi, Telugu, English)",
        example="Bengali"
    )


class ScanTriggerResponse(BaseModel):
    status: str = Field(default="success", example="success")
    village_id: str = Field(..., example="VILLAGE_001")
    flooded_hectares: float = Field(..., example=142.5)
    flood_percentage: float = Field(..., example=27.8)
    risk_level: str = Field(..., example="Severe")
    advisory_sms: str = Field(..., example="কৃষিকবচ সতর্কতা: জমি জলমগ্ন...")
    sms_sid: str = Field(..., example="SM9b87a213e4f50123456789abcdef0123")
    pipeline_details: Dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str = "KrishiKavach API"
    version: str = "1.0.0"


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/", tags=["General"])
async def root_info() -> Dict[str, Any]:
    """Root metadata and system status."""
    return {
        "service": "KrishiKavach Agricultural Disaster Advisory API",
        "status": "online",
        "docs": "/docs",
        "endpoints": {
            "scan_trigger": "POST /api/v1/scan-trigger",
            "map_overlay": "GET /api/v1/maps/overlay/{village_id}",
            "health": "GET /health",
        },
    }


@app.get("/health", response_model=HealthResponse, tags=["General"])
async def health_check() -> HealthResponse:
    """Service health check endpoint."""
    return HealthResponse()


# -----------------------------------------------------------------------------
# 1. POST /api/v1/scan-trigger
# -----------------------------------------------------------------------------

@app.post(
    "/api/v1/scan-trigger",
    response_model=ScanTriggerResponse,
    status_code=status.HTTP_200_OK,
    tags=["Disaster Scan & Advisory"],
    summary="Execute bi-temporal flood scan, risk calculation, AI advisory synthesis, and SMS alert dispatch"
)
async def scan_trigger(payload: ScanTriggerRequest) -> ScanTriggerResponse:
    """
    Executes the end-to-end KrishiKavach disaster assessment pipeline:
    1. **Geospatial Ingestion**: Reads village boundaries and loads paired T1/T2 Sentinel-2 rasters (512x512).
    2. **Vision Inference**: Runs Siamese feature-difference / NDWI spectral analysis to calculate flooded area.
    3. **Risk Assessment**: Computes flood severity tier and PMFBY claim priority.
    4. **Gemini Advisory Synthesis**: Synthesizes localized agricultural recovery guidelines in the chosen language.
    5. **Twilio SMS Dispatch**: Sends actionable alerts to the target mobile number.
    """
    logger.info(
        f"Received scan trigger request for village '{payload.village_id}', "
        f"phone '{payload.phone_number}', language '{payload.language}'"
    )

    try:
        # Step 1: Geospatial Ingestion
        paired_data = load_paired_raster_tensors(village_id=payload.village_id)
        bbox = paired_data.bbox

        # Step 2: Vision Inundation Inference
        infer_result = run_flood_inference(
            t1_tensor=paired_data.pre_disaster_tensor,
            t2_tensor=paired_data.post_disaster_tensor,
            village_id=payload.village_id,
        )

        flooded_ha = round(infer_result.flooded_area_hectares, 2)
        flood_pct = round(infer_result.flood_percentage, 2)

        # Step 3: Risk Calculation
        risk_eval = calculate_flood_risk(
            flooded_hectares=flooded_ha,
            flood_percentage=flood_pct,
        )

        # Step 4: Gemini AI Advisory Synthesis
        advisory_text = advisory_service.generate_advisory(
            village_id=payload.village_id,
            flooded_hectares=flooded_ha,
            flood_percentage=flood_pct,
            risk_level=risk_eval.risk_level,
            language=payload.language,
        )

        # Step 5: Twilio SMS Dispatch
        sms_result = sms_service.send_sms(
            to_number=payload.phone_number,
            message_body=advisory_text,
        )

        pipeline_details = {
            "bbox": bbox,
            "inference_mode": infer_result.inference_mode,
            "flooded_pixels": infer_result.flooded_pixel_count,
            "total_pixels": infer_result.total_pixel_count,
            "risk_score": risk_eval.risk_score,
            "crop_loss_estimate_pct": risk_eval.crop_loss_estimate_pct,
            "pmfby_claim_recommended": risk_eval.pmfby_claim_recommended,
            "priority": risk_eval.priority,
            "sms_delivery": sms_result,
        }

        return ScanTriggerResponse(
            status="success",
            village_id=payload.village_id,
            flooded_hectares=flooded_ha,
            flood_percentage=flood_pct,
            risk_level=risk_eval.risk_level,
            advisory_sms=advisory_text,
            sms_sid=sms_result.get("sms_sid", ""),
            pipeline_details=pipeline_details,
        )

    except Exception as e:
        logger.error(f"Error processing scan trigger for village '{payload.village_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline processing failed: {str(e)}"
        )


# -----------------------------------------------------------------------------
# 2. GET /api/v1/maps/overlay/{village_id}
# -----------------------------------------------------------------------------

@app.get(
    "/api/v1/maps/overlay/{village_id}",
    tags=["Map Overlays"],
    summary="Get GeoJSON FeatureCollection for MapLibre village boundary and flood extent overlay"
)
async def get_map_overlay(village_id: str) -> Dict[str, Any]:
    """
    Returns a GeoJSON FeatureCollection containing:
    1. Village polygon boundary with styling properties.
    2. High-precision vector flood inundation extent polygon(s).
    """
    logger.info(f"Generating map overlay GeoJSON for village '{village_id}'...")

    try:
        # Extract village bounding box
        bbox = extract_village_bbox(village_id)

        # Ingest and infer current flood mask for village
        paired_data = load_paired_raster_tensors(village_id=village_id)
        infer_result = run_flood_inference(
            t1_tensor=paired_data.pre_disaster_tensor,
            t2_tensor=paired_data.post_disaster_tensor,
            village_id=village_id,
        )

        geojson_data = generate_map_overlay_geojson(
            village_id=village_id,
            bbox=bbox,
            binary_mask=infer_result.binary_mask,
            flooded_hectares=infer_result.flooded_area_hectares,
            risk_level="Severe" if infer_result.flood_percentage > 20 else "Moderate",
        )

        return geojson_data

    except Exception as e:
        logger.error(f"Error generating map overlay for '{village_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate map overlay: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    print("Starting KrishiKavach FastAPI server on http://localhost:8000 ...")
    uvicorn.run("src.app.main:app", host="0.0.0.0", port=8000, reload=True)
