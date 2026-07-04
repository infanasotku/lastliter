from sqladmin import ModelView

from app.infra.postgres.models.station import Station


class StationView(ModelView, model=Station):
    can_create, can_delete, can_edit, can_export = False, False, False, False
