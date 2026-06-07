"""Tests for static-window wiring in the storage layer.

The store module imports a few Home Assistant symbols at module load time;
these are stubbed below so the pure data-manipulation logic (add/update/complete
chore window handling) can be exercised without a running Home Assistant.
"""
from __future__ import annotations

import sys
import types
from datetime import date

import pytest

# --- Minimal Home Assistant stubs (must be registered before importing store) ---
_ha = sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
_ha_helpers = sys.modules.setdefault(
    "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
)
_ha_storage = sys.modules.setdefault(
    "homeassistant.helpers.storage", types.ModuleType("homeassistant.helpers.storage")
)
_ha_core = sys.modules.setdefault(
    "homeassistant.core", types.ModuleType("homeassistant.core")
)


class _StubStore:
    """Stand-in for homeassistant.helpers.storage.Store."""

    def __class_getitem__(cls, _item):  # support Store[dict[str, Any]]
        return cls

    def __init__(self, *args, **kwargs) -> None:
        pass


_ha_storage.Store = _StubStore
_ha_core.HomeAssistant = object

from custom_components.simple_chores.store import SimpleChoresStore  # noqa: E402


@pytest.fixture
def store() -> SimpleChoresStore:
    return SimpleChoresStore(hass=object())


class TestAddChoreWindow:
    """Windowed chores get a static calendar window on creation."""

    def test_biannual_chore_gets_window(self, store):
        chore = store.add_chore(
            "Service furnace",
            "area_garage",
            "biannual",
            start_date=date(2099, 3, 15),  # far-future to be deterministic
        )
        assert chore["window_start"] == "2099-01-01"
        assert chore["window_end"] == "2099-06-30"
        # next_due is kept in sync with the window end for the sensor layer.
        assert chore["next_due"] == "2099-06-30"

    def test_quarterly_chore_gets_window(self, store):
        chore = store.add_chore(
            "Clean gutters",
            "area_garage",
            "quarterly",
            start_date=date(2099, 5, 10),
        )
        assert chore["window_start"] == "2099-04-01"
        assert chore["window_end"] == "2099-06-30"
        assert chore["next_due"] == "2099-06-30"

    def test_non_windowed_chore_has_no_window(self, store):
        chore = store.add_chore(
            "Vacuum",
            "area_living_room",
            "weekly",
            start_date=date(2099, 3, 15),
        )
        assert chore.get("window_start") is None
        assert chore.get("window_end") is None
        # Existing behavior unchanged: next_due == start_date.
        assert chore["next_due"] == "2099-03-15"


class TestCompleteChoreWindow:
    """Completing a windowed chore advances to the next static calendar window."""

    def test_completion_advances_to_next_static_window(self, store):
        # Target window starts as H1 2099 (Jan-Jun).
        chore = store.add_chore(
            "Service furnace",
            "area_garage",
            "biannual",
            start_date=date(2099, 3, 15),
        )
        chore_id = chore["id"]
        # Completing (in March, inside H1) advances to H2 2099 (Jul-Dec) -
        # statically, NOT to March + 6 months.
        result = store.complete_chore(
            chore_id, user_id="u1", user_name="Alice", next_due=None
        )
        assert result["window_start"] == "2099-07-01"
        assert result["window_end"] == "2099-12-31"
        assert result["next_due"] == "2099-12-31"
        assert result["is_completed"] is False
        assert result["last_completed_by"] == "u1"

    def test_second_completion_wraps_to_next_year(self, store):
        chore = store.add_chore(
            "Service furnace",
            "area_garage",
            "biannual",
            start_date=date(2099, 3, 15),
        )
        cid = chore["id"]
        store.complete_chore(cid, "u1", "Alice", next_due=None)  # -> H2 2099
        result = store.complete_chore(cid, "u1", "Alice", next_due=None)  # -> H1 2100
        assert result["window_start"] == "2100-01-01"
        assert result["window_end"] == "2100-06-30"

    def test_one_off_completion_still_marks_done(self, store):
        chore = store.add_chore("Hang picture", "area_office", "once")
        result = store.complete_chore(chore["id"], "u1", "Alice", next_due=None)
        assert result["is_completed"] is True


class TestMigrateWindows:
    """Legacy windowed chores are backfilled with static window fields on load."""

    def test_legacy_windowed_chore_gets_window_from_next_due(self, store):
        # Simulate a pre-window chore persisted before windows existed.
        store._data["chores"]["legacy1"] = {
            "id": "legacy1",
            "name": "Service furnace",
            "room_id": "area_garage",
            "frequency": "biannual",
            "next_due": "2099-04-10",
        }
        store._migrate_chores()
        chore = store._data["chores"]["legacy1"]
        # Window is the calendar window containing the existing due date.
        assert chore["window_start"] == "2099-01-01"
        assert chore["window_end"] == "2099-06-30"
        assert chore["next_due"] == "2099-06-30"

    def test_legacy_non_windowed_chore_untouched(self, store):
        store._data["chores"]["legacy2"] = {
            "id": "legacy2",
            "name": "Vacuum",
            "room_id": "area_living_room",
            "frequency": "weekly",
            "next_due": "2099-04-10",
        }
        store._migrate_chores()
        chore = store._data["chores"]["legacy2"]
        assert chore.get("window_start") is None
        assert chore.get("window_end") is None
        assert chore["next_due"] == "2099-04-10"


class TestUpdateChoreWindow:
    """Changing frequency to/from a windowed frequency adjusts window fields."""

    def test_switch_to_windowed_sets_window(self, store):
        chore = store.add_chore(
            "Vacuum",
            "area_living_room",
            "weekly",
            start_date=date(2099, 3, 15),
        )
        updated = store.update_chore(chore["id"], frequency="biannual")
        assert updated["window_start"] == "2099-01-01"
        assert updated["window_end"] == "2099-06-30"
        assert updated["next_due"] == "2099-06-30"

    def test_switch_to_non_windowed_clears_window(self, store):
        chore = store.add_chore(
            "Service furnace",
            "area_garage",
            "biannual",
            start_date=date(2099, 3, 15),
        )
        updated = store.update_chore(chore["id"], frequency="weekly")
        assert updated.get("window_start") is None
        assert updated.get("window_end") is None
