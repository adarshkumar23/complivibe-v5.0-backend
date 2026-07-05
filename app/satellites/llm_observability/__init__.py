"""Satellite-only LLM runtime observability adapters.

Core code must not import this package. This satellite pushes monitoring values into
core only through the existing inbound `/api/v1/ai-monitoring/readings` endpoint.
"""
