"""Transactional coordination between deterministic C-lite and process primaries."""

from __future__ import annotations

import hashlib
import hmac
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from itertools import islice
from typing import Literal, TypeVar, cast

from .brain_backend import (
    BrainBackend,
    BrainBackendFactory,
    BrainCheckpointMismatchError,
    BrainFeedbackRequest,
    BrainFeedbackResult,
    BrainStepRequest,
    BrainStepResult,
    get_brain_backend_factory,
)
from .brain_c_lite import (
    CLiteEventCandidate,
    CLiteFeedbackCandidate,
    CLiteState,
    Route,
    evolve_c_event,
    evolve_c_feedback,
)
from .brain_errors import BrainDurabilityError, BrainValidationError
from .brain_state import MAX_COUNTER, EventAllocation, FeedbackAllocation
from .brain_store import (
    BackendCheckpoint,
    EventCommitted,
    FeedbackCommitted,
    _is_authentic_store_acknowledgement,
    event_id_digest,
    feedback_id_digest,
)

MAX_CHECKPOINT_BYTES = 64 * 1024
WARMUP_ACCEPTED_EVENTS = 32
MAX_PRIMARY_ALPHA = 0.1

BackendSource = Literal["lite", "primary"]


@dataclass(frozen=True, slots=True)
class CoordinatedStep:
    request: BrainStepRequest
    lite_candidate: CLiteEventCandidate
    allocation: EventAllocation
    source: BackendSource
    degraded: bool
    proposal: tuple[float, ...]
    eligibility: tuple[float, ...]
    authority_alpha: float
    provisional_checkpoint: BackendCheckpoint | None
    primary_invoked: bool
    failure_reason: str | None = None

    @property
    def generation(self) -> int:
        return self.allocation.generation

    @property
    def candidate_mutation_seq(self) -> int:
        return self.allocation.mutation_seq


@dataclass(frozen=True, slots=True)
class CoordinatedFeedback:
    request: BrainFeedbackRequest
    lite_candidate: CLiteFeedbackCandidate
    allocation: FeedbackAllocation
    state_tick: int
    source: BackendSource
    degraded: bool
    combined_changed: bool
    applied_synapses: int
    provisional_checkpoint: BackendCheckpoint | None
    primary_invoked: bool
    failure_reason: str | None = None

    @property
    def generation(self) -> int:
        return self.allocation.generation

    @property
    def candidate_mutation_seq(self) -> int:
        if self.combined_changed:
            return self.allocation.next_mutation_seq
        return self.allocation.expected_mutation_seq


CoordinatedCandidate = CoordinatedStep | CoordinatedFeedback
PositiveStoreAcknowledgement = EventCommitted | FeedbackCommitted
_CandidateT = TypeVar("_CandidateT", bound=CoordinatedCandidate)


class _PrimaryConstructionError(Exception):
    """A trusted factory failed before returning a supervisor instance."""


def _raw_session_digest(value: object) -> bytes:
    if type(value) is not bytes or len(value) != 32:
        raise BrainValidationError("session_digest must be raw 32 bytes")
    return value


