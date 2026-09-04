import numpy as np

from agent.model_router.hydra import OnnxEmbeddingBackend


class _Session:
    def __init__(self):
        self.calls = []

    def get_inputs(self):
        return [
            type("Input", (), {"name": "input_ids"})(),
            type("Input", (), {"name": "attention_mask"})(),
        ]

    def run(self, _outputs, feeds):
        self.calls.append(feeds)
        return [np.asarray([[[1.0, 0.0], [0.0, 1.0]]], dtype=np.float32)]


def test_onnx_embedding_backend_uses_injected_tokenizer_and_mean_pools():
    session = _Session()
    backend = OnnxEmbeddingBackend(
        session=session,
        tokenizer=lambda text: {
            "input_ids": np.asarray([[1, 2]], dtype=np.int64),
            "attention_mask": np.asarray([[1, 1]], dtype=np.int64),
        },
    )

    vector = backend.embed("private prompt")

    assert np.allclose(vector, [0.70710677, 0.70710677])
    assert session.calls[0]["input_ids"].shape == (1, 2)


def test_onnx_embedding_backend_is_fail_closed_when_runtime_errors():
    backend = OnnxEmbeddingBackend(
        session=object(), tokenizer=lambda _text: {},
    )
    assert backend.try_embed("prompt") is None
