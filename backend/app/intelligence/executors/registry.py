from __future__ import annotations

from app.intelligence.executors.base import BaseExecutor
from app.intelligence.executors.create_content_brief import CreateContentBriefExecutor
from app.intelligence.executors.fix_missing_title import FixMissingTitleExecutor
from app.intelligence.executors.improve_internal_links import ImproveInternalLinksExecutor
from app.intelligence.executors.optimize_gbp_profile import OptimizeGbpProfileExecutor
from app.intelligence.executors.publish_schema_markup import PublishSchemaMarkupExecutor

_EXECUTORS: dict[str, BaseExecutor] = {
    CreateContentBriefExecutor.execution_type: CreateContentBriefExecutor(),
    ImproveInternalLinksExecutor.execution_type: ImproveInternalLinksExecutor(),
    FixMissingTitleExecutor.execution_type: FixMissingTitleExecutor(),
    OptimizeGbpProfileExecutor.execution_type: OptimizeGbpProfileExecutor(),
    PublishSchemaMarkupExecutor.execution_type: PublishSchemaMarkupExecutor(),
}


def get_executor(execution_type: str) -> BaseExecutor:
    resolved = _EXECUTORS.get(execution_type)
    if resolved is None:
        raise ValueError(f'Unsupported execution_type: {execution_type}')
    return resolved


def list_execution_types() -> list[str]:
    return sorted(_EXECUTORS.keys())
