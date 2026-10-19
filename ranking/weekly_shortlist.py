from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ==========================================================
# PROJECT PATHS
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"

CANDIDATES_FILE = DATA_DIR / "candidates.json"
RANKED_CANDIDATES_FILE = DATA_DIR / "ranked_candidates.json"
TRACKED_CONNECTIONS_FILE = DATA_DIR / "tracked_connections.json"

WEEKLY_SHORTLIST_FILE = DATA_DIR / "weekly_shortlist.json"
WEEKLY_SHORTLIST_HISTORY_FILE = (
    DATA_DIR
    / "weekly_shortlist_history.json"
)


# ==========================================================
# SETTINGS
# ==========================================================

# Candidate relevance threshold.
#
# This is separate from the POST relevance threshold.
#
# POST:
# >= 75 means inspect comments / notify lawyer.
#
# CANDIDATE:
# >= 75 means strong enough to potentially appear
# in This Week's recommendations.
MINIMUM_AI_SCORE = int(
    os.getenv(
        "WEEKLY_MIN_AI_SCORE",
        "75",
    )
)


# Default weekly shortlist size.
#
# This is configurable.
#
# Example:
#
# WEEKLY_SHORTLIST_MAX=15
#
# or:
#
# WEEKLY_SHORTLIST_MAX=20
MAXIMUM_CANDIDATES = int(
    os.getenv(
        "WEEKLY_SHORTLIST_MAX",
        "10",
    )
)


RECOMMENDATION_REQUIRED = (
    "recommend"
)


# Candidates with one of these decisions should
# not come back as a new weekly recommendation.
DISQUALIFYING_DECISIONS = {

    "connect_selected",

    "follow_selected",

    "saved",

    "not_relevant",

    "rejected",

    "archived",

    "connected",

    "pending_connection",

    "connection_pending",

    "removed",
}


# ==========================================================
# TIME
# ==========================================================

def utc_now() -> str:

    return (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )


def current_week_key() -> str:

    now = (
        datetime.now(
            timezone.utc
        )
    )

    (
        iso_year,
        iso_week,
        _,
    ) = (
        now.isocalendar()
    )

    return (
        f"{iso_year}-W{iso_week:02d}"
    )


# ==========================================================
# JSON HELPERS
# ==========================================================

def load_json(
    path: Path,
    default: Any,
) -> Any:

    if not path.exists():

        return default

    try:

        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        json.JSONDecodeError,
        OSError,
    ):

        return default


