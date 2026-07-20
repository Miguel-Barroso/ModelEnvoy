from __future__ import annotations

from abc import ABC, abstractmethod

from ..result import ConsultResult


class Transport(ABC):
    @abstractmethod
    def consult(self, prompt: str) -> ConsultResult:
        ...