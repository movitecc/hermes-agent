from plugins.context_engine.lcm.iteration_schema import IterationRecord
from plugins.context_engine.lcm.lesson_distiller import distill_lessons, select_lesson_for_record


def _record(session_id: str, project_root: str, failed_test: str, summary: str = "Traceback") -> IterationRecord:
    return IterationRecord(
        session_id=session_id,
        project_root=project_root,
        status="failure",
        signals=["engine:lcm", "status:failure"],
        summary=summary,
        failed_tests=[failed_test],
        artifact_refs=[],
    )


def test_repeated_same_failure_distills_to_one_lesson():
    records = [
        _record("sess-1", "/proj", "tests/test_auth.py::test_login"),
        _record("sess-2", "/proj", "tests/test_auth.py::test_login"),
    ]

    lessons = distill_lessons(records)

    assert len(lessons) == 1
    lesson = lessons[0]
    assert lesson.signature.endswith("tests/test_auth.py::test_login")
    assert "tests/test_auth.py::test_login" in lesson.lesson
    assert "Action:" in lesson.lesson
    assert "Traceback" not in lesson.lesson
    assert lesson.confidence >= 0.55
    assert lesson.evidence_refs == ["sess-1", "sess-2"]
    assert lesson.recommended_next_action.startswith("Fix the regression around tests/test_auth.py::test_login")


def test_different_failure_clusters_remain_separate():
    records = [
        _record("sess-1", "/proj", "tests/test_auth.py::test_login"),
        _record("sess-2", "/proj", "tests/test_auth.py::test_login"),
        _record("sess-3", "/proj", "tests/test_payments.py::test_charge"),
        _record("sess-4", "/proj", "tests/test_payments.py::test_charge"),
    ]

    lessons = distill_lessons(records)

    assert len(lessons) == 2
    assert {lesson.trigger for lesson in lessons} == {
        "tests/test_auth.py::test_login",
        "tests/test_payments.py::test_charge",
    }


def test_select_lesson_for_record_matches_signature():
    records = [
        _record("sess-1", "/proj", "tests/test_auth.py::test_login"),
        _record("sess-2", "/proj", "tests/test_auth.py::test_login"),
        _record("sess-3", "/proj", "tests/test_other.py::test_feature"),
        _record("sess-4", "/proj", "tests/test_other.py::test_feature"),
    ]
    lessons = distill_lessons(records)
    focus = _record("sess-5", "/proj", "tests/test_other.py::test_feature")

    selected = select_lesson_for_record(focus, lessons)

    assert selected is not None
    assert selected.trigger == "tests/test_other.py::test_feature"
    assert "Action:" in selected.lesson
