import json
import os
import time

from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


# ======================================================
# PROJECT PATHS
# ======================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

ENGAGEMENT_OPPORTUNITIES_FILE = (
    PROJECT_ROOT
    / "data"
    / "engagement_opportunities.json"
)

RANKED_ENGAGEMENT_FILE = (
    PROJECT_ROOT
    / "data"
    / "ranked_engagement_opportunities.json"
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


# ======================================================
# ENVIRONMENT
# ======================================================

load_dotenv(
    ENV_FILE
)


OPENAI_API_KEY = (
    os.getenv(
        "OPENAI_API_KEY"
    )
)


# First preference:
# POST_AI_MODEL
#
# Fallback:
# whatever model your candidate ranker already uses.
#
# Final fallback:
# gpt-5.5
POST_AI_MODEL = (
    os.getenv(
        "POST_AI_MODEL"
    )
    or
    os.getenv(
        "OPENAI_MODEL"
    )
    or
    "gpt-5.5"
)


# 0 means evaluate ALL pending opportunities.
#
# For testing:
#
# POST_AI_LIMIT=2
#
# Normal automation:
#
# POST_AI_LIMIT=0
POST_AI_LIMIT = int(
    os.getenv(
        "POST_AI_LIMIT",
        "0"
    )
)


# False:
# already successfully evaluated posts are skipped.
#
# True:
# evaluate them again.
POST_AI_RERANK_EXISTING = (
    os.getenv(
        "POST_AI_RERANK_EXISTING",
        "false"
    )
    .strip()
    .lower()
    in {
        "1",
        "true",
        "yes"
    }
)


# ======================================================
# VERSION
# ======================================================

POST_AI_VERSION = (
    "network_scout_post_relevance_v1"
)


# ======================================================
# THRESHOLDS
#
# These are controlled by Python, not by the AI.
# ======================================================

ENGAGE_THRESHOLD = 70

CONSIDER_THRESHOLD = 50


# ======================================================
# OPENAI
# ======================================================

if not OPENAI_API_KEY:

    raise RuntimeError(
        "\nOPENAI_API_KEY is missing.\n"
        "Add it to your .env file."
    )


client = OpenAI(
    api_key=OPENAI_API_KEY
)


# ======================================================
# TIME
# ======================================================

def utc_now():

    return (
        datetime.now(
            timezone.utc
        ).isoformat()
    )


# ======================================================
# JSON HELPERS
# ======================================================

def load_json(
    path,
    default=None
):

    if default is None:

        default = {}

    if not path.exists():

        return default

    with path.open(
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(
            file
        )


def save_json(
    path,
    data
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temporary_file = (
        path.with_suffix(
            path.suffix + ".tmp"
        )
    )

    with temporary_file.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False
        )

    temporary_file.replace(
        path
    )


# ======================================================
# TEXT
# ======================================================

def clean_text(
    value,
    max_length=None
):

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
        > max_length
    ):

        return (
            value[
                :max_length
            ]
            + "..."
        )

    return value


# ======================================================
# LOAD DATA
# ======================================================

def load_opportunities():

    data = (
        load_json(
            ENGAGEMENT_OPPORTUNITIES_FILE,
            default=[]
        )
    )

    if not isinstance(
        data,
        list
    ):

        raise ValueError(
            "engagement_opportunities.json "
            "must contain a JSON list."
        )

    return data


def load_preferences():

    preferences = (
        load_json(
            PREFERENCES_FILE,
            default={}
        )
    )

    if not isinstance(
        preferences,
        dict
    ):

        raise ValueError(
            "networking_preferences.json "
            "must contain a JSON object."
        )

    return preferences


# ======================================================
# BUILD POST PAYLOAD
# ======================================================

def build_opportunity_payload(
    opportunity
):

    return {

        "tracked_connection":

            {

                "name":
                    clean_text(
                        opportunity.get(
                            "connection_name"
                        ),
                        300
                    ),

                "profile_url":
                    clean_text(
                        opportunity.get(
                            "connection_profile_url"
                        ),
                        1000
                    ),

                "connection_source":
                    clean_text(
                        opportunity.get(
                            "connection_source"
                        ),
                        300
                    )
            },

        "new_post":

            {

                "post_url":
                    clean_text(
                        opportunity.get(
                            "post_url"
                        ),
                        1500
                    ),

                "post_urn":
                    clean_text(
                        opportunity.get(
                            "post_urn"
                        ),
                        500
                    ),

                "post_text":
                    clean_text(
                        opportunity.get(
                            "post_text"
                        ),
                        10000
                    ),

                "visible_comment_count":
                    opportunity.get(
                        "visible_comment_count"
                    ),

                "detected_at":
                    clean_text(
                        opportunity.get(
                            "detected_at"
                        ),
                        200
                    )
            }
    }


# ======================================================
# STRUCTURED OUTPUT SCHEMA
#
# AI supplies component scores.
#
# Python will calculate the actual total.
# ======================================================

AI_RESPONSE_SCHEMA = {

    "type":
        "object",

    "properties":

        {

            # How relevant is the subject matter
            # to the lawyer's stated networking goals?
            "professional_relevance":

                {
                    "type":
                        "integer",

                    "minimum":
                        0,

                    "maximum":
                        35
                },

            # Does engagement with this particular
            # connection have relationship-building
            # value?
            "relationship_value":

                {
                    "type":
                        "integer",

                    "minimum":
                        0,

                    "maximum":
                        25
                },

            # Is there a genuine opportunity for the
            # lawyer to contribute something useful?
            "contribution_opportunity":

                {
                    "type":
                        "integer",

                    "minimum":
                        0,

                    "maximum":
                        25
                },

            # Do we actually have enough information
            # to make a sensible assessment?
            "evidence_quality":

                {
                    "type":
                        "integer",

                    "minimum":
                        0,

                    "maximum":
                        15
                },

            "post_summary":

                {
                    "type":
                        "string"
                },

            "why_it_matters":

                {
                    "type":
                        "string"
                },

            "engagement_angle":

                {
                    "type":
                        "string"
                },

            "key_topics":

                {
                    "type":
                        "array",

                    "items":

                        {
                            "type":
                                "string"
                        }
                },

            "evidence":

                {
                    "type":
                        "array",

                    "items":

                        {
                            "type":
                                "string"
                        }
                },

            "concerns":

                {
                    "type":
                        "array",

                    "items":

                        {
                            "type":
                                "string"
                        }
                },

            "confidence":

                {
                    "type":
                        "string",

                    "enum":
                        [
                            "high",
                            "medium",
                            "low"
                        ]
                }
        },

    "required":

        [
            "professional_relevance",
            "relationship_value",
            "contribution_opportunity",
            "evidence_quality",
            "post_summary",
            "why_it_matters",
            "engagement_angle",
            "key_topics",
            "evidence",
            "concerns",
            "confidence"
        ],

    "additionalProperties":
        False
}


# ======================================================
# SYSTEM INSTRUCTIONS
# ======================================================

SYSTEM_INSTRUCTIONS = """
You are the engagement intelligence layer for Network Scout.

Network Scout helps a lawyer maintain meaningful
professional relationships on LinkedIn.

A tracked professional has posted something new.

Your task is NOT to write a LinkedIn comment.

Your task is to decide whether this post is worth the
lawyer reviewing for possible engagement.

The lawyer makes the final decision.

Use only:

1. the supplied networking preferences,
2. the tracked connection information,
3. the supplied LinkedIn post content.

Do not invent missing facts.

Do not infer sensitive personal characteristics.

Do not reward a post simply because it has many likes
or comments.

Do not assume every post from an important person is
worth engaging with.

Avoid recommending engagement with posts where the
lawyer would have little meaningful professional
contribution.

Evaluate the post using these categories:

PROFESSIONAL RELEVANCE — 0 to 35

How closely does the actual subject of this post align
with the lawyer's networking goals, professional
interests, sectors, expertise, or relationship goals?

RELATIONSHIP VALUE — 0 to 25

Would thoughtfully engaging with this particular
tracked professional's post plausibly help maintain or
strengthen a genuine professional relationship?

A useful existing or newly formed professional
connection can score well here, but do not assume that
every connection deserves engagement on every post.

CONTRIBUTION OPPORTUNITY — 0 to 25

Does the post create a natural opportunity for the
lawyer to add something thoughtful?

Good opportunities include:

- professional insight
- legal perspective
- business perspective
- thoughtful question
- supportive professional observation
- relevant experience or expertise

Low scores should be used when the only realistic
response would be generic praise such as:

"Great post"
"Congratulations"
"Thanks for sharing"

unless relationship context makes such engagement
genuinely meaningful.

EVIDENCE QUALITY — 0 to 15

How much useful information is present in the supplied
post and context?

If the post text is sparse, unclear, truncated, or
mostly interface noise, lower this score.

POST SUMMARY

Summarize the actual post in one or two concise
sentences.

WHY IT MATTERS

Explain why this is or is not worth the lawyer's
attention.

ENGAGEMENT ANGLE

Describe a natural angle the lawyer could potentially
take if she chooses to engage.

Do NOT draft the actual comment.

Do NOT write text pretending to be the lawyer.

KEY TOPICS

Return only topics clearly supported by the post.

EVIDENCE

List the strongest facts from the supplied post that
support the assessment.

CONCERNS

List reasons engagement may be weak, forced, risky,
generic, or unsupported.

Return an empty list if there are no meaningful
concerns.

CONFIDENCE

high:
clear post content and strong basis for evaluation

medium:
reasonable but incomplete basis

low:
post is sparse, unclear, truncated, or ambiguous

Be conservative.

The objective is quality of professional engagement,
not maximizing the number of comments the lawyer makes.
"""


# ======================================================
# OPENAI CALL
# ======================================================

def evaluate_with_openai(
    opportunity_payload,
    networking_preferences
):

    request_payload = {

        "networking_preferences":
            networking_preferences,

        "engagement_opportunity":
            opportunity_payload
    }

    response = (
        client.responses.create(

            model=POST_AI_MODEL,

            instructions=SYSTEM_INSTRUCTIONS,

            input=[
                {

                    "role":
                        "user",

                    "content":
                        json.dumps(
                            request_payload,
                            ensure_ascii=False
                        )
                }
            ],

            text={
                "format":
                    {

                        "type":
                            "json_schema",

                        "name":
                            "network_scout_post_relevance",

                        "description":
                            (
                                "Structured assessment "
                                "of whether a tracked "
                                "connection's LinkedIn "
                                "post is worth engaging "
                                "with."
                            ),

                        "schema":
                            AI_RESPONSE_SCHEMA,

                        "strict":
                            True
                    }
            },

            store=False
        )
    )

    output_text = (
        response.output_text
        or ""
    ).strip()

    if not output_text:

        raise RuntimeError(
            "OpenAI returned no assessment."
        )

    return (
        json.loads(
            output_text
        )
    )


# ======================================================
# RETRY WRAPPER
# ======================================================

def evaluate_with_retry(
    opportunity_payload,
    networking_preferences,
    max_attempts=3
):

    last_error = None

    for attempt in range(
        1,
        max_attempts + 1
    ):

        try:

            return (
                evaluate_with_openai(
                    opportunity_payload,
                    networking_preferences
                )
            )

        except Exception as error:

            last_error = (
                error
            )

            if (
                attempt
                >= max_attempts
            ):

                break

            print(
                f"OpenAI attempt "
                f"{attempt} failed."
            )

            print(
                "Retrying..."
            )

            time.sleep(
                2 * attempt
            )

    raise last_error


# ======================================================
# SCORE SAFETY
# ======================================================

def clamp_integer(
    value,
    minimum,
    maximum
):

    try:

        value = int(
            value
        )

    except Exception:

        value = (
            minimum
        )

    return max(
        minimum,
        min(
            maximum,
            value
        )
    )


# ======================================================
# NORMALIZE ASSESSMENT
# ======================================================

def normalize_assessment(
    raw
):

    professional_relevance = (
        clamp_integer(
            raw.get(
                "professional_relevance"
            ),
            0,
            35
        )
    )

    relationship_value = (
        clamp_integer(
            raw.get(
                "relationship_value"
            ),
            0,
            25
        )
    )

    contribution_opportunity = (
        clamp_integer(
            raw.get(
                "contribution_opportunity"
            ),
            0,
            25
        )
    )

    evidence_quality = (
        clamp_integer(
            raw.get(
                "evidence_quality"
            ),
            0,
            15
        )
    )

    total_score = (

        professional_relevance

        + relationship_value

        + contribution_opportunity

        + evidence_quality
    )

    # ==================================================
    # PYTHON CONTROLS FINAL RECOMMENDATION
    # ==================================================

    if (
        total_score
        >= ENGAGE_THRESHOLD
    ):

        recommendation = (
            "engage"
        )

        worth_engaging = (
            True
        )

    elif (
        total_score
        >= CONSIDER_THRESHOLD
    ):

        recommendation = (
            "consider"
        )

        worth_engaging = (
            False
        )

    else:

        recommendation = (
            "skip"
        )

        worth_engaging = (
            False
        )

    confidence = (
        raw.get(
            "confidence"
        )
        or "low"
    )

    if confidence not in {
        "high",
        "medium",
        "low"
    }:

        confidence = (
            "low"
        )

    return {

        "professional_relevance":
            professional_relevance,

        "relationship_value":
            relationship_value,

        "contribution_opportunity":
            contribution_opportunity,

        "evidence_quality":
            evidence_quality,

        "total_score":
            total_score,

        "recommendation":
            recommendation,

        "worth_engaging":
            worth_engaging,

        "confidence":
            confidence,

        "post_summary":
            clean_text(
                raw.get(
                    "post_summary"
                ),
                2500
            ),

        "why_it_matters":
            clean_text(
                raw.get(
                    "why_it_matters"
                ),
                3000
            ),

        "engagement_angle":
            clean_text(
                raw.get(
                    "engagement_angle"
                ),
                3000
            ),

        "key_topics":
            [
                clean_text(
                    topic,
                    300
                )
                for topic
                in (
                    raw.get(
                        "key_topics"
                    )
                    or []
                )
                if clean_text(
                    topic
                )
            ],

        "evidence":
            [
                clean_text(
                    item,
                    1000
                )
                for item
                in (
                    raw.get(
                        "evidence"
                    )
                    or []
                )
                if clean_text(
                    item
                )
            ],

        "concerns":
            [
                clean_text(
                    item,
                    1000
                )
                for item
                in (
                    raw.get(
                        "concerns"
                    )
                    or []
                )
                if clean_text(
                    item
                )
            ]
    }


# ======================================================
# ELIGIBILITY
# ======================================================

def opportunity_needs_evaluation(
    opportunity
):

    # Ignore completed / closed items.
    status = (
        opportunity.get(
            "status"
        )
        or "pending_review"
    )

    if status not in {
        "pending_review",
        "open"
    }:

        return False

    if POST_AI_RERANK_EXISTING:

        return True

    ai_status = (
        opportunity.get(
            "ai_relevance_status"
        )
        or "pending"
    )

    if ai_status == "success":

        return False

    return True


def get_pending_indexes(
    opportunities
):

    indexes = [
        index
        for index, opportunity
        in enumerate(
            opportunities
        )
        if opportunity_needs_evaluation(
            opportunity
        )
    ]

    if (
        POST_AI_LIMIT
        > 0
    ):

        indexes = (
            indexes[
                :POST_AI_LIMIT
            ]
        )

    return indexes


# ======================================================
# SAVE SUCCESS
# ======================================================

def save_success(
    opportunity,
    assessment
):

    opportunity[
        "ai_relevance_assessment"
    ] = assessment

    opportunity[
        "ai_relevance_status"
    ] = (
        "success"
    )

    opportunity[
        "ai_relevance_version"
    ] = (
        POST_AI_VERSION
    )

    opportunity[
        "ai_relevance_model"
    ] = (
        POST_AI_MODEL
    )

    opportunity[
        "ai_relevance_scored_at"
    ] = (
        utc_now()
    )

    opportunity.pop(
        "ai_relevance_error",
        None
    )


# ======================================================
# SAVE FAILURE
# ======================================================

def save_failure(
    opportunity,
    error
):

    opportunity[
        "ai_relevance_status"
    ] = (
        "failed"
    )

    opportunity[
        "ai_relevance_version"
    ] = (
        POST_AI_VERSION
    )

    opportunity[
        "ai_relevance_model"
    ] = (
        POST_AI_MODEL
    )

    opportunity[
        "ai_relevance_last_attempt_at"
    ] = (
        utc_now()
    )

    opportunity[
        "ai_relevance_error"
    ] = (
        str(
            error
        )
    )


# ======================================================
# SORTED SNAPSHOT
# ======================================================

def build_ranked_snapshot(
    opportunities
):

    scored = []

    for opportunity in opportunities:

        if (
            opportunity.get(
                "ai_relevance_status"
            )
            != "success"
        ):

            continue

        assessment = (
            opportunity.get(
                "ai_relevance_assessment"
            )
            or {}
        )

        if not isinstance(
            assessment,
            dict
        ):

            continue

        scored.append(
            opportunity
        )

    scored.sort(

        key=lambda opportunity: (

            opportunity
            .get(
                "ai_relevance_assessment",
                {}
            )
            .get(
                "total_score",
                0
            )

        ),

        reverse=True
    )

    return scored


# ======================================================
# SAVE BOTH FILES
# ======================================================

def save_all(
    opportunities
):

    save_json(
        ENGAGEMENT_OPPORTUNITIES_FILE,
        opportunities
    )

    ranked = (
        build_ranked_snapshot(
            opportunities
        )
    )

    save_json(
        RANKED_ENGAGEMENT_FILE,
        ranked
    )


# ======================================================
# EVALUATE ONE POST
# ======================================================

def evaluate_opportunity(
    opportunity,
    networking_preferences,
    position,
    total
):

    print(
        "\n================================"
    )

    print(
        f"POST AI {position}/{total}"
    )

    print(
        "================================"
    )

    print(
        "Connection:",
        opportunity.get(
            "connection_name"
        )
    )

    print(
        "Post:",
        opportunity.get(
            "post_url"
        )
    )

    print(
        "Model:",
        POST_AI_MODEL
    )

    post_text = (
        opportunity.get(
            "post_text"
        )
    )

    if not post_text:

        raise RuntimeError(
            "Opportunity contains no post text."
        )

    payload = (
        build_opportunity_payload(
            opportunity
        )
    )

    raw_assessment = (
        evaluate_with_retry(
            payload,
            networking_preferences
        )
    )

    assessment = (
        normalize_assessment(
            raw_assessment
        )
    )

    save_success(
        opportunity,
        assessment
    )

    print(
        "\nAI RESULT"
    )

    print(
        "Professional relevance:",
        f"{assessment.get('professional_relevance')}/35"
    )

    print(
        "Relationship value:",
        f"{assessment.get('relationship_value')}/25"
    )

    print(
        "Contribution opportunity:",
        f"{assessment.get('contribution_opportunity')}/25"
    )

    print(
        "Evidence quality:",
        f"{assessment.get('evidence_quality')}/15"
    )

    print(
        "TOTAL:",
        f"{assessment.get('total_score')}/100"
    )

    print(
        "Recommendation:",
        assessment.get(
            "recommendation"
        )
    )

    print(
        "Confidence:",
        assessment.get(
            "confidence"
        )
    )

    print(
        "Summary:",
        assessment.get(
            "post_summary"
        )
    )

    print(
        "Why it matters:",
        assessment.get(
            "why_it_matters"
        )
    )

    print(
        "Engagement angle:",
        assessment.get(
            "engagement_angle"
        )
    )


# ======================================================
# MAIN
# ======================================================

def run():

    print(
        "\n================================"
    )

    print(
        "NETWORK SCOUT"
    )

    print(
        "POST RELEVANCE AI"
    )

    print(
        "================================"
    )

    print(
        "Model:",
        POST_AI_MODEL
    )

    opportunities = (
        load_opportunities()
    )

    networking_preferences = (
        load_preferences()
    )

    print(
        "Total engagement opportunities:",
        len(
            opportunities
        )
    )

    pending_indexes = (
        get_pending_indexes(
            opportunities
        )
    )

    print(
        "Opportunities needing AI evaluation:",
        len(
            pending_indexes
        )
    )

    if POST_AI_RERANK_EXISTING:

        print(
            "Re-evaluate existing AI results: YES"
        )

    else:

        print(
            "Re-evaluate existing AI results: NO"
        )

    if (
        POST_AI_LIMIT
        > 0
    ):

        print(
            "Run limit:",
            POST_AI_LIMIT
        )

    else:

        print(
            "Run limit: ALL pending opportunities"
        )

    # ==================================================
    # NOTHING TO PROCESS
    # ==================================================

    if not pending_indexes:

        print(
            "\nNothing needs AI evaluation."
        )

        save_all(
            opportunities
        )

        return

    successful = 0

    failed = 0

    total_pending = (
        len(
            pending_indexes
        )
    )

    # ==================================================
    # PROCESS
    # ==================================================

    for position, opportunity_index in enumerate(
        pending_indexes,
        start=1
    ):

        opportunity = (
            opportunities[
                opportunity_index
            ]
        )

        try:

            evaluate_opportunity(
                opportunity,
                networking_preferences,
                position,
                total_pending
            )

            successful += 1

        except Exception as error:

            failed += 1

            save_failure(
                opportunity,
                error
            )

            print(
                "\nPOST AI FAILED"
            )

            print(
                "Connection:",
                opportunity.get(
                    "connection_name"
                )
            )

            print(
                "Error:",
                error
            )

        # Save after every post.
        save_all(
            opportunities
        )

    # ==================================================
    # SUMMARY
    # ==================================================

    ranked = (
        build_ranked_snapshot(
            opportunities
        )
    )

    engage_count = sum(

        1
        for opportunity
        in ranked
        if (
            opportunity
            .get(
                "ai_relevance_assessment",
                {}
            )
            .get(
                "recommendation"
            )
            == "engage"
        )
    )

    consider_count = sum(

        1
        for opportunity
        in ranked
        if (
            opportunity
            .get(
                "ai_relevance_assessment",
                {}
            )
            .get(
                "recommendation"
            )
            == "consider"
        )
    )

    skip_count = sum(

        1
        for opportunity
        in ranked
        if (
            opportunity
            .get(
                "ai_relevance_assessment",
                {}
            )
            .get(
                "recommendation"
            )
            == "skip"
        )
    )

    print(
        "\n================================"
    )

    print(
        "POST RELEVANCE AI COMPLETE"
    )

    print(
        "================================"
    )

    print(
        "Attempted:",
        total_pending
    )

    print(
        "Successful:",
        successful
    )

    print(
        "Failed:",
        failed
    )

    print(
        "Engage:",
        engage_count
    )

    print(
        "Consider:",
        consider_count
    )

    print(
        "Skip:",
        skip_count
    )

    print(
        "\nUpdated opportunities:"
    )

    print(
        ENGAGEMENT_OPPORTUNITIES_FILE
    )

    print(
        "\nRanked opportunities:"
    )

    print(
        RANKED_ENGAGEMENT_FILE
    )


if __name__ == "__main__":

    run()