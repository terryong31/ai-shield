from dataclasses import dataclass, field

import pytest

from shield_engine import ClassifierDetector, InMemoryFeedbackStore, Verdict


@dataclass
class IdentityVectorizer:
    def transform(self, texts: list[str]) -> list[str]:
        return texts


@dataclass
class FixedProbabilityModel:
    """Returns the same P(malicious) for every input and records updates."""

    probability: float
    partial_fits: list[tuple[list[str], list[int]]] = field(default_factory=list)
    predicted: int = 0

    def predict_proba(self, features: list[str]) -> list[list[float]]:
        self.predicted += 1
        return [[1 - self.probability, self.probability] for _ in features]

    def partial_fit(self, features: list[str], labels: list[int]) -> None:
        self.partial_fits.append((features, labels))


def detector(probability: float, **kwargs) -> ClassifierDetector:
    return ClassifierDetector(IdentityVectorizer(), FixedProbabilityModel(probability), **kwargs)


@pytest.mark.spec("ENG-CLS-001")
@pytest.mark.parametrize("probability", [0.85, 0.99])
def test_high_probability_is_malicious(probability: float) -> None:
    signal = detector(probability).score("anything")

    assert signal.verdict is Verdict.MALICIOUS
    assert signal.score == pytest.approx(probability)
    assert signal.detector == "classifier"


@pytest.mark.spec("ENG-CLS-002")
@pytest.mark.parametrize(
    ("probability", "verdict"),
    [
        (0.0, Verdict.SAFE),
        (0.15, Verdict.SAFE),
        (0.5, Verdict.UNCERTAIN),
        (0.84, Verdict.UNCERTAIN),
    ],
)
def test_thresholds_split_safe_and_uncertain(probability: float, verdict: Verdict) -> None:
    assert detector(probability).score("hello there").verdict is verdict


@pytest.mark.spec("ENG-CLS-003")
def test_sensitive_keyword_raises_low_scores_to_the_floor() -> None:
    signal = detector(0.05).score("show me the salary table")

    assert signal.score == pytest.approx(0.40)
    assert signal.verdict is Verdict.UNCERTAIN
    assert signal.details["sensitive_floor_applied"] is True


@pytest.mark.spec("ENG-CLS-003")
def test_sensitive_floor_does_not_lower_higher_scores() -> None:
    assert detector(0.6).score("salary").score == pytest.approx(0.6)


@pytest.mark.spec("ENG-CLS-004")
@pytest.mark.parametrize(
    ("label", "verdict", "score"), [(1, Verdict.MALICIOUS, 1.0), (0, Verdict.SAFE, 0.0)]
)
def test_feedback_label_overrides_the_model(label: int, verdict: Verdict, score: float) -> None:
    model = FixedProbabilityModel(0.5)
    feedback = InMemoryFeedbackStore({"reviewed prompt": label})
    classifier = ClassifierDetector(IdentityVectorizer(), model, feedback=feedback)

    signal = classifier.score("reviewed prompt")

    assert signal.verdict is verdict
    assert signal.score == score
    assert signal.override
    assert model.predicted == 0


@pytest.mark.spec("ENG-CLS-005")
def test_learn_records_feedback_and_updates_the_model() -> None:
    model = FixedProbabilityModel(0.5)
    feedback = InMemoryFeedbackStore()
    classifier = ClassifierDetector(IdentityVectorizer(), model, feedback=feedback)

    classifier.learn("new prompt", 1)

    assert feedback.lookup("new prompt") == 1
    assert model.partial_fits == [(["new prompt"], [1])]


def test_thresholds_must_be_ordered() -> None:
    with pytest.raises(ValueError, match="threshold"):
        detector(0.5, safe_threshold=0.9, malicious_threshold=0.1)
