# nodes/cleaning.py
import re
from ..utils.arabic import display_arabic
from ..config import logger
from ..state_type.types_utils import CommentaryState

def clean_text(text: str) -> str:
    text = re.sub(r'\s+', ' ', text)
    filler_phrases = [
        r'الوطن العزيز السلام عليكم',
        r'اسعد الله اوقاتكم',
        r'بكل حب وخير نلتقي',
        r'عبر قنوات التلفزه الوطنيه',
        r'النقل المباشر لمقابلات',
        r'نعطيكم فكره على البنك'
    ]
    for phrase in filler_phrases:
        text = re.sub(phrase, '', text, flags=re.IGNORECASE)
    return text.strip()


def clean_commentary_node(state: CommentaryState) -> CommentaryState:
    cleaned = clean_text(state["original_commentary"])
    logger.info("Commentary cleaned")
    return {**state, "cleaned_commentary": cleaned}