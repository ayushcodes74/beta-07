"""Course leaderboard: access via CourseService, ranking rows from the course_leaderboard RPC (faked)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.database.leaderboard_repository import LeaderboardUnavailableError
from app.schemas.user import Role
from app.services.auth_service import CurrentUser
from app.services.course_service import CourseNotFoundError, CourseRecord, CourseService
from app.services.leaderboard_service import LeaderboardService

TEACHER = CurrentUser(id=uuid4(), email=None, role=Role.TEACHER)
OTHER_TEACHER = CurrentUser(id=uuid4(), email=None, role=Role.TEACHER)
STUDENT = CurrentUser(id=uuid4(), email=None, role=Role.STUDENT)
OUTSIDER = CurrentUser(id=uuid4(), email=None, role=Role.STUDENT)
COURSE = CourseRecord(id=uuid4(), teacher_id=TEACHER.id, name="Digital Logic", created_at=datetime.now(UTC))


class CourseRepo:
    def get(self, course_id, *, access_token):
        return COURSE if course_id == COURSE.id else None

    def is_student_enrolled(self, course_id, student_id, *, access_token):
        return course_id == COURSE.id and student_id == STUDENT.id


class LeaderboardRepo:
    def __init__(self, rows=None, fail=False):
        self.rows = rows or []
        self.fail = fail
        self.calls = 0

    def course_leaderboard(self, course_id, *, access_token):
        self.calls += 1
        if self.fail:
            raise LeaderboardUnavailableError("function does not exist")
        return self.rows


def _row(rank, student_id, name, total, graded=2, possible=20, counted=2, published="2026-10-30T10:00:00+00:00"):
    return {
        "leaderboard_rank": rank, "student_id": str(student_id), "display_name": name,
        "total_score": total, "total_possible": possible, "assignments_graded": graded,
        "assignments_counted": counted, "last_published_at": published,
    }


def _service(repo):
    return LeaderboardService(CourseService(CourseRepo()), repo)


def test_student_sees_ranked_classmates_with_own_row_marked():
    other, third = uuid4(), uuid4()
    repo = LeaderboardRepo([
        _row(2, STUDENT.id, "Asha", "15.5"),
        _row(1, other, "Bilal", 18),
        _row(2, third, "  ", 15.5),
    ])

    board = _service(repo).course_leaderboard(STUDENT, COURSE.id, access_token="t")

    assert board.course_name == "Digital Logic"
    assert board.total_possible == 20.0 and board.assignments_counted == 2
    assert [(e.rank, e.name) for e in board.entries] == [(1, "Bilal"), (2, "Asha"), (2, "Student")]
    me = next(e for e in board.entries if e.is_you)
    assert me.student_id == STUDENT.id and me.total_score == 15.5 and me.percentage == 77.5
    assert sum(e.is_you for e in board.entries) == 1


def test_teacher_sees_board_and_no_row_is_marked_as_theirs():
    repo = LeaderboardRepo([_row(1, STUDENT.id, "Asha", 10)])
    board = _service(repo).course_leaderboard(TEACHER, COURSE.id, access_token="t")
    assert [e.is_you for e in board.entries] == [False]


def test_nothing_published_yet_gives_zero_totals_and_no_percentage():
    repo = LeaderboardRepo([_row(1, STUDENT.id, "Asha", 0, graded=0, possible=0, counted=0, published=None)])
    board = _service(repo).course_leaderboard(TEACHER, COURSE.id, access_token="t")
    assert board.total_possible == 0 and board.assignments_counted == 0
    assert board.entries[0].percentage is None and board.entries[0].last_published_at is None


@pytest.mark.parametrize("user", [OTHER_TEACHER, OUTSIDER])
def test_non_members_get_404_before_the_rpc_is_called(user):
    repo = LeaderboardRepo([_row(1, STUDENT.id, "Asha", 10)])
    with pytest.raises(CourseNotFoundError):
        _service(repo).course_leaderboard(user, COURSE.id, access_token="t")
    assert repo.calls == 0


def test_missing_rpc_surfaces_as_unavailable():
    with pytest.raises(LeaderboardUnavailableError):
        _service(LeaderboardRepo(fail=True)).course_leaderboard(TEACHER, COURSE.id, access_token="t")
