"""
KrishiKavach Advisory Synthesis Service.

Synthesizes actionable, localized agricultural recovery advisories for farmers and local authorities
using Google Gemini AI with multilingual support (Bengali, Odia, Hindi, Telugu, English).
Provides realistic fallback synthesis when Gemini API key is not configured or in offline mode.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("KrishiKavach.Advisory")

# Try importing Google Generative AI if installed
try:
    import google.generativeai as genai
    GEMINI_SDK_AVAILABLE = True
except ImportError:
    genai = None  # type: ignore
    GEMINI_SDK_AVAILABLE = False


class AdvisorySynthesizer:
    """Service to synthesize flood recovery advisories using Gemini AI with multilingual templates."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self._gemini_client_ready = False

        if self.api_key and GEMINI_SDK_AVAILABLE and genai is not None:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel("gemini-1.5-flash")
                self._gemini_client_ready = True
                logger.info("Initialized Gemini AI client for dynamic agricultural advisory generation.")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini AI ({e}). Using offline multilingual synthesis.")
                self._gemini_client_ready = False
        else:
            logger.info("Gemini API key not found or SDK not loaded. Using domain-specific multilingual synthesizer.")

    def generate_advisory(
        self,
        village_id: str,
        flooded_hectares: float,
        flood_percentage: float,
        risk_level: str,
        language: str = "Bengali",
    ) -> str:
        """
        Generates an SMS-length (120-250 characters), actionable agricultural disaster advisory.

        :param village_id: Target village identifier.
        :param flooded_hectares: Total inundated hectares.
        :param flood_percentage: Percentage of village farmland inundated.
        :param risk_level: Assessed risk tier ('Low', 'Moderate', 'Severe', 'Catastrophic').
        :param language: Output language (e.g. 'Bengali', 'Odia', 'Hindi', 'English', 'Telugu').
        :return: String containing the SMS advisory text.
        """
        lang_normalized = language.strip().lower()

        # Attempt live Gemini AI synthesis if available
        if self._gemini_client_ready:
            try:
                prompt = (
                    f"You are KrishiKavach, an AI agricultural disaster assistant in India. "
                    f"Write an urgent, highly actionable, empathetic SMS advisory for farmers in village {village_id}. "
                    f"Disaster Data: Flood risk: {risk_level}, Inundated Area: {flooded_hectares:.1f} hectares ({flood_percentage:.1f}%). "
                    f"Language required: {language}. "
                    f"Instructions: "
                    f"1. Advise immediate water drainage/trenching to save standing crops (paddy/vegetables). "
                    f"2. Mention applying fungicide (e.g., Carbendazim/Trichoderma) after water recedes to prevent root rot. "
                    f"3. Urge reporting crop loss under PMFBY (Pradhan Mantri Fasal Bima Yojana) within 72 hours via toll-free/app. "
                    f"Keep the message concise under 200 characters suitable for SMS. Do not use markdown or bold text."
                )
                response = self.model.generate_content(prompt)
                if response and response.text:
                    cleaned_text = response.text.strip().replace("**", "").replace("#", "")
                    logger.info("Successfully synthesized advisory via Gemini AI.")
                    return cleaned_text
            except Exception as e:
                logger.warning(f"Gemini API call failed ({e}). Falling back to multilingual template.")

        # Multilingual domain-expert fallback templates
        return self._generate_template_advisory(
            village_id=village_id,
            flooded_hectares=flooded_hectares,
            flood_percentage=flood_percentage,
            risk_level=risk_level,
            language=lang_normalized,
        )

    def _generate_template_advisory(
        self,
        village_id: str,
        flooded_hectares: float,
        flood_percentage: float,
        risk_level: str,
        language: str,
    ) -> str:
        """Generates localized expert advisories in Indian languages."""
        ha_str = f"{flooded_hectares:.1f}"
        pct_str = f"{flood_percentage:.1f}"

        if "bengali" in language or "bangla" in language or "বাংলা" in language:
            if risk_level in ("Severe", "Catastrophic"):
                return (
                    f"কৃষিকবচ সতর্কতা ({village_id}): {ha_str}হেক্টর ({pct_str}%) জমি জলমগ্ন। "
                    f"দ্রুত জমির জল নিষ্কাশন করুন। পচন রোধে ছত্রাকনাশক (কার্বেনডাজিম) স্প্রে করুন। "
                    f"PMFBY ফসল বীমা ক্ষতিপূরণের জন্য ৭২ ঘণ্টার মধ্যে কৃষি আধিকারিককে জানান।"
                )
            else:
                return (
                    f"কৃষিকবচ পরামর্শ ({village_id}): {ha_str}হেক্টর জমিতে অতিরিক্ত জল জমেছে। "
                    f"নালা কেটে জল বের করুন ও শিকড় পচা রোধে ব্যবস্থা নিন। সহায়তার জন্য কিষাণ কল সেন্টারে যোগাযোগ করুন।"
                )

        elif "odia" in language or "oriya" in language or "ଓଡ଼ିଆ" in language:
            if risk_level in ("Severe", "Catastrophic"):
                return (
                    f"କୃଷିକବଚ ସତର୍କତା ({village_id}): {ha_str} ହେକ୍ଟର ({pct_str}%) ଜମି ଜଳମଗ୍ନ। "
                    f"ତୁରନ୍ତ ଜଳ ନିଷ୍କାସନ କରନ୍ତୁ ଏବଂ ଚେର ପଚା ରୋକିବା ପାଇଁ ଫିମ୍ପିନାଶକ ସ୍ପ୍ରେ କରନ୍ତୁ। "
                    f"PMFBY ଫସଲ ବୀମା କ୍ଷତିପୂରଣ ପାଇଁ ୭୨ ଘଣ୍ଟା ମଧ୍ୟରେ ଜଣାନ୍ତୁ।"
                )
            else:
                return (
                    f"କୃଷିକବଚ ପରାମର୍ଶ ({village_id}): {ha_str} ହେକ୍ଟର ଜମିରେ ଜଳ ଜମି ରହିଛି। "
                    f"ନଳା ତିଆରି କରି ଜଳ ବାହାର କରନ୍ତୁ। PMFBY ସହାୟତା ପାଇଁ ଆବେଦନ କରନ୍ତୁ।"
                )

        elif "hindi" in language or "हिंदी" in language:
            if risk_level in ("Severe", "Catastrophic"):
                return (
                    f"कृषिकवच सतर्कता ({village_id}): {ha_str} हेक्टेयर ({pct_str}%) भूमि जलमग्न है। "
                    f"खेतों से तुरंत जल निकासी करें व फफूंदनाशक का छिड़काव करें। "
                    f"PMFBY फसल बीमा मुआवजे हेतु 72 घंटों के भीतर टोल-फ्री नंबर पर क्लेम दर्ज करें।"
                )
            else:
                return (
                    f"कृषिकवच सलाह ({village_id}): {ha_str} हेक्टेयर क्षेत्र में जलभराव है। "
                    f"नाली बनाकर पानी निकालें और फफूंद संक्रमण से बचाव करें। सहायता हेतु किसान कॉल सेंटर संपर्क करें।"
                )

        elif "telugu" in language or "తెలుగు" in language:
            return (
                f"కృషికవచ్ హెచ్చరిక ({village_id}): {ha_str} హెక్టార్లు ({pct_str}%) ముంపునకు గురయ్యాయి. "
                f"తక్షణమే నీటిని బయటకు పంపండి. పంట నష్టపరిహారం (PMFBY) కోసం 72 గంటల్లో రిపోర్ట్ చేయండి."
            )

        # Default English advisory
        if risk_level in ("Severe", "Catastrophic"):
            return (
                f"KrishiKavach Alert ({village_id}): {ha_str} ha ({pct_str}%) inundated. "
                f"Drain excess water immediately. Apply fungicide to prevent root rot. "
                f"Report crop loss under PMFBY within 72 hrs via toll-free / app."
            )
        else:
            return (
                f"KrishiKavach Advisory ({village_id}): {ha_str} ha ({pct_str}%) waterlogged. "
                f"Clear drainage channels and inspect soil aeration. Contact local Krishi Kendra for aid."
            )
