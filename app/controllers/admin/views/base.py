from datetime import UTC, datetime

from markupsafe import Markup
from sqladmin import ModelView


def format_browser_datetime(value: datetime) -> Markup:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    iso_value = value.isoformat()
    return Markup('<time data-browser-datetime datetime="{value}">{value}</time>').format(value=iso_value)


class AdminModelView(ModelView):
    list_template = "admin/list.html"
    details_template = "admin/details.html"
    column_type_formatters = {
        **ModelView.column_type_formatters,
        datetime: format_browser_datetime,
    }
