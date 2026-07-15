from sqladmin import ModelView
from starlette.requests import Request

from app.controllers.admin.views.mixins import (
    AddStationBySharedLinkForm,
    AddStationBySharedLinkMixin,
    AddStationsByAreaForm,
    AddStationsByAreaMixin,
    GdebenzLinkMixin,
    StationStatsMixin,
)
from app.infra.postgres.models.station import Station

__all__ = [
    "AddStationBySharedLinkForm",
    "AddStationsByAreaForm",
    "StationView",
]


class StationView(
    GdebenzLinkMixin,
    StationStatsMixin,
    AddStationsByAreaMixin,
    AddStationBySharedLinkMixin,
    ModelView,
    model=Station,
):
    can_create, can_delete, can_edit, can_export = False, False, False, False
    name = "Station"
    name_plural = "Stations"
    icon = "fa-solid fa-gas-pump"

    column_list = [
        Station.id,
        Station.name,
        Station.address,
        "gdebenz",
        Station.description,
        Station.lat,
        Station.lon,
    ]
    column_details_list = column_list
    page_size = 25

    def _optional_str(self, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()
        return value or None

    def _stations_list_url(self, request: Request) -> str:
        return str(request.url_for("admin:list", identity=self.identity))
