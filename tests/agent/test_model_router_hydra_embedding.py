import numpy as np

from agent.model_router.hydra import build_requirement_vector
from agent.model_router.types import RoutingRequest
from agent.model_router.triage import triage


class _SemanticBackend:
    def try_embed(self, text):
        if "code" in text.lower():
            return np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
        if "reason" in text.lower():
            return np.asarray([0.0, 1.0, 0.0], dtype=np.float32)
        return np.asarray([0.0, 0.0, 1.0], dtype=np.float32)


def test_hydra_embedding_backend_adjusts_requirement_vector():
    request = RoutingRequest("code", turn_type="main_loop")
    deterministic = build_requirement_vector(request, triage(request.prompt_text))
    semantic = build_requirement_vector(
        request, triage(request.prompt_text), embedding_backend=_SemanticBackend()
    )

    assert semantic.code_gen > deterministic.code_gen
    assert semantic.reasoning == deterministic.reasoning


def test_hydra_embedding_failure_keeps_deterministic_vector():
    class Broken:
        def try_embed(self, _text):
            return None

    request = RoutingRequest("code")
    expected = build_requirement_vector(request, triage(request.prompt_text))
    actual = build_requirement_vector(
        request, triage(request.prompt_text), embedding_backend=Broken()
    )
    assert actual == expected
