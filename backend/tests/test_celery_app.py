from datetime import timedelta

from celery.schedules import crontab

from app.celery_app import check_schedule


def test_whole_hour_intervals_align_to_window_starts():
    schedule = check_schedule(3)
    assert isinstance(schedule, crontab)
    assert schedule.hour == {0, 3, 6, 9, 12, 15, 18, 21}
    assert schedule.minute == {0}


def test_uneven_intervals_fall_back_to_timedelta():
    assert check_schedule(5) == timedelta(hours=5)
    assert check_schedule(0.5) == timedelta(minutes=30)
