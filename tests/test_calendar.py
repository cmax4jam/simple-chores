"""Tests for windowed multi-day events in the calendar platform.

Home Assistant symbols imported by calendar.py (and its coordinator/store
dependencies) are stubbed so the pure event-generation logic can run headless.
"""
from __future__ import annotations

import sys
import types
from datetime import date, timedelta

import pytest


def _module(name: str) -> types.ModuleType:
    return sys.modules.setdefault(name, types.ModuleType(name))


# --- Minimal Home Assistant stubs ---
_module("homeassistant")
_module("homeassistant.components")
_ha_cal = _module("homeassistant.components.calendar")
_ha_config = _module("homeassistant.config_entries")
_ha_core = _module("homeassistant.core")
_module("homeassistant.helpers")
_ha_ep = _module("homeassistant.helpers.entity_platform")
_ha_uc = _module("homeassistant.helpers.update_coordinator")
_ha_storage = _module("homeassistant.helpers.storage")


class _CalendarEvent:
    def __init__(self, start, end, summary, description=None, uid=None):
        self.start = start
        self.end = end
        self.summary = summary
        self.description = description
        self.uid = uid


class _Base:
    def __class_getitem__(cls, _item):
        return cls

    def __init__(self, *args, **kwargs):
        pass


class _CalendarEntity(_Base):
    pass


class _CoordinatorEntity(_Base):
    pass


class _DataUpdateCoordinator(_Base):
    pass


class _Store(_Base):
    pass


_ha_cal.CalendarEntity = _CalendarEntity
_ha_cal.CalendarEvent = _CalendarEvent
_ha_config.ConfigEntry = object
_ha_core.HomeAssistant = object
_ha_ep.AddEntitiesCallback = object
_ha_uc.CoordinatorEntity = _CoordinatorEntity
_ha_uc.DataUpdateCoordinator = _DataUpdateCoordinator
_ha_storage.Store = _Store

from custom_components.simple_chores.calendar import (  # noqa: E402
    SimpleChoresCalendar,
)


@pytest.fixture
def calendar() -> SimpleChoresCalendar:
    # Bypass __init__ (needs a real coordinator); _generate_chore_events is
    # effectively a pure method that doesn't touch instance state.
    return object.__new__(SimpleChoresCalendar)


class TestWindowedCalendarEvents:
    def test_biannual_chore_yields_multiday_window_spans(self, calendar):
        chore = {
            "id": "c1",
            "name": "Service furnace",
            "room_id": "area_garage",
            "frequency": "biannual",
            "next_due": "2024-06-30",
            "window_start": "2024-01-01",
            "window_end": "2024-06-30",
        }
        events = calendar._generate_chore_events(
            chore, {"area_garage": "Garage"}, date(2024, 1, 1), date(2024, 12, 31)
        )
        spans = [(e.start, e.end) for e in events]
        assert spans == [
            (date(2024, 1, 1), date(2024, 7, 1)),  # H1, end exclusive
            (date(2024, 7, 1), date(2025, 1, 1)),  # H2, end exclusive
        ]

    def test_window_event_is_multiday(self, calendar):
        chore = {
            "id": "c1",
            "name": "Clean gutters",
            "room_id": "area_garage",
            "frequency": "quarterly",
            "next_due": "2024-03-31",
            "window_start": "2024-01-01",
            "window_end": "2024-03-31",
        }
        events = calendar._generate_chore_events(
            chore, {"area_garage": "Garage"}, date(2024, 1, 1), date(2024, 3, 31)
        )
        assert len(events) == 1
        event = events[0]
        assert (event.end - event.start) == timedelta(days=91)  # Q1 2024 length

    def test_non_windowed_chore_stays_single_day(self, calendar):
        chore = {
            "id": "c2",
            "name": "Vacuum",
            "room_id": "area_living_room",
            "frequency": "weekly",
            "next_due": "2024-06-03",
            "recurrence_type": "interval",
            "interval": 1,
        }
        events = calendar._generate_chore_events(
            chore, {"area_living_room": "Living"}, date(2024, 6, 1), date(2024, 6, 10)
        )
        assert events, "expected at least one weekly event"
        for event in events:
            assert (event.end - event.start) == timedelta(days=1)
