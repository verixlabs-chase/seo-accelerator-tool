from __future__ import annotations

import logging

from fastapi import FastAPI


logger = logging.getLogger("lsos.tracing")
_tracing_initialized = False


def setup_tracing(app: FastAPI, *, otel_exporter_endpoint: str) -> None:
    global _tracing_initialized
    endpoint = otel_exporter_endpoint.strip()
    if not endpoint or _tracing_initialized:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception:
        logger.warning("OpenTelemetry packages unavailable; tracing bootstrap skipped.")
        return

    try:
        resource = Resource.create({"service.name": "lsos-api"})
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        trace.set_tracer_provider(tracer_provider)
        FastAPIInstrumentor.instrument_app(app)
        RequestsInstrumentor().instrument()
        _tracing_initialized = True
    except Exception:
        logger.exception("OpenTelemetry bootstrap failed; continuing without tracing.")
