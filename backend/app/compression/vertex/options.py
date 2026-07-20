"""Frequently adjusted Vertex request options for context compression."""

COMPRESSION_VERTEX_THINKING_LEVEL = "MEDIUM"
COMPRESSION_VERTEX_INCLUDE_THOUGHTS = False


def validate_compression_vertex_options() -> None:
    if COMPRESSION_VERTEX_THINKING_LEVEL not in {"MINIMAL", "LOW", "MEDIUM", "HIGH"}:
        raise ValueError("unsupported Vertex compression thinking level")


validate_compression_vertex_options()
