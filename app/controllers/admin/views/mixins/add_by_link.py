from typing import Any, Protocol

from dependency_injector.wiring import Provide, inject
from sqladmin import action, expose
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from wtforms import Form, StringField
from wtforms.validators import InputRequired

from app.container import Container
from app.dto.station import StartAddStationBySharedLinkCmd
from app.infra.common.correlation import get_request_context
from app.infra.logging import get_logger
from app.services.station import StationService

logger = get_logger().getChild(__name__)


class _AddStationBySharedLinkView(Protocol):
    identity: str
    name_plural: str
    templates: Any

    def _add_station_by_shared_link_url(self, request: Request) -> str: ...

    def _build_add_station_by_shared_link_cmd(
        self,
        form: "AddStationBySharedLinkForm",
    ) -> StartAddStationBySharedLinkCmd: ...

    def _optional_str(self, value: str | None) -> str | None: ...

    def _stations_list_url(self, request: Request) -> str: ...

    async def start_add_station_by_shared_link(self, cmd: StartAddStationBySharedLinkCmd) -> None: ...


class AddStationBySharedLinkForm(Form):
    shared_link = StringField(
        "Shared link",
        validators=[InputRequired()],
        description="Station shared link from gdebenz.ru.",
        render_kw={"class": "form-control"},
    )


class AddStationBySharedLinkMixin:
    @action(
        "add-station-by-shared-link-form",
        label="Add by link",
        add_in_detail=False,
    )
    async def add_station_by_shared_link_form_action(self: _AddStationBySharedLinkView, request: Request) -> Response:
        return RedirectResponse(self._add_station_by_shared_link_url(request), status_code=303)

    @expose("/add-by-shared-link", methods=["GET", "POST"])
    async def add_station_by_shared_link_form(self: _AddStationBySharedLinkView, request: Request) -> Response:
        form = (
            AddStationBySharedLinkForm(await request.form())
            if request.method == "POST"
            else AddStationBySharedLinkForm()
        )

        if request.method == "POST" and form.validate():
            cmd = self._build_add_station_by_shared_link_cmd(form)
            logger.info(
                f"Admin requested station add by shared link {cmd.shared_link}",
                extra={
                    "correlation_id": cmd.correlation_id,
                    "shared_link": cmd.shared_link,
                },
            )
            await self.start_add_station_by_shared_link(cmd)
            return RedirectResponse(self._stations_list_url(request), status_code=303)

        if request.method == "POST":
            logger.warning(f"Admin station add by shared link form validation failed: {form.errors}")

        return await self.templates.TemplateResponse(
            request,
            "station_add_by_shared_link.html",
            {
                "form": form,
                "form_action_url": self._add_station_by_shared_link_url(request),
                "list_url": self._stations_list_url(request),
                "model_view": self,
                "subtitle": self.name_plural,
                "title": "Add station by shared link",
            },
        )

    @inject
    async def start_add_station_by_shared_link(
        self,
        cmd: StartAddStationBySharedLinkCmd,
        #
        svc: StationService = Provide[Container.station_service],
    ) -> None:
        await svc.add_by_shared_link.start(cmd)

    def _build_add_station_by_shared_link_cmd(
        self: _AddStationBySharedLinkView,
        form: AddStationBySharedLinkForm,
    ) -> StartAddStationBySharedLinkCmd:
        shared_link = self._optional_str(form.shared_link.data)
        if shared_link is None:
            raise ValueError("Station add by shared link form is missing shared link")

        ctx = get_request_context()
        return StartAddStationBySharedLinkCmd(
            shared_link=shared_link,
            correlation_id=ctx.request_id,
        )

    def _add_station_by_shared_link_url(self: _AddStationBySharedLinkView, request: Request) -> str:
        return str(request.url_for(f"admin:view-{self.identity}-add_station_by_shared_link_form"))
