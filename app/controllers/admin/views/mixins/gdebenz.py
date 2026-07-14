from collections.abc import Callable
from typing import Any, Protocol, cast
from urllib.parse import quote

from dependency_injector.wiring import Provide, inject
from markupsafe import Markup, escape
from sqladmin import expose
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.container import Container
from app.infra.postgres.models.station import Station
from app.services.station import StationService


class _GdebenzLinkView(Protocol):
    _detail_formatters: dict[str, Callable[[Station, str], Any]]
    _list_formatters: dict[str, Callable[[Station, str], Any]]
    identity: str

    def _admin_base_url(self) -> str: ...

    def gdebenz(self, model: Station, _: str) -> Markup: ...

    async def get_link_by_station_id(self, station_id: str) -> str: ...


class GdebenzLinkMixin:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        view = cast(_GdebenzLinkView, self)
        view._list_formatters["gdebenz"] = view.gdebenz
        view._detail_formatters["gdebenz"] = view.gdebenz

    def gdebenz(self: _GdebenzLinkView, model: Station, _: str) -> Markup:
        station_id = quote(model.id, safe="")
        href = f"{self._admin_base_url()}/{self.identity}/extend/{station_id}"

        return Markup(f'<a href="{escape(href)}" target="_blank" rel="noopener noreferrer">gdebenz</a>')

    @expose("/extend/{station_id}", methods=["GET"])
    async def extend(self: _GdebenzLinkView, request: Request) -> Response:
        station_id = request.path_params["station_id"]
        link = await self.get_link_by_station_id(station_id)

        return RedirectResponse(link, status_code=303)

    @inject
    async def get_link_by_station_id(
        self,
        station_id: str,
        #
        svc: StationService = Provide[Container.station_service],
    ) -> str:
        return await svc.get_link_by_station_id(station_id)

    def _admin_base_url(self: _GdebenzLinkView) -> str:
        admin = getattr(self, "_admin_ref", None)
        base_url = getattr(admin, "base_url", "/admin")

        return str(base_url).rstrip("/")
