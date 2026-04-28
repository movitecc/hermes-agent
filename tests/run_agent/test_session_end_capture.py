from unittest.mock import MagicMock

from run_agent import AIAgent


def _make_agent() -> AIAgent:
    agent = AIAgent.__new__(AIAgent)
    agent.session_id = "sess-1"
    agent._api_call_count = 3
    agent._interrupt_requested = False
    agent._memory_manager = None
    agent.context_compressor = MagicMock()
    return agent


def test_shutdown_memory_provider_forwards_iteration_metadata():
    agent = _make_agent()

    agent.shutdown_memory_provider([{"role": "assistant", "content": "done"}])

    agent.context_compressor.on_session_end.assert_called_once()
    args, kwargs = agent.context_compressor.on_session_end.call_args
    assert args[0] == "sess-1"
    assert args[1] == [{"role": "assistant", "content": "done"}]
    assert kwargs["api_call_count"] == 3
    assert kwargs["interrupted"] is False
    assert kwargs["completed"] is True
    assert kwargs["turn_exit_reason"] == "shutdown"
    assert kwargs["project_root"]


def test_commit_memory_session_forwards_compression_metadata():
    agent = _make_agent()

    agent.commit_memory_session([{"role": "assistant", "content": "done"}])

    agent.context_compressor.on_session_end.assert_called_once()
    args, kwargs = agent.context_compressor.on_session_end.call_args
    assert args[0] == "sess-1"
    assert args[1] == [{"role": "assistant", "content": "done"}]
    assert kwargs["api_call_count"] == 3
    assert kwargs["interrupted"] is False
    assert kwargs["completed"] is False
    assert kwargs["turn_exit_reason"] == "compression"
    assert kwargs["project_root"]
