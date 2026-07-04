from dependency_injector.wiring import Provide, inject
from sqladmin import ModelView, action, expose
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from wtforms import FloatField, Form
from wtforms.validators import InputRequired, NumberRange

from app.container import Container
from app.dto.station import SyncStationCmd
from app.infra.postgres.models.station import Station
from app.services.station import StationService


class StationSyncForm(Form):
    lat1 = FloatField(
        "Latitude 1",
        validators=[
            InputRequired(),
            NumberRange(min=-90, max=90),
        ],
        description="South-west or first square corner latitude.",
        render_kw={"class": "form-control"},
    )
    lon1 = FloatField(
        "Longitude 1",
        validators=[
            InputRequired(),
            NumberRange(min=-180, max=180),
        ],
        description="South-west or first square corner longitude.",
        render_kw={"class": "form-control"},
    )
    lat2 = FloatField(
        "Latitude 2",
        validators=[
            InputRequired(),
            NumberRange(min=-90, max=90),
        ],
        description="North-east or opposite square corner latitude.",
        render_kw={"class": "form-control"},
    )
    lon2 = FloatField(
        "Longitude 2",
        validators=[
            InputRequired(),
            NumberRange(min=-180, max=180),
        ],
        description="North-east or opposite square corner longitude.",
        render_kw={"class": "form-control"},
    )


class StationView(ModelView, model=Station):
    can_create, can_delete, can_edit, can_export = False, False, False, False
    name = "Station"
    name_plural = "Stations"

    @action(
        "sync-stations-form",
        label="Sync stations",
        add_in_detail=False,
    )
    async def sync_stations_form_action(self, request: Request) -> Response:
        return RedirectResponse(self._sync_stations_url(request), status_code=303)

    @expose("/sync", methods=["GET", "POST"])
    async def sync_stations_form(self, request: Request) -> Response:
        form = StationSyncForm(await request.form()) if request.method == "POST" else StationSyncForm()

        if request.method == "POST" and form.validate():
            cmd = self._build_sync_stations_cmd(form)
            await self.sync_stations(cmd)
            return RedirectResponse(self._stations_list_url(request), status_code=303)

        return await self.templates.TemplateResponse(
            request,
            "station_sync.html",
            {
                "form": form,
                "form_action_url": self._sync_stations_url(request),
                "list_url": self._stations_list_url(request),
                "model_view": self,
                "subtitle": self.name_plural,
                "title": "Sync stations",
            },
        )

    @inject
    async def sync_stations(
        self,
        cmd: SyncStationCmd,
        #
        svc: StationService = Provide[Container.station_service],
    ) -> None:
        await svc.sync_stations(cmd)

    def _build_sync_stations_cmd(self, form: StationSyncForm) -> SyncStationCmd:
        if form.lat1.data is None or form.lon1.data is None or form.lat2.data is None or form.lon2.data is None:
            raise ValueError("Station sync form is missing required coordinates")

        return SyncStationCmd(
            lat1=form.lat1.data,
            lon1=form.lon1.data,
            lat2=form.lat2.data,
            lon2=form.lon2.data,
        )

    def _sync_stations_url(self, request: Request) -> str:
        return str(request.url_for(f"admin:view-{self.identity}-sync_stations_form"))

    def _stations_list_url(self, request: Request) -> str:
        return str(request.url_for("admin:list", identity=self.identity))
