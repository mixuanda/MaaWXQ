import unittest
from datetime import datetime, timezone
from main import apply_event, initial_state, with_freshness

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
class StateTests(unittest.TestCase):
    def test_unknown_and_identity(self):
        original = initial_state()
        event = {"type": "opponent_observation", "opponent_id": "unknown", "observed_at": "2026-10-17T11:59:00Z", "units": [{"name": "弈星"}]}
        state = apply_event(original, event, NOW)
        self.assertEqual(original["opponent_history"], [])
        self.assertEqual(state["player_chess_player"]["entity_type"], "chess_player")
        self.assertEqual(state["opponent_history"][0]["units"][0], {"entity_type": "hero", "name": "弈星", "hero_id": "unknown"})
        state = apply_event(state, event, NOW)
        self.assertEqual(len(state["opponent_history"]), 2)

    def test_freshness(self):
        state = apply_event(initial_state(), {"type": "opponent_observation", "opponent_id": "p2", "observed_at": "2026-10-17T11:58:00Z", "units": []}, NOW)
        self.assertEqual(with_freshness(state, 120, NOW)["opponent_history"][0]["freshness"], "fresh")
        self.assertEqual(with_freshness(state, 119, NOW)["opponent_history"][0]["freshness"], "stale")
        self.assertEqual(with_freshness(state, 120, NOW)["opening_bans"]["freshness"], "unknown")

    def test_bans_and_invalid_events(self):
        event = {"type": "opening_bans", "observed_at": "2026-10-17T11:59:00Z", "lineups": []}
        state = apply_event(initial_state(), event, NOW)
        self.assertEqual(state["opening_bans"]["status"], "observed")
        for patch in ({"observed_at": "2026-10-17T11:59:00"}, {"observed_at": "2099-01-01T00:00:00Z"}, {"lineups": "bad"}, {"unexpected": 1}):
            with self.assertRaises(ValueError):
                apply_event(state, event | patch, NOW)
        with self.assertRaises(ValueError):
            apply_event(state, event | {"observed_at": "2026-10-17T11:58:00Z"}, NOW)

if __name__ == "__main__":
    unittest.main()
