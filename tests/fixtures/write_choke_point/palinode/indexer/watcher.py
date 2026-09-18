"""Intentional raw-write probe for the write-choke-point guard test."""


def injected_memory_write(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
