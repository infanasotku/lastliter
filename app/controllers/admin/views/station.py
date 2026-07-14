from sqladmin import ModelView
from starlette.requests import Request

from app.controllers.admin.views.mixins import (
    AddStationBySharedLinkForm,
    AddStationBySharedLinkMixin,
    AddStationsByAreaForm,
    AddStationsByAreaMixin,
    StationStatsMixin,
)
from app.infra.postgres.models.station import Station

__all__ = [
    "AddStationBySharedLinkForm",
    "AddStationsByAreaForm",
    "StationView",
]


class StationView(
    StationStatsMixin,
    AddStationsByAreaMixin,
    AddStationBySharedLinkMixin,
    ModelView,
    model=Station,
):
    can_create, can_delete, can_edit, can_export = False, False, False, False
    name = "Station"
    name_plural = "Stations"

    column_list = "__all__"
    column_details_list = column_list
    page_size = 25

    def _optional_str(self, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()
        return value or None

    def _stations_list_url(self, request: Request) -> str:
        return str(request.url_for("admin:list", identity=self.identity))
