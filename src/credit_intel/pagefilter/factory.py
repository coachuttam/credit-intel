"""Building the optional classifier for a run (PRD v0.4.31): ``None`` and a reason word when it cannot be used, never an error."""

from collections.abc import Callable, Mapping

from credit_intel.config import JevSettings, typesafe_api_key
from credit_intel.pagefilter.classifier import PageClassifier
from credit_intel.pagefilter.jev import JevClassifier

ClassifierFactory = Callable[[JevSettings, Mapping[str, str]], PageClassifier | None]


def build_classifier(settings: JevSettings, env: Mapping[str, str]) -> PageClassifier | None:
    """The Jev classifier, or ``None`` if there is no key. No network is touched: the client is built on the first call."""
    if typesafe_api_key(env) is None:
        return None
    return JevClassifier(settings, env)
