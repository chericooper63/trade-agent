from __future__ import annotations

from .events import AgentEvent


class KnowledgeGraph:
    """A lightweight shared agent knowledge graph for entities and relations.

    This keeps the repository aligned with the requested seven-agent layered
    trading architecture by giving the agents a minimal common memory object.
    """

    def __init__(self):
        self.entities: dict[str, dict] = {}
        self.relations: set[tuple[str, str, str]] = set()
        self.events: list[dict] = []

    def add_entity(self, name: str, facts: dict | None = None) -> None:
        self.entities[name] = dict(facts or {})

    def add_relation(self, left: str, relation: str, right: str) -> None:
        self.relations.add((left, relation, right))

    def record_event(self, event: AgentEvent) -> dict:
        self.add_entity(event.symbol, {"symbol": event.symbol})
        payload = {
            "source": event.source,
            "event_type": event.event_type,
            "symbol": event.symbol,
            "confidence": event.confidence,
            "evidence": dict(event.evidence),
            "assumptions": list(event.assumptions),
            "payload": dict(event.payload),
        }
        self.events.append(payload)
        return payload

    def related_entities(self, name: str) -> list[tuple[str, str, str]]:
        return [item for item in self.relations if item[0] == name or item[2] == name]

    def snapshot(self) -> dict:
        return {
            "entities": self.entities,
            "relations": sorted(list(self.relations)),
            "events": list(self.events),
        }
