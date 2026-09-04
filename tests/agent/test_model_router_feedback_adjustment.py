from agent.model_router.feedback import FeedbackConfig, adjust_scores
from agent.model_router.scoring import ScoredCandidate


def test_feedback_adjustment_requires_minimum_samples_and_is_bounded():
    scores = (
        ScoredCandidate("good", .8, 0, 0, 0, .8),
        ScoredCandidate("new", .79, 0, 0, 0, .79),
    )
    stats = {
        "by_model": {
            "good": {"total": 10, "success_rate": 1.0},
            "new": {"total": 1, "success_rate": 0.0},
        }
    }
    adjusted = adjust_scores(scores, stats, FeedbackConfig(enabled=True, max_adjustment=.05))
    assert adjusted[0].model_id == "good"
    assert adjusted[0].composite_score <= .85
    assert adjusted[1].composite_score == .79


def test_feedback_disabled_preserves_scores():
    score = ScoredCandidate("m", .8, 0, 0, 0, .8)
    assert adjust_scores((score,), {}, FeedbackConfig()) == (score,)
