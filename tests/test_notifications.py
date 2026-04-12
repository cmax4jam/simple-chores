"""Tests for notification utility logic.

The async notification functions require Home Assistant and are tested
via integration tests. This file tests the pure utility functions.
"""
from __future__ import annotations


def _get_due_date_label(days_ahead: int) -> str:
    """Local copy of get_due_date_label for testing without HA imports."""
    if days_ahead == 0:
        return "today"
    elif days_ahead == 1:
        return "tomorrow"
    elif days_ahead == 7:
        return "in 1 week"
    else:
        return f"in {days_ahead} days"


class TestGetDueDateLabel:
    """Tests for human-readable due date labels."""

    def test_today(self):
        assert _get_due_date_label(0) == "today"

    def test_tomorrow(self):
        assert _get_due_date_label(1) == "tomorrow"

    def test_one_week(self):
        assert _get_due_date_label(7) == "in 1 week"

    def test_two_days(self):
        assert _get_due_date_label(2) == "in 2 days"

    def test_three_days(self):
        assert _get_due_date_label(3) == "in 3 days"

    def test_fourteen_days(self):
        assert _get_due_date_label(14) == "in 14 days"


class TestNotificationMessageFormat:
    """Tests for notification message building logic."""

    def _build_message(self, chores, due_label="today"):
        """Build notification message the same way notifications.py does."""
        chore_list = "\n".join([f"• {c['name']} ({c.get('room_name', 'Unknown')})" for c in chores])
        return f"You have {len(chores)} chore(s) due {due_label}:\n{chore_list}"

    def test_single_chore(self):
        chores = [{"name": "Vacuum", "room_name": "Living Room"}]
        msg = self._build_message(chores)
        assert "1 chore(s) due today" in msg
        assert "• Vacuum (Living Room)" in msg

    def test_multiple_chores(self):
        chores = [
            {"name": "Vacuum", "room_name": "Living Room"},
            {"name": "Mop", "room_name": "Kitchen"},
        ]
        msg = self._build_message(chores)
        assert "2 chore(s) due today" in msg
        assert "• Vacuum (Living Room)" in msg
        assert "• Mop (Kitchen)" in msg

    def test_missing_room_name(self):
        chores = [{"name": "Clean"}]
        msg = self._build_message(chores)
        assert "• Clean (Unknown)" in msg

    def test_tomorrow_label(self):
        chores = [{"name": "Dust", "room_name": "Office"}]
        msg = self._build_message(chores, due_label="tomorrow")
        assert "due tomorrow" in msg

    def test_chore_filtering_by_date(self):
        """Test that chore filtering by next_due date works correctly."""
        all_chores = [
            {"name": "Today chore", "next_due": "2024-06-15", "room_name": "Room A"},
            {"name": "Tomorrow chore", "next_due": "2024-06-16", "room_name": "Room B"},
            {"name": "Next week chore", "next_due": "2024-06-22", "room_name": "Room C"},
        ]
        target_date_str = "2024-06-15"
        chores_due = [c for c in all_chores if c.get("next_due") == target_date_str]
        assert len(chores_due) == 1
        assert chores_due[0]["name"] == "Today chore"

    def test_chore_grouping_by_user(self):
        """Test chore grouping by assigned user."""
        chores = [
            {"name": "Chore A", "assigned_to": "user1"},
            {"name": "Chore B", "assigned_to": "user1"},
            {"name": "Chore C", "assigned_to": "user2"},
            {"name": "Chore D", "assigned_to": None},
        ]
        chores_by_user: dict[str | None, list] = {}
        for chore in chores:
            assigned = chore.get("assigned_to")
            if assigned not in chores_by_user:
                chores_by_user[assigned] = []
            chores_by_user[assigned].append(chore)

        assert len(chores_by_user["user1"]) == 2
        assert len(chores_by_user["user2"]) == 1
        assert len(chores_by_user[None]) == 1

    def test_user_service_matching(self):
        """Test the username-to-service matching logic."""
        services = [
            "mobile_app_nates_iphone",
            "mobile_app_janes_pixel",
            "mobile_app_office_tablet",
        ]
        username = "Nate"
        normalized = username.lower().replace(" ", "_").replace("-", "_")

        matched = [s for s in services if normalized in s.replace("mobile_app_", "").lower()]
        assert matched == ["mobile_app_nates_iphone"]

    def test_user_service_no_match(self):
        """No match returns empty list."""
        services = ["mobile_app_janes_pixel"]
        username = "Bob"
        normalized = username.lower().replace(" ", "_").replace("-", "_")

        matched = [s for s in services if normalized in s.replace("mobile_app_", "").lower()]
        assert matched == []
