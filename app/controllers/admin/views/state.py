from sqladmin.filters import StaticValuesFilter

from app.controllers.admin.views.base import AdminModelView
from app.domains.state import PipelineType
from app.infra.postgres.models.ingestion import IngestionPipelineState


class IngestionPipelineStateView(AdminModelView, model=IngestionPipelineState):
    """Admin view for IngestionPipelineState model."""

    can_create, can_delete, can_edit, can_export = False, False, False, False
    name = "Pipeline"
    name_plural = "Pipelines"
    icon = "fa-solid fa-timeline"

    column_list = [
        IngestionPipelineState.station_id,
        IngestionPipelineState.pipeline_type,
        IngestionPipelineState.meta,
        IngestionPipelineState.last_processed_at,
        IngestionPipelineState.next_run_at,
        IngestionPipelineState.interval_sec,
        IngestionPipelineState.error,
        IngestionPipelineState.priority,
        IngestionPipelineState.claimed_by,
        IngestionPipelineState.lease_until,
    ]
    column_details_list = column_list
    column_filters = [
        StaticValuesFilter(
            IngestionPipelineState.pipeline_type,
            values=[(pipeline_type.value, pipeline_type.value) for pipeline_type in PipelineType],
            title="Pipeline",
        )
    ]
    page_size = 25
