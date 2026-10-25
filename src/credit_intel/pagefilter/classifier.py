"""The classifier interface and an offline stand-in for tests (PRD v0.4.31)."""

from collections.abc import Callable, Mapping
from typing import Protocol

from credit_intel.pagefilter.labels import ClassifierError, PageClassification


class PageClassifier(Protocol):
    """Labels one page. ``sends_off_machine`` is true if the page text leaves the machine (the send rule then applies)."""

    sends_off_machine: bool

    def classify(self, page_number: int, text: str) -> PageClassification: ...


class FakeClassifier:
    """Scripted answers by page number, or a function of (page number, text). An ``Exception`` value is raised. No network."""

    sends_off_machine = False

    def __init__(self, script: Mapping[int, PageClassification | BaseException] | Callable[[int, str], PageClassification]) -> None:
        self._script = script
        self.calls: list[int] = []

    def classify(self, page_number: int, text: str) -> PageClassification:
        self.calls.append(page_number)
        if callable(self._script):
            return self._script(page_number, text)
        answer = self._script.get(page_number)
        if answer is None:
            raise ClassifierError("error")
        if isinstance(answer, BaseException):
            raise answer
        return answer
