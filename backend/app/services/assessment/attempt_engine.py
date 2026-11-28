from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.assessment import Attempt, Response, Test, TestQuestion
from app.repositories.attempt_repo import AttemptRepository
from app.schemas.attempt import (
    AttemptCurrentOut,
    AttemptListResponse,
    AttemptResultsOut,
    AttemptSummaryOut,
    LockedQuestionFeedbackOut,
    NavigateRequest,
    PlayerOptionOut,
    PlayerQuestionOut,
    QuestionPaletteItemOut,
    ResponseSaveOut,
    SaveResponseRequest,
    SelfReportOut,
    SelfReportRequest,
)
from app.services.assessment.scoring_service import (
    AttemptPostSubmitHook,
    ScoringService,
    noop_post_submit_hook,
)
from app.services.assessment.timer_service import (
    EXPIRY_GRACE_MS,
    ClockFn,
    compute_elapsed_ms,
    ensure_utc,
    is_expired,
    remaining_seconds,
    utcnow_clock,
)


class AttemptNotFoundError(Exception):
    """Raised when a test or attempt does not exist."""


class AttemptAccessDeniedError(Exception):
    """Raised when a user accesses an attempt or test owned by another user."""


class AttemptConflictError(Exception):
    """Raised for 409 Conflict timer/submission state transitions."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


class AttemptBadRequestError(Exception):
    """Raised for invalid mode actions (e.g. navigate in Speed Challenge)."""


class AttemptValidationError(Exception):
    """Raised for invalid target indices or option keys."""


def _sanitized_player_settings(test: Test) -> dict[str, Any]:
    raw = test.settings_json or {}
    return {
        "timer_mode": raw.get("timer_mode"),
        "per_question_seconds": raw.get("per_question_seconds"),
        "total_duration_seconds": raw.get("total_duration_seconds"),
        "auto_advance_on_timeout": bool(raw.get("auto_advance_on_timeout", True)),
        "points_per_question": str(raw.get("points_per_question", "2.00")),
        "negative_marking_enabled": bool(raw.get("negative_marking_enabled", False)),
        "negative_points": str(raw.get("negative_points", "0.00")),
        "show_explanation_after": raw.get("show_explanation_after", "after_submission"),
        "hints_enabled": bool(raw.get("hints_enabled", False)),
    }


def _build_locked_feedback(
    response: Response,
    tq: TestQuestion,
) -> LockedQuestionFeedbackOut:
    snap = tq.question_snapshot_json or {}
    answer_key = snap.get("answer_key") or {}
    selected_key = (
        response.selected_answer_json.get("selected_option_key")
        if response.selected_answer_json
        else None
    )
    return LockedQuestionFeedbackOut(
        response_id=response.id,
        test_question_id=tq.id,
        selected_option_key=selected_key,
        correct_option_key=answer_key.get("correct_option_key"),
        is_correct=response.is_correct,
        explanation=str(answer_key.get("explanation") or ""),
        answer_key_provenance=str(answer_key.get("answer_key_provenance") or "unverified"),
        source_page_number=snap.get("source_page_number"),
        supporting_excerpt=snap.get("supporting_excerpt"),
    )


def _build_player_question(
    response: Response,
    tq: TestQuestion,
    *,
    now: datetime,
    hints_enabled: bool,
) -> PlayerQuestionOut:
    """Construct `PlayerQuestionOut` from public snapshot fields ONLY (zero answer keys)."""
    snap = tq.question_snapshot_json or {}
    options = [
        PlayerOptionOut(
            key=str(opt.get("key", "")),
            text=str(opt.get("text", "")),
            display_order=int(opt.get("display_order", idx)),
        )
        for idx, opt in enumerate(snap.get("options") or [])
    ]
    selected_key = (
        response.selected_answer_json.get("selected_option_key")
        if response.selected_answer_json
        else None
    )
    doc_id_str = snap.get("document_id")
    topic_id_str = snap.get("topic_id")
    diagram_id_str = snap.get("diagram_asset_id")
    passage_id_str = snap.get("passage_group_id")

    hint_text: str | None = None
    if hints_enabled:
        topic_label = snap.get("topic_name") or snap.get("subject_code")
        if topic_label:
            hint_text = f"Topic focus: {topic_label} ({snap.get('difficulty', 'medium')})"

    return PlayerQuestionOut(
        test_question_id=tq.id,
        display_order=tq.display_order,
        subject_code=str(snap.get("subject_code") or "unknown"),
        topic_id=UUID(topic_id_str) if topic_id_str else None,
        topic_name=snap.get("topic_name"),
        question_text=str(snap.get("question_text") or ""),
        question_type=str(snap.get("question_type") or "single_choice"),
        difficulty=str(snap.get("difficulty") or "medium"),
        document_id=UUID(doc_id_str) if doc_id_str else None,
        source_page_number=snap.get("source_page_number"),
        diagram_asset_id=UUID(diagram_id_str) if diagram_id_str else None,
        passage_group_id=UUID(passage_id_str) if passage_id_str else None,
        passage_text=snap.get("passage_text"),
        options=options,
        points=Decimal(tq.points).quantize(Decimal("0.01")),
        negative_points=Decimal(tq.negative_points).quantize(Decimal("0.01")),
        time_limit_seconds=tq.time_limit_seconds,
        section_code=tq.section_code,
        selected_option_key=selected_key,
        is_marked_for_review=response.is_marked_for_review,
        status=response.status,
        shown_at=response.shown_at,
        question_expires_at=response.question_expires_at,
        question_remaining_seconds=remaining_seconds(now, response.question_expires_at),
        time_spent_ms=int(response.time_spent_ms or 0),
        is_locked=response.locked_at is not None,
        hint=hint_text,
    )


def _to_attempt_summary(attempt: Attempt, test: Test) -> AttemptSummaryOut:
    return AttemptSummaryOut(
        attempt_id=attempt.id,
        test_id=test.id,
        test_title=test.title,
        timer_mode=attempt.timer_mode,
        status=attempt.status,
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
        total_score=(
            Decimal(attempt.total_score).quantize(Decimal("0.01"))
            if attempt.total_score is not None
            else None
        ),
        max_score=Decimal(attempt.max_score).quantize(Decimal("0.01")),
        total_time_ms=int(attempt.total_time_ms or 0),
        total_questions=test.total_questions,
        correct_count=attempt.correct_count,
        incorrect_count=attempt.incorrect_count,
        skipped_count=attempt.skipped_count,
        timed_out_count=attempt.timed_out_count,
    )


class AttemptEngine:
    """Server-authoritative timed test execution engine."""

    def __init__(
        self,
        db: Session,
        *,
        clock: ClockFn = utcnow_clock,
        grace_ms: int = EXPIRY_GRACE_MS,
        post_submit_hook: AttemptPostSubmitHook = noop_post_submit_hook,
    ) -> None:
        self._db = db
        self._repo = AttemptRepository(db)
        self._scorer = ScoringService()
        self._clock = clock
        self._grace_ms = grace_ms
        self._post_submit_hook = post_submit_hook

    def _now(self) -> datetime:
        now = ensure_utc(self._clock())
        assert now is not None
        return now

    def _load_owned_attempt(
        self,
        attempt_id: UUID,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> tuple[Attempt, Test, list[tuple[Response, TestQuestion]]]:
        attempt = self._repo.get_attempt(attempt_id, for_update=for_update)
        if attempt is None:
            raise AttemptNotFoundError(f"Attempt '{attempt_id}' not found")
        if attempt.user_id != user_id:
            raise AttemptAccessDeniedError("You do not have access to this attempt")
        test = self._repo.get_test(attempt.test_id)
        if test is None:
            raise AttemptNotFoundError(f"Test '{attempt.test_id}' not found")
        pairs = self._repo.list_responses_with_questions(attempt.id)
        return attempt, test, pairs

    def _open_question(
        self,
        *,
        attempt: Attempt,
        response: Response,
        tq: TestQuestion,
        now: datetime,
    ) -> None:
        if response.shown_at is None:
            response.shown_at = now
        if attempt.timer_mode == "speed_challenge":
            limit_secs = tq.time_limit_seconds or attempt.per_question_seconds or 35
            if response.question_expires_at is None and response.locked_at is None:
                response.question_expires_at = response.shown_at + timedelta(seconds=limit_secs)
        if response.locked_at is None:
            response.last_resumed_at = now
            response.visit_count += 1

    def _accumulate_active_time(
        self,
        *,
        attempt: Attempt,
        response: Response,
        tq: TestQuestion,
        now: datetime,
    ) -> None:
        if response.last_resumed_at is None or response.locked_at is not None:
            return
        max_ms: int | None = None
        if attempt.timer_mode == "speed_challenge":
            limit_secs = tq.time_limit_seconds or attempt.per_question_seconds or 35
            remaining_budget = max(0, limit_secs * 1000 - int(response.time_spent_ms or 0))
            max_ms = remaining_budget
        delta = compute_elapsed_ms(response.last_resumed_at, now, max_ms=max_ms)
        response.time_spent_ms = int(response.time_spent_ms or 0) + delta
        response.last_resumed_at = None

    def _finalize_and_commit(
        self,
        *,
        attempt: Attempt,
        test: Test,
        pairs: list[tuple[Response, TestQuestion]],
        submitted_at: datetime,
        timed_out_submission: bool,
    ) -> None:
        self._scorer.finalize_attempt(
            attempt=attempt,
            test=test,
            pairs=pairs,
            submitted_at=submitted_at,
            timed_out_submission=timed_out_submission,
        )
        self._repo.commit()
        self._post_submit_hook(self._db, attempt.id)

    def _reconcile_expiries(
        self,
        *,
        attempt: Attempt,
        test: Test,
        pairs: list[tuple[Response, TestQuestion]],
        now: datetime,
    ) -> bool:
        """Auto-close expired questions or total attempt duration before serving state.

        Returns True if a DB commit occurred due to state changes.
        """
        if attempt.status != "in_progress" or not pairs:
            return False

        changed = False
        if attempt.timer_mode == "exam_simulation" and is_expired(
            now, attempt.expires_at, grace_ms=self._grace_ms
        ):
            exp_ts = ensure_utc(attempt.expires_at) or now
            idx = min(attempt.current_question_index, len(pairs) - 1)
            active_resp, active_tq = pairs[idx]
            self._accumulate_active_time(
                attempt=attempt, response=active_resp, tq=active_tq, now=exp_ts
            )
            self._finalize_and_commit(
                attempt=attempt,
                test=test,
                pairs=pairs,
                submitted_at=exp_ts,
                timed_out_submission=True,
            )
            return True

        if attempt.timer_mode == "speed_challenge":
            idx = attempt.current_question_index
            if 0 <= idx < len(pairs):
                resp, tq = pairs[idx]
                if resp.locked_at is None and is_expired(
                    now, resp.question_expires_at, grace_ms=self._grace_ms
                ):
                    limit_secs = tq.time_limit_seconds or attempt.per_question_seconds or 35
                    resp.status = "timed_out"
                    resp.locked_at = ensure_utc(resp.question_expires_at) or now
                    resp.time_spent_ms = limit_secs * 1000
                    resp.last_resumed_at = None
                    changed = True

                    if idx + 1 < len(pairs):
                        attempt.current_question_index = idx + 1
                        next_resp, next_tq = pairs[idx + 1]
                        self._open_question(
                            attempt=attempt, response=next_resp, tq=next_tq, now=now
                        )
                    else:
                        self._finalize_and_commit(
                            attempt=attempt,
                            test=test,
                            pairs=pairs,
                            submitted_at=resp.locked_at,
                            timed_out_submission=True,
                        )
                        return True

        if changed:
            self._repo.commit()
        return changed

    def _build_current_out(
        self,
        *,
        attempt: Attempt,
        test: Test,
        pairs: list[tuple[Response, TestQuestion]],
        now: datetime,
    ) -> AttemptCurrentOut:
        settings = _sanitized_player_settings(test)
        hints_enabled = bool(settings.get("hints_enabled", False))
        show_after = settings.get("show_explanation_after", "after_submission")

        palette = [
            QuestionPaletteItemOut(
                index=idx,
                test_question_id=tq.id,
                status=resp.status,
                is_marked_for_review=resp.is_marked_for_review,
                selected_option_key=(
                    resp.selected_answer_json.get("selected_option_key")
                    if resp.selected_answer_json
                    else None
                ),
                is_locked=resp.locked_at is not None,
            )
            for idx, (resp, tq) in enumerate(pairs)
        ]

        current_q: PlayerQuestionOut | None = None
        locked_feedback: LockedQuestionFeedbackOut | None = None
        if attempt.status == "in_progress" and pairs:
            idx = min(max(attempt.current_question_index, 0), len(pairs) - 1)
            cur_resp, cur_tq = pairs[idx]
            current_q = _build_player_question(
                cur_resp,
                cur_tq,
                now=now,
                hints_enabled=hints_enabled,
            )
            if (
                attempt.timer_mode == "learning_mode"
                and show_after == "after_question"
                and cur_resp.locked_at is not None
            ):
                locked_feedback = _build_locked_feedback(cur_resp, cur_tq)

        return AttemptCurrentOut(
            attempt_id=attempt.id,
            test_id=test.id,
            test_title=test.title,
            status=attempt.status,
            timer_mode=attempt.timer_mode,
            server_now=now,
            started_at=attempt.started_at,
            attempt_expires_at=attempt.expires_at,
            attempt_remaining_seconds=remaining_seconds(now, attempt.expires_at),
            current_question_index=attempt.current_question_index,
            total_questions=len(pairs),
            current_question=current_q,
            palette=palette,
            settings=settings,
            locked_feedback=locked_feedback,
        )

    def start_attempt(self, *, test_id: UUID, user_id: UUID) -> AttemptCurrentOut:
        """Start a new timed attempt for an owned test and initialize responses."""
        test = self._repo.get_test(test_id)
        if test is None:
            raise AttemptNotFoundError(f"Test '{test_id}' not found")
        if test.user_id != user_id:
            raise AttemptAccessDeniedError("You do not have access to this test")

        tqs = self._repo.list_test_questions(test.id)
        if not tqs:
            raise AttemptValidationError("Test has no questions.")

        now = self._now()
        settings = test.settings_json or {}
        timer_mode = str(settings.get("timer_mode") or "speed_challenge")
        per_question_seconds = settings.get("per_question_seconds")
        total_duration_seconds = settings.get("total_duration_seconds")

        expires_at: datetime | None = None
        if timer_mode == "exam_simulation":
            duration = int(total_duration_seconds or (len(tqs) * 60))
            total_duration_seconds = duration
            expires_at = now + timedelta(seconds=duration)
        elif timer_mode == "speed_challenge":
            per_question_seconds = int(per_question_seconds or 35)

        attempt = Attempt(
            test_id=test.id,
            user_id=user_id,
            timer_mode=timer_mode,
            status="in_progress",
            current_question_index=0,
            started_at=now,
            expires_at=expires_at,
            total_duration_seconds=total_duration_seconds,
            per_question_seconds=per_question_seconds,
            max_score=test.max_score,
        )

        responses: list[Response] = []
        for idx, tq in enumerate(tqs):
            resp = Response(
                test_question_id=tq.id,
                status="unvisited",
                time_spent_ms=0,
                visit_count=0,
                is_marked_for_review=False,
            )
            if idx == 0:
                self._open_question(attempt=attempt, response=resp, tq=tq, now=now)
            responses.append(resp)

        self._repo.create_attempt_with_responses(attempt, responses)
        pairs = list(zip(responses, tqs, strict=True))
        return self._build_current_out(attempt=attempt, test=test, pairs=pairs, now=now)

    def reconcile_expired_exam_attempts(self, user_id: UUID) -> int:
        """Finalize any owned exam_simulation attempts whose server deadline has passed."""
        rows = self._repo.list_attempts_for_user(user_id, limit=50, offset=0)
        now = self._now()
        reconciled = 0
        for att, test in rows:
            if (
                att.status == "in_progress"
                and att.timer_mode == "exam_simulation"
                and is_expired(now, att.expires_at, grace_ms=self._grace_ms)
            ):
                pairs = self._repo.list_responses_with_questions(att.id)
                if self._reconcile_expiries(attempt=att, test=test, pairs=pairs, now=now):
                    reconciled += 1
        return reconciled

    def list_attempts(
        self,
        user_id: UUID,
        *,
        test_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AttemptListResponse:
        """List attempts owned by `user_id`."""
        self.reconcile_expired_exam_attempts(user_id)
        rows = self._repo.list_attempts_for_user(
            user_id, test_id=test_id, limit=limit, offset=offset
        )
        items = [_to_attempt_summary(att, t) for att, t in rows]
        return AttemptListResponse(items=items, total=len(items))

    def get_current(self, *, attempt_id: UUID, user_id: UUID) -> AttemptCurrentOut:
        """Return server-authoritative state for resume/refresh after reconciling expiries."""
        attempt, test, pairs = self._load_owned_attempt(attempt_id, user_id, for_update=True)
        now = self._now()
        self._reconcile_expiries(attempt=attempt, test=test, pairs=pairs, now=now)
        return self._build_current_out(attempt=attempt, test=test, pairs=pairs, now=now)

    def navigate(
        self,
        *,
        attempt_id: UUID,
        user_id: UUID,
        payload: NavigateRequest,
    ) -> AttemptCurrentOut:
        """Move active cursor in Exam Simulation or Learning Mode, tracking per-question time."""
        attempt, test, pairs = self._load_owned_attempt(attempt_id, user_id, for_update=True)
        if attempt.status != "in_progress":
            raise AttemptConflictError(
                "ATTEMPT_ALREADY_SUBMITTED", "Attempt has already been submitted"
            )

        if attempt.timer_mode == "speed_challenge":
            raise AttemptBadRequestError("Navigation is disabled in Speed Challenge mode.")

        now = self._now()
        if self._reconcile_expiries(attempt=attempt, test=test, pairs=pairs, now=now):
            raise AttemptConflictError(
                "ATTEMPT_EXPIRED", "Attempt time has expired and was submitted"
            )

        if payload.target_index < 0 or payload.target_index >= len(pairs):
            raise AttemptValidationError(
                f"target_index must be between 0 and {len(pairs) - 1}"
            )

        old_idx = min(max(attempt.current_question_index, 0), len(pairs) - 1)
        if old_idx != payload.target_index:
            old_resp, old_tq = pairs[old_idx]
            self._accumulate_active_time(
                attempt=attempt, response=old_resp, tq=old_tq, now=now
            )
            if old_resp.status == "unvisited":
                old_resp.status = "skipped"

            target_resp, target_tq = pairs[payload.target_index]
            attempt.current_question_index = payload.target_index
            self._open_question(attempt=attempt, response=target_resp, tq=target_tq, now=now)
            self._repo.commit()

        return self._build_current_out(attempt=attempt, test=test, pairs=pairs, now=now)

    def save_response(
        self,
        *,
        attempt_id: UUID,
        user_id: UUID,
        payload: SaveResponseRequest,
    ) -> ResponseSaveOut:
        """Persist an answer, skip, or review flag with strict server deadline checks."""
        attempt, test, pairs = self._load_owned_attempt(attempt_id, user_id, for_update=True)
        if attempt.status != "in_progress":
            raise AttemptConflictError(
                "ATTEMPT_ALREADY_SUBMITTED", "Attempt has already been submitted"
            )

        now = self._now()

        # Check total Exam Simulation expiry first
        if attempt.timer_mode == "exam_simulation" and is_expired(
            now, attempt.expires_at, grace_ms=self._grace_ms
        ):
            self._reconcile_expiries(attempt=attempt, test=test, pairs=pairs, now=now)
            raise AttemptConflictError(
                "ATTEMPT_EXPIRED", "Attempt time has expired and was submitted"
            )

        target_pair: tuple[int, Response, TestQuestion] | None = None
        for idx, (resp, tq) in enumerate(pairs):
            if tq.id == payload.test_question_id:
                target_pair = (idx, resp, tq)
                break
        if target_pair is None:
            raise AttemptValidationError(
                f"test_question_id '{payload.test_question_id}' does not belong to this attempt"
            )

        q_idx, resp, tq = target_pair

        # Speed Challenge strict per-question ordering and timeout check
        if attempt.timer_mode == "speed_challenge":
            if resp.status == "timed_out":
                raise AttemptConflictError("QUESTION_TIMED_OUT", "Question time has expired")
            if resp.locked_at is not None:
                raise AttemptConflictError(
                    "QUESTION_ALREADY_LOCKED", "Question has already been answered or skipped"
                )
            if q_idx != attempt.current_question_index:
                raise AttemptBadRequestError(
                    "Speed Challenge responses must be submitted for the active question."
                )
            if is_expired(now, resp.question_expires_at, grace_ms=self._grace_ms):
                limit_secs = tq.time_limit_seconds or attempt.per_question_seconds or 35
                resp.status = "timed_out"
                resp.locked_at = ensure_utc(resp.question_expires_at) or now
                resp.time_spent_ms = limit_secs * 1000
                resp.last_resumed_at = None
                if q_idx + 1 < len(pairs):
                    attempt.current_question_index = q_idx + 1
                    next_resp, next_tq = pairs[q_idx + 1]
                    self._open_question(attempt=attempt, response=next_resp, tq=next_tq, now=now)
                    self._repo.commit()
                else:
                    self._finalize_and_commit(
                        attempt=attempt,
                        test=test,
                        pairs=pairs,
                        submitted_at=resp.locked_at,
                        timed_out_submission=True,
                    )
                raise AttemptConflictError("QUESTION_TIMED_OUT", "Question time has expired")

        if resp.locked_at is not None and payload.action in ("answer", "skip"):
            raise AttemptConflictError(
                "QUESTION_ALREADY_LOCKED", "Question has already been locked"
            )

        if payload.is_marked_for_review is not None:
            resp.is_marked_for_review = payload.is_marked_for_review

        settings = test.settings_json or {}
        show_after = settings.get("show_explanation_after", "after_submission")
        neg_enabled = bool(settings.get("negative_marking_enabled", False))
        locked_feedback: LockedQuestionFeedbackOut | None = None

        if payload.action == "mark_review":
            resp.is_marked_for_review = True
            self._repo.commit()
        elif payload.action == "unmark_review":
            resp.is_marked_for_review = False
            self._repo.commit()
        elif payload.action in ("answer", "skip"):
            if payload.action == "answer":
                snap_opts = {
                    str(opt.get("key", "")).upper()
                    for opt in (tq.question_snapshot_json or {}).get("options", [])
                }
                if not payload.selected_option_key or not payload.selected_option_key.strip():
                    raise AttemptValidationError(
                        "selected_option_key is required when action='answer'"
                    )
                selected_key = payload.selected_option_key.strip().upper()
                if snap_opts and selected_key not in snap_opts:
                    raise AttemptValidationError(
                        f"Invalid option key '{selected_key}' for this question"
                    )
                resp.selected_answer_json = {"selected_option_key": selected_key}
                resp.status = "answered"
            else:
                resp.selected_answer_json = None
                resp.status = "skipped"

            self._accumulate_active_time(attempt=attempt, response=resp, tq=tq, now=now)
            resp.submitted_at = now

            if attempt.timer_mode == "speed_challenge":
                resp.locked_at = now
                if payload.advance and q_idx + 1 < len(pairs):
                    attempt.current_question_index = q_idx + 1
                    next_resp, next_tq = pairs[q_idx + 1]
                    self._open_question(attempt=attempt, response=next_resp, tq=next_tq, now=now)
            elif attempt.timer_mode == "learning_mode" and show_after == "after_question":
                resp.locked_at = now
                if resp.status == "answered":
                    self._scorer.grade_single_response(
                        response=resp,
                        test_question=tq,
                        negative_marking_enabled=neg_enabled,
                    )
                else:
                    resp.is_correct = None
                    resp.graded_points = Decimal("0.00")
                locked_feedback = _build_locked_feedback(resp, tq)
                if payload.advance and q_idx + 1 < len(pairs):
                    attempt.current_question_index = q_idx + 1
                    next_resp, next_tq = pairs[q_idx + 1]
                    self._open_question(attempt=attempt, response=next_resp, tq=next_tq, now=now)
            else:
                # Exam Simulation or Learning Mode (after_submission): keep unlocked until submit
                if payload.advance and q_idx + 1 < len(pairs):
                    attempt.current_question_index = q_idx + 1
                    next_resp, next_tq = pairs[q_idx + 1]
                    self._open_question(attempt=attempt, response=next_resp, tq=next_tq, now=now)
                else:
                    # Staying on same question: resume active clock so additional think time counts
                    resp.last_resumed_at = now

            self._repo.commit()

        next_state = self._build_current_out(attempt=attempt, test=test, pairs=pairs, now=now)
        selected_out = (
            resp.selected_answer_json.get("selected_option_key")
            if resp.selected_answer_json
            else None
        )
        return ResponseSaveOut(
            response_id=resp.id,
            attempt_id=attempt.id,
            test_question_id=tq.id,
            status=resp.status,
            selected_option_key=selected_out,
            is_marked_for_review=resp.is_marked_for_review,
            is_locked=resp.locked_at is not None,
            time_spent_ms=int(resp.time_spent_ms or 0),
            next_state=next_state,
            locked_feedback=locked_feedback,
        )

    def save_self_report(
        self,
        *,
        attempt_id: UUID,
        response_id: UUID,
        user_id: UUID,
        payload: SelfReportRequest,
    ) -> SelfReportOut:
        """Record optional confidence and mistake-reason self-report tags on a response."""
        attempt = self._repo.get_attempt(attempt_id)
        if attempt is None:
            raise AttemptNotFoundError(f"Attempt '{attempt_id}' not found")
        if attempt.user_id != user_id:
            raise AttemptAccessDeniedError("You do not have access to this attempt")

        resp = self._repo.get_response_by_id(attempt_id, response_id)
        if resp is None:
            raise AttemptNotFoundError(f"Response '{response_id}' not found")

        if "confidence_self_report" in payload.model_fields_set:
            resp.confidence_self_report = payload.confidence_self_report
        if "mistake_reason_self_report" in payload.model_fields_set:
            resp.mistake_reason_self_report = payload.mistake_reason_self_report
        self._repo.commit()

        return SelfReportOut(
            response_id=resp.id,
            attempt_id=attempt.id,
            confidence_self_report=resp.confidence_self_report,
            mistake_reason_self_report=resp.mistake_reason_self_report,
        )

    def submit_attempt(self, *, attempt_id: UUID, user_id: UUID) -> AttemptSummaryOut:
        """Finalize and score an attempt idempotently using exact Decimal arithmetic."""
        attempt, test, pairs = self._load_owned_attempt(attempt_id, user_id, for_update=True)
        if attempt.status != "in_progress":
            return _to_attempt_summary(attempt, test)

        now = self._now()
        timed_out_sub = False
        submitted_ts = now

        if attempt.timer_mode == "exam_simulation" and is_expired(
            now, attempt.expires_at, grace_ms=self._grace_ms
        ):
            timed_out_sub = True
            submitted_ts = ensure_utc(attempt.expires_at) or now

        if pairs:
            idx = min(max(attempt.current_question_index, 0), len(pairs) - 1)
            active_resp, active_tq = pairs[idx]
            self._accumulate_active_time(
                attempt=attempt, response=active_resp, tq=active_tq, now=submitted_ts
            )

        self._finalize_and_commit(
            attempt=attempt,
            test=test,
            pairs=pairs,
            submitted_at=submitted_ts,
            timed_out_submission=timed_out_sub,
        )
        return _to_attempt_summary(attempt, test)

    def get_results(self, *, attempt_id: UUID, user_id: UUID) -> AttemptResultsOut:
        """Return full graded results and explanations; rejects in-progress attempts with 409."""
        attempt, test, pairs = self._load_owned_attempt(attempt_id, user_id, for_update=False)
        if attempt.status == "in_progress":
            raise AttemptConflictError(
                "ATTEMPT_IN_PROGRESS",
                "Results and answer keys are unavailable until the attempt is submitted.",
            )
        return self._scorer.build_results(attempt=attempt, test=test, pairs=pairs)
