"""The explanation layer -- and nothing more.

The LLM receives deterministic evidence that has already been calculated and
classified. It summarises and explains; it never calculates, never reclassifies
and never reaches the database.

Failure here is expected and contained: the caller receives ``available=False``
with a reason, and the deterministic dashboard carries on unchanged. No
explanation is ever fabricated.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx

from app.config.settings import BACKEND_DIR, get_settings

logger = logging.getLogger(__name__)


def _load_usage_tracker():
    """Load ``llm_usage_tracker.py`` (project root) by file path.

    That module is deliberately independent of this application -- see its
    own docstring -- so it is loaded this way, rather than by adding the
    project root to ``sys.path`` and doing a normal ``import``, to keep that
    independence one-directional and explicit: this app reaches out to it,
    it never reaches back in. A missing or broken tracker file disables
    usage logging (logged once, below) without affecting any explanation.
    """
    tracker_path = BACKEND_DIR.parent / "llm_usage_tracker.py"
    if not tracker_path.exists():
        return None
    try:
        spec = importlib.util.spec_from_file_location("llm_usage_tracker", tracker_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:  # noqa: BLE001 - usage logging must never block startup
        logger.warning("Could not load llm_usage_tracker.py; usage will not be logged", exc_info=True)
        return None


_usage_tracker = _load_usage_tracker()

#: Transient provider failures worth a short retry before giving up. Measured
#: against the live Groq endpoint: 429 (rate limited) and, intermittently,
#: 413 both occurred for a request that succeeded moments later with the
#: identical payload -- i.e. upstream flakiness, not a hard, repeatable limit
#: on this evidence. A momentary hiccup should not surface to the operator as
#: "unavailable" when one retry would have worked.
_RETRYABLE_STATUS_CODES = {408, 413, 429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 0.75
#: Ceiling on how long a single retry waits, including a provider-supplied
#: Retry-After -- long enough to clear a brief rate-limit window, short enough
#: that the operator is never left waiting well past the configured timeout.
_MAX_RETRY_DELAY_SECONDS = 3.0

SYSTEM_INSTRUCTION = """You are an operational data explanation assistant.

The supplied JSON is authoritative deterministic evidence.

Do not calculate, modify, reinterpret, infer or invent values.

Do not invent causes.

Do not assign responsibility unless explicitly provided by the evidence.

Do not create business rules.

Explain only what the supplied evidence supports.

The "summary" figures (well_count, task_count, status_counts) always cover every well and \
task in scope. The "tasks" list is only a representative sample -- chosen to span every \
status and as many distinct wells as possible -- never the full list. When the scope covers \
more than one well, describe the scope as a whole using the summary figures first, and refer \
to specific wells only as individual examples within that whole. Never describe the scope as \
if it were about only the well(s) shown in the sample.

If information is missing, state that it is unavailable.

Use the supplied quantity_status exactly as provided.

Do not replace SQL/Python classifications with your own classification.

Do not describe quantity differences as errors unless the evidence explicitly \
identifies them as errors.

Report the progress value exactly as given. Its unit is not defined in the \
business rules, so never call it a percentage, never multiply it, and never \
describe how complete the task is from it.

Write for a construction operations supervisor reading a morning brief. Write \
in flowing prose paragraphs, the way a person would explain it out loud -- NOT \
as a bulleted or numbered list, and not broken into labelled sections. Do not \
use markdown formatting of any kind: no asterisks, no bold, no headings, no \
bullet points, no tables.

One exception, and the only one: wrap every literal value you copy directly \
from the evidence in backticks -- a well ID, task code, activity code, WBS \
name, crew code, unit of measure, quantity, date, or status code -- for \
example `30365`, `54 Joint`, `BELOW_PLAN`, `FLME1150-30365-T07`. This lets the \
reader tell your own words apart from a value taken straight from the record. \
Never wrap your own wording, a rounded or approximate figure, or anything you \
did not copy verbatim from the evidence.

