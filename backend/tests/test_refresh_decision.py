"""When does the scheduled refresh produce a new forecast?"""

from datetime import UTC, datetime, timedelta

from app.services.refresh import forecast_reason

NOW = datetime(2026, 11, 4, 6, 0, tzinfo=UTC)
WEEK = timedelta(days=7)


def test_forced() -> None:
    assert forecast_reason(NOW, NOW - timedelta(days=1), NOW, force=True, max_age=WEEK) == "forced"


def test_first_forecast_with_this_model_version() -> None:
    assert "no forecast" in (forecast_reason(None, None, NOW, force=False, max_age=WEEK) or "")


def test_new_results_since_last_forecast() -> None:
    last_run = NOW - timedelta(hours=10)
    reason = forecast_reason(last_run, NOW - timedelta(hours=2), NOW, force=False, max_age=WEEK)
    assert reason is not None and "changed" in reason


def test_nothing_changed_and_recent() -> None:
    last_run = NOW - timedelta(days=2)
    assert (
        forecast_reason(last_run, last_run - timedelta(hours=1), NOW, force=False, max_age=WEEK)
        is None
    )


def test_stale_forecast_is_refreshed_even_without_new_results() -> None:
    last_run = NOW - timedelta(days=8)
    reason = forecast_reason(last_run, last_run - timedelta(days=1), NOW, force=False, max_age=WEEK)
    assert reason is not None and "older" in reason
