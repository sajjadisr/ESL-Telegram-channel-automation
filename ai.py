import json
import google.generativeai as genai
from config import GEMINI_API_KEY

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

def generate_content(prompt):
    response = model.generate_content(prompt)
    return response.text.strip()

def review_content(review_prompt):
    raw = generate_content(review_prompt)
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"ok": True, "feedback": ""}