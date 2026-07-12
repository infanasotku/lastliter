from dependency_injector.wiring import Provide, inject
from sqladmin import ModelView, action, expose
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from wtforms import FloatField, Form, StringField
from wtforms.validators import InputRequired, NumberRange, Optional

from app.container import Container
from app.domains.station import StationScore
from app.dto.station import GetStationStatsCmd, StartSyncStationCmd, SyncStationFilters
from app.infra.common.correlation import get_request_context
from app.infra.logging import get_logger
from app.infra.postgres.models.station import Station
from app.services.station import StationService

logger = get_logger().getChild(__name__)


class StationSyncForm(Form):
    by_id = StringField(
        "ID filter",
        validators=[Optional()],
        description="Optional exact station id.",
        render_kw={"class": "form-control"},
    )
    by_name = StringField(
        "Name filter",
        validators=[Optional()],
        description="Optional station name substring.",
        render_kw={"class": "form-control"},
    )
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

    column_list = "__all__"
    column_details_list = column_list
    page_size = 25

    @action(
        "station-stats",
        label="Statistics",
        add_in_detail=True,
        add_in_list=False,
    )
    async def station_stats_action(self, request: Request) -> Response:
        station_id = request.query_params.get("pks", "").split(",", maxsplit=1)[0]
        if not station_id:
            return RedirectResponse(self._stations_list_url(request), status_code=303)

        return RedirectResponse(self._station_stats_url(request, station_id), status_code=303)

    @expose("/stats/{station_id}", methods=["GET"])
    async def station_stats(self, request: Request) -> Response:
        station_id = request.path_params["station_id"]
        scores = await self.get_stats(GetStationStatsCmd(station_id=station_id))

        return await self.templates.TemplateResponse(
            request,
            "station_stats.html",
            {
                "hours": range(24),
                "list_url": self._stations_list_url(request),
                "model_view": self,
                "scores": [
                    {
                        "confidence": score.confidence,
                        "hour": score.hour,
                        "score": score.score,
                        "weekday": score.weekday,
                    }
                    for score in scores
                ],
                "station_id": station_id,
                "subtitle": self.name_plural,
                "title": f"Station {station_id} statistics",
                "weekdays": enumerate(
                    ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"),
                    start=1,
                ),
            },
        )

    @inject
    async def get_stats(
        self,
        cmd: GetStationStatsCmd,
        #
        svc: StationService = Provide[Container.station_service],
    ) -> list[StationScore]:
        return await svc.get_station_stats(cmd)

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
            logger.info(
                f"Admin requested station sync for bounds ({cmd.lat1}, {cmd.lon1}) - ({cmd.lat2}, {cmd.lon2})",
                extra={
                    "by_id": cmd.filters.by_id,
                    "by_name": cmd.filters.by_name,
                    "correlation_id": cmd.correlation_id,
                    "lat1": cmd.lat1,
                    "lon1": cmd.lon1,
                    "lat2": cmd.lat2,
                    "lon2": cmd.lon2,
                },
            )
            await self.sync_stations(cmd)
            return RedirectResponse(self._stations_list_url(request), status_code=303)

        if request.method == "POST":
            logger.warning(f"Admin station sync form validation failed: {form.errors}")

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
        cmd: StartSyncStationCmd,
        #
        svc: StationService = Provide[Container.station_service],
    ) -> None:
        await svc.start_sync_stations(cmd)

    def _build_sync_stations_cmd(self, form: StationSyncForm) -> StartSyncStationCmd:
        if form.lat1.data is None or form.lon1.data is None or form.lat2.data is None or form.lon2.data is None:
            raise ValueError("Station sync form is missing required coordinates")

        ctx = get_request_context()
        return StartSyncStationCmd(
            lat1=form.lat1.data,
            lon1=form.lon1.data,
            lat2=form.lat2.data,
            lon2=form.lon2.data,
            correlation_id=ctx.request_id,
            filters=SyncStationFilters(
                by_id=self._optional_str(form.by_id.data),
                by_name=self._optional_str(form.by_name.data),
            ),
        )

    def _optional_str(self, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()
        return value or None

    def _sync_stations_url(self, request: Request) -> str:
        return str(request.url_for(f"admin:view-{self.identity}-sync_stations_form"))

    def _stations_list_url(self, request: Request) -> str:
        return str(request.url_for("admin:list", identity=self.identity))

    def _station_stats_url(self, request: Request, station_id: str) -> str:
        return str(
            request.url_for(
                f"admin:view-{self.identity}-station_stats",
                station_id=station_id,
            )
        )
