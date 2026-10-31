"""
Gemma 4 LLM client for DemoToSkill.
Provides:
1. Google GenAI SDK integration with GEMINI_API_KEY.
2. Multimodal image input support with automatic 1024px downscaling.
3. Strict JSON extraction with code fence stripping and Pydantic validation.
4. Auto-retry once on validation or parse failure.
5. asyncio.Semaphore concurrency throttling (default 3 concurrent).
6. SHA-256 caching by (prompt + images + model).
7. Full invocation telemetry logging to call_logger for the UI Call Inspector.
"""

import os
import re
import json
import time
import asyncio
from pathlib import Path
from typing import Type, TypeVar, Optional, Union, Any
from pydantic import BaseModel, ValidationError

from app.config import (
    GEMINI_API_KEY,
    GEMMA_MODEL,
    GEMMA_REPAIR_MODEL,
    MAX_CONCURRENT_GEMMA_CALLS
)
from app.imaging import (
    resize_and_compress_image,
    compute_image_hash
)
from app.cache import llm_cache
from app.call_logger import call_logger

T = TypeVar("T", bound=BaseModel)


def extract_json_payload(raw_text: str) -> dict[str, Any]:
    """
    Extracts a JSON dictionary from model output text.
    Resilient to:
    - Standard JSON
    - Markdown code block wrappers (```json ... ``` or ``` ...)
    - Preceding or trailing prose
    """
    cleaned = raw_text.strip()

    # 1. Direct parse attempt
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 2. Markdown code fences regex
    fence_pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
    match = re.search(fence_pattern, cleaned, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # 3. Find outermost matching braces
    start_idx = cleaned.find("{")
    end_idx = cleaned.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        candidate = cleaned[start_idx : end_idx + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    raise ValueError(f"Could not extract a valid JSON object from model response:\n{raw_text}")


class GemmaClient:
    """Async client for Gemma 4 multimodal models."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        max_concurrency: int = MAX_CONCURRENT_GEMMA_CALLS
    ):
        self.api_key = api_key or GEMINI_API_KEY
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self._client = None

    def _get_genai_client(self):
        """Lazy initialization of google-genai Client."""
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "GEMINI_API_KEY is not configured. "
                    "Please set it in .env or pass it to GemmaClient."
                )
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "google-genai SDK not installed. "
                    "Run 'pip install google-genai>=1.0.0'."
                )
        return self._client

    async def generate_structured(
        self,
        prompt: str,
        schema_class: Type[T],
        model: Optional[str] = None,
        images: Optional[list[Union[bytes, str, Path]]] = None,
        temperature: float = 0.2,
        endpoint: str = "custom",
        use_cache: bool = True
    ) -> T:
        """
        Invokes Gemma 4 with multimodal images and a prompt, validates against a Pydantic schema,
        and logs the transaction. Retries once upon validation failure.
        """
        model_id = model or GEMMA_MODEL
        img_inputs = images or []

        # Process and downscale images to JPEG quality 70 / max-width 1024px
        processed_images: list[bytes] = []
        image_hashes: list[str] = []
        for img in img_inputs:
            jpeg_bytes = resize_and_compress_image(img)
            processed_images.append(jpeg_bytes)
            image_hashes.append(compute_image_hash(jpeg_bytes))

        # Check Cache
        cache_key = llm_cache.compute_key(prompt, image_hashes, model_id)
        if use_cache and llm_cache.has(cache_key):
            cached_data = llm_cache.get(cache_key)
            # Reconstruct model from cached parsed_json
            call_logger.log(
                endpoint=endpoint,
                model=model_id,
                prompt_summary=prompt[:140] + ("..." if len(prompt) > 140 else ""),
                response_raw=cached_data.get("raw_text", ""),
                parsed_json=cached_data.get("parsed", {}),
                latency_ms=0.0,
                status="success",
                image_paths=image_hashes
            )
            return schema_class.model_validate(cached_data.get("parsed"))

        # Acquire concurrency semaphore
        async with self.semaphore:
            return await self._execute_with_retry(
                prompt=prompt,
                schema_class=schema_class,
                model_id=model_id,
                processed_images=processed_images,
                image_hashes=image_hashes,
                temperature=temperature,
                endpoint=endpoint,
                cache_key=cache_key
            )

    async def _execute_with_retry(
        self,
        prompt: str,
        schema_class: Type[T],
        model_id: str,
        processed_images: list[bytes],
        image_hashes: list[str],
        temperature: float,
        endpoint: str,
        cache_key: str
    ) -> T:
        """Internal call execution with 1-attempt retry on parse or validation error."""
        from google.genai import types

        client = self._get_genai_client()

        # Build contents array (images first, then prompt text)
        contents: list[Any] = []
        for img_bytes in processed_images:
            contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))
        contents.append(prompt)

        prompt_summary = prompt[:140] + ("..." if len(prompt) > 140 else "")
        last_error = None
        raw_text = ""

        for attempt in range(2):
            t0 = time.time()
            try:
                # If retry attempt, append correction instruction to contents
                current_contents = list(contents)
                if attempt == 1 and last_error:
                    current_contents.append(
                        f"\nCRITICAL: Your previous response failed validation: {last_error}.\n"
                        f"Return ONLY strictly valid JSON conforming to the requested schema. Do not include markdown fences."
                    )

                # Execute synchronous SDK call in thread pool to avoid blocking async event loop
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_id,
                    contents=current_contents,
                    config=types.GenerateContentConfig(
                        temperature=temperature
                    )
                )

                latency_ms = (time.time() - t0) * 1000
                raw_text = (response.text or "").strip()

                # Parse JSON
                parsed_dict = extract_json_payload(raw_text)

                # Validate with Pydantic
                validated_obj = schema_class.model_validate(parsed_dict)

                # Cache and Log success
                llm_cache.set(cache_key, {"raw_text": raw_text, "parsed": parsed_dict})
                call_logger.log(
                    endpoint=endpoint,
                    model=model_id,
                    prompt_summary=prompt_summary,
                    response_raw=raw_text,
                    parsed_json=parsed_dict,
                    latency_ms=latency_ms,
                    status="retry" if attempt > 0 else "success",
                    image_paths=image_hashes
                )

                return validated_obj

            except (ValueError, ValidationError, json.JSONDecodeError) as e:
                latency_ms = (time.time() - t0) * 1000
                last_error = str(e)
                if attempt == 0:
                    # Will retry once
                    continue

                # Final failure after retry
                call_logger.log(
                    endpoint=endpoint,
                    model=model_id,
                    prompt_summary=prompt_summary,
                    response_raw=raw_text,
                    latency_ms=latency_ms,
                    status="error",
                    error=last_error,
                    image_paths=image_hashes
                )
                raise RuntimeError(
                    f"Gemma 4 generation failed schema validation for {schema_class.__name__} "
                    f"after retry: {last_error}"
                ) from e

            except Exception as e:
                # API / Network / HTTP 429 error
                latency_ms = (time.time() - t0) * 1000
                call_logger.log(
                    endpoint=endpoint,
                    model=model_id,
                    prompt_summary=prompt_summary,
                    response_raw=raw_text,
                    latency_ms=latency_ms,
                    status="error",
                    error=str(e),
                    image_paths=image_hashes
                )
                raise


# Global singleton client instance
gemma_client = GemmaClient()
