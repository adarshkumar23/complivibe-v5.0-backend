from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

from app.core.config import get_settings
from app.db.session import get_engine

_sqlalchemy_instrumented = False


def build_tracer_provider(exporter: SpanExporter | None = None) -> TracerProvider:
    settings = get_settings()
    provider = TracerProvider(resource=Resource.create({"service.name": settings.OTEL_SERVICE_NAME}))

    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))
    elif settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)))

    return provider


def instrument_app(app: FastAPI, tracer_provider: TracerProvider | None = None) -> TracerProvider | None:
    settings = get_settings()
    if tracer_provider is None:
        if not settings.OTEL_ENABLED:
            return None
        tracer_provider = build_tracer_provider()

    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)

    global _sqlalchemy_instrumented
    if not _sqlalchemy_instrumented:
        SQLAlchemyInstrumentor().instrument(engine=get_engine(), tracer_provider=tracer_provider)
        _sqlalchemy_instrumented = True

    return tracer_provider


def uninstrument_app(app: FastAPI) -> None:
    FastAPIInstrumentor.uninstrument_app(app)

    global _sqlalchemy_instrumented
    if _sqlalchemy_instrumented:
        SQLAlchemyInstrumentor().uninstrument()
        _sqlalchemy_instrumented = False