Two to four short paragraphs is normal; a single \
paragraph is fine for a small scope. Use conservative wording: say "the \
reported actual quantity is below the planned quantity", never "the crew \
underperformed". Never convert between units of measure. Keep the response \
under 220 words."""

#: Endpoint used when LLM_BASE_URL is not set. Both providers speak the
#: OpenAI-compatible chat completions protocol.
_PROVIDER_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "openai": "https://api.openai.com/v1",
}


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    """Seconds to wait before the next attempt.

    Honours a provider-supplied ``Retry-After`` (seconds form) when present,
    capped so one flaky response can never stall the request past a few
    seconds; otherwise backs off a little longer on each attempt.
    """
    retry_after = response.headers.get("Retry-After")
    if retry_after is not None:
        try:
            return min(float(retry_after), _MAX_RETRY_DELAY_SECONDS)
        except ValueError:
            pass
    return min(_RETRY_BACKOFF_SECONDS * attempt, _MAX_RETRY_DELAY_SECONDS)


class LLMUnavailable(RuntimeError):
    """The explanation could not be produced. The dashboard continues regardless."""


#: Bump this whenever SYSTEM_INSTRUCTION, the evidence-sampling strategy
#: (``EvidenceService._representative_sample``), or anything else that could
#: change what a given evidence payload *should* produce is edited. It is
#: mixed into the cache key below, so every explanation cached under an
#: older version becomes permanently unreachable the moment this changes --
#: a prompt improvement takes effect on the very next request instead of
#: being masked by an answer generated under the old prompt, with no need to
#: find and clear the persisted cache file by hand.
_PROMPT_VERSION = 2


def _evidence_hash(evidence: Dict[str, Any]) -> str:
    """A content-address for one evidence payload, salted by `_PROMPT_VERSION`.

    Two requests that resolve to byte-identical evidence, under the same
    prompt version, describe the same day, the same scope and filters, and
    the same figures the dataset resolved for them -- there is nothing left
    for a second LLM call to add. Hashing the evidence itself (rather than
    the request's scope/filter parameters) is what makes that guarantee
    exact rather than assumed: if the underlying data changes for any
    reason, the evidence changes and the hash changes with it, so a stale
    explanation can never be served for changed data. ``sort_keys`` makes
    the JSON dump stable regardless of the dict's insertion order.
    """
    canonical = json.dumps(evidence, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(f"{_PROMPT_VERSION}:{canonical}".encode("utf-8")).hexdigest()


class _ExplainCache:
    """Cache of successful explanations, keyed by report date, persisted to disk.

    Not a fixed-size cache of hashes alone: entries are grouped by report date
    so a "Refresh" on one date can drop only that date's cached explanations
    (`invalidate_date`) without touching any other date the operator has open.
    Within a date, the key is the evidence's content hash (`_evidence_hash`),
    so identical evidence always resolves to the same cached text and changed
    evidence never does.

    Only successful explanations are ever stored -- see `LLMService.explain_safe`.
    A transient failure must never be "remembered" as permanent; the next
    identical request should retry the provider, not repeat a stale error.

    **Why this writes to disk.** A purely in-memory cache is wiped by every
    process restart -- a dev auto-reload, a redeploy, a plain re-run -- so the
    very first request after any restart always paid for a fresh LLM call
    again, even for a well explained a minute before the restart. Every
    change is written straight through to `file_path` (default
    `backend/.cache/explain_cache.json`, see `Settings.explain_cache_file`),
    and the constructor loads whatever is already there, so a fresh process
    starts warm: only a genuinely new question -- one this file has never
    seen, on this date, in any previous run -- ever costs a new LLM call.
    Content-hashing is still what makes this *correct*, not just cheap: a
    real data change still produces a different hash and is never served a
    stale answer, no matter how many restarts sit between the two requests.
    """

    def __init__(self, file_path: Optional[Path] = None) -> None:
        self._file_path = file_path
        self._by_date: "OrderedDict[str, OrderedDict[str, Dict[str, Any]]]" = OrderedDict()
        self._lock = threading.Lock()
        # One lock per (date, evidence hash) key, used to serialise concurrent
        # requests for the exact same not-yet-cached evidence -- see
        # `key_lock`. Deliberately never pruned: a `threading.Lock` is a few
        # dozen bytes, and the number of distinct (date, evidence) pairs this
        # process will ever be asked to explain is small next to that.
        self._key_locks: Dict[Tuple[str, str], threading.Lock] = {}
        self._key_locks_guard = threading.Lock()
        self._load()

    def _load(self) -> None:
        """Warm the cache from disk. Never raises -- a missing or corrupt
        file just means starting cold, exactly like before this existed."""
        if self._file_path is None:
            return
        try:
            raw = self._file_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except OSError:
            logger.warning("Could not read explanation cache file %s", self._file_path)
            return
        try:
            data = json.loads(raw)
        except ValueError:
            logger.warning(
                "Explanation cache file %s is not valid JSON; starting empty",
                self._file_path,
            )
            return
        if not isinstance(data, dict):
            return
        loaded: "OrderedDict[str, OrderedDict[str, Dict[str, Any]]]" = OrderedDict()
        for report_date, bucket in data.items():
            if isinstance(bucket, dict):
                loaded[report_date] = OrderedDict(bucket)
        self._by_date = loaded
        logger.info(
            "Explanation cache warmed from %s: %d date(s), %d entr%s",
            self._file_path,
            len(loaded),
            sum(len(b) for b in loaded.values()),
            "y" if sum(len(b) for b in loaded.values()) == 1 else "ies",
        )

    def _persist(self) -> None:
        """Write the whole cache back out. Called with `self._lock` already
        held, so the file on disk never reflects a half-updated in-memory
        state. Failure to write is logged, never raised -- a full disk or a
        permissions problem must degrade to an in-memory-only cache for the
        rest of this process, not break explanations altogether."""
        if self._file_path is None:
            return
        try:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._file_path.with_suffix(self._file_path.suffix + ".tmp")
            tmp_path.write_text(
                json.dumps(self._by_date, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            # Atomic on both POSIX and Windows (Python 3.3+): a reader never
            # observes a half-written file, even if this process is killed
            # mid-write.
            os.replace(tmp_path, self._file_path)
        except OSError:
            logger.warning(
                "Could not persist explanation cache to %s; continuing in-memory only",
                self._file_path,
            )

    def key_lock(self, report_date: str, evidence_hash: str) -> threading.Lock:
        """The lock guarding this one (date, evidence) key.

        Held only around the "still a miss? then call the LLM and store it"
        step in `LLMService.explain_safe` -- never around a cache read, and
        never across two different keys -- so requests for a different well,
        scope or date proceed fully in parallel; only two requests racing on
        the exact same not-yet-cached evidence ever wait on each other.
        """
        with self._key_locks_guard:
            lock = self._key_locks.get((report_date, evidence_hash))
            if lock is None:
                lock = threading.Lock()
                self._key_locks[(report_date, evidence_hash)] = lock
            return lock

    def get(self, report_date: str, evidence_hash: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            bucket = self._by_date.get(report_date)
            if bucket is None:
                return None
            entry = bucket.get(evidence_hash)
            if entry is None:
                return None
            # Touch both levels so an active date and its active entries are
            # the least likely to be evicted next.
            bucket.move_to_end(evidence_hash)
            self._by_date.move_to_end(report_date)
            return entry

    def put(
        self, report_date: str, evidence_hash: str, entry: Dict[str, Any], *, max_entries: int
    ) -> None:
        with self._lock:
            bucket = self._by_date.setdefault(report_date, OrderedDict())
            bucket[evidence_hash] = entry
            bucket.move_to_end(evidence_hash)
            self._by_date.move_to_end(report_date)

            # Two-level LRU eviction: trim the oldest entry within whichever
            # date holds the most, dropping an emptied date entirely, until
            # the total across every date is back within budget. This keeps
            # one very busy date from starving every other date's cache.
            total = sum(len(b) for b in self._by_date.values())
            while total > max_entries and self._by_date:
                oldest_date = next(iter(self._by_date))
                oldest_bucket = self._by_date[oldest_date]
                if oldest_bucket:
                    oldest_bucket.popitem(last=False)
                if not oldest_bucket:
                    del self._by_date[oldest_date]
                total -= 1

            self._persist()

    def invalidate_date(self, report_date: str) -> None:
        with self._lock:
            self._by_date.pop(report_date, None)
            self._persist()


class LLMService:
    """Thin OpenAI-compatible chat-completions client."""

    def __init__(self) -> None:
        cache_file = get_settings().explain_cache_file
        path = (BACKEND_DIR / cache_file) if cache_file else None
        self._cache = _ExplainCache(path)

    def invalidate_date(self, report_date: date) -> None:
        """Drop every cached explanation for one report date.

        Called wherever the day's dataset itself is force-refreshed (the
        "Refresh" control bypasses the dataset's own TTL cache), so a refresh
        always gets a fresh explanation on the next request even in the rare
        case where the reloaded data happens to be byte-identical to before.
        """
        self._cache.invalidate_date(report_date.isoformat())

    def status(self) -> Dict[str, Any]:
        settings = get_settings()
        return {
            "configured": settings.llm_configured,
            "provider": settings.llm_provider,
            "model": settings.llm_model if settings.llm_configured else None,
        }

    def _endpoint(self) -> str:
        settings = get_settings()
        base = settings.llm_base_url or _PROVIDER_BASE_URLS.get(
            (settings.llm_provider or "").lower()
        )
        if not base:
            raise LLMUnavailable(
                "No LLM endpoint configured. Set LLM_BASE_URL in backend/.env."
            )
        return base.rstrip("/") + "/chat/completions"

    def _post_with_retry(self, payload: Dict[str, Any], settings: Any) -> httpx.Response:
        """POST the chat-completion request, retrying a transient failure once or twice.

        Raises:
            LLMUnavailable: the request could not be sent, or every attempt
                (including retries) came back with an error.
        """
        last_response: Optional[httpx.Response] = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = httpx.post(
                    self._endpoint(),
                    headers={
                        "Authorization": f"Bearer {settings.llm_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=settings.llm_timeout_seconds,
                )
            except httpx.HTTPError as exc:
                logger.warning("LLM request failed: %s", type(exc).__name__)
                raise LLMUnavailable(
                    "The AI explanation service could not be reached."
                ) from None

            if response.status_code < 400:
                return response

            last_response = response
            retryable = response.status_code in _RETRYABLE_STATUS_CODES
            if not retryable or attempt == _MAX_ATTEMPTS:
                break

            delay = _retry_delay(response, attempt)
            logger.info(
                "LLM returned HTTP %s on attempt %d/%d; retrying in %.2fs",
                response.status_code,
                attempt,
                _MAX_ATTEMPTS,
                delay,
            )
            time.sleep(delay)

        # Log the status only: the body can echo request content.
        logger.warning("LLM returned HTTP %s", last_response.status_code)
        if last_response.status_code == 413:
            # Evidence size is capped per scope in evidence_service, so this
            # should now be rare -- but a plain-language reason still beats
            # surfacing a raw HTTP status to an operator.
            raise LLMUnavailable(
                "This selection has too much data for the AI to summarise at once."
            )
        raise LLMUnavailable(
            f"The AI explanation service returned HTTP {last_response.status_code}."
        )

    def explain(self, evidence: Dict[str, Any]) -> Tuple[str, str]:
        """Return ``(explanation, model)`` for the supplied evidence.

        Raises:
            LLMUnavailable: for any configuration, transport or response
                problem. The caller reports it; it never fabricates text.
        """
        settings = get_settings()
        if not settings.llm_configured:
            raise LLMUnavailable(
                "The AI explanation service is not configured. "
                "Set LLM_API_KEY and LLM_MODEL in backend/.env."
            )

        payload = {
            "model": settings.llm_model,
            "temperature": settings.llm_temperature,
            "max_tokens": settings.llm_max_tokens,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {
                    "role": "user",
                    "content": (
                        "Explain the following deterministic evidence for the "
                        "daily morning brief. Use only these values.\n\n"
                        + json.dumps(evidence, ensure_ascii=False, indent=2)
                    ),
                },
            ],
        }

        started = time.perf_counter()
        response = self._post_with_retry(payload, settings)
        elapsed_seconds = time.perf_counter() - started

        try:
            body = response.json()
            message = body["choices"][0]["message"]
            text = (message.get("content") or "").strip()
            if not text:
                # Some reasoning models place the answer in a separate field.
                text = (message.get("reasoning_content") or "").strip()
        except (ValueError, KeyError, IndexError, TypeError):
            logger.warning("LLM returned an unreadable response body")
            raise LLMUnavailable(
                "The AI explanation service returned an unreadable response."
            ) from None

        if not text:
            raise LLMUnavailable("The AI explanation service returned no text.")

        logger.info("LLM explanation generated with model %s", settings.llm_model)

        # This point is reached only for a real, successful call to the
        # provider -- never for a cache hit (explain_safe short-circuits
        # before ever calling this method) -- so every row in the usage log
        # represents tokens actually spent, never a reused answer.
        usage = body.get("usage") if isinstance(body, dict) else None
        if _usage_tracker is not None:
            try:
                # prompt_tokens_details.cached_tokens is OpenAI's breakdown of
                # how much of prompt_tokens was served from its own prompt
                # cache (typically billed at a discount). Not every provider
                # reports it -- absent entirely on a provider that doesn't,
                # so this stays None rather than a misleading 0.
                cache_details = (usage or {}).get("prompt_tokens_details") or {}
                _usage_tracker.log_usage(
                    input_tokens=(usage or {}).get("prompt_tokens"),
                    output_tokens=(usage or {}).get("completion_tokens"),
                    input_cache_tokens=cache_details.get("cached_tokens"),
                    duration_seconds=elapsed_seconds,
                )
            except Exception:  # noqa: BLE001 - logging usage must never break an explanation
                logger.warning("Could not log LLM usage", exc_info=True)

        return text, str(settings.llm_model)

    def explain_safe(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """Never raises. Returns the explanation or a plain unavailable reason.

        Identical evidence is served from cache instead of calling the LLM
        again -- pressing "AI summary" a second time for the same well, group
        or day, with nothing changed underneath it, costs no additional
        tokens. See ``_evidence_hash`` and ``_ExplainCache`` for exactly what
        "identical" means and how a real data change or a "Refresh" still
        forces a fresh call.

        Two requests for the same not-yet-cached evidence arriving together --
        two browser tabs on the same well, or a client that fires a request
        twice in quick succession -- must not both reach the LLM: whichever
        arrives second waits on ``key_lock`` and then finds the first one's
        answer already cached, rather than paying for a second, independently
        generated (and, at a non-zero temperature, differently worded) answer
        to the exact same question.
        """
        report_date = str(evidence.get("report_date") or "")
        evidence_hash = _evidence_hash(evidence)

        cached = self._cache.get(report_date, evidence_hash)
        if cached is not None:
            return {**cached, "cached": True}

        with self._cache.key_lock(report_date, evidence_hash):
            # Re-check: whoever held this lock before us may have just
            # finished computing and storing the very answer we were about
            # to ask the LLM for.
            cached = self._cache.get(report_date, evidence_hash)
            if cached is not None:
                return {**cached, "cached": True}

            try:
                text, model = self.explain(evidence)
                result = {"available": True, "explanation": text, "model": model, "error": None}
            except LLMUnavailable as exc:
                # Never cached: a transient failure must be retried next
                # time, not remembered as a permanent answer.
                return {
                    "available": False,
                    "explanation": None,
                    "model": None,
                    "error": str(exc),
                    "cached": False,
                }
            except Exception:  # noqa: BLE001 - the dashboard must survive anything here
                logger.exception("Unexpected LLM failure")
                return {
                    "available": False,
                    "explanation": None,
                    "model": None,
                    "error": "The AI explanation service failed unexpectedly.",
                    "cached": False,
                }

            self._cache.put(
                report_date,
                evidence_hash,
                result,
                max_entries=get_settings().explain_cache_max_entries,
            )
            return {**result, "cached": False}
