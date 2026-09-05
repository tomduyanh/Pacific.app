import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend import main, vlm_screen
from backend.state import AppState


class LiveScreenTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.state = AppState()
        self.state.live_screen_last_commentary = "Reading documentation."
        self.state.live_screen_last_analysis = "Reading the introduction."
        self.result = {
            "commentary": "Reading documentation.",
            "screen_analysis": "Reading the API authentication section.",
            "events": [],
        }
        self.vision = AsyncMock(return_value=(self.result, "{}"))
        self.rescore = AsyncMock()
        for target, value in [
            ("app_state", self.state),
            ("analyze_live_screen", self.vision),
            ("_rescore_background", self.rescore),
        ]:
            patcher = patch.object(main, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def body(self, **kwargs):
        return main.LiveScreenTickBody(image_base64="ZnJhbWU=", **kwargs)

    async def test_web_analysis_updates_without_waiting_for_ranking_or_events(self):
        response = await main.live_screen_tick(self.body(rescore=False))
        self.assertTrue(response["state_changed"])
        self.assertFalse(response["applied"])
        self.assertEqual(self.state.live_screen_last_analysis, self.result["screen_analysis"])
        self.rescore.assert_not_awaited()
        self.assertEqual(self.vision.call_args.args[-1], "Reading the introduction.")

    async def test_existing_callers_still_receive_synchronous_ranking(self):
        await main.live_screen_tick(self.body())
        self.rescore.assert_awaited_once()

    async def test_rate_limit_measures_starts_not_completions(self):
        clock = [100.0]

        async def slow_vision(*args):
            clock[0] += main.LIVE_MIN_INTERVAL_SEC + 1
            return self.result, "{}"

        self.vision.side_effect = slow_vision
        with patch.object(main, "time", SimpleNamespace(monotonic=lambda: clock[0])):
            first = await main.live_screen_tick(self.body(rescore=False))
            second = await main.live_screen_tick(self.body(rescore=False))
        self.assertFalse(first["skipped"])
        self.assertFalse(second["skipped"])
        self.assertEqual(self.vision.await_count, 2)

    async def test_fast_repeat_is_throttled(self):
        await main.live_screen_tick(self.body(rescore=False))
        response = await main.live_screen_tick(self.body(rescore=False))
        self.assertEqual(response["reason"], "rate_limit")
        self.vision.assert_awaited_once()

    async def test_overlapping_frames_do_not_start_another_vision_call(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def held_vision(*args):
            entered.set()
            await release.wait()
            return self.result, "{}"

        self.vision.side_effect = held_vision
        task = asyncio.create_task(main.live_screen_tick(self.body(rescore=False)))
        await entered.wait()
        try:
            response = await main.live_screen_tick(self.body(rescore=False))
            self.assertEqual(response["reason"], "in_flight")
            self.vision.assert_awaited_once()
        finally:
            release.set()
            await task
        self.assertFalse(self.state.live_screen_inflight)

    async def test_reset_during_vision_discards_old_result(self):
        async def reset_during_vision(*args):
            with patch.object(self.state, "save_session"), patch.object(main, "collector"):
                await main.clear_session()
            return self.result, "{}"

        self.vision.side_effect = reset_during_vision
        response = await main.live_screen_tick(self.body(rescore=False))
        self.assertEqual(response["reason"], "session_reset")
        self.assertEqual(self.state.live_screen_last_analysis, "")
        self.rescore.assert_not_awaited()

    async def test_stalled_frame_has_a_total_deadline_and_releases_guard(self):
        async def stalled(*args):
            await asyncio.Event().wait()

        self.vision.side_effect = stalled
        with patch.object(main, "LIVE_MAX_LATENCY_SEC", 0.01):
            with self.assertRaises(HTTPException) as error:
                await main.live_screen_tick(self.body(rescore=False))
        self.assertEqual(error.exception.status_code, 504)
        self.assertFalse(self.state.live_screen_inflight)

    async def test_preview_does_not_change_retrieval_state(self):
        response = await main.live_screen_tick(self.body(apply=False))
        self.assertFalse(response["state_changed"])
        self.assertEqual(self.state.live_screen_last_analysis, "Reading the introduction.")
        self.rescore.assert_not_awaited()

    async def test_invalid_vision_json_is_not_reported_as_success(self):
        for output in ['{"commentary":', '{}']:
            with self.subTest(output=output):
                with patch.object(vlm_screen, "llm_vision_call", AsyncMock(return_value=output)):
                    with self.assertRaises(ValueError):
                        await vlm_screen.analyze_live_screen(b"frame", "image/jpeg", "", "")


if __name__ == "__main__":
    unittest.main()
