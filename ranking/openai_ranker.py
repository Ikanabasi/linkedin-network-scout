from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


# ==========================================================
# PROJECT PATHS / ENVIRONMENT
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CANDIDATES_FILE = (
    PROJECT_ROOT
    / "data"
    / "candidates.json"
)

RANKED_CANDIDATES_FILE = (
    PROJECT_ROOT
    / "data"
    / "ranked_candidates.json"
)

PREFERENCES_FILE = (
    PROJECT_ROOT
    / "config"
    / "networking_preferences.json"
)

ENV_FILE = (
    PROJECT_ROOT
    / ".env"
)


load_dotenv(
    ENV_FILE
)


OPENAI_API_KEY = (
    os.getenv(
        "OPENAI_API_KEY"
    )
)


OPENAI_MODEL = (
    os.getenv(
        "OPENAI_MODEL",
        "gpt-6-luna",
    )
)


# 0 means:
# process every candidate that genuinely needs scoring.
#
# Example:
# AI_RANKING_LIMIT=3
#
# Normal automation:
# AI_RANKING_LIMIT=0
AI_RANKING_LIMIT = int(
    os.getenv(
        "AI_RANKING_LIMIT",
        "0",
    )
)


# If true:
# force every enriched candidate through AI again.
#
# Normally keep false.
AI_RERANK_EXISTING = (
    os.getenv(
        "AI_RERANK_EXISTING",
        "false",
    )
    .strip()
    .lower()
    in {
        "1",
        "true",
        "yes",
    }
)


AI_SCORING_VERSION = (
    "network_scout_ranker_v3"
)


if not OPENAI_API_KEY:

    raise RuntimeError(
        "\nOPENAI_API_KEY is missing.\n"
        "Add it to your .env file."
    )


client = OpenAI(
    api_key=
        OPENAI_API_KEY
)


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


def parse_timestamp(
    value: Any,
) -> datetime | None:

    if not value:

        return None

    try:

        text = (
            str(
                value
            )
            .strip()
        )


        if text.endswith(
            "Z"
        ):

            text = (
                text[:-1]
                +
                "+00:00"
            )


        parsed = (
            datetime.fromisoformat(
                text
            )
        )


        if parsed.tzinfo is None:

            parsed = (
                parsed.replace(
                    tzinfo=
                        timezone.utc
                )
            )


        return (
            parsed.astimezone(
                timezone.utc
            )
        )


    except Exception:

        return None


# ==========================================================
# JSON HELPERS
# ==========================================================

