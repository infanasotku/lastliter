from sqladmin.filters import StaticValuesFilter

from app.controllers.admin.views.state import IngestionPipelineStateView
from app.domains.state import PipelineType
from app.infra.postgres.models.ingestion import IngestionPipelineState


def test_pipeline_type_uses_sqladmin_column_filter():
    [pipeline_type_filter] = IngestionPipelineStateView.column_filters

    assert isinstance(pipeline_type_filter, StaticValuesFilter)
    assert pipeline_type_filter.column is IngestionPipelineState.pipeline_type
    assert pipeline_type_filter.parameter_name == "pipeline_type"
    assert pipeline_type_filter.values == [(pipeline_type.value, pipeline_type.value) for pipeline_type in PipelineType]