def _counter(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BrainValidationError(f"{name} must be a non-boolean counter")
    if not 0 <= value <= MAX_COUNTER:
        raise BrainValidationError(f"{name} is outside the persisted counter domain")
    return value


def _timeout(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BrainValidationError("timeout_ms must be a positive non-boolean integer")
    return value


def _nonempty_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise BrainValidationError(f"{name} must be a nonempty string")
    return value


def _finite_tuple(
    name: str,
    values: object,
    *,
    length: int,
    lower: float,
    upper: float,
) -> tuple[float, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise BrainValidationError(f"{name} must contain exactly {length} values")
    try:
        materialized = tuple(islice(cast(Iterable[object], values), length + 1))
    except TypeError as error:
        raise BrainValidationError(f"{name} must contain exactly {length} values") from error
    if len(materialized) != length:
        raise BrainValidationError(f"{name} must contain exactly {length} values")
    converted: list[float] = []
    for index, item in enumerate(materialized):
        if isinstance(item, bool):
            raise BrainValidationError(f"{name}[{index}] must be finite")
        try:
            number = float(cast(float, item))
        except (TypeError, ValueError, OverflowError) as error:
            raise BrainValidationError(f"{name}[{index}] must be finite") from error
        if not math.isfinite(number):
            raise BrainValidationError(f"{name}[{index}] must be finite")
        if not lower <= number <= upper:
            raise BrainValidationError(f"{name}[{index}] is outside [{lower}, {upper}]")
        converted.append(number)
    return tuple(converted)


def _validate_checkpoint(
    checkpoint: BackendCheckpoint | None,
    *,
    primary_name: str,
) -> BackendCheckpoint | None:
    if checkpoint is None:
        return None
    if not isinstance(checkpoint, BackendCheckpoint):
        raise BrainValidationError("acknowledged_checkpoint must be a BackendCheckpoint")
    _counter("checkpoint generation", checkpoint.generation)
    _counter("checkpoint backend_state_version", checkpoint.backend_state_version)
    _counter("checkpoint acknowledged_mutation_seq", checkpoint.acknowledged_mutation_seq)
    if checkpoint.backend_name != primary_name:
        raise BrainValidationError("checkpoint backend_name does not match primary")
    if type(checkpoint.token) is not bytes:
        raise BrainValidationError("checkpoint token must be bytes")
    if len(checkpoint.token) > MAX_CHECKPOINT_BYTES:
        raise BrainValidationError("checkpoint token exceeds 64KB")
    if type(checkpoint.token_sha256) is not bytes or len(checkpoint.token_sha256) != 32:
        raise BrainValidationError("checkpoint token_sha256 must be raw 32 bytes")
    if checkpoint.token_sha256 != hashlib.sha256(checkpoint.token).digest():
        raise BrainValidationError("checkpoint token_sha256 mismatch")
    return checkpoint


class BrainBackendCoordinator:
    """Own a pure lite reference and one discardable process-supervisor instance."""

    def __init__(
        self,
        *,
        session_digest: bytes,
        lite_state: CLiteState,
        primary_name: str = "lite",
        primary_factory: BrainBackendFactory | None = None,
        acknowledged_checkpoint: BackendCheckpoint | None = None,
        primary_alpha: float = 0.0,
    ) -> None:
        self._session_digest = _raw_session_digest(session_digest)
        if not isinstance(lite_state, CLiteState):
            raise BrainValidationError("lite_state must be a CLiteState")
        self._lite_state = lite_state.copy()
        self._primary_name = _nonempty_text("primary_name", primary_name)
        if isinstance(primary_alpha, bool):
            raise BrainValidationError("primary_alpha must be finite and in [0, 0.1]")
        try:
            alpha = float(primary_alpha)
        except (TypeError, ValueError, OverflowError) as error:
            raise BrainValidationError("primary_alpha must be finite and in [0, 0.1]") from error
        if not math.isfinite(alpha) or not 0.0 <= alpha <= MAX_PRIMARY_ALPHA:
            raise BrainValidationError("primary_alpha must be finite and in [0, 0.1]")
        self._primary_alpha = alpha
        self._pending: CoordinatedCandidate | None = None
        self._primary_instance: BrainBackend | None = None
        self._primary_opened = False
        self._needs_reload = False
        self._closed = False
        self._canary_required = self._primary_name != "lite"
        self._warmup_remaining = WARMUP_ACCEPTED_EVENTS if self._primary_name != "lite" else 0

        if self._primary_name == "lite":
            if primary_factory is not None or acknowledged_checkpoint is not None:
                raise BrainValidationError(
                    "lite backend cannot use an external primary or checkpoint"
                )
            self._primary_factory: BrainBackendFactory | None = None
            self._acknowledged_checkpoint = None
            self._open_token = None
            self._primary_state_version = 0
            return

        if primary_factory is None:
            try:
                primary_factory = get_brain_backend_factory(self._primary_name)
            except KeyError as error:
                raise BrainValidationError(
                    f"unknown brain backend {self._primary_name!r}"
                ) from error
        self._primary_factory = primary_factory
        checkpoint = _validate_checkpoint(
            acknowledged_checkpoint,
            primary_name=self._primary_name,
        )
        self._acknowledged_checkpoint = checkpoint
        self._open_token = None if checkpoint is None else checkpoint.token
        self._primary_state_version = 0 if checkpoint is None else checkpoint.backend_state_version
        try:
            self._primary_instance = self._new_primary()
        except _PrimaryConstructionError:
            self._primary_instance = None

    @property
    def lite_state(self) -> CLiteState:
        return self._lite_state.copy()

    @property
    def primary_instance(self) -> BrainBackend | None:
        return self._primary_instance

    @property
    def acknowledged_checkpoint(self) -> BackendCheckpoint | None:
        return self._acknowledged_checkpoint

    @property
    def warmup_remaining(self) -> int:
        return self._warmup_remaining

    @property
    def canary_required(self) -> bool:
        return self._canary_required

    @property
    def needs_reload(self) -> bool:
        return self._needs_reload

    def _new_primary(self) -> BrainBackend:
        factory = self._primary_factory
        if factory is None:  # pragma: no cover - guarded by the lite branch
            raise AssertionError("external primary factory is absent")
        try:
            instance = factory()
        except Exception as error:
            raise _PrimaryConstructionError("primary backend construction failed") from error
        try:
            isolated = getattr(instance, "is_process_isolated", False)
        except BaseException:
            try:
                instance.abort("primary isolation probe failed")
            except BaseException:
                pass
            try:
                instance.close()
            except BaseException:
                pass
            raise
        if isolated is not True:
            try:
                instance.abort("primary is not process isolated")
            except BaseException:
                pass
            try:
                instance.close()
            except BaseException:
                pass
            raise BrainValidationError("non-lite primary must be process isolated")
        return instance

    @staticmethod
    def _abort_and_close_primary(instance: BrainBackend, reason: str) -> None:
        control_error: BaseException | None = None
        try:
            instance.abort(reason)
        except BaseException as error:
            if not isinstance(error, Exception):
                control_error = error
        try:
            instance.close()
        except BaseException as error:
            if control_error is None and not isinstance(error, Exception):
                control_error = error
        if control_error is not None:
            raise control_error

    def _discard_primary(self, reason: str) -> None:
        instance = self._primary_instance
        self._primary_instance = None
        self._primary_opened = False
        if instance is not None:
            self._abort_and_close_primary(instance, reason)

    def _discard_after_base_exception(self, reason: str) -> None:
        """Discard live state while preserving the base exception already in flight."""
        try:
            self._discard_primary(reason)
        except BaseException:
            pass

    def _assert_ready(self) -> None:
        if self._closed:
            raise BrainDurabilityError("brain backend coordinator is closed")
        if self._needs_reload:
            raise BrainDurabilityError("authoritative state must reload before backend reuse")
        if self._pending is not None:
            raise BrainDurabilityError("a provisional backend candidate is still in flight")

    def _fail_closed(self) -> None:
        self._pending = None
        self._needs_reload = True

    def _ensure_primary(self, timeout_ms: int) -> tuple[bool, str | None]:
        if self._primary_factory is None:
            return False, None
        if self._primary_instance is None:
            try:
                self._primary_instance = self._new_primary()
            except Exception as error:
                return False, f"primary construction failed: {type(error).__name__}"
            except BaseException:
                raise
        if self._primary_opened:
            return True, None
        instance = self._primary_instance
        try:
            instance.open(self._session_digest, self._open_token, timeout_ms=timeout_ms)
        except BrainCheckpointMismatchError:
            self._discard_primary("checkpoint mismatch")
            self._open_token = None
            self._primary_state_version = 0
            self._warmup_remaining = WARMUP_ACCEPTED_EVENTS
            self._canary_required = True
            try:
                self._primary_instance = self._new_primary()
                self._primary_instance.open(self._session_digest, None, timeout_ms=timeout_ms)
            except Exception as error:
                self._discard_primary("primary reinitialization failed")
                return False, f"primary reinitialization failed: {type(error).__name__}"
            except BaseException:
                self._discard_after_base_exception("primary reinitialization interrupted")
                raise
        except Exception as error:
            self._discard_primary("primary open failed")
            return False, f"primary open failed: {type(error).__name__}"
        except BaseException:
            self._discard_after_base_exception("primary open interrupted")
            raise
        self._primary_opened = True
        return True, None

    def _authority_alpha(self) -> float:
        if self._warmup_remaining or self._canary_required:
            return 0.0
        return self._primary_alpha

    def _validate_step_request(self, request: object) -> BrainStepRequest:
        if not isinstance(request, BrainStepRequest):
            raise BrainValidationError("request must be a BrainStepRequest")
        _nonempty_text("request_id", request.request_id)
        _nonempty_text("event_id", request.event_id)
        _counter("tick_id", request.tick_id)
        expected = _counter("expected_state_version", request.expected_state_version)
        _finite_tuple("event", request.event, length=8, lower=-1.0, upper=1.0)
        if self._primary_factory is not None and expected != self._primary_state_version:
            raise BrainValidationError("request expected_state_version is stale")
        return request

    def _validate_feedback_request(self, request: object) -> BrainFeedbackRequest:
        if not isinstance(request, BrainFeedbackRequest):
            raise BrainValidationError("request must be a BrainFeedbackRequest")
        _nonempty_text("request_id", request.request_id)
        _nonempty_text("feedback_id", request.feedback_id)
        _counter("target_tick", request.target_tick)
        expected = _counter("expected_state_version", request.expected_state_version)
        _finite_tuple("feedback signal", (request.value,), length=1, lower=-1.0, upper=1.0)
        _finite_tuple("feedback confidence", (request.confidence,), length=1, lower=0.0, upper=1.0)
        if self._primary_factory is not None and expected != self._primary_state_version:
            raise BrainValidationError("request expected_state_version is stale")
        return request

    def _validate_step_result(
        self,
        request: BrainStepRequest,
        result: object,
    ) -> tuple[BrainStepResult, tuple[float, ...], tuple[float, ...]]:
        if not isinstance(result, BrainStepResult):
            raise BrainValidationError("primary step returned an unknown result")
        if result.request_id != request.request_id:
            raise BrainValidationError("primary step request_id mismatch")
        if result.event_id != request.event_id:
            raise BrainValidationError("primary step event_id mismatch")
        if result.tick_id != request.tick_id:
            raise BrainValidationError("primary step tick_id mismatch")
        if result.expected_state_version != request.expected_state_version:
            raise BrainValidationError("primary step expected_state_version mismatch")
        if result.state_version != request.expected_state_version + 1:
            raise BrainValidationError("primary step state_version mismatch")
        proposal = _finite_tuple(
            "primary proposal", result.proposal, length=8, lower=-1.0, upper=1.0
        )
        eligibility = _finite_tuple(
            "primary eligibility", result.eligibility, length=128, lower=0.0, upper=8.0
        )
        return result, proposal, eligibility

    def _validate_feedback_result(
        self,
        request: BrainFeedbackRequest,
        result: object,
    ) -> tuple[BrainFeedbackResult, bool]:
        if not isinstance(result, BrainFeedbackResult):
            raise BrainValidationError("primary feedback returned an unknown result")
        if result.request_id != request.request_id:
            raise BrainValidationError("primary feedback request_id mismatch")
        if result.feedback_id != request.feedback_id:
            raise BrainValidationError("primary feedback feedback_id mismatch")
        if result.target_tick != request.target_tick:
            raise BrainValidationError("primary feedback target_tick mismatch")
        if result.expected_state_version != request.expected_state_version:
            raise BrainValidationError("primary feedback expected_state_version mismatch")
        applied = result.applied_synapses
        if isinstance(applied, bool) or not isinstance(applied, int) or not 0 <= applied <= 128:
            raise BrainValidationError("primary feedback applied_synapses is outside [0, 128]")
        expected_result_version = request.expected_state_version + (1 if applied else 0)
        if result.state_version != expected_result_version:
            raise BrainValidationError("primary feedback state_version mismatch")
        return result, bool(applied)

    def _checkpoint(
        self,
        *,
        generation: int,
        candidate_mutation_seq: int,
        backend_state_version: int,
        timeout_ms: int,
    ) -> BackendCheckpoint:
        instance = self._primary_instance
        if instance is None:  # pragma: no cover - call sites require a live primary
            raise BrainValidationError("primary instance disappeared before checkpoint")
        token = instance.checkpoint(timeout_ms=timeout_ms)
        if type(token) is not bytes:
            raise BrainValidationError("checkpoint token must be bytes")
        if len(token) > MAX_CHECKPOINT_BYTES:
            raise BrainValidationError("checkpoint token exceeds 64KB")
        return BackendCheckpoint(
            generation=generation,
            backend_name=self._primary_name,
            backend_state_version=backend_state_version,
            acknowledged_mutation_seq=candidate_mutation_seq,
            token=token,
            token_sha256=hashlib.sha256(token).digest(),
        )

    def prepare_step(
        self,
        request: BrainStepRequest,
        *,
        allocation: EventAllocation,
        route: Route,
        created_at: float,
        delta_t: float,
        timeout_ms: int,
    ) -> CoordinatedStep:
        self._assert_ready()
        validated = self._validate_step_request(request)
        if not isinstance(allocation, EventAllocation):
            raise BrainValidationError("allocation must be an EventAllocation")
        if allocation.tick_id != validated.tick_id:
            raise BrainValidationError("event allocation tick_id does not match request")
        bounded_timeout = _timeout(timeout_ms)

        lite = evolve_c_event(
            self._lite_state,
            validated.event,
            route=route,
            tick_id=validated.tick_id,
            created_at=created_at,
            delta_t=delta_t,
        )
        source: BackendSource = "lite"
        degraded = False
        proposal = lite.proposal
        eligibility = tuple(lite.c_trace)
        provisional: BackendCheckpoint | None = None
        invoked = False
        failure: str | None = None

        available, failure = self._ensure_primary(bounded_timeout)
        if self._primary_factory is not None:
            degraded = not available
        if available:
            invoked = True
            effective_request = replace(
                validated,
                expected_state_version=self._primary_state_version,
            )
            try:
                result, proposal, eligibility = self._validate_step_result(
                    effective_request,
                    cast(BrainBackend, self._primary_instance).step(
                        effective_request,
                        timeout_ms=bounded_timeout,
                    ),
                )
                provisional = self._checkpoint(
                    generation=allocation.generation,
                    candidate_mutation_seq=allocation.mutation_seq,
                    backend_state_version=result.state_version,
                    timeout_ms=bounded_timeout,
                )
            except Exception as error:
                failure = f"primary step failed: {type(error).__name__}"
                self._discard_primary(failure)
                proposal = lite.proposal
                eligibility = tuple(lite.c_trace)
                degraded = True
            except BaseException:
                self._discard_after_base_exception("primary step interrupted")
                raise
            else:
                source = "primary"

        candidate = CoordinatedStep(
            request=validated,
            lite_candidate=lite,
            allocation=allocation,
            source=source,
            degraded=degraded,
            proposal=proposal,
            eligibility=eligibility,
            authority_alpha=self._authority_alpha() if source == "primary" else 0.0,
            provisional_checkpoint=provisional,
            primary_invoked=invoked,
            failure_reason=failure,
        )
        self._pending = candidate
        return candidate

    def step(
        self,
        request: BrainStepRequest,
        *,
        allocation: EventAllocation,
        route: Route,
        created_at: float,
        delta_t: float,
        timeout_ms: int,
    ) -> CoordinatedStep:
        """Compatibility spelling for callers that model the operation as one step."""
        return self.prepare_step(
            request,
            allocation=allocation,
            route=route,
            created_at=created_at,
            delta_t=delta_t,
            timeout_ms=timeout_ms,
        )

    def prepare_feedback(
        self,
        request: BrainFeedbackRequest,
        *,
        allocation: FeedbackAllocation,
        state_tick: int,
        trusted_now: float,
        state_clock: float,
        feedback_ttl_seconds: float,
        b_changed: bool,
        timeout_ms: int,
    ) -> CoordinatedFeedback:
        self._assert_ready()
        validated = self._validate_feedback_request(request)
        if not isinstance(allocation, FeedbackAllocation):
            raise BrainValidationError("allocation must be a FeedbackAllocation")
        if allocation.target_tick != validated.target_tick:
            raise BrainValidationError("feedback allocation target_tick does not match request")
        if allocation.next_mutation_seq != allocation.expected_mutation_seq + 1:
            raise BrainValidationError("feedback allocation mutation sequence is not consecutive")
        validated_state_tick = _counter("state_tick", state_tick)
        if type(b_changed) is not bool:
            raise BrainValidationError("b_changed must be a boolean")
        bounded_timeout = _timeout(timeout_ms)

        lite = evolve_c_feedback(
            self._lite_state,
            target_tick=validated.target_tick,
            state_tick=validated_state_tick,
            value=validated.value,
            confidence=validated.confidence,
            trusted_now=trusted_now,
            state_clock=state_clock,
            feedback_ttl_seconds=feedback_ttl_seconds,
        )
        source: BackendSource = "lite"
        degraded = False
        provisional: BackendCheckpoint | None = None
        invoked = False
        failure: str | None = None
        primary_changed = False
        primary_checkpoint_changed = False
        applied_synapses = len(lite.applied_synapses)

        available, failure = self._ensure_primary(bounded_timeout)
        if self._primary_factory is not None:
            degraded = not available
        if available:
            invoked = True
            effective_request = replace(
                validated,
                expected_state_version=self._primary_state_version,
            )
            try:
                result, primary_changed = self._validate_feedback_result(
                    effective_request,
                    cast(BrainBackend, self._primary_instance).apply_feedback(
                        effective_request,
                        timeout_ms=bounded_timeout,
                    ),
                )
                provisional = self._checkpoint(
                    generation=allocation.generation,
                    candidate_mutation_seq=allocation.next_mutation_seq,
                    backend_state_version=result.state_version,
                    timeout_ms=bounded_timeout,
                )
                applied_synapses = result.applied_synapses
                acknowledged = self._acknowledged_checkpoint
                primary_checkpoint_changed = (
                    acknowledged is None
                    or provisional.backend_state_version != acknowledged.backend_state_version
                    or provisional.token != acknowledged.token
                )
            except Exception as error:
                failure = f"primary feedback failed: {type(error).__name__}"
                self._discard_primary(failure)
                degraded = True
            except BaseException:
                self._discard_after_base_exception("primary feedback interrupted")
                raise
            else:
                source = "primary"

        combined_changed = (
            b_changed or lite.status == "applied" or primary_changed or primary_checkpoint_changed
        )
        if invoked and provisional is not None and not combined_changed:
            self._discard_primary("feedback combined result was a no-op")
            provisional = None
            source = "lite"
            applied_synapses = len(lite.applied_synapses)

        candidate = CoordinatedFeedback(
            request=validated,
            lite_candidate=lite,
            allocation=allocation,
            state_tick=validated_state_tick,
            source=source,
            degraded=degraded,
            combined_changed=combined_changed,
            applied_synapses=applied_synapses,
            provisional_checkpoint=provisional,
            primary_invoked=invoked,
            failure_reason=failure,
        )
        self._pending = candidate
        return candidate

    def apply_feedback(
        self,
        request: BrainFeedbackRequest,
        *,
        allocation: FeedbackAllocation,
        state_tick: int,
        trusted_now: float,
        state_clock: float,
        feedback_ttl_seconds: float,
        b_changed: bool,
        timeout_ms: int,
    ) -> CoordinatedFeedback:
        return self.prepare_feedback(
            request,
            allocation=allocation,
            state_tick=state_tick,
            trusted_now=trusted_now,
            state_clock=state_clock,
            feedback_ttl_seconds=feedback_ttl_seconds,
            b_changed=b_changed,
            timeout_ms=timeout_ms,
        )

    def _validate_positive_ack(
        self,
        candidate: CoordinatedCandidate,
        acknowledgement: object,
    ) -> None:
        if isinstance(candidate, CoordinatedStep):
            if not isinstance(acknowledgement, EventCommitted):
                raise BrainDurabilityError("event candidate lacks a positive EventCommitted ack")
        elif not isinstance(acknowledgement, FeedbackCommitted):
            raise BrainDurabilityError("feedback candidate lacks a positive FeedbackCommitted ack")
        if not isinstance(acknowledgement, (EventCommitted, FeedbackCommitted)):
            raise BrainDurabilityError("store acknowledgement type is invalid")
        if not _is_authentic_store_acknowledgement(acknowledgement):
            raise BrainDurabilityError("store acknowledgement seal is invalid")
        if not hmac.compare_digest(acknowledgement.session_digest, self._session_digest):
            raise BrainDurabilityError("store acknowledgement session digest mismatch")
        if isinstance(candidate, CoordinatedStep):
            expected_identifier = event_id_digest(candidate.request.event_id)
        else:
            expected_identifier = feedback_id_digest(candidate.request.feedback_id)
        if not hmac.compare_digest(acknowledgement.id_digest, expected_identifier):
            raise BrainDurabilityError("store acknowledgement identifier digest mismatch")
        expected_checkpoint_digest = (
            None
            if candidate.provisional_checkpoint is None
            else candidate.provisional_checkpoint.token_sha256
        )
        if acknowledgement.checkpoint_token_sha256 != expected_checkpoint_digest:
            raise BrainDurabilityError("store acknowledgement checkpoint digest mismatch")
        receipt = acknowledgement.receipt
        if (
            receipt.generation != candidate.generation
            or receipt.mutation_seq != candidate.candidate_mutation_seq
        ):
            raise BrainDurabilityError("store acknowledgement does not match candidate version")
        if isinstance(candidate, CoordinatedStep):
            expected_status = "degraded" if candidate.degraded else "applied"
            if (
                receipt.kind != "event"
                or receipt.status != expected_status
                or receipt.tick_id != candidate.request.tick_id
                or receipt.history_epoch != candidate.allocation.history_epoch
            ):
                raise BrainDurabilityError("event store acknowledgement identity mismatch")
        else:
            if candidate.degraded:
                expected_feedback_status = "degraded"
            elif candidate.combined_changed:
                expected_feedback_status = "applied"
            else:
                expected_feedback_status = candidate.lite_candidate.status
            if (
                receipt.kind != "feedback"
                or receipt.status != expected_feedback_status
                or receipt.tick_id != candidate.state_tick
                or receipt.target_tick != candidate.request.target_tick
            ):
                raise BrainDurabilityError("feedback store acknowledgement identity mismatch")

    def acknowledge(
        self,
        candidate: CoordinatedCandidate,
        acknowledgement: PositiveStoreAcknowledgement,
    ) -> None:
        if candidate is not self._pending:
            raise BrainDurabilityError("candidate is stale or already finalized")
        try:
            self._validate_positive_ack(candidate, acknowledgement)
        except Exception:
            self._fail_closed()
            self._discard_primary("store acknowledgement was not positive")
            raise
        except BaseException:
            self._fail_closed()
            self._discard_after_base_exception("store acknowledgement validation was interrupted")
            raise
        try:
            finalized_lite_state = candidate.lite_candidate.state.copy()
        except BaseException:
            self._fail_closed()
            self._discard_after_base_exception("post-acknowledgement finalization was interrupted")
            raise
        self._lite_state = finalized_lite_state
        checkpoint = candidate.provisional_checkpoint
        if checkpoint is not None:
            self._acknowledged_checkpoint = checkpoint
            self._open_token = checkpoint.token
            self._primary_state_version = checkpoint.backend_state_version
        if (
            isinstance(candidate, CoordinatedStep)
            and checkpoint is not None
            and self._warmup_remaining > 0
        ):
            self._warmup_remaining -= 1
        self._pending = None

    def reject(self, candidate: CoordinatedCandidate, reason: str) -> None:
        if candidate is not self._pending:
            raise BrainDurabilityError("candidate is stale or already finalized")
        validated_reason = _nonempty_text("reason", reason)
        self._pending = None
        if candidate.primary_invoked:
            self._needs_reload = True
        self._discard_primary(validated_reason)

    def commit(
        self,
        candidate: _CandidateT,
        store_commit: Callable[[_CandidateT], PositiveStoreAcknowledgement],
    ) -> PositiveStoreAcknowledgement:
        if candidate is not self._pending:
            raise BrainDurabilityError("candidate is stale or already finalized")
        try:
            acknowledgement = store_commit(candidate)
        except Exception:
            self._fail_closed()
            self._discard_primary("store commit was not acknowledged")
            raise
        except BaseException:
            self._fail_closed()
            self._discard_after_base_exception("store commit was interrupted")
            raise
        try:
            self._validate_positive_ack(candidate, acknowledgement)
        except Exception:
            self._fail_closed()
            self._discard_primary("store commit returned no positive acknowledgement")
            raise
        except BaseException:
            self._fail_closed()
            self._discard_after_base_exception("store commit acknowledgement was interrupted")
            raise
        self.acknowledge(candidate, acknowledgement)
        return acknowledgement

    def reload_authoritative(
        self,
        lite_state: CLiteState,
        checkpoint: BackendCheckpoint | None,
    ) -> None:
        if not self._needs_reload:
            raise BrainDurabilityError("coordinator is not waiting for an authoritative reload")
        if self._pending is not None or self._primary_instance is not None:
            raise BrainDurabilityError("reload requires no provisional or live primary state")
        if not isinstance(lite_state, CLiteState):
            raise BrainValidationError("lite_state must be a CLiteState")
        validated = _validate_checkpoint(checkpoint, primary_name=self._primary_name)
        self._lite_state = lite_state.copy()
        self._acknowledged_checkpoint = validated
        self._open_token = None if validated is None else validated.token
        self._primary_state_version = 0 if validated is None else validated.backend_state_version
        if self._primary_factory is not None:
            self._warmup_remaining = WARMUP_ACCEPTED_EVENTS
            self._canary_required = True
        self._needs_reload = False

    def promote_primary(self, *, alpha: float | None = None) -> None:
        if self._warmup_remaining:
            raise BrainDurabilityError("primary warmup is not complete")
        if alpha is not None:
            if isinstance(alpha, bool) or not math.isfinite(alpha) or not 0.0 <= alpha <= 0.1:
                raise BrainValidationError("primary alpha must be finite and in [0, 0.1]")
            self._primary_alpha = alpha
        self._canary_required = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._pending is not None:
            try:
                self._discard_primary("coordinator closed with a provisional candidate")
            finally:
                self._pending = None
        else:
            instance = self._primary_instance
            self._primary_instance = None
            self._primary_opened = False
            if instance is not None:
                try:
                    instance.close()
                except Exception:
                    self._abort_and_close_primary(instance, "primary close failed")
                except BaseException:
                    try:
                        self._abort_and_close_primary(instance, "primary close was interrupted")
                    except BaseException:
                        pass
                    raise
