from dataclasses import dataclass


@dataclass
class MemoryItem:

    key: str

    value: str

    category: str = "general"
