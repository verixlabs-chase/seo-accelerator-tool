from __future__ import annotations

from app.intelligence.global_graph.graph_query_engine import GraphQueryEngine
from app.intelligence.global_graph.graph_store import PersistentGraphStore
from app.intelligence.global_graph.graph_update_pipeline import GraphUpdatePipeline

_GRAPH_STORE = PersistentGraphStore()
_GRAPH_QUERY_ENGINE = GraphQueryEngine(_GRAPH_STORE)
_GRAPH_UPDATE_PIPELINE = GraphUpdatePipeline(_GRAPH_STORE)


def get_graph_store() -> PersistentGraphStore:
    return _GRAPH_STORE


def get_graph_query_engine() -> GraphQueryEngine:
    return _GRAPH_QUERY_ENGINE


def get_graph_update_pipeline() -> GraphUpdatePipeline:
    return _GRAPH_UPDATE_PIPELINE
