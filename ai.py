import json
import google.generativeai as genai
from config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")


def generate_content(prompt):
    response = model.generate_content(prompt)
    return response.text.strip()


def generate_json(prompt, fallback=None):
    """Like generate_content, but strips ```json fences and parses the result.
    Used for review_content, build_poll_prompt output, and the strategy step —
    anywhere the model is asked to return JSON only."""
    raw = generate_content(prompt)
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return fallback


def review_content(review_prompt):
    return generate_json(review_prompt, fallback={"ok": True, "feedback": ""})