def save_json(
    path: Path,
    data: Any,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = (
        path.with_name(
            path.name
            +
            ".tmp"
        )
    )

    temporary_path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(
        path
    )


def extract_list(
    payload: Any,
    possible_keys: list[str],
) -> list[
    dict[str, Any]
]:

    if isinstance(
        payload,
        list,
    ):

        return [

            item

            for item
            in payload

            if isinstance(
                item,
                dict,
            )
        ]


    if isinstance(
        payload,
        dict,
    ):

        for key in possible_keys:

            value = (
                payload.get(
                    key
                )
            )

            if isinstance(
                value,
                list,
            ):

                return [

                    item

                    for item
                    in value

                    if isinstance(
                        item,
                        dict,
                    )
                ]


    return []


# ==========================================================
# URL NORMALIZATION
# ==========================================================

def normalize_profile_url(
    value: str | None,
) -> str | None:

    if not value:

        return None


    match = re.search(
        r"https://(?:www\.)?linkedin\.com/in/([^/?#]+)",
        str(
            value
        ),
        flags=re.IGNORECASE,
    )


    if not match:

        return None


    slug = (

        match.group(
            1
        )

        .strip()

        .lower()
    )


    if not slug:

        return None


    return (
        f"https://www.linkedin.com/in/{slug}/"
    )


# ==========================================================
# DATA LOADERS
# ==========================================================

def load_candidates() -> list[
    dict[str, Any]
]:

    payload = (
        load_json(
            CANDIDATES_FILE,
            [],
        )
    )


    return (
        extract_list(
            payload,
            [
                "candidates",
                "items",
            ],
        )
    )


def load_ranked_candidates() -> list[
    dict[str, Any]
]:

    payload = (
        load_json(
            RANKED_CANDIDATES_FILE,
            [],
        )
    )


    return (
        extract_list(
            payload,
            [
                "candidates",
                "ranked_candidates",
                "items",
            ],
        )
    )


def load_tracked_connections() -> list[
    dict[str, Any]
]:

    payload = (
        load_json(
            TRACKED_CONNECTIONS_FILE,
            [],
        )
    )


    return (
        extract_list(
            payload,
            [
                "connections",
                "tracked_connections",
                "items",
            ],
        )
    )


# ==========================================================
# HISTORY
# ==========================================================

def load_history() -> tuple[
    Any,
    list[
        dict[str, Any]
    ],
    str | None,
]:

    payload = (
        load_json(
            WEEKLY_SHORTLIST_HISTORY_FILE,
            [],
        )
    )


    # ======================================================
    # OLD / SIMPLE LIST FORMAT
    # ======================================================

    if isinstance(
        payload,
        list,
    ):

        return (

            payload,

            [
                item

                for item
                in payload

                if isinstance(
                    item,
                    dict,
                )
            ],

            None,
        )


    # ======================================================
    # OBJECT FORMAT
    # ======================================================

    if isinstance(
        payload,
        dict,
    ):

        for key in [

            "weeks",

            "history",

            "shortlists",

        ]:

            value = (
                payload.get(
                    key
                )
            )


            if isinstance(
                value,
                list,
            ):

                return (

                    payload,

                    [
                        item

                        for item
                        in value

                        if isinstance(
                            item,
                            dict,
                        )
                    ],

                    key,
                )


        return (

            payload,

            [],

            "weeks",
        )


    return (

        [],

        [],

        None,
    )


def save_history(
    original_payload: Any,
    entries: list[
        dict[str, Any]
    ],
    list_key: str | None,
) -> None:

    # ======================================================
    # PRESERVE EXISTING LIST FORMAT
    # ======================================================

    if isinstance(
        original_payload,
        list,
    ):

        save_json(
            WEEKLY_SHORTLIST_HISTORY_FILE,
            entries,
        )

        return


    # ======================================================
    # PRESERVE EXISTING OBJECT FORMAT
    # ======================================================

    if isinstance(
        original_payload,
        dict,
    ):

        updated = dict(
            original_payload
        )


        updated[
            list_key
            or
            "weeks"
        ] = (
            entries
        )


        updated[
            "updated_at"
        ] = (
            utc_now()
        )


        save_json(
            WEEKLY_SHORTLIST_HISTORY_FILE,
            updated,
        )

        return


    save_json(
        WEEKLY_SHORTLIST_HISTORY_FILE,
        entries,
    )


def upsert_history_entry(
    entries: list[
        dict[str, Any]
    ],
    shortlist: dict[
        str,
        Any,
    ],
) -> list[
    dict[str, Any]
]:

    week_key = (
        shortlist.get(
            "week_key"
        )
    )


    if not week_key:

        return entries


    output: list[
        dict[str, Any]
    ] = []


    replaced = False


    for entry in entries:

        if (
            entry.get(
                "week_key"
            )
            ==
            week_key
        ):

            output.append(
                shortlist
            )

            replaced = True


        else:

            output.append(
                entry
            )


    if not replaced:

        output.append(
            shortlist
        )


    output.sort(
        key=lambda item:
            str(
                item.get(
                    "week_key"
                )
                or
                ""
            )
    )


    return output


def previously_shortlisted_urls(
    history_entries: list[
        dict[str, Any]
    ],
    exclude_week: str | None = None,
) -> set[str]:

    urls: set[
        str
    ] = set()


    for entry in history_entries:

        if (
            exclude_week
            and
            entry.get(
                "week_key"
            )
            ==
            exclude_week
        ):

            continue


        candidates = (

            entry.get(
                "candidates"
            )

            or

            []
        )


        if not isinstance(
            candidates,
            list,
        ):

            continue


        for candidate in candidates:

            if not isinstance(
                candidate,
                dict,
            ):

                continue


            profile_url = (
                normalize_profile_url(
                    candidate.get(
                        "profile_url"
                    )
                )
            )


            if profile_url:

                urls.add(
                    profile_url
                )


    return urls


# ==========================================================
# CANDIDATE LOOKUP
# ==========================================================

def build_candidate_lookup(
    candidates: list[
        dict[str, Any]
    ],
) -> dict[
    str,
    dict[str, Any],
]:

    lookup: dict[
        str,
        dict[str, Any],
    ] = {}


    for candidate in candidates:

        profile_url = (
            normalize_profile_url(
                candidate.get(
                    "profile_url"
                )
            )
        )


        if profile_url:

            lookup[
                profile_url
            ] = (
                candidate
            )


    return lookup


def merge_latest_candidate_data(
    ranked_candidates: list[
        dict[str, Any]
    ],
    canonical_candidates: list[
        dict[str, Any]
    ],
) -> list[
    dict[str, Any]
]:

    canonical_lookup = (
        build_candidate_lookup(
            canonical_candidates
        )
    )


    output: list[
        dict[str, Any]
    ] = []


    seen: set[
        str
    ] = set()


    for ranked_candidate in ranked_candidates:

        profile_url = (
            normalize_profile_url(
                ranked_candidate.get(
                    "profile_url"
                )
            )
        )


        if not profile_url:

            continue


        if profile_url in seen:

            continue


        latest = (
            canonical_lookup.get(
                profile_url
            )
        )


        if latest:

            merged = {

                **ranked_candidate,

                **latest,
            }


        else:

            merged = dict(
                ranked_candidate
            )


        merged[
            "profile_url"
        ] = (
            profile_url
        )


        output.append(
            merged
        )


        seen.add(
            profile_url
        )


    return output


# ==========================================================
# TRACKED / DECISION FILTERS
# ==========================================================

def tracked_profile_urls(
    tracked_connections: list[
        dict[str, Any]
    ],
) -> set[str]:

    urls: set[
        str
    ] = set()


    for connection in tracked_connections:

        profile_url = (
            normalize_profile_url(
                connection.get(
                    "profile_url"
                )
            )
        )


        if profile_url:

            urls.add(
                profile_url
            )


    return urls


def get_decision_status(
    candidate: dict[
        str,
        Any,
    ],
) -> str:

    return (

        str(

            candidate.get(
                "decision_status"
            )

            or

            candidate.get(
                "lawyer_decision"
            )

            or

            "pending_review"
        )

        .strip()

        .lower()
    )


# ==========================================================
# AI / PROFILE HELPERS
# ==========================================================

def get_assessment(
    candidate: dict[
        str,
        Any,
    ],
) -> dict[
    str,
    Any,
]:

    assessment = (

        candidate.get(
            "ai_assessment"
        )

        or

        {}
    )


    if not isinstance(
        assessment,
        dict,
    ):

        return {}


    return assessment


def get_score(
    candidate: dict[
        str,
        Any,
    ],
) -> int:

    assessment = (
        get_assessment(
            candidate
        )
    )


    try:

        return int(

            assessment.get(
                "total_score",
                0,
            )

            or

            0
        )


    except Exception:

        return 0


def confidence_weight(
    candidate: dict[
        str,
        Any,
    ],
) -> int:

    assessment = (
        get_assessment(
            candidate
        )
    )


    confidence = (

        str(

            assessment.get(
                "confidence"
            )

            or

            ""
        )

        .strip()

        .lower()
    )


    return {

        "high":
            3,

        "medium":
            2,

        "low":
            1,

    }.get(
        confidence,
        0,
    )


def get_profile_data(
    candidate: dict[
        str,
        Any,
    ],
) -> dict[
    str,
    Any,
]:

    profile = (

        candidate.get(
            "linkedin_profile_data"
        )

        or

        {}
    )


    if not isinstance(
        profile,
        dict,
    ):

        return {}


    return profile


def get_profile_photo_url(
    candidate: dict[
        str,
        Any,
    ],
) -> str | None:

    profile = (
        get_profile_data(
            candidate
        )
    )


    options = [

        profile.get(
            "profile_photo_local_url"
        ),

        candidate.get(
            "profile_photo_local_url"
        ),

        profile.get(
            "profile_photo_url"
        ),

        candidate.get(
            "profile_photo_url"
        ),

        profile.get(
            "photo_url"
        ),

        candidate.get(
            "photo_url"
        ),
    ]


    for value in options:

        if value:

            return str(
                value
            )


    return None


# ==========================================================
# DISCOVERY CONTEXT
# ==========================================================

def source_value(
    source: dict[
        str,
        Any,
    ],
    candidate: dict[
        str,
        Any,
    ],
    *keys: str,
) -> Any:

    for key in keys:

        value = (
            source.get(
                key
            )
        )


        if value not in (

            None,

            "",

            [],

            {},

        ):

            return value


    for key in keys:

        value = (
            candidate.get(
                key
            )
        )


        if value not in (

            None,

            "",

            [],

            {},

        ):

            return value


    return None


def get_primary_source(
    candidate: dict[
        str,
        Any,
    ],
) -> dict[
    str,
    Any,
]:

    raw_sources = (

        candidate.get(
            "sources"
        )

        or

        []
    )


    sources = [

        item

        for item
        in raw_sources

        if isinstance(
            item,
            dict,
        )
    ]


    if sources:

        def source_sort_key(
            source: dict[
                str,
                Any,
            ],
        ) -> tuple[
            int,
            str,
        ]:

            try:

                relevance = int(

                    source.get(
                        "source_post_relevance_score"
                    )

                    or

                    0
                )


            except Exception:

                relevance = 0


            discovered_at = str(

                source.get(
                    "discovered_at"
                )

                or

                ""
            )


            return (

                relevance,

                discovered_at,
            )


        return max(
            sources,
            key=
                source_sort_key,
        )


    return {}


def build_discovery_context(
    candidate: dict[
        str,
        Any,
    ],
) -> dict[
    str,
    Any,
]:

    source = (
        get_primary_source(
            candidate
        )
    )


    discovery_method = (
        source_value(
            source,
            candidate,
            "discovery_method",
            "source",
        )
    )


    source_connection_name = (
        source_value(
            source,
            candidate,
            "source_connection_name",
            "source_connection",
        )
    )


    source_connection_profile_url = (
        source_value(
            source,
            candidate,
            "source_connection_profile_url",
        )
    )


    source_post_url = (
        source_value(
            source,
            candidate,
            "source_post_url",
        )
    )


    source_post_summary = (
        source_value(
            source,
            candidate,
            "source_post_summary",
        )
    )


    source_post_relevance_score = (
        source_value(
            source,
            candidate,
            "source_post_relevance_score",
        )
    )


    source_comment_text = (
        source_value(
            source,
            candidate,
            "source_comment_text",
            "comment_text",
        )
    )


    found_through = None


    if (
        discovery_method
        ==
        "relevant_post_commenter"
    ):

        if source_connection_name:

            found_through = (
                "Commented on "
                f"{source_connection_name}'s "
                "relevant LinkedIn post."
            )


        else:

            found_through = (
                "Discovered in the comments "
                "of a relevant LinkedIn post."
            )


    elif source_connection_name:

        found_through = (
            "Discovered through professional "
            "activity around "
            f"{source_connection_name}."
        )


    elif discovery_method:

        found_through = (

            str(
                discovery_method
            )

            .replace(
                "_",
                " ",
            )

            .strip()

            .capitalize()
        )


    return {

        "discovery_method":
            discovery_method,


        "source_connection_name":
            source_connection_name,


        "source_connection_profile_url":
            source_connection_profile_url,


        "source_post_url":
            source_post_url,


        "source_post_summary":
            source_post_summary,


        "source_post_relevance_score":
            source_post_relevance_score,


        "source_comment_text":
            source_comment_text,


        "found_through":
            found_through,
    }


# ==========================================================
# ELIGIBILITY
# ==========================================================

def candidate_is_eligible(
    candidate: dict[
        str,
        Any,
    ],
    tracked_urls: set[str],
    previous_week_urls: set[str],
) -> tuple[
    bool,
    str,
]:

    profile_url = (
        normalize_profile_url(
            candidate.get(
                "profile_url"
            )
        )
    )


    if not profile_url:

        return (
            False,
            "invalid_profile_url",
        )


    # ======================================================
    # ALREADY BEING TRACKED BY NETWORK SCOUT
    # ======================================================

    if (
        profile_url
        in tracked_urls
    ):

        return (
            False,
            "already_tracked",
        )


    # ======================================================
    # ALREADY SHOWN IN AN OLDER WEEK
    # ======================================================

    if (
        profile_url
        in previous_week_urls
    ):

        return (
            False,
            "previously_shortlisted",
        )


    # ======================================================
    # LAWYER ALREADY MADE A DECISION
    # ======================================================

    decision_status = (
        get_decision_status(
            candidate
        )
    )


    if (
        decision_status
        in
        DISQUALIFYING_DECISIONS
    ):

        return (
            False,
            f"decision_{decision_status}",
        )


    # ======================================================
    # MUST HAVE A VALID AI SCORE
    # ======================================================

    if (
        candidate.get(
            "ai_scoring_status"
        )
        !=
        "success"
    ):

        return (
            False,
            "ai_not_successfully_scored",
        )


    assessment = (
        get_assessment(
            candidate
        )
    )


    recommendation = (

        str(

            assessment.get(
                "recommendation"
            )

            or

            ""
        )

        .strip()

        .lower()
    )


    # ======================================================
    # ONLY STRONG RECOMMENDATIONS
    # ======================================================

    if (
        recommendation
        !=
        RECOMMENDATION_REQUIRED
    ):

        return (
            False,
            "not_recommended",
        )


    score = (
        get_score(
            candidate
        )
    )


    if (
        score
        <
        MINIMUM_AI_SCORE
    ):

        return (
            False,
            "below_minimum_score",
        )


    return (
        True,
        "eligible",
    )


# ==========================================================
# DETERMINISTIC SORTING
# ==========================================================

def sort_key(
    candidate: dict[
        str,
        Any,
    ],
) -> tuple[
    int,
    int,
    int,
    int,
    int,
    str,
]:

    assessment = (
        get_assessment(
            candidate
        )
    )


    try:

        professional = int(

            assessment.get(
                "professional_relevance",
                0,
            )

            or

            0
        )


    except Exception:

        professional = 0


    try:

        strategic = int(

            assessment.get(
                "strategic_network_value",
                0,
            )

            or

            0
        )


    except Exception:

        strategic = 0


    try:

        interaction = int(

            assessment.get(
                "interaction_signal",
                0,
            )

            or

            0
        )


    except Exception:

        interaction = 0


    name = (

        str(

            candidate.get(
                "name"
            )

            or

            ""
        )

        .lower()
    )


    # ======================================================
    # PRIORITY
    #
    # 1. Total AI score
    # 2. Confidence
    # 3. Professional relevance
    # 4. Strategic network value
    # 5. Interaction quality
    # 6. Name only for deterministic tie-breaking
    # ======================================================

    return (

        get_score(
            candidate
        ),

        confidence_weight(
            candidate
        ),

        professional,

        strategic,

        interaction,

        name,
    )


# ==========================================================
# BUILD LAWYER-FACING SHORTLIST RECORD
# ==========================================================

def build_shortlist_record(
    candidate: dict[
        str,
        Any,
    ],
    rank: int,
) -> dict[
    str,
    Any,
]:

    assessment = (
        get_assessment(
            candidate
        )
    )


    profile = (
        get_profile_data(
            candidate
        )
    )


    discovery = (
        build_discovery_context(
            candidate
        )
    )


    name = (

        profile.get(
            "name"
        )

        or

        candidate.get(
            "name"
        )

        or

        "Unknown Candidate"
    )


    headline = (

        profile.get(
            "headline"
        )

        or

        candidate.get(
            "headline"
        )
    )


    profile_url = (
        normalize_profile_url(
            candidate.get(
                "profile_url"
            )
        )
    )


    return {

        # ==================================================
        # SHORTLIST IDENTITY
        # ==================================================

        "rank":
            rank,


        "candidate_id":
            candidate.get(
                "candidate_id"
            ),


        "name":
            name,


        "profile_url":
            profile_url,


        # ==================================================
        # PROFESSIONAL PROFILE
        # ==================================================

        "headline":
            headline,


        "current_role":
            profile.get(
                "current_role"
            ),


        "current_company":
            profile.get(
                "current_company"
            ),


        "location":
            profile.get(
                "location"
            ),


        "profile_photo_url":
            get_profile_photo_url(
                candidate
            ),


        # ==================================================
        # AI RANKING
        # ==================================================

        "ai_score":
            get_score(
                candidate
            ),


        "recommendation":
            assessment.get(
                "recommendation"
            ),


        "confidence":
            assessment.get(
                "confidence"
            ),


        "why_relevant":
            assessment.get(
                "why_relevant"
            ),


        "networking_angle":
            assessment.get(
                "networking_angle"
            ),


        "shared_interests":
            (
                assessment.get(
                    "shared_interests"
                )
                or
                []
            ),


        "professional_relevance":
            assessment.get(
                "professional_relevance"
            ),


        "strategic_network_value":
            assessment.get(
                "strategic_network_value"
            ),


        "shared_interest_signal":
            assessment.get(
                "shared_interest_signal"
            ),


        "interaction_signal":
            assessment.get(
                "interaction_signal"
            ),


        "evidence_quality":
            assessment.get(
                "evidence_quality"
            ),


        # ==================================================
        # HUMAN-IN-THE-LOOP STATUS
        # ==================================================

        "decision_status":
            get_decision_status(
                candidate
            ),


        # ==================================================
        # WHY NETWORK SCOUT FOUND THIS PERSON
        # ==================================================

        "discovery_method":
            discovery.get(
                "discovery_method"
            ),


        "found_through":
            discovery.get(
                "found_through"
            ),


        "source_connection_name":
            discovery.get(
                "source_connection_name"
            ),


        "source_connection_profile_url":
            discovery.get(
                "source_connection_profile_url"
            ),


        "source_post_url":
            discovery.get(
                "source_post_url"
            ),


        "source_post_summary":
            discovery.get(
                "source_post_summary"
            ),


        "source_post_relevance_score":
            discovery.get(
                "source_post_relevance_score"
            ),


        "source_comment_text":
            discovery.get(
                "source_comment_text"
            ),


        # ==================================================
        # TRACEABILITY
        # ==================================================

        "ai_scored_at":
            candidate.get(
                "ai_scored_at"
            ),


        "ai_scoring_version":
            candidate.get(
                "ai_scoring_version"
            ),
    }


# ==========================================================
# GENERATE SHORTLIST
# ==========================================================

def generate_shortlist(
    refresh_current_week: bool,
) -> None:

    week_key = (
        current_week_key()
    )


    existing_shortlist = (
        load_json(
            WEEKLY_SHORTLIST_FILE,
            {},
        )
    )


    if not isinstance(
        existing_shortlist,
        dict,
    ):

        existing_shortlist = {}


    # ======================================================
    # SAME-WEEK IDEMPOTENCY
    #
    # If the automatic scheduler accidentally runs twice
    # during the same week, do NOT suddenly change the
    # lawyer's recommendations.
    # ======================================================

    if (
        existing_shortlist.get(
            "week_key"
        )
        ==
        week_key

        and

        not refresh_current_week
    ):

        existing_candidates = (

            existing_shortlist.get(
                "candidates"
            )

            or

            []
        )


        print(
            "\n================================"
        )


        print(
            "NETWORK SCOUT WEEKLY SHORTLIST"
        )


        print(
            "================================"
        )


        print(
            "Week:",
            week_key,
        )


        print(
            "Shortlist already exists for this week."
        )


        print(
            "Selected:",
            len(
                existing_candidates
            ),
        )


        print(
            (
                "No changes made. "
                "Use --refresh-current-week "
                "only when you intentionally "
                "want to rebuild this week's picks."
            )
        )


        print(
            "File:",
            WEEKLY_SHORTLIST_FILE,
        )


        return


    # ======================================================
    # LOAD DATA
    # ======================================================

    ranked_candidates = (
        load_ranked_candidates()
    )


    canonical_candidates = (
        load_candidates()
    )


    tracked_connections = (
        load_tracked_connections()
    )


    (
        history_payload,
        history_entries,
        history_key,
    ) = (
        load_history()
    )


    # ======================================================
    # ARCHIVE PREVIOUS WEEK
    # ======================================================

    if (
        existing_shortlist
        and
        existing_shortlist.get(
            "week_key"
        )
        and
        existing_shortlist.get(
            "week_key"
        )
        !=
        week_key
    ):

        history_entries = (
            upsert_history_entry(
                history_entries,
                existing_shortlist,
            )
        )


    # ======================================================
    # USE RANKED ORDER + LATEST CANDIDATE STATE
    # ======================================================

    latest_ranked_candidates = (
        merge_latest_candidate_data(
            ranked_candidates,
            canonical_candidates,
        )
    )


    tracked_urls = (
        tracked_profile_urls(
            tracked_connections
        )
    )


    previous_week_urls = (
        previously_shortlisted_urls(
            history_entries,
            exclude_week=
                week_key,
        )
    )


    # ======================================================
    # FILTER STRONG CANDIDATES
    # ======================================================

    eligible: list[
        dict[str, Any]
    ] = []


    excluded_reasons: dict[
        str,
        int,
    ] = {}


    for candidate in (
        latest_ranked_candidates
    ):

        (
            is_eligible,
            reason,
        ) = (
            candidate_is_eligible(
                candidate,
                tracked_urls,
                previous_week_urls,
            )
        )


        if is_eligible:

            eligible.append(
                candidate
            )


        else:

            excluded_reasons[
                reason
            ] = (

                excluded_reasons.get(
                    reason,
                    0,
                )

                +

                1
            )


    # ======================================================
    # STRONGEST FIRST
    # ======================================================

    eligible.sort(
        key=
            sort_key,
        reverse=
            True,
    )


    selected = (
        eligible[
            :max(
                0,
                MAXIMUM_CANDIDATES,
            )
        ]
    )


    shortlist_records = [

        build_shortlist_record(
            candidate,
            rank,
        )

        for rank, candidate
        in enumerate(
            selected,
            start=1,
        )
    ]


    # ======================================================
    # OUTPUT
    # ======================================================

    shortlist = {

        "week_key":
            week_key,


        "created_at":
            utc_now(),


        "minimum_ai_score":
            MINIMUM_AI_SCORE,


        "maximum_candidates":
            MAXIMUM_CANDIDATES,


        "eligible_candidate_count":
            len(
                eligible
            ),


        "selected_candidate_count":
            len(
                shortlist_records
            ),


        "ranked_candidate_count":
            len(
                latest_ranked_candidates
            ),


        "tracked_profiles_excluded":
            len(
                tracked_urls
            ),


        "previously_shortlisted_profile_count":
            len(
                previous_week_urls
            ),


        "selection_rule":
            (
                "AI recommendation must be 'recommend', "
                f"score must be >= {MINIMUM_AI_SCORE}, "
                "candidate must not already be tracked, "
                "actioned, or previously shortlisted."
            ),


        "excluded_reason_counts":
            excluded_reasons,


        "candidates":
            shortlist_records,
    }


    # ======================================================
    # SAVE CURRENT WEEK
    # ======================================================

    save_json(
        WEEKLY_SHORTLIST_FILE,
        shortlist,
    )


    # ======================================================
    # SAVE HISTORY
    # ======================================================

    history_entries = (
        upsert_history_entry(
            history_entries,
            shortlist,
        )
    )


    save_history(
        history_payload,
        history_entries,
        history_key,
    )


    # ======================================================
    # TERMINAL SUMMARY
    # ======================================================

    print(
        "\n================================"
    )


    print(
        "NETWORK SCOUT WEEKLY SHORTLIST"
    )


    print(
        "================================"
    )


    print(
        "Week:",
        week_key,
    )


    print(
        "Ranked candidates available:",
        len(
            latest_ranked_candidates
        ),
    )


    print(
        "Minimum AI score:",
        MINIMUM_AI_SCORE,
    )


    print(
        "Eligible strong candidates:",
        len(
            eligible
        ),
    )


    print(
        "Selected for This Week:",
        len(
            shortlist_records
        ),
    )


    print(
        "Maximum allowed:",
        MAXIMUM_CANDIDATES,
    )


    print(
        "Excluded:",
        excluded_reasons,
    )


    if shortlist_records:

        print(
            "\nTHIS WEEK"
        )


        for record in shortlist_records:

            print(
                (
                    f"#{record['rank']} "
                    f"{record.get('name')} "
                    f"— {record.get('ai_score')}/100"
                )
            )


            if record.get(
                "found_through"
            ):

                print(
                    "   Found through:",
                    record.get(
                        "found_through"
                    ),
                )


            print(
                "   Why:",
                record.get(
                    "why_relevant"
                ),
            )


    else:

        print(
            (
                "\nNo candidate met the weekly "
                "shortlist rules. Network Scout "
                "will not add weak filler picks."
            )
        )


    print(
        "\nWeekly shortlist:"
    )


    print(
        WEEKLY_SHORTLIST_FILE
    )


    print(
        "\nShortlist history:"
    )


    print(
        WEEKLY_SHORTLIST_HISTORY_FILE
    )


# ==========================================================
# CLI
# ==========================================================

def parse_arguments() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Create Network Scout's weekly "
            "lawyer-facing candidate shortlist."
        )
    )


    parser.add_argument(
        "--refresh-current-week",
        action="store_true",
        help=(
            "Intentionally rebuild the current "
            "week's shortlist. Normal automatic "
            "runs should not use this flag."
        ),
    )


    return (
        parser.parse_args()
    )


# ==========================================================
# MAIN
# ==========================================================

def main() -> None:

    args = (
        parse_arguments()
    )


    generate_shortlist(
        refresh_current_week=
            args.refresh_current_week,
    )


if __name__ == "__main__":

    main()