"""Unit tests for slack_engine module."""

from datetime import date, datetime
from uuid import uuid4

import pytest

from app.models.enums import CreatedBy, EnergyLevel, Priority, TaskStatus
from app.models.heartbeat import HeartbeatSeverity
from app.models.task import Task
from app.services.slack_engine import (
    TaskSlackResult,
    compute_all_slack,
    severity_from_ratio,
    sort_by_slack_priority,
)
from app.utils.datetime_utils import UTC

TZ = "Asia/Tokyo"
NOW = datetime(2024, 3, 1, 12, 0, tzinfo=UTC)  # 2024-03-01 21:00 JST
DAILY_CAP = 60  # 60 minutes/day


def _make_task(**overrides) -> Task:
    """Create a minimal Task for testing."""
    now = overrides.pop("now", NOW)
    data = {
        "id": uuid4(),
        "user_id": "user",
        "title": "Test Task",
        "description": None,
        "purpose": None,
        "project_id": None,
        "phase_id": None,
        "importance": Priority.MEDIUM,
        "urgency": Priority.MEDIUM,
        "energy_level": EnergyLevel.LOW,
        "estimated_minutes": 60,
        "due_date": None,
        "start_not_before": None,
        "pinned_date": None,
        "parent_id": None,
        "order_in_parent": None,
        "dependency_ids": [],
        "same_day_allowed": True,
        "min_gap_days": 0,
        "progress": 0,
        "start_time": None,
        "end_time": None,
        "is_fixed_time": False,
        "is_all_day": False,
        "location": None,
        "attendees": [],
        "meeting_notes": None,
        "recurring_meeting_id": None,
        "recurring_task_id": None,
        "milestone_id": None,
        "touchpoint_count": None,
        "touchpoint_minutes": None,
        "touchpoint_gap_days": 0,
        "touchpoint_steps": [],
        "completion_note": None,
        "guide": None,
        "requires_all_completion": False,
        "status": TaskStatus.TODO,
        "source_capture_id": None,
        "created_by": CreatedBy.USER,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "completed_by": None,
    }
    data.update(overrides)
    return Task(**data)


# ---------------------------------------------------------------------------
# severity_from_ratio
# ---------------------------------------------------------------------------
class TestSeverityFromRatio:
    def test_none_returns_low(self):
        assert severity_from_ratio(None) == HeartbeatSeverity.LOW

    def test_below_critical(self):
        assert severity_from_ratio(0.5) == HeartbeatSeverity.CRITICAL
        assert severity_from_ratio(0.99) == HeartbeatSeverity.CRITICAL

    def test_at_critical_boundary(self):
        assert severity_from_ratio(1.0) == HeartbeatSeverity.HIGH

    def test_between_critical_and_high(self):
        assert severity_from_ratio(1.2) == HeartbeatSeverity.HIGH
        assert severity_from_ratio(1.49) == HeartbeatSeverity.HIGH

    def test_at_high_boundary(self):
        assert severity_from_ratio(1.5) == HeartbeatSeverity.MEDIUM

    def test_between_high_and_medium(self):
        assert severity_from_ratio(1.8) == HeartbeatSeverity.MEDIUM

    def test_at_medium_boundary(self):
        assert severity_from_ratio(2.0) == HeartbeatSeverity.LOW

    def test_above_medium(self):
        assert severity_from_ratio(3.0) == HeartbeatSeverity.LOW
        assert severity_from_ratio(100.0) == HeartbeatSeverity.LOW

    def test_infinity(self):
        assert severity_from_ratio(float("inf")) == HeartbeatSeverity.LOW


# ---------------------------------------------------------------------------
# compute_all_slack — single task scenarios
# ---------------------------------------------------------------------------
class TestComputeSlackSingleTask:
    def test_single_task_with_deadline(self):
        """Task with 60min estimate, due in 2 days → ratio = 2*60/60 = 2.0."""
        due = datetime(2024, 3, 3, 14, 0, tzinfo=UTC)  # 2 days from today JST
        task = _make_task(estimated_minutes=60, due_date=due)
        summary = compute_all_slack([task], DAILY_CAP, TZ, NOW)

        assert len(summary.results) == 1
        r = summary.results[0]
        assert r.task_id == task.id
        assert r.remaining_minutes == 60
        assert r.chain_remaining_minutes == 60
        # days_until = (3/3 - 3/1).days + 1 = 3 days, available = 3*60 = 180
        assert r.available_minutes == 180
        assert r.slack_ratio == pytest.approx(3.0)
        assert r.severity == HeartbeatSeverity.LOW
        assert r.is_actionable is True

    def test_single_task_no_deadline(self):
        """Task without deadline → ratio = None, severity = LOW."""
        task = _make_task(estimated_minutes=120)
        summary = compute_all_slack([task], DAILY_CAP, TZ, NOW)

        r = summary.results[0]
        assert r.slack_ratio is None
        assert r.available_minutes is None
        assert r.effective_deadline is None
        assert r.severity == HeartbeatSeverity.LOW

    def test_task_with_progress(self):
        """50% progress → remaining = 30min instead of 60min."""
        due = datetime(2024, 3, 2, 14, 0, tzinfo=UTC)  # 1 day from today JST
        task = _make_task(estimated_minutes=60, progress=50, due_date=due)
        summary = compute_all_slack([task], DAILY_CAP, TZ, NOW)

        r = summary.results[0]
        assert r.remaining_minutes == 30
        assert r.chain_remaining_minutes == 30
        # available = 2 days * 60 = 120, ratio = 120/30 = 4.0
        assert r.slack_ratio == pytest.approx(4.0)

    def test_overdue_task(self):
        """Task with deadline in the past → ratio < 1.0 → CRITICAL."""
        due = datetime(2024, 2, 28, 14, 0, tzinfo=UTC)  # yesterday
        task = _make_task(estimated_minutes=60, due_date=due)
        summary = compute_all_slack([task], DAILY_CAP, TZ, NOW)

        r = summary.results[0]
        # days_until = max(0, (2/28 - 3/1).days + 1) → max(0, -1) → 0
        # available = 0, ratio = 0/60 = 0.0
        assert r.slack_ratio == pytest.approx(0.0)
        assert r.severity == HeartbeatSeverity.CRITICAL

    def test_chain_remaining_zero(self):
        """Task with no estimate → uses default, ratio = inf if 0 remaining."""
        due = datetime(2024, 3, 5, 14, 0, tzinfo=UTC)
        task = _make_task(estimated_minutes=60, progress=100, due_date=due)
        # progress=100 but status is TODO → remaining_minutes via formula = 0
        # fallback: get_remaining_minutes returns 0, but slack_engine uses
        # get_effective_estimated_minutes as fallback → 60 min
        summary = compute_all_slack([task], DAILY_CAP, TZ, NOW)
        r = summary.results[0]
        # When remaining from progress calc is 0, we use estimated as fallback
        assert r.remaining_minutes > 0


# ---------------------------------------------------------------------------
# compute_all_slack — dependency chain scenarios
# ---------------------------------------------------------------------------
class TestComputeSlackChain:
    def test_chain_a_b_c_deadline_on_c(self):
        """Chain A→B→C (C has deadline). A's chain_remaining includes B and C."""
        id_a, id_b, id_c = uuid4(), uuid4(), uuid4()
        due_c = datetime(2024, 3, 10, 14, 0, tzinfo=UTC)  # 9 days from today

        task_a = _make_task(id=id_a, estimated_minutes=60, dependency_ids=[])
        task_b = _make_task(id=id_b, estimated_minutes=60, dependency_ids=[id_a])
        task_c = _make_task(id=id_c, estimated_minutes=60, dependency_ids=[id_b], due_date=due_c)

        tasks = [task_a, task_b, task_c]
        summary = compute_all_slack(tasks, DAILY_CAP, TZ, NOW)
        by_id = summary.results_by_id

        # A: chain_remaining = A(60) + downstream B(60) + C(60) = 180（先頭が最も危険）
        # A's effective_deadline comes from downstream (C's deadline)
        r_a = by_id[id_a]
        assert r_a.chain_remaining_minutes == 180
        assert r_a.effective_deadline == due_c.astimezone(
            __import__("zoneinfo", fromlist=["ZoneInfo"]).ZoneInfo(TZ)
        ).date()

        # B: chain_remaining = B(60) + downstream C(60) = 120
        r_b = by_id[id_b]
        assert r_b.chain_remaining_minutes == 120

        # C: chain_remaining = C(60) only（末端タスク）
        r_c = by_id[id_c]
        assert r_c.chain_remaining_minutes == 60

        # A is actionable (no deps), B is blocked (A not done), C is blocked
        assert r_a.is_actionable is True
        assert r_b.is_actionable is False
        assert r_c.is_actionable is False

    def test_chain_middle_task_has_earlier_deadline(self):
        """If B has an earlier deadline than C, A's effective_deadline uses B's."""
        id_a, id_b, id_c = uuid4(), uuid4(), uuid4()
        due_b = datetime(2024, 3, 5, 14, 0, tzinfo=UTC)
        due_c = datetime(2024, 3, 10, 14, 0, tzinfo=UTC)

        task_a = _make_task(id=id_a, estimated_minutes=60)
        task_b = _make_task(id=id_b, estimated_minutes=60, dependency_ids=[id_a], due_date=due_b)
        task_c = _make_task(id=id_c, estimated_minutes=60, dependency_ids=[id_b], due_date=due_c)

        tasks = [task_a, task_b, task_c]
        summary = compute_all_slack(tasks, DAILY_CAP, TZ, NOW)

        # A's effective_deadline should be B's deadline (earlier)
        r_a = summary.results_by_id[id_a]
        expected = due_b.astimezone(
            __import__("zoneinfo", fromlist=["ZoneInfo"]).ZoneInfo(TZ)
        ).date()
        assert r_a.effective_deadline == expected

    def test_done_dependency_excluded_from_chain_remaining(self):
        """DONE tasks in chain don't contribute to chain_remaining."""
        id_a, id_b = uuid4(), uuid4()
        due_b = datetime(2024, 3, 5, 14, 0, tzinfo=UTC)

        task_a = _make_task(id=id_a, estimated_minutes=120, status=TaskStatus.DONE)
        task_b = _make_task(id=id_b, estimated_minutes=60, dependency_ids=[id_a], due_date=due_b)

        tasks = [task_a, task_b]
        summary = compute_all_slack(tasks, DAILY_CAP, TZ, NOW)

        # B's chain_remaining = only B(60), A is DONE
        r_b = summary.results_by_id[id_b]
        assert r_b.chain_remaining_minutes == 60
        assert r_b.is_actionable is True  # A is DONE


# ---------------------------------------------------------------------------
# compute_all_slack — filtering
# ---------------------------------------------------------------------------
class TestComputeSlackFiltering:
    def test_done_tasks_excluded(self):
        task = _make_task(status=TaskStatus.DONE)
        summary = compute_all_slack([task], DAILY_CAP, TZ, NOW)
        assert len(summary.results) == 0

    def test_waiting_tasks_excluded(self):
        task = _make_task(status=TaskStatus.WAITING)
        summary = compute_all_slack([task], DAILY_CAP, TZ, NOW)
        assert len(summary.results) == 0

    def test_fixed_time_tasks_excluded(self):
        task = _make_task(
            is_fixed_time=True,
            start_time=datetime(2024, 3, 1, 10, 0, tzinfo=UTC),
            end_time=datetime(2024, 3, 1, 11, 0, tzinfo=UTC),
        )
        summary = compute_all_slack([task], DAILY_CAP, TZ, NOW)
        assert len(summary.results) == 0

    def test_parent_tasks_excluded(self):
        parent_id = uuid4()
        parent = _make_task(id=parent_id, estimated_minutes=120)
        child = _make_task(parent_id=parent_id, estimated_minutes=60)
        summary = compute_all_slack([parent, child], DAILY_CAP, TZ, NOW)
        # Only child should be in results
        assert len(summary.results) == 1
        assert summary.results[0].task_id == child.id

    def test_empty_task_list(self):
        summary = compute_all_slack([], DAILY_CAP, TZ, NOW)
        assert len(summary.results) == 0
        assert summary.is_overloaded is False


# ---------------------------------------------------------------------------
# compute_all_slack — global capacity check
# ---------------------------------------------------------------------------
class TestGlobalCapacityCheck:
    def test_overloaded_when_demand_exceeds_capacity(self):
        """3 tasks × 2000min each = 6000min, horizon 60 days × 60min = 3600min."""
        tasks = [
            _make_task(estimated_minutes=2000),
            _make_task(estimated_minutes=2000),
            _make_task(estimated_minutes=2000),
        ]
        summary = compute_all_slack(tasks, DAILY_CAP, TZ, NOW, horizon_days=60)
        assert summary.total_demand_minutes == 6000
        assert summary.total_capacity_minutes == 3600
        assert summary.is_overloaded is True

    def test_not_overloaded_when_fits(self):
        tasks = [_make_task(estimated_minutes=30)]
        summary = compute_all_slack(tasks, DAILY_CAP, TZ, NOW, horizon_days=60)
        assert summary.is_overloaded is False


# ---------------------------------------------------------------------------
# sort_by_slack_priority
# ---------------------------------------------------------------------------
class TestSortBySlackPriority:
    def _make_result(self, task_id, ratio, severity=None):
        sev = severity or severity_from_ratio(ratio)
        return TaskSlackResult(
            task_id=task_id,
            remaining_minutes=60,
            chain_remaining_minutes=60,
            effective_deadline=date(2024, 3, 10),
            available_minutes=120,
            slack_ratio=ratio,
            severity=sev,
            is_actionable=True,
        )

    def test_danger_zone_sorted_by_ratio_ascending(self):
        """Tasks in danger zone (ratio < 1.5) sorted by ratio."""
        id1, id2, id3 = uuid4(), uuid4(), uuid4()
        r1 = self._make_result(id1, 0.5)  # CRITICAL
        r2 = self._make_result(id2, 1.2)  # HIGH
        r3 = self._make_result(id3, 0.8)  # CRITICAL

        t1 = _make_task(id=id1, importance=Priority.LOW)
        t2 = _make_task(id=id2, importance=Priority.HIGH)
        t3 = _make_task(id=id3, importance=Priority.MEDIUM)
        tasks_by_id = {t.id: t for t in [t1, t2, t3]}

        sorted_results = sort_by_slack_priority([r1, r2, r3], tasks_by_id)
        ratios = [r.slack_ratio for r in sorted_results]
        assert ratios == [0.5, 0.8, 1.2]

    def test_safe_zone_sorted_by_importance_descending(self):
        """Tasks in safe zone sorted by importance desc, then ratio asc."""
        id1, id2, id3 = uuid4(), uuid4(), uuid4()
        r1 = self._make_result(id1, 3.0)  # LOW severity
        r2 = self._make_result(id2, 2.5)  # LOW severity
        r3 = self._make_result(id3, 4.0)  # LOW severity

        t1 = _make_task(id=id1, importance=Priority.LOW)
        t2 = _make_task(id=id2, importance=Priority.HIGH)
        t3 = _make_task(id=id3, importance=Priority.MEDIUM)
        tasks_by_id = {t.id: t for t in [t1, t2, t3]}

        sorted_results = sort_by_slack_priority([r1, r2, r3], tasks_by_id)
        ids = [r.task_id for r in sorted_results]
        # HIGH first, then MEDIUM, then LOW
        assert ids == [id2, id3, id1]

    def test_danger_zone_before_safe_zone(self):
        """Danger zone tasks always come before safe zone."""
        id_danger, id_safe = uuid4(), uuid4()
        r_danger = self._make_result(id_danger, 1.0)  # HIGH
        r_safe = self._make_result(id_safe, 5.0)  # LOW

        t_danger = _make_task(id=id_danger, importance=Priority.LOW)
        t_safe = _make_task(id=id_safe, importance=Priority.HIGH)
        tasks_by_id = {t.id: t for t in [t_danger, t_safe]}

        sorted_results = sort_by_slack_priority([r_safe, r_danger], tasks_by_id)
        ids = [r.task_id for r in sorted_results]
        assert ids == [id_danger, id_safe]

    def test_none_ratio_goes_to_safe_zone(self):
        """Tasks with None ratio (no deadline) go to safe zone."""
        id_none, id_danger = uuid4(), uuid4()
        r_none = self._make_result(id_none, None)
        r_danger = self._make_result(id_danger, 0.9)

        t_none = _make_task(id=id_none, importance=Priority.HIGH)
        t_danger = _make_task(id=id_danger, importance=Priority.LOW)
        tasks_by_id = {t.id: t for t in [t_none, t_danger]}

        sorted_results = sort_by_slack_priority([r_none, r_danger], tasks_by_id)
        ids = [r.task_id for r in sorted_results]
        # Danger first, then safe (even though safe has HIGH importance)
        assert ids == [id_danger, id_none]

    def test_same_importance_sorted_by_ratio(self):
        """Within safe zone, same importance → sorted by ratio ascending."""
        id1, id2 = uuid4(), uuid4()
        r1 = self._make_result(id1, 3.0)
        r2 = self._make_result(id2, 2.0)

        t1 = _make_task(id=id1, importance=Priority.HIGH)
        t2 = _make_task(id=id2, importance=Priority.HIGH)
        tasks_by_id = {t.id: t for t in [t1, t2]}

        sorted_results = sort_by_slack_priority([r1, r2], tasks_by_id)
        ids = [r.task_id for r in sorted_results]
        assert ids == [id2, id1]  # ratio 2.0 before 3.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_no_estimate_uses_default(self):
        """Tasks with None estimated_minutes use default_task_minutes."""
        due = datetime(2024, 3, 5, 14, 0, tzinfo=UTC)
        task = _make_task(estimated_minutes=None, due_date=due)
        summary = compute_all_slack([task], DAILY_CAP, TZ, NOW, default_task_minutes=30)

        r = summary.results[0]
        assert r.remaining_minutes == 30  # uses default

    def test_no_estimate_defaults_to_daily_capacity(self):
        """When default_task_minutes is 0, falls back to daily_capacity."""
        due = datetime(2024, 3, 5, 14, 0, tzinfo=UTC)
        task = _make_task(estimated_minutes=None, due_date=due)
        summary = compute_all_slack([task], DAILY_CAP, TZ, NOW, default_task_minutes=0)

        r = summary.results[0]
        assert r.remaining_minutes == DAILY_CAP  # falls back to daily capacity

    def test_circular_dependency_no_infinite_loop(self):
        """Circular deps should not cause infinite loop (visited set)."""
        id_a, id_b = uuid4(), uuid4()
        task_a = _make_task(id=id_a, estimated_minutes=60, dependency_ids=[id_b])
        task_b = _make_task(id=id_b, estimated_minutes=60, dependency_ids=[id_a])

        # Should not hang
        summary = compute_all_slack([task_a, task_b], DAILY_CAP, TZ, NOW)
        assert len(summary.results) == 2

    def test_due_date_today(self):
        """Task due today → available = 1 day * capacity."""
        due_jst = datetime(2024, 3, 1, 14, 0, tzinfo=UTC)  # 3/1 23:00 JST
        task = _make_task(estimated_minutes=60, due_date=due_jst)
        summary = compute_all_slack([task], DAILY_CAP, TZ, NOW)

        r = summary.results[0]
        # due_date in JST = 3/1, today = 3/1 → days_until = (3/1 - 3/1).days + 1 = 1
        # available = 1 * 60 = 60, ratio = 60/60 = 1.0
        assert r.available_minutes == 60
        assert r.slack_ratio == pytest.approx(1.0)
        assert r.severity == HeartbeatSeverity.HIGH  # ratio = 1.0, which is >= 1.0 but < 1.5
