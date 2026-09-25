"""
KrishiKavach FastAPI Application Server.

Main API server providing:
1. Lifespan lifecycle hooks to start and stop APScheduler.
2. Auth0 JWT security protection on critical endpoints.
3. POST /api/v1/scan/trigger (Protected by Auth0): Accepts a bounding box, village ID, and phone number,
   and delegates the end-to-end pipeline (GEE -> PyTorch with Lock -> GeoPandas -> Alert Gateway)
   to FastAPI BackgroundTasks.
4. POST /api/v1/scan-trigger (Synchronous) & GET /api/v1/maps/overlay/{village_id} (MapLibre GeoJSON).
5. CORS middleware enabled for frontend integration.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.app.core.auth import get_current_user, verify_jwt_token
from src.app.core.scheduler import (
    PipelineExecutionResult,
    execute_pipeline,
    shutdown_scheduler,
    start_scheduler,
)
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


# =============================================================================
# 1. FastAPI Lifespan Lifecycle Hook (Scheduler Management)
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager to start the background scheduler on startup and stop on shutdown."""
    logger.info("Initializing KrishiKavach background scheduler service...")
    start_scheduler()
    yield
    logger.info("Shutting down KrishiKavach background scheduler service...")
    shutdown_scheduler()


# Initialize FastAPI App with Lifespan
app = FastAPI(
    title="KrishiKavach API",
    description="AI-driven Satellite Geospatial Inundation Monitoring & Agricultural Disaster Advisory Engine",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# =============================================================================
# 2. CORS Middleware for Frontend & MapLibre Integration
# =============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for frontend & map clients
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

class AsyncScanTriggerRequest(BaseModel):
    bbox: Optional[List[float]] = Field(
        default=[85.82, 20.46, 85.87, 20.51],
        description="Bounding box coordinates [minx, miny, maxx, maxy] in EPSG:4326",
        example=[85.8200, 20.4600, 85.8700, 20.5100]
    )
    village_id: str = Field(
        default="VILLAGE_001",
        description="Unique identifier of the village grid (e.g., VILLAGE_001, Rampur, DEMO_VILLAGE)",
        example="VILLAGE_001"
    )
    phone_number: str = Field(
        default="+919876543210",
        description="Recipient mobile number in E.164 format for SMS and Voice alert dispatch",
        example="+919876543210"
    )
    language: str = Field(
        default="Bengali",
        description="Advisory language (e.g. Bengali, Odia, Hindi, Telugu, English)",
        example="Bengali"
    )
    audio_url: str = Field(
        default="https://krishikavach.org/cache/alert.mp3",
        description="Public URL for streaming the synthesized ElevenLabs MP3 via Twilio Voice TwiML",
        example="https://krishikavach.org/cache/alert.mp3"
    )


class AsyncScanTriggerResponse(BaseModel):
    status: str = Field(default="queued", example="queued")
    job_id: str = Field(..., example="job_e814a1c5d79b")
    message: str = Field(..., example="Pipeline execution successfully queued in background.")
    village_id: str = Field(..., example="VILLAGE_001")
    bbox: List[float] = Field(..., example=[85.82, 20.46, 85.87, 20.51])
    submitted_at: str = Field(...)
    auth_user: Optional[str] = Field(default=None, example="auth0|admin_user")


class ScanTriggerRequest(BaseModel):
    village_id: str = Field(
        default="VILLAGE_001",
        description="Unique identifier of the village grid",
        example="VILLAGE_001"
    )
    phone_number: str = Field(
        default="+919876543210",
        description="Recipient mobile number in E.164 format",
        example="+919876543210"
    )
    language: str = Field(
        default="Bengali",
        description="Advisory language (e.g. Bengali, Odia, Hindi)",
        example="Bengali"
    )


class ScanTriggerResponse(BaseModel):
    status: str = Field(default="success", example="success")
    village_id: str = Field(..., example="VILLAGE_001")
    flooded_hectares: float = Field(..., example=142.5)
    flood_percentage: float = Field(..., example=27.8)
    risk_level: str = Field(..., example="Severe")
    advisory_sms: str = Field(..., example="জরুরি সতর্কতা: জমি প্লাবিত...")
    sms_sid: str = Field(..., example="SM9b87a213e4f50123456789abcdef0123")
    pipeline_details: Dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str = "KrishiKavach API"
    version: str = "2.0.0"
    scheduler_running: bool = True


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/", tags=["General"])
async def root_info() -> Dict[str, Any]:
    """Root metadata and system status."""
    return {
        "service": "KrishiKavach Agricultural Disaster Advisory API",
        "version": "2.0.0",
        "status": "online",
        "docs": "/docs",
        "endpoints": {
            "async_scan_trigger": "POST /api/v1/scan/trigger (Auth0 Protected)",
            "sync_scan_trigger": "POST /api/v1/scan-trigger",
            "map_overlay": "GET /api/v1/maps/overlay/{village_id}",
            "health": "GET /health",
        },
    }


@app.get("/health", response_model=HealthResponse, tags=["General"])
async def health_check() -> HealthResponse:
    """Service health check endpoint."""
    return HealthResponse(
        status="healthy",
        service="KrishiKavach API",
        version="2.0.0",
        scheduler_running=True,
    )


# -----------------------------------------------------------------------------
# 3. POST /api/v1/scan/trigger (Protected by Auth0 JWT + BackgroundTasks)
# -----------------------------------------------------------------------------

@app.post(
    "/api/v1/scan/trigger",
    response_model=AsyncScanTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Disaster Scan & Advisory"],
    summary="Trigger end-to-end background pipeline with bounding box (Auth0 Protected)"
)
async def trigger_background_scan(
    payload: AsyncScanTriggerRequest,
    background_tasks: BackgroundTasks,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> AsyncScanTriggerResponse:
    """
    Accepts bounding box coordinates, verifies Auth0 JWT authentication, and delegates the
    full multi-stage pipeline (GEE Ingestion -> PyTorch Lock Inference -> GeoPandas -> Alert Gateway)
    to FastAPI BackgroundTasks.
    """
    user_id = current_user.get("sub", "anonymous")
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    logger.info(
        f"[Auth0 Authenticated: {user_id}] Enqueueing background pipeline job '{job_id}' "
        f"for village '{payload.village_id}', BBox: {payload.bbox}"
    )

    # Add execute_pipeline task to FastAPI background tasks
    background_tasks.add_task(
        execute_pipeline,
        bbox=payload.bbox,
        village_id=payload.village_id,
        phone_number=payload.phone_number,
        language=payload.language,
        audio_url=payload.audio_url,
    )

    return AsyncScanTriggerResponse(
        status="queued",
        job_id=job_id,
        message="Pipeline execution successfully enqueued in background tasks.",
        village_id=payload.village_id,
        bbox=payload.bbox or [85.82, 20.46, 85.87, 20.51],
        submitted_at=now_iso,
        auth_user=user_id,
    )


# -----------------------------------------------------------------------------
# 4. POST /api/v1/scan-trigger (Synchronous Pipeline Execution)
# -----------------------------------------------------------------------------

@app.post(
    "/api/v1/scan-trigger",
    response_model=ScanTriggerResponse,
    status_code=status.HTTP_200_OK,
    tags=["Disaster Scan & Advisory"],
    summary="Execute bi-temporal flood scan synchronously and return results immediately"
)
async def scan_trigger(payload: ScanTriggerRequest) -> ScanTriggerResponse:
    """
    Executes the synchronous KrishiKavach disaster assessment pipeline.
    """
    logger.info(f"Received synchronous scan trigger request for village '{payload.village_id}'")

    try:
        pipeline_res: PipelineExecutionResult = execute_pipeline(
            village_id=payload.village_id,
            phone_number=payload.phone_number,
            language=payload.language,
        )

        return ScanTriggerResponse(
            status="success",
            village_id=pipeline_res.village_id,
            flooded_hectares=pipeline_res.flooded_hectares,
            flood_percentage=pipeline_res.flood_percentage,
            risk_level=pipeline_res.risk_level,
            advisory_sms=pipeline_res.bengali_sms_text,
            sms_sid=pipeline_res.dispatch_result.get("sms_sid", ""),
            pipeline_details=pipeline_res.summary(),
        )

    except Exception as e:
        logger.error(f"Error processing synchronous scan trigger: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline processing failed: {str(e)}"
        )


# -----------------------------------------------------------------------------
# 5. GET /api/v1/maps/overlay/{village_id} (MapLibre GeoJSON)
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
