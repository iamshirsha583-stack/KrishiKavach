"""
KrishiKavach Background Pipeline Scheduler & Concurrency Controller.

Features:
1. APScheduler configured with a strict ThreadPoolExecutor(max_workers=1) for single-worker sequential job processing.
2. 'execute_pipeline' orchestrating:
   - GEE (Google Earth Engine) fetcher & Geospatial Ingestion
   - PyTorch Siamese Feature-Difference inference wrapped strictly in a threading.Lock() to prevent GPU/RAM OOM errors
   - GeoPandas boundary evaluation and PMFBY risk calculation
   - Alert Gateway (Bengali SMS generation via Gemini, ElevenLabs voice synthesis, and Twilio dispatch).
3. Thread-safe scheduler lifecycle start/shutdown hooks for FastAPI.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

# Optional APScheduler imports with graceful fallbacks
try:
    from apscheduler.executors.pool import ThreadPoolExecutor as APSThreadPoolExecutor
    from apscheduler.schedulers.background import BackgroundScheduler
    APSCHEDULER_AVAILABLE = True
except ImportError:
    BackgroundScheduler = None  # type: ignore
    APSThreadPoolExecutor = None  # type: ignore
    APSCHEDULER_AVAILABLE = False

from src.app.pipeline.geospatial.ingestion import (
    BoundingBox,
    extract_village_bbox,
    load_paired_raster_tensors,
)
from src.app.pipeline.risk_engine.alert_gateway import (
    AlertDispatchResult,
    dispatch_alerts,
    generate_bengali_sms,
    synthesize_voice_alert,
)
from src.app.pipeline.vision.infer import FloodInferenceResult, run_flood_inference
from src.app.services.risk import RiskEvaluation, calculate_flood_risk

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("KrishiKavach.Scheduler")

# =============================================================================
# PyTorch GPU/RAM Concurrency Lock (Prevents Out-Of-Memory Crashes)
# =============================================================================
PYTORCH_LOCK = threading.Lock()


@dataclass
class PipelineExecutionResult:
    """Dataclass encapsulating end-to-end multi-stage pipeline execution results."""
    village_id: str
    bbox: BoundingBox
    flooded_hectares: float
    flood_percentage: float
    risk_level: str
    risk_score: float
    pmfby_claim_recommended: bool
    bengali_sms_text: str
    voice_audio_path: str
    dispatch_result: Dict[str, Any]
    inference_mode: str
    execution_time_seconds: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def summary(self) -> Dict[str, Any]:
        """Returns concise summary dictionary."""
        return {
            "village_id": self.village_id,
            "bbox": self.bbox,
            "flooded_hectares": self.flooded_hectares,
            "flood_percentage": self.flood_percentage,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
            "pmfby_claim_recommended": self.pmfby_claim_recommended,
            "sms_sid": self.dispatch_result.get("sms_sid"),
            "call_sid": self.dispatch_result.get("call_sid"),
            "execution_time_sec": round(self.execution_time_seconds, 2),
            "inference_mode": self.inference_mode,
        }


# =============================================================================
# 1. Pipeline Execution Core Orchestrator
# =============================================================================

def execute_pipeline(
    bbox: Optional[Union[BoundingBox, Tuple[float, float, float, float], list]] = None,
    village_id: str = "VILLAGE_001",
    phone_number: str = "+919876543210",
    language: str = "Bengali",
    audio_url: str = "https://krishikavach.org/cache/alert.mp3",
) -> PipelineExecutionResult:
    """
    Executes the full KrishiKavach agricultural disaster assessment & alert pipeline:
    1. GEE / Geospatial Ingestion: Loads pre/post satellite raster arrays.
    2. PyTorch Vision Inference: Runs Siamese UNet with threading.Lock() protection.
    3. GeoPandas Evaluator & Risk Assessment: Computes flood extent and PMFBY risk.
    4. Alert Gateway: Generates Bengali SMS, synthesizes ElevenLabs voice audio, and dispatches via Twilio.

    :param bbox: Optional bounding box (minx, miny, maxx, maxy).
    :param village_id: Target village identifier.
    :param phone_number: Recipient phone number for SMS and Voice alerts.
    :param language: Output language (e.g. 'Bengali').
    :param audio_url: Public URL to stream the synthesized MP3 during voice calls.
    :return: PipelineExecutionResult with complete stage metrics.
    """
    start_time = time.time()
    logger.info(f"=== Starting Pipeline Execution for village '{village_id}' ===")

    # Resolve bounding box
    if bbox is None:
        resolved_bbox = extract_village_bbox(village_id)
    elif isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        resolved_bbox = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    else:
        resolved_bbox = extract_village_bbox(village_id)

    logger.info(f"[Stage 1/4] GEE / Geospatial Ingestion for BBox: {resolved_bbox}...")
    paired_data = load_paired_raster_tensors(village_id=village_id)

    # -------------------------------------------------------------------------
    # Stage 2: PyTorch Model Inference wrapped in Concurrency Lock
    # -------------------------------------------------------------------------
    logger.info("[Stage 2/4] Acquiring PyTorch GPU/RAM Lock for Siamese Inference...")
    with PYTORCH_LOCK:
        logger.info("  [PyTorch Lock Acquired] Running neural flood inference...")
        infer_result: FloodInferenceResult = run_flood_inference(
            t1_tensor=paired_data.pre_disaster_tensor,
            t2_tensor=paired_data.post_disaster_tensor,
            village_id=village_id,
        )
        logger.info(
            f"  [PyTorch Lock Released] Inference finished: "
            f"{infer_result.flooded_area_hectares:.2f} ha flooded ({infer_result.flood_percentage:.2f}%)"
        )

    # -------------------------------------------------------------------------
    # Stage 3: GeoPandas & PMFBY Risk Assessment
    # -------------------------------------------------------------------------
    logger.info("[Stage 3/4] Evaluating GeoPandas bounds and computing PMFBY risk scores...")
    flooded_ha = round(infer_result.flooded_area_hectares, 2)
    flood_pct = round(infer_result.flood_percentage, 2)
    flooded_acres = round(flooded_ha * 2.47105, 2)  # Convert hectares to acres

    risk_eval: RiskEvaluation = calculate_flood_risk(
        flooded_hectares=flooded_ha,
        flood_percentage=flood_pct,
    )
    logger.info(
        f"  Assessed Risk Level: {risk_eval.risk_level} (Score: {risk_eval.risk_score}/100), "
        f"PMFBY Claim Recommended: {risk_eval.pmfby_claim_recommended}"
    )

    # -------------------------------------------------------------------------
    # Stage 4: Alert Gateway (Gemini 2.5 Flash -> ElevenLabs -> Twilio)
    # -------------------------------------------------------------------------
    logger.info("[Stage 4/4] Activating Alert Gateway for multi-modal notification...")
    
    # 4a. Generate action-oriented Bengali SMS via Gemini 2.5 Flash
    sms_text = generate_bengali_sms(
        village_name=village_id,
        flooded_acres=flooded_acres,
    )

    # 4b. Synthesize ElevenLabs voice alert audio
    audio_path = synthesize_voice_alert(
        text=sms_text,
        output_path="data/cache/alert.mp3",
    )

    # 4c. Dispatch SMS and Emergency Voice Call via Twilio
    dispatch_res: AlertDispatchResult = dispatch_alerts(
        to_number=phone_number,
        sms_text=sms_text,
        audio_url=audio_url,
    )

    elapsed_time = time.time() - start_time
    logger.info(f"=== Pipeline Execution Completed in {elapsed_time:.2f} seconds ===")

    return PipelineExecutionResult(
        village_id=village_id,
        bbox=resolved_bbox,
        flooded_hectares=flooded_ha,
        flood_percentage=flood_pct,
        risk_level=risk_eval.risk_level,
        risk_score=risk_eval.risk_score,
        pmfby_claim_recommended=risk_eval.pmfby_claim_recommended,
        bengali_sms_text=sms_text,
        voice_audio_path=str(audio_path),
        dispatch_result=dispatch_res.summary(),
        inference_mode=infer_result.inference_mode,
        execution_time_seconds=elapsed_time,
        metadata={
            "flooded_acres": flooded_acres,
            "crop_loss_pct": risk_eval.crop_loss_estimate_pct,
            "priority": risk_eval.priority,
        },
    )


# =============================================================================
# 2. APScheduler Singleton & Lifecycle Controller
# =============================================================================

class PipelineSchedulerManager:
    """Manages APScheduler lifecycle with ThreadPoolExecutor(max_workers=1)."""

    def __init__(self):
        self.scheduler: Optional[Any] = None
        self._is_running = False
        self._initialize_scheduler()

    def _initialize_scheduler(self) -> None:
        """Initializes APScheduler with single-threaded pool."""
        if not APSCHEDULER_AVAILABLE:
            logger.warning("APScheduler package not installed. Operating with thread-pool fallback.")
            self.scheduler = None
            return

        try:
            executors = {
                "default": APSThreadPoolExecutor(max_workers=1)
            }
            job_defaults = {
                "coalesce": True,
                "max_instances": 1,
            }
            self.scheduler = BackgroundScheduler(
                executors=executors,
                job_defaults=job_defaults
            )
            logger.info("Initialized APScheduler with ThreadPoolExecutor(max_workers=1).")
        except Exception as e:
            logger.error(f"Failed to initialize APScheduler: {e}")
            self.scheduler = None

    def start(self) -> None:
        """Starts the scheduler background thread."""
        if self.scheduler and not self._is_running:
            try:
                self.scheduler.start()
                self._is_running = True
                logger.info("APScheduler background service successfully started.")
            except Exception as e:
                logger.error(f"Error starting APScheduler: {e}")

    def shutdown(self) -> None:
        """Shuts down the scheduler gracefully."""
        if self.scheduler and self._is_running:
            try:
                self.scheduler.shutdown(wait=False)
                self._is_running = False
                logger.info("APScheduler background service shut down.")
            except Exception as e:
                logger.warning(f"Error during APScheduler shutdown: {e}")

    def is_running(self) -> bool:
        return self._is_running


# Scheduler singleton
scheduler_manager = PipelineSchedulerManager()


def start_scheduler() -> None:
    """Starts the global pipeline scheduler."""
    scheduler_manager.start()


def shutdown_scheduler() -> None:
    """Stops the global pipeline scheduler."""
    scheduler_manager.shutdown()


def get_scheduler() -> Optional[Any]:
    """Returns the underlying APScheduler instance."""
    return scheduler_manager.scheduler