def load_json(
    path: Path,
    default: Any = None,
) -> Any:

    if default is None:

        default = {}


    if not path.exists():

        return default


    try:

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:

            return (
                json.load(
                    file
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


    temporary_file = (
        path.with_suffix(
            path.suffix
            +
            ".tmp"
        )
    )


    with temporary_file.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False,
        )


    temporary_file.replace(
        path
    )


# ==========================================================
# TEXT HELPERS
# ==========================================================

def clean_text(
    value: Any,
    max_length: int | None = None,
) -> str | None:

    if value is None:

        return None


    value = (
        str(
            value
        )
        .replace(
            "\u200b",
            ""
        )
        .replace(
            "\xa0",
            " "
        )
        .strip()
    )


    if not value:

        return None


    if (
        max_length
        and
        len(
            value
        )
        >
        max_length
    ):

        return (
            value[
                :max_length
            ]
            +
            "..."
        )


    return value


def clean_string_list(
    values: Any,
    max_item_length: int,
) -> list[str]:

    if not isinstance(
        values,
        list,
    ):

        return []


    output: list[
        str
    ] = []


    for item in values:

        cleaned = (
            clean_text(
                item,
                max_item_length,
            )
        )


        if cleaned:

            output.append(
                cleaned
            )


    return output


# ==========================================================
# LOAD PROJECT DATA
# ==========================================================

def load_candidates() -> list[
    dict[
        str,
        Any,
    ]
]:

    data = (
        load_json(
            CANDIDATES_FILE,
            default=[],
        )
    )


    if not isinstance(
        data,
        list,
    ):

        raise ValueError(
            (
                "data/candidates.json "
                "must contain a JSON list."
            )
        )


    return [
        candidate
        for candidate
        in data
        if isinstance(
            candidate,
            dict,
        )
    ]


def load_preferences() -> dict[
    str,
    Any,
]:

    preferences = (
        load_json(
            PREFERENCES_FILE,
            default={},
        )
    )


    if not preferences:

        raise RuntimeError(
            (
                "\nNetworking preferences file "
                "is empty or missing:\n"
                f"{PREFERENCES_FILE}"
            )
        )


    if not isinstance(
        preferences,
        dict,
    ):

        raise ValueError(
            (
                "config/networking_preferences.json "
                "must contain a JSON object."
            )
        )


    return preferences


# ==========================================================
# SOURCE HISTORY
#
# Supports:
#
# OLD FORMAT:
# source_connection
# comment_text
#
# NEW RELEVANT-POST COMMENTER FORMAT:
# discovery_method
# source_connection_name
# source_connection_profile_url
# source_post_url
# source_post_summary
# source_post_relevance_score
# source_comment_text
#
# This means the reason a commenter was discovered survives
# all the way into AI ranking.
# ==========================================================

def normalize_source_record(
    source: dict[
        str,
        Any,
    ],
    candidate: dict[
        str,
        Any,
    ],
) -> dict[
    str,
    Any,
]:

    source_connection = (
        source.get(
            "source_connection"
        )
        or
        source.get(
            "source_connection_name"
        )
    )


    comment_text = (
        source.get(
            "comment_text"
        )
        or
        source.get(
            "source_comment_text"
        )
    )


    return {

        "discovery_method":
            clean_text(
                source.get(
                    "discovery_method"
                )
                or
                candidate.get(
                    "discovery_method"
                )
                or
                candidate.get(
                    "source"
                ),
                200,
            ),


        "source_connection":
            clean_text(
                source_connection,
                300,
            ),


        "source_connection_profile_url":
            clean_text(
                source.get(
                    "source_connection_profile_url"
                ),
                1000,
            ),


        "source_post_position":
            source.get(
                "source_post_position"
            ),


        "source_post_url":
            clean_text(
                source.get(
                    "source_post_url"
                ),
                1000,
            ),


        "source_post_urn":
            clean_text(
                source.get(
                    "source_post_urn"
                ),
                500,
            ),


        "source_post_summary":
            clean_text(
                source.get(
                    "source_post_summary"
                ),
                3000,
            ),


        "source_post_relevance_score":
            source.get(
                "source_post_relevance_score"
            ),


        "visible_comment_count":
            source.get(
                "visible_comment_count"
            ),


        "comment_text":
            clean_text(
                comment_text,
                3000,
            ),


        "discovered_at":
            clean_text(
                source.get(
                    "discovered_at"
                ),
                200,
            ),
    }


def build_source_history(
    candidate: dict[
        str,
        Any,
    ],
) -> list[
    dict[
        str,
        Any,
    ]
]:

    raw_sources = (
        candidate.get(
            "sources"
        )
        or
        []
    )


    cleaned_sources: list[
        dict[
            str,
            Any,
        ]
    ] = []


    # ======================================================
    # MULTI-SOURCE FORMAT
    # ======================================================

    if isinstance(
        raw_sources,
        list,
    ):

        for source in raw_sources:

            if not isinstance(
                source,
                dict,
            ):

                continue


            cleaned_sources.append(
                normalize_source_record(
                    source,
                    candidate,
                )
            )


    # ======================================================
    # TOP-LEVEL / BACKWARDS COMPATIBILITY
    # ======================================================

    if not cleaned_sources:

        top_level_source = {

            "discovery_method":
                candidate.get(
                    "discovery_method"
                )
                or
                candidate.get(
                    "source"
                ),


            "source_connection":
                candidate.get(
                    "source_connection"
                )
                or
                candidate.get(
                    "source_connection_name"
                ),


            "source_connection_profile_url":
                candidate.get(
                    "source_connection_profile_url"
                ),


            "source_post_position":
                candidate.get(
                    "source_post_position"
                ),


            "source_post_url":
                candidate.get(
                    "source_post_url"
                ),


            "source_post_urn":
                candidate.get(
                    "source_post_urn"
                ),


            "source_post_summary":
                candidate.get(
                    "source_post_summary"
                ),


            "source_post_relevance_score":
                candidate.get(
                    "source_post_relevance_score"
                ),


            "visible_comment_count":
                candidate.get(
                    "visible_comment_count"
                ),


            "comment_text":
                candidate.get(
                    "comment_text"
                )
                or
                candidate.get(
                    "source_comment_text"
                ),


            "discovered_at":
                candidate.get(
                    "discovered_at"
                )
                or
                candidate.get(
                    "last_discovered_at"
                ),
        }


        has_source_evidence = any(

            value not in (
                None,
                "",
                [],
                {},
            )

            for value
            in top_level_source.values()
        )


        if has_source_evidence:

            cleaned_sources.append(
                normalize_source_record(
                    top_level_source,
                    candidate,
                )
            )


    return cleaned_sources


# ==========================================================
# SOURCE NETWORK STATISTICS
# ==========================================================

def build_source_statistics(
    sources: list[
        dict[
            str,
            Any,
        ]
    ],
) -> dict[
    str,
    Any,
]:

    connection_names: set[
        str
    ] = set()


    connection_urls: set[
        str
    ] = set()


    post_urls: set[
        str
    ] = set()


    comments: list[
        str
    ] = []


    for source in sources:

        name = (
            clean_text(
                source.get(
                    "source_connection"
                )
            )
        )


        url = (
            clean_text(
                source.get(
                    "source_connection_profile_url"
                )
            )
        )


        post = (
            clean_text(
                source.get(
                    "source_post_url"
                )
            )
        )


        comment = (
            clean_text(
                source.get(
                    "comment_text"
                )
            )
        )


        if name:

            connection_names.add(
                name.lower()
            )


        if url:

            connection_urls.add(
                url.lower()
            )


        if post:

            post_urls.add(
                post.lower()
            )


        if comment:

            comments.append(
                comment
            )


    distinct_connections = max(

        len(
            connection_names
        ),

        len(
            connection_urls
        ),
    )


    return {

        "number_of_discovery_sources":
            len(
                sources
            ),


        "number_of_distinct_source_connections":
            distinct_connections,


        "number_of_distinct_source_posts":
            len(
                post_urls
            ),


        "number_of_captured_comments":
            len(
                comments
            ),


        "appears_across_multiple_network_connections":
            (
                distinct_connections
                >=
                2
            ),
    }


# ==========================================================
# LINKEDIN PROFILE PAYLOAD
# ==========================================================

def build_linkedin_profile_payload(
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

        profile = {}


    return {

        "name":
            clean_text(
                profile.get(
                    "name"
                )
                or
                candidate.get(
                    "name"
                ),
                300,
            ),


        "profile_url":
            clean_text(
                profile.get(
                    "profile_url"
                )
                or
                candidate.get(
                    "profile_url"
                ),
                1000,
            ),


        "headline":
            clean_text(
                profile.get(
                    "headline"
                )
                or
                candidate.get(
                    "headline"
                ),
                1000,
            ),


        "location":
            clean_text(
                profile.get(
                    "location"
                ),
                500,
            ),


        "current_role":
            clean_text(
                profile.get(
                    "current_role"
                ),
                1000,
            ),


        "current_company":
            clean_text(
                profile.get(
                    "current_company"
                ),
                1000,
            ),


        "about":
            clean_text(
                profile.get(
                    "about"
                ),
                6000,
            ),


        "experience_text":
            clean_text(
                profile.get(
                    "experience_text"
                ),
                8000,
            ),


        "education_text":
            clean_text(
                profile.get(
                    "education_text"
                ),
                4000,
            ),


        "top_card_preview":
            clean_text(
                profile.get(
                    "top_card_preview"
                ),
                3000,
            ),
    }


# ==========================================================
# COMPLETE CANDIDATE PAYLOAD
# ==========================================================

def build_candidate_payload(
    candidate: dict[
        str,
        Any,
    ],
) -> dict[
    str,
    Any,
]:

    sources = (
        build_source_history(
            candidate
        )
    )


    source_statistics = (
        build_source_statistics(
            sources
        )
    )


    return {

        "candidate": {

            "name":
                clean_text(
                    candidate.get(
                        "name"
                    ),
                    300,
                ),


            "profile_url":
                clean_text(
                    candidate.get(
                        "profile_url"
                    ),
                    1000,
                ),


            "connection_degree":
                clean_text(
                    candidate.get(
                        "connection_degree"
                    ),
                    100,
                ),


            "discovery_headline":
                clean_text(
                    candidate.get(
                        "headline"
                    ),
                    1000,
                ),


            "discovery_status":
                clean_text(
                    candidate.get(
                        "status"
                    ),
                    100,
                ),


            "discovery_method":
                clean_text(
                    candidate.get(
                        "discovery_method"
                    )
                    or
                    candidate.get(
                        "source"
                    ),
                    200,
                ),


            "discovered_at":
                clean_text(
                    candidate.get(
                        "discovered_at"
                    ),
                    200,
                ),


            "last_discovered_at":
                clean_text(
                    candidate.get(
                        "last_discovered_at"
                    ),
                    200,
                ),
        },


        "linkedin_profile":
            build_linkedin_profile_payload(
                candidate
            ),


        "source_statistics":
            source_statistics,


        "discovery_sources":
            sources,
    }


# ==========================================================
# AI RESPONSE SCHEMA
# ==========================================================

AI_RESPONSE_SCHEMA = {

    "type":
        "object",


    "properties": {

        "professional_relevance": {

            "type":
                "integer",

            "minimum":
                0,

            "maximum":
                30,
        },


        "strategic_network_value": {

            "type":
                "integer",

            "minimum":
                0,

            "maximum":
                25,
        },


        "shared_interest_signal": {

            "type":
                "integer",

            "minimum":
                0,

            "maximum":
                20,
        },


        "interaction_signal": {

            "type":
                "integer",

            "minimum":
                0,

            "maximum":
                15,
        },


        "evidence_quality": {

            "type":
                "integer",

            "minimum":
                0,

            "maximum":
                10,
        },


        "why_relevant": {

            "type":
                "string",
        },


        "shared_interests": {

            "type":
                "array",

            "items": {

                "type":
                    "string",
            },
        },


        "networking_angle": {

            "type":
                "string",
        },


        "evidence": {

            "type":
                "array",

            "items": {

                "type":
                    "string",
            },
        },


        "concerns": {

            "type":
                "array",

            "items": {

                "type":
                    "string",
            },
        },


        "confidence": {

            "type":
                "string",

            "enum": [
                "high",
                "medium",
                "low",
            ],
        },
    },


    "required": [

        "professional_relevance",

        "strategic_network_value",

        "shared_interest_signal",

        "interaction_signal",

        "evidence_quality",

        "why_relevant",

        "shared_interests",

        "networking_angle",

        "evidence",

        "concerns",

        "confidence",
    ],


    "additionalProperties":
        False,
}


# ==========================================================
# SYSTEM INSTRUCTIONS
# ==========================================================

SYSTEM_INSTRUCTIONS = """
You are the professional networking intelligence engine
for Network Scout.

Your job is to evaluate whether a discovered LinkedIn
professional is worth presenting to a lawyer as a
potential professional connection.

You are NOT deciding whether to automatically connect.
The lawyer makes that decision.

Use only the evidence supplied in the candidate payload
and networking preferences.

Do not invent facts.

Do not infer sensitive personal characteristics.

Do not assume two people know each other simply because
one commented on another person's post.

A candidate appearing meaningfully in discussions around
multiple different people already in the lawyer's network
is a stronger network-proximity signal than appearing
once, but it must not overwhelm professional relevance.

A source post relevance score explains why Network Scout
inspected that discussion.

It is NOT automatically proof that the commenter is a
strong candidate.

Judge the commenter independently using their professional
profile and the actual interaction evidence supplied.

Evaluate:

1. PROFESSIONAL RELEVANCE — 0 to 30

How closely the person's role, profession, experience,
industry, work, or expertise aligns with the lawyer's
networking goals and interests.

2. STRATEGIC NETWORK VALUE — 0 to 25

Potential value for a genuine long-term professional
relationship.

Consider complementary expertise, leadership,
entrepreneurship, business relevance, technology/AI
relevance, professional services, community leadership,
and useful network adjacency.

Do not reward fame for its own sake.

3. SHARED INTEREST SIGNAL — 0 to 20

Evidence of shared professional interests based on the
LinkedIn profile, About/Experience information, source
post context, and captured comments.

4. INTERACTION SIGNAL — 0 to 15

Quality of how the candidate appeared in the existing
network.

A thoughtful substantive comment should score higher
than a generic reaction-style comment.

Appearing meaningfully around multiple distinct network
connections can strengthen this score.

Do not treat raw comment volume alone as quality.

5. EVIDENCE QUALITY — 0 to 10

How much reliable information is actually available.

A well-enriched LinkedIn profile plus useful captured
comments should score higher.

Sparse or unclear information should lower this score.

For why_relevant:

Explain in concise plain language why this person may
or may not be worth the lawyer reviewing.

For networking_angle:

Give a practical, natural reason the lawyer could use
to understand the networking opportunity.

Do not write a fake personalized message.

For shared_interests:

Return only interests actually supported by supplied
evidence.

For evidence:

List the strongest concrete facts supporting your
assessment.

For concerns:

List uncertainties or weaknesses.

Return an empty list if there are none.

For confidence:

Use high when evidence is strong and identity/profile
information is clear.

Use medium when reasonably supported.

Use low when information is sparse or ambiguous.

Be conservative.

Never fabricate missing information.
"""


# ==========================================================
# OPENAI REQUEST
# ==========================================================

def score_with_openai(
    candidate_payload: dict[
        str,
        Any,
    ],
    networking_preferences: dict[
        str,
        Any,
    ],
) -> dict[
    str,
    Any,
]:

    request_payload = {

        "networking_preferences":
            networking_preferences,


        "candidate_data":
            candidate_payload,
    }


    response = (
        client.responses.create(

            model=
                OPENAI_MODEL,


            instructions=
                SYSTEM_INSTRUCTIONS,


            input=[
                {

                    "role":
                        "user",


                    "content":
                        json.dumps(
                            request_payload,
                            ensure_ascii=False,
                        ),
                }
            ],


            text={

                "format": {

                    "type":
                        "json_schema",


                    "name":
                        "network_scout_candidate_assessment",


                    "description":
                        (
                            "Structured professional "
                            "networking candidate assessment."
                        ),


                    "schema":
                        AI_RESPONSE_SCHEMA,


                    "strict":
                        True,
                }
            },


            store=False,
        )
    )


    output_text = (
        response.output_text
        or
        ""
    ).strip()


    if not output_text:

        raise RuntimeError(
            (
                "OpenAI returned "
                "no assessment text."
            )
        )


    parsed = (
        json.loads(
            output_text
        )
    )


    if not isinstance(
        parsed,
        dict,
    ):

        raise RuntimeError(
            (
                "OpenAI assessment "
                "was not a JSON object."
            )
        )


    return parsed


# ==========================================================
# SCORE SAFETY
# ==========================================================

def clamp_integer(
    value: Any,
    minimum: int,
    maximum: int,
) -> int:

    try:

        value = int(
            value
        )


    except Exception:

        value = minimum


    return max(

        minimum,

        min(
            maximum,
            value,
        ),
    )


def normalize_ai_assessment(
    raw_assessment: dict[
        str,
        Any,
    ],
) -> dict[
    str,
    Any,
]:

    professional_relevance = (
        clamp_integer(
            raw_assessment.get(
                "professional_relevance"
            ),
            0,
            30,
        )
    )


    strategic_network_value = (
        clamp_integer(
            raw_assessment.get(
                "strategic_network_value"
            ),
            0,
            25,
        )
    )


    shared_interest_signal = (
        clamp_integer(
            raw_assessment.get(
                "shared_interest_signal"
            ),
            0,
            20,
        )
    )


    interaction_signal = (
        clamp_integer(
            raw_assessment.get(
                "interaction_signal"
            ),
            0,
            15,
        )
    )


    evidence_quality = (
        clamp_integer(
            raw_assessment.get(
                "evidence_quality"
            ),
            0,
            10,
        )
    )


    total_score = (

        professional_relevance

        +

        strategic_network_value

        +

        shared_interest_signal

        +

        interaction_signal

        +

        evidence_quality
    )


    # ======================================================
    # PYTHON CHOOSES FINAL RECOMMENDATION
    # ======================================================

    if total_score >= 75:

        recommendation = (
            "recommend"
        )


    elif total_score >= 50:

        recommendation = (
            "maybe"
        )


    else:

        recommendation = (
            "not_relevant"
        )


    confidence = (
        raw_assessment.get(
            "confidence"
        )
        or
        "low"
    )


    if confidence not in {

        "high",

        "medium",

        "low",

    }:

        confidence = (
            "low"
        )


    return {

        "professional_relevance":
            professional_relevance,


        "strategic_network_value":
            strategic_network_value,


        "shared_interest_signal":
            shared_interest_signal,


        "interaction_signal":
            interaction_signal,


        "evidence_quality":
            evidence_quality,


        "total_score":
            total_score,


        "recommendation":
            recommendation,


        "confidence":
            confidence,


        "why_relevant":
            clean_text(
                raw_assessment.get(
                    "why_relevant"
                ),
                3000,
            ),


        "shared_interests":
            clean_string_list(
                raw_assessment.get(
                    "shared_interests"
                ),
                300,
            ),


        "networking_angle":
            clean_text(
                raw_assessment.get(
                    "networking_angle"
                ),
                3000,
            ),


        "evidence":
            clean_string_list(
                raw_assessment.get(
                    "evidence"
                ),
                1000,
            ),


        "concerns":
            clean_string_list(
                raw_assessment.get(
                    "concerns"
                ),
                1000,
            ),
    }


# ==========================================================
# ENRICHMENT STATUS
# ==========================================================

def candidate_is_enriched(
    candidate: dict[
        str,
        Any,
    ],
) -> bool:

    status = (

        candidate.get(
            "profile_enrichment_status"
        )

        or

        ""
    ).lower()


    return (

        status
        in {

            "success",

            "partial",
        }
    )


# ==========================================================
# LATEST CANDIDATE EVIDENCE
#
# We use timestamps to determine whether an old AI score
# became stale because:
#
# - the profile was enriched later
# - the candidate was rediscovered later
# - a new source/comment was added later
# ==========================================================

def get_latest_candidate_evidence_at(
    candidate: dict[
        str,
        Any,
    ],
) -> datetime | None:

    timestamps: list[
        datetime
    ] = []


    # ======================================================
    # TOP-LEVEL TIMESTAMPS
    # ======================================================

    for field_name in [

        "profile_enriched_at",

        "profile_enrichment_last_attempt_at",

        "last_discovered_at",

        "discovered_at",
    ]:

        parsed = (
            parse_timestamp(
                candidate.get(
                    field_name
                )
            )
        )


        if parsed:

            timestamps.append(
                parsed
            )


    # ======================================================
    # LINKEDIN PROFILE TIMESTAMPS
    # ======================================================

    profile = (

        candidate.get(
            "linkedin_profile_data"
        )

        or

        {}
    )


    if isinstance(
        profile,
        dict,
    ):

        for field_name in [

            "captured_at",

            "enriched_at",

            "updated_at",
        ]:

            parsed = (
                parse_timestamp(
                    profile.get(
                        field_name
                    )
                )
            )


            if parsed:

                timestamps.append(
                    parsed
                )


    # ======================================================
    # SOURCE DISCOVERY TIMESTAMPS
    # ======================================================

    sources = (
        candidate.get(
            "sources"
        )
        or
        []
    )


    if isinstance(
        sources,
        list,
    ):

        for source in sources:

            if not isinstance(
                source,
                dict,
            ):

                continue


            parsed = (
                parse_timestamp(
                    source.get(
                        "discovered_at"
                    )
                )
            )


            if parsed:

                timestamps.append(
                    parsed
                )


    if not timestamps:

        return None


    return max(
        timestamps
    )


def candidate_has_newer_evidence_than_score(
    candidate: dict[
        str,
        Any,
    ],
) -> bool:

    scored_at = (
        parse_timestamp(
            candidate.get(
                "ai_scored_at"
            )
        )
    )


    # If an old successful score has no timestamp,
    # we cannot safely prove it is current.
    if scored_at is None:

        return True


    latest_evidence_at = (
        get_latest_candidate_evidence_at(
            candidate
        )
    )


    if latest_evidence_at is None:

        return False


    return (

        latest_evidence_at
        >
        scored_at
    )


# ==========================================================
# SCORING INPUT HASH
#
# Once v3 scores a candidate, Network Scout stores a
# SHA-256 fingerprint of:
#
# - networking preferences
# - candidate profile
# - commenter/discovery context
# - scoring version
# - model
#
# If any of those inputs change later, the candidate
# becomes eligible for re-ranking.
# ==========================================================

def build_scoring_input_hash(
    candidate: dict[
        str,
        Any,
    ],
    networking_preferences: dict[
        str,
        Any,
    ],
) -> str:

    hash_payload = {

        "scoring_version":
            AI_SCORING_VERSION,


        "model":
            OPENAI_MODEL,


        "networking_preferences":
            networking_preferences,


        "candidate_payload":
            build_candidate_payload(
                candidate
            ),
    }


    canonical_json = (
        json.dumps(

            hash_payload,

            ensure_ascii=False,

            sort_keys=True,

            separators=(
                ",",
                ":",
            ),

            default=str,
        )
    )


    return (
        hashlib.sha256(
            canonical_json.encode(
                "utf-8"
            )
        )
        .hexdigest()
    )


# ==========================================================
# WHY DOES THIS CANDIDATE NEED SCORING?
# ==========================================================

def get_scoring_reason(
    candidate: dict[
        str,
        Any,
    ],
    networking_preferences: dict[
        str,
        Any,
    ],
) -> str | None:

    if not candidate_is_enriched(
        candidate
    ):

        return None


    # ======================================================
    # MANUAL FORCE
    # ======================================================

    if AI_RERANK_EXISTING:

        return (
            "forced_rerank"
        )


    scoring_status = (

        candidate.get(
            "ai_scoring_status"
        )

        or

        ""
    ).lower()


    # ======================================================
    # NEVER SCORED / PREVIOUS FAILURE
    # ======================================================

    if scoring_status != "success":

        if scoring_status == "failed":

            return (
                "retry_failed_score"
            )


        return (
            "never_scored"
        )


    # ======================================================
    # OLD SCORE + NEW PROFILE/DISCOVERY EVIDENCE
    #
    # This fixes the exact problem we just encountered:
    #
    # profile was enriched successfully,
    # but the candidate already had an older AI score.
    # ======================================================

    if (
        candidate_has_newer_evidence_than_score(
            candidate
        )
    ):

        return (
            "newer_profile_or_discovery_evidence"
        )


    # ======================================================
    # V3 HASH CHECK
    # ======================================================

    existing_hash = (
        candidate.get(
            "ai_scoring_input_hash"
        )
    )


    if existing_hash:

        current_hash = (
            build_scoring_input_hash(
                candidate,
                networking_preferences,
            )
        )


        if (
            current_hash
            !=
            existing_hash
        ):

            return (
                "scoring_input_changed"
            )


    return None


def candidate_needs_scoring(
    candidate: dict[
        str,
        Any,
    ],
    networking_preferences: dict[
        str,
        Any,
    ],
) -> bool:

    return (

        get_scoring_reason(
            candidate,
            networking_preferences,
        )

        is not None
    )


# ==========================================================
# LEGACY SCORE HASH MIGRATION
#
# Existing v2 candidates do not have an input fingerprint.
#
# We do NOT re-rank every old candidate just because v3 was
# installed.
#
# Stable old candidates get a baseline hash for free.
#
# Candidates whose enrichment/discovery evidence is newer
# than their AI score do NOT get bootstrapped. They remain
# pending and are re-ranked.
# ==========================================================

def bootstrap_existing_score_hashes(
    candidates: list[
        dict[
            str,
            Any,
        ]
    ],
    networking_preferences: dict[
        str,
        Any,
    ],
) -> int:

    initialized = 0


    for candidate in candidates:

        if not candidate_is_enriched(
            candidate
        ):

            continue


        scoring_status = (

            candidate.get(
                "ai_scoring_status"
            )

            or

            ""
        ).lower()


        if scoring_status != "success":

            continue


        if candidate.get(
            "ai_scoring_input_hash"
        ):

            continue


        # Do not bless stale scores with a fresh hash.
        if (
            candidate_has_newer_evidence_than_score(
                candidate
            )
        ):

            continue


        candidate[
            "ai_scoring_input_hash"
        ] = (
            build_scoring_input_hash(
                candidate,
                networking_preferences,
            )
        )


        candidate[
            "ai_scoring_hash_initialized_at"
        ] = (
            utc_now()
        )


        initialized += 1


    return initialized


# ==========================================================
# PENDING CANDIDATES
# ==========================================================

def get_pending_candidate_indexes(
    candidates: list[
        dict[
            str,
            Any,
        ]
    ],
    networking_preferences: dict[
        str,
        Any,
    ],
) -> list[int]:

    indexes = [

        index

        for index, candidate
        in enumerate(
            candidates
        )

        if candidate_needs_scoring(
            candidate,
            networking_preferences,
        )
    ]


    if AI_RANKING_LIMIT > 0:

        indexes = (
            indexes[
                :AI_RANKING_LIMIT
            ]
        )


    return indexes


# ==========================================================
# SAVE AI RESULT
# ==========================================================

def save_assessment_to_candidate(
    candidate: dict[
        str,
        Any,
    ],
    assessment: dict[
        str,
        Any,
    ],
    source_statistics: dict[
        str,
        Any,
    ],
    scoring_input_hash: str,
) -> None:

    candidate[
        "ai_assessment"
    ] = assessment


    candidate[
        "ai_scoring_status"
    ] = (
        "success"
    )


    candidate[
        "ai_scoring_version"
    ] = (
        AI_SCORING_VERSION
    )


    candidate[
        "ai_scored_at"
    ] = (
        utc_now()
    )


    candidate[
        "ai_model"
    ] = (
        OPENAI_MODEL
    )


    candidate[
        "network_signal_summary"
    ] = (
        source_statistics
    )


    candidate[
        "ai_scoring_input_hash"
    ] = (
        scoring_input_hash
    )


    candidate[
        "ai_scoring_input_hashed_at"
    ] = (
        utc_now()
    )


    candidate.pop(
        "ai_scoring_error",
        None,
    )


    candidate.pop(
        "ai_scoring_last_attempt_at",
        None,
    )


def save_scoring_failure(
    candidate: dict[
        str,
        Any,
    ],
    error: Exception,
) -> None:

    candidate[
        "ai_scoring_status"
    ] = (
        "failed"
    )


    candidate[
        "ai_scoring_version"
    ] = (
        AI_SCORING_VERSION
    )


    candidate[
        "ai_scoring_last_attempt_at"
    ] = (
        utc_now()
    )


    candidate[
        "ai_scoring_error"
    ] = (
        str(
            error
        )
    )


# ==========================================================
# RANKED OUTPUT
# ==========================================================

def build_ranked_candidates_snapshot(
    candidates: list[
        dict[
            str,
            Any,
        ]
    ],
) -> list[
    dict[
        str,
        Any,
    ]
]:

    scored: list[
        dict[
            str,
            Any,
        ]
    ] = []


    for candidate in candidates:

        if (
            candidate.get(
                "ai_scoring_status"
            )
            !=
            "success"
        ):

            continue


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

            continue


        scored.append(
            candidate
        )


    scored.sort(

        key=lambda candidate: (

            candidate

            .get(
                "ai_assessment",
                {},
            )

            .get(
                "total_score",
                0,
            )
        ),

        reverse=True,
    )


    return scored


def save_all_files(
    candidates: list[
        dict[
            str,
            Any,
        ]
    ],
) -> None:

    save_json(
        CANDIDATES_FILE,
        candidates,
    )


    ranked = (
        build_ranked_candidates_snapshot(
            candidates
        )
    )


    save_json(
        RANKED_CANDIDATES_FILE,
        ranked,
    )


# ==========================================================
# SCORE ONE CANDIDATE
# ==========================================================

def score_candidate(
    candidate: dict[
        str,
        Any,
    ],
    networking_preferences: dict[
        str,
        Any,
    ],
    position: int,
    total: int,
) -> None:

    print(
        "\n================================"
    )


    print(
        f"AI RANKING {position}/{total}"
    )


    print(
        "================================"
    )


    print(
        "Candidate:",
        candidate.get(
            "name"
        ),
    )


    print(
        "Profile:",
        candidate.get(
            "profile_url"
        ),
    )


    payload = (
        build_candidate_payload(
            candidate
        )
    )


    source_statistics = (

        payload.get(
            "source_statistics"
        )

        or

        {}
    )


    print(
        "Discovery method:",
        candidate.get(
            "discovery_method"
        )
        or
        candidate.get(
            "source"
        ),
    )


    print(
        "Discovery sources:",
        source_statistics.get(
            "number_of_discovery_sources"
        ),
    )


    print(
        "Distinct source connections:",
        source_statistics.get(
            "number_of_distinct_source_connections"
        ),
    )


    print(
        "Distinct source posts:",
        source_statistics.get(
            "number_of_distinct_source_posts"
        ),
    )


    print(
        "Scoring reason:",
        get_scoring_reason(
            candidate,
            networking_preferences,
        ),
    )


    print(
        "Model:",
        OPENAI_MODEL,
    )


    scoring_input_hash = (
        build_scoring_input_hash(
            candidate,
            networking_preferences,
        )
    )


    raw_assessment = (
        score_with_openai(
            payload,
            networking_preferences,
        )
    )


    assessment = (
        normalize_ai_assessment(
            raw_assessment
        )
    )


    save_assessment_to_candidate(
        candidate,
        assessment,
        source_statistics,
        scoring_input_hash,
    )


    print(
        "\nAI RESULT"
    )


    print(
        "Professional relevance:",
        (
            f"{assessment.get('professional_relevance')}"
            "/30"
        ),
    )


    print(
        "Strategic network value:",
        (
            f"{assessment.get('strategic_network_value')}"
            "/25"
        ),
    )


    print(
        "Shared interest signal:",
        (
            f"{assessment.get('shared_interest_signal')}"
            "/20"
        ),
    )


    print(
        "Interaction signal:",
        (
            f"{assessment.get('interaction_signal')}"
            "/15"
        ),
    )


    print(
        "Evidence quality:",
        (
            f"{assessment.get('evidence_quality')}"
            "/10"
        ),
    )


    print(
        "TOTAL:",
        (
            f"{assessment.get('total_score')}"
            "/100"
        ),
    )


    print(
        "Recommendation:",
        assessment.get(
            "recommendation"
        ),
    )


    print(
        "Confidence:",
        assessment.get(
            "confidence"
        ),
    )


    print(
        "Why relevant:",
        assessment.get(
            "why_relevant"
        ),
    )


# ==========================================================
# MAIN
# ==========================================================

def run() -> None:

    print(
        "\n================================"
    )


    print(
        "NETWORK SCOUT AI RANKER"
    )


    print(
        "================================"
    )


    print(
        "Model:",
        OPENAI_MODEL,
    )


    candidates = (
        load_candidates()
    )


    networking_preferences = (
        load_preferences()
    )


    print(
        "Total candidates:",
        len(
            candidates
        ),
    )


    enriched_count = sum(

        1

        for candidate
        in candidates

        if candidate_is_enriched(
            candidate
        )
    )


    print(
        "Enriched / scoreable:",
        enriched_count,
    )


    # ======================================================
    # MIGRATE OLD STABLE SCORES TO HASH SYSTEM
    # ======================================================

    initialized_hashes = (
        bootstrap_existing_score_hashes(
            candidates,
            networking_preferences,
        )
    )


    print(
        "Legacy score fingerprints initialized:",
        initialized_hashes,
    )


    # ======================================================
    # FIND TRUE PENDING CANDIDATES
    # ======================================================

    pending_indexes = (
        get_pending_candidate_indexes(
            candidates,
            networking_preferences,
        )
    )


    print(
        "Candidates needing AI scoring:",
        len(
            pending_indexes
        ),
    )


    print(
        "Re-rank existing scores:",
        (
            "YES"
            if AI_RERANK_EXISTING
            else
            "NO"
        ),
    )


    # ======================================================
    # EXPLAIN WHY THEY ARE BEING SCORED
    # ======================================================

    if pending_indexes:

        reason_counts: dict[
            str,
            int,
        ] = {}


        for candidate_index in pending_indexes:

            reason = (

                get_scoring_reason(
                    candidates[
                        candidate_index
                    ],
                    networking_preferences,
                )

                or

                "unknown"
            )


            reason_counts[
                reason
            ] = (

                reason_counts.get(
                    reason,
                    0,
                )

                +

                1
            )


        print(
            "Pending reasons:",
            reason_counts,
        )


    # ======================================================
    # RUN LIMIT
    # ======================================================

    if AI_RANKING_LIMIT > 0:

        print(
            "Run limit:",
            AI_RANKING_LIMIT,
        )


    else:

        print(
            "Run limit: ALL pending candidates"
        )


    # Save hashes we created for stable legacy scores before
    # making any OpenAI calls.
    if initialized_hashes:

        save_all_files(
            candidates
        )


    # ======================================================
    # NOTHING TO SCORE
    # ======================================================

    if not pending_indexes:

        print(
            "\nNothing needs AI scoring."
        )


        save_all_files(
            candidates
        )


        return


    successful = 0

    failed = 0

    total_pending = (
        len(
            pending_indexes
        )
    )


    # ======================================================
    # SCORE PENDING CANDIDATES
    # ======================================================

    for position, candidate_index in enumerate(

        pending_indexes,

        start=1,
    ):

        candidate = (
            candidates[
                candidate_index
            ]
        )


        try:

            score_candidate(
                candidate,
                networking_preferences,
                position,
                total_pending,
            )


            successful += 1


        except Exception as error:

            failed += 1


            save_scoring_failure(
                candidate,
                error,
            )


            print(
                "\nAI RANKING FAILED"
            )


            print(
                "Candidate:",
                candidate.get(
                    "name"
                ),
            )


            print(
                "Error:",
                error,
            )


        # ==================================================
        # SAVE AFTER EVERY CANDIDATE
        #
        # If a later API request fails, successful earlier
        # candidate scores are already safely stored.
        # ==================================================

        save_all_files(
            candidates
        )


    # ======================================================
    # FINAL SUMMARY
    # ======================================================

    ranked_snapshot = (
        build_ranked_candidates_snapshot(
            candidates
        )
    )


    recommended = sum(

        1

        for candidate
        in ranked_snapshot

        if (

            candidate

            .get(
                "ai_assessment",
                {},
            )

            .get(
                "recommendation"
            )

            ==

            "recommend"
        )
    )


    maybe = sum(

        1

        for candidate
        in ranked_snapshot

        if (

            candidate

            .get(
                "ai_assessment",
                {},
            )

            .get(
                "recommendation"
            )

            ==

            "maybe"
        )
    )


    not_relevant = sum(

        1

        for candidate
        in ranked_snapshot

        if (

            candidate

            .get(
                "ai_assessment",
                {},
            )

            .get(
                "recommendation"
            )

            ==

            "not_relevant"
        )
    )


    print(
        "\n================================"
    )


    print(
        "AI RANKING COMPLETE"
    )


    print(
        "================================"
    )


    print(
        "Attempted this run:",
        total_pending,
    )


    print(
        "Successful:",
        successful,
    )


    print(
        "Failed:",
        failed,
    )


    print(
        "Total successfully scored:",
        len(
            ranked_snapshot
        ),
    )


    print(
        "Recommend:",
        recommended,
    )


    print(
        "Maybe:",
        maybe,
    )


    print(
        "Not relevant:",
        not_relevant,
    )


    print(
        "\nUpdated candidate data:"
    )


    print(
        CANDIDATES_FILE
    )


    print(
        "\nSorted ranking snapshot:"
    )


    print(
        RANKED_CANDIDATES_FILE
    )


if __name__ == "__main__":

    run()