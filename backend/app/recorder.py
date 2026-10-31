"""
Playwright-based interactive recording session for DemoToSkill.
Launches a headed Chromium browser, injects client-side DOM event listeners,
captures settled before/after screenshots, compresses them to 1024px JPEG,
coalesces sequential input events, and broadcasts live steps to SSE queues.

Thread-isolated: Runs Playwright inside a dedicated background thread with
a Windows ProactorEventLoop to ensure complete reliability regardless of
Uvicorn's server event loop policy.
"""

import sys
import uuid
import asyncio
import threading
from typing import Optional, Callable, Any
from pathlib import Path

from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page

from app.config import (
    SHOTS_DIR,
    NETWORK_IDLE_TIMEOUT_MS,
    POST_ACTION_SETTLE_MS
)
from app.imaging import resize_and_compress_image, save_screenshot_bytes
from app.injected_script import INJECTED_RECORDER_JS
from app.locators import coalesce_recorded_events
from app.models import Step


class PlaywrightRecorder:
    """Manages an active browser recording session."""

    def __init__(self, recording_id: Optional[str] = None):
        self.recording_id = recording_id or f"rec_{uuid.uuid4().hex[:8]}"
        self.raw_events: list[dict[str, Any]] = []
        self.subscribers: list[asyncio.Queue] = []
        self.is_active = False

        self._thread: Optional[threading.Thread] = None
        self._thread_loop: Optional[asyncio.AbstractEventLoop] = None
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._step_counter = 0
        self._lock = threading.Lock()

    def subscribe(self) -> asyncio.Queue:
        """Subscribes an async queue to receive real-time step notifications."""
        q = asyncio.Queue()
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        """Removes a subscriber queue."""
        if q in self.subscribers:
            self.subscribers.remove(q)

    async def _broadcast(self, event_data: dict[str, Any]):
        """Broadcasts event data to all connected SSE subscriber queues thread-safely."""
        if self._main_loop and not self._main_loop.is_closed():
            for q in list(self.subscribers):
                try:
                    self._main_loop.call_soon_threadsafe(q.put_nowait, event_data)
                except Exception:
                    pass
        else:
            for q in list(self.subscribers):
                try:
                    q.put_nowait(event_data)
                except Exception:
                    pass

    async def _settle_page(self):
        """Awaits DOM stability: network idle capped at 1.5s + 300ms pause."""
        if not self._page or self._page.is_closed():
            return
        try:
            await self._page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT_MS)
        except Exception:
            # Networkidle timeout is expected on pages with polling or long-lived streams
            pass
        await asyncio.sleep(POST_ACTION_SETTLE_MS / 1000.0)

    async def _capture_screenshot(self, suffix: str) -> str:
        """Captures page screenshot, downscales to 1024px JPEG Q70, and returns filepath."""
        if not self._page or self._page.is_closed():
            return ""
        try:
            raw_png = await self._page.screenshot(type="png", full_page=False)
            compressed_jpeg = resize_and_compress_image(raw_png)
            filename = f"{self.recording_id}_step_{self._step_counter}_{suffix}.jpg"
            saved_path = save_screenshot_bytes(compressed_jpeg, filename)
            # Return relative static URL for frontend
            return f"/static/shots/{filename}"
        except Exception as e:
            print(f"[Recorder] Screenshot error: {e}")
            return ""

    async def _handle_dom_event(self, source, event_data: dict[str, Any]):
        """Handler invoked when injected JavaScript dispatches window.__record."""
        with self._lock:
            if not self.is_active:
                return

            self._step_counter += 1
            action = event_data.get("action")

            # Capture shot_before
            shot_before = await self._capture_screenshot("before")

            # Allow browser action to apply and settle
            await self._settle_page()

            # Capture shot_after
            shot_after = await self._capture_screenshot("after")

            recorded_event = {
                "idx": self._step_counter,
                "action": action,
                "value": event_data.get("value"),
                "key": event_data.get("key"),
                "target": event_data.get("target", {}),
                "shot_before": shot_before,
                "shot_after": shot_after,
                "timestamp": event_data.get("timestamp")
            }

            self.raw_events.append(recorded_event)

            step_summary = (
                event_data.get("target", {}).get("accessible_name") or
                event_data.get("target", {}).get("label") or
                event_data.get("target", {}).get("tag") or ""
            )
            step_dict = {
                "idx": self._step_counter,
                "action": action,
                "value": event_data.get("value"),
                "key": event_data.get("key"),
                "shot_before": shot_before,
                "shot_after": shot_after,
                "intent": f"{action.capitalize()} {step_summary}".strip(),
                "locators": [
                    {
                        "kind": "role",
                        "role": event_data.get("target", {}).get("role", "generic"),
                        "name": event_data.get("target", {}).get("accessible_name", "")
                    }
                ] if event_data.get("target") else [],
                "target_summary": step_summary
            }

            # Broadcast event for live SSE streaming
            await self._broadcast({
                "type": "step_recorded",
                "step": step_dict,
                **step_dict
            })

    async def start(self, start_url: str, headed: bool = True) -> str:
        """Launches browser in isolated Proactor thread, attaches listeners, and navigates."""
        try:
            self._main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._main_loop = None

        ready_evt = threading.Event()
        err_box = []

        def _thread_target():
            if sys.platform == "win32":
                self._thread_loop = asyncio.WindowsProactorEventLoopPolicy().new_event_loop()
            else:
                self._thread_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._thread_loop)

            async def _init_session():
                try:
                    self._playwright = await async_playwright().start()

                    launch_args = ["--no-default-browser-check"]
                    if headed:
                        launch_args.append("--start-maximized")

                    self._browser = await self._playwright.chromium.launch(
                        headless=not headed,
                        args=launch_args
                    )

                    self._context = await self._browser.new_context(
                        viewport={"width": 1280, "height": 800},
                        ignore_https_errors=True
                    )

                    await self._context.expose_binding("__record", self._handle_dom_event)
                    await self._context.add_init_script(INJECTED_RECORDER_JS)

                    self._page = await self._context.new_page()
                    self.is_active = True

                    try:
                        await self._page.goto(start_url, wait_until="domcontentloaded", timeout=15000)
                        await self._settle_page()
                    except Exception as nav_err:
                        err_str = str(nav_err)
                        if "ERR_CONNECTION_REFUSED" in err_str:
                            raise ConnectionError(
                                f"Cannot connect to '{start_url}' (Connection Refused). "
                                f"Please ensure your target web application is running, or visit the embedded demo at 'http://localhost:8000/demo/'."
                            )
                        elif "Timeout" in err_str:
                            raise TimeoutError(
                                f"Navigation to '{start_url}' timed out after 15s. Please check that the URL is active and reachable."
                            )
                        raise RuntimeError(f"Navigation failed: {err_str}")

                    # Record initial navigation step
                    self._step_counter += 1
                    initial_shot = await self._capture_screenshot("after")
                    nav_event = {
                        "idx": self._step_counter,
                        "action": "goto",
                        "url": start_url,
                        "shot_after": initial_shot
                    }
                    self.raw_events.append(nav_event)

                    step_dict = {
                        "idx": self._step_counter,
                        "action": "goto",
                        "value": start_url,
                        "url": start_url,
                        "shot_before": "",
                        "shot_after": initial_shot,
                        "intent": f"Navigate to {start_url}",
                        "locators": [],
                        "target_summary": start_url
                    }

                    await self._broadcast({
                        "type": "step_recorded",
                        "step": step_dict,
                        **step_dict
                    })
                except Exception as e:
                    err_box.append(e)
                finally:
                    ready_evt.set()

            self._thread_loop.create_task(_init_session())
            self._thread_loop.run_forever()

        self._thread = threading.Thread(target=_thread_target, daemon=True)
        self._thread.start()

        # Await startup without blocking the calling async loop
        while not ready_evt.is_set():
            await asyncio.sleep(0.05)

        if err_box:
            await self.stop()
            raise err_box[0]

        return self.recording_id

    async def stop(self) -> list[Step]:
        """Stops the session, closes browser, and returns coalesced Step objects."""
        self.is_active = False
        stopped_evt = threading.Event()

        async def _close():
            try:
                if self._context:
                    await self._context.close()
                if self._browser:
                    await self._browser.close()
                if self._playwright:
                    await self._playwright.stop()
            except Exception as e:
                print(f"[Recorder] Error during browser teardown: {e}")
            finally:
                if self._thread_loop and self._thread_loop.is_running():
                    self._thread_loop.stop()
                stopped_evt.set()

        if self._thread_loop and self._thread_loop.is_running():
            asyncio.run_coroutine_threadsafe(_close(), self._thread_loop)
            while not stopped_evt.is_set():
                await asyncio.sleep(0.05)

        # Broadcast completion
        await self._broadcast({"type": "recording_stopped", "recording_id": self.recording_id})

        # Coalesce consecutive input keystrokes into final fill steps
        final_steps = coalesce_recorded_events(self.raw_events)
        return final_steps
