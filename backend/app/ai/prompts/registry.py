from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """Immutable versioned prompt definition."""

    name: str
    version: str
    system_instruction: str
    user_template: str

    def render(self, **kwargs: object) -> str:
        """Format the prompt template with explicit named arguments."""
        return self.user_template.format(**kwargs)


class PromptRegistry:
    """In-memory registry for versioned AI prompt templates."""

    def __init__(self) -> None:
        self._templates: dict[tuple[str, str], PromptTemplate] = {}
        self._latest: dict[str, PromptTemplate] = {}

    def register(self, template: PromptTemplate) -> PromptTemplate:
        key = (template.name, template.version)
        if key in self._templates:
            raise ValueError(f"Duplicate prompt template: {template.name}:{template.version}")
        self._templates[key] = template
        self._latest[template.name] = template
        return template

    def get(self, name: str, version: str | None = None) -> PromptTemplate:
        if version is None:
            if name not in self._latest:
                raise KeyError(f"Prompt template '{name}' is not registered")
            return self._latest[name]
        key = (name, version)
        if key not in self._templates:
            raise KeyError(f"Prompt template '{name}:{version}' is not registered")
        return self._templates[key]

    def list_versions(self, name: str) -> list[str]:
        return [ver for (n, ver) in self._templates if n == name]


PROMPT_REGISTRY = PromptRegistry()
