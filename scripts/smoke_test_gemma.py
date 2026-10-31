"""
Gemma 4 Multimodal Smoke Test (Hour 0:00 - 0:45 Go/No-Go Gate)
Verifies:
1. Google GenAI SDK connection via GEMINI_API_KEY.
2. Multimodal image input support.
3. Strict JSON output parsing.
4. Response latency and thinking mode support (if available).
"""

import os
import sys
import time
import json
from io import BytesIO
from PIL import Image, ImageDraw
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_ID = os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it")
REPAIR_MODEL_ID = os.getenv("GEMMA_REPAIR_MODEL", "gemma-4-31b-it")

def create_synthetic_test_image() -> bytes:
    """Generates a simple 400x200 JPEG image with a blue button labeled 'Submit Application'."""
    img = Image.new("RGB", (400, 200), color=(245, 247, 250))
    draw = ImageDraw.Draw(img)
    # Draw blue button box
    draw.rectangle([50, 70, 350, 130], fill=(30, 64, 175))
    draw.text((120, 92), "Submit Application", fill=(255, 255, 255))
    
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=75)
    return buffer.getvalue()

def run_smoke_test():
    print("=" * 60)
    print("🚀 DemoToSkill: Gemma 4 API Smoke Test")
    print(f"Primary Model: {MODEL_ID}")
    print(f"Repair Model:  {REPAIR_MODEL_ID}")
    print("=" * 60)

    if not API_KEY or API_KEY == "your_gemini_api_key_here":
        print("❌ Error: GEMINI_API_KEY is not set or still default in .env")
        print("Please obtain a free key from Google AI Studio and update your .env file.")
        sys.exit(1)

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("❌ Error: google-genai SDK not installed. Run: pip install google-genai")
        sys.exit(1)

    client = genai.Client(api_key=API_KEY)
    test_img_bytes = create_synthetic_test_image()

    prompt = """
    Examine the provided image of a UI element.
    Respond with strictly valid JSON only:
    {
      "element_type": "string",
      "visible_text": "string",
      "intent": "string",
      "confidence": float
    }
    """

    print("\n[1/2] Testing Primary Multimodal Inference...")
    t0 = time.time()
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=[
                types.Part.from_bytes(data=test_img_bytes, mime_type="image/jpeg"),
                prompt
            ],
            config=types.GenerateContentConfig(
                temperature=0.2,
            )
        )
        latency = (time.time() - t0) * 1000
        raw_text = response.text.strip()
        print(f"✅ Response received in {latency:.1f}ms")
        print(f"Raw Output Preview:\n{raw_text[:200]}...")

        # Parse JSON
        import re
        clean_json = raw_text
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
        if fence_match:
            clean_json = fence_match.group(1)
        
        parsed = json.loads(clean_json)
        print(f"✅ Successfully parsed JSON: {parsed}")

    except Exception as e:
        print(f"❌ Primary model test failed: {e}")
        print("\nFallback Notice: Verify your GEMINI_API_KEY or model availability.")
        sys.exit(1)

    print("\n[2/2] Testing Repair Model Accessibility...")
    t1 = time.time()
    try:
        resp_repair = client.models.generate_content(
            model=REPAIR_MODEL_ID,
            contents=["Respond with JSON: {\"status\": \"ok\", \"model\": \"" + REPAIR_MODEL_ID + "\"}"],
            config=types.GenerateContentConfig(temperature=0.1)
        )
        latency_repair = (time.time() - t1) * 1000
        print(f"✅ Repair model responded in {latency_repair:.1f}ms")
    except Exception as e:
        print(f"⚠️ Repair model ({REPAIR_MODEL_ID}) check note: {e}")
        print(f"Falling back to {MODEL_ID} for repair node if needed.")

    print("\n" + "=" * 60)
    print("🎉 ALL CRITICAL GEMMA 4 GATES PASSED! READY TO BUILD.")
    print("=" * 60)

if __name__ == "__main__":
    run_smoke_test()
