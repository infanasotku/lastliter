from datetime import datetime, timedelta, timezone

from markupsafe import Markup

from app.controllers.admin.views.base import AdminModelView, format_browser_datetime


def test_formats_aware_datetime_for_browser_conversion():
    tz = timezone(timedelta(hours=7))
    value = datetime(2026, 7, 15, 21, 55, 50, tzinfo=tz)

    formatted = format_browser_datetime(value)

    assert isinstance(formatted, Markup)
    assert str(formatted) == (
        '<time data-browser-datetime datetime="2026-07-15T21:55:50+07:00">2026-07-15T21:55:50+07:00</time>'
    )
    assert value.tzinfo is tz


def test_treats_naive_datetime_as_utc():
    formatted = format_browser_datetime(datetime(2026, 7, 15, 14, 55, 50))

    assert 'datetime="2026-07-15T14:55:50+00:00"' in formatted


def test_admin_views_include_browser_datetime_script():
    assert AdminModelView.list_template == "admin/list.html"
    assert AdminModelView.details_template == "admin/details.html"
    assert AdminModelView.column_type_formatters[datetime] is format_browser_datetime
