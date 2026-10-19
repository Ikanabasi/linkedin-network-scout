import json
import os
import re

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from exa_py import Exa


# ======================================================
# PROJECT PATHS
# ======================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

CANDIDATE_FILE = (
    PROJECT_ROOT
    / "data"
    / "candidates.json"
)

ENV_FILE = (
    PROJECT_ROOT
    / ".env"
)


# ======================================================
# SETTINGS
# ======================================================

# Keep first test small.
MAX_CANDIDATES_PER_RUN = 5

# Number of Exa results requested.
SEARCH_RESULTS_PER_CANDIDATE = 10

# Maximum verified sources retained.
MAX_VERIFIED_SOURCES = 5

# Keep a few rejected results for debugging.
MAX_REJECTED_SOURCES_TO_STORE = 5

# Minimum score required before evidence
# is allowed to belong to this person.
IDENTITY_SCORE_THRESHOLD = 60

# LinkedIn itself is already our identity source.
SKIP_DOMAINS = {
    "linkedin.com",
    "www.linkedin.com"
}


# ======================================================
# ENVIRONMENT
# ======================================================

load_dotenv(
    ENV_FILE
)

EXA_API_KEY = os.getenv(
    "EXA_API_KEY"
)

if not EXA_API_KEY:

    raise ValueError(
        "\nEXA_API_KEY was not found.\n"
        "\nYour project-root .env should contain:\n"
        "\nEXA_API_KEY=your_actual_key\n"
    )


# ======================================================
# EXA CLIENT
# ======================================================

exa = Exa(
    api_key=EXA_API_KEY
)


# ======================================================
# TEXT NORMALIZATION
# ======================================================

def normalize_text(value):

    if not value:
        return ""

    value = (
        str(value)
        .replace("\u200b", "")
        .replace("\xa0", " ")
        .lower()
        .strip()
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    value = re.sub(
        r"[^\w\s]",
        " ",
        value
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


# ======================================================
# DOMAIN
# ======================================================

def get_domain(url):

    if not url:
        return None

    try:

        parsed = urlparse(
            url
        )

        return (
            parsed.netloc
            .lower()
            .strip()
        )

    except Exception:

        return None


# ======================================================
# LOAD / SAVE
# ======================================================

def load_candidates():

    if not CANDIDATE_FILE.exists():

        raise FileNotFoundError(
            f"Candidate file not found:\n"
            f"{CANDIDATE_FILE}"
        )

    with CANDIDATE_FILE.open(
        "r",
        encoding="utf-8"
    ) as file:

        candidates = json.load(
            file
        )

    if not isinstance(
        candidates,
        list
    ):

        raise ValueError(
            "candidates.json must contain a list."
        )

    return candidates


def save_candidates(
    candidates
):

    CANDIDATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with CANDIDATE_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            candidates,
            file,
            indent=4,
            ensure_ascii=False
        )


# ======================================================
# CLEAN EXA HIGHLIGHTS
# ======================================================

def clean_highlights(
    highlights
):

    if not highlights:
        return []

    if isinstance(
        highlights,
        str
    ):

        highlights = [
            highlights
        ]

    cleaned = []

    for highlight in highlights:

        if not highlight:
            continue

        text = (
            str(highlight)
            .replace("\xa0", " ")
            .strip()
        )

        text = re.sub(
            r"\s+",
            " ",
            text
        )

        if (
            text
            and text not in cleaned
        ):

            cleaned.append(
                text
            )

    return cleaned


# ======================================================
# EXA RESULT → DICTIONARY
# ======================================================

def exa_result_to_dict(
    result
):

    url = getattr(
        result,
        "url",
        None
    )

    return {

        "title":
            getattr(
                result,
                "title",
                None
            ),

        "url":
            url,

        "domain":
            get_domain(
                url
            ),

        "published_date":
            getattr(
                result,
                "published_date",
                None
            ),

        "author":
            getattr(
                result,
                "author",
                None
            ),

        "highlights":
            clean_highlights(
                getattr(
                    result,
                    "highlights",
                    None
                )
            )
    }


# ======================================================
# CAN THIS CANDIDATE BE RESEARCHED?
# ======================================================

def candidate_is_ready(
    candidate
):

    identity_status = (
        candidate.get(
            "identity_status"
        )
        or ""
    ).lower()

    identity = (
        candidate.get(
            "linkedin_identity"
        )
        or {}
    )

    name = (
        identity.get(
            "name"
        )
        or ""
    ).strip()

    if (
        identity_status
        not in {
            "success",
            "partial"
        }
    ):

        return False

    if not name:

        return False

    # ----------------------------------------------
    # Don't repeat new verified research.
    # ----------------------------------------------

    verification_version = (
        candidate.get(
            "research_verification_version"
        )
    )

    if (
        verification_version
        == 1
    ):

        return False

    return True


# ======================================================
# MEANINGFUL HEADLINE KEYWORDS
# ======================================================

STOP_WORDS = {
    "and",
    "the",
    "with",
    "for",
    "from",
    "into",
    "this",
    "that",
    "your",
    "their",
    "our",
    "are",
    "was",
    "were",
    "been",
    "being",
    "at",
    "in",
    "on",
    "of",
    "to",
    "by",
    "a",
    "an",
    "is",
    "as",
    "or",
    "it",
    "i",
    "we",
    "you",
    "building",
    "professional",
    "profile"
}


def get_headline_keywords(
    headline
):

    if not headline:
        return []

    text = normalize_text(
        headline
    )

    words = text.split()

    keywords = []

    for word in words:

        if len(word) < 4:
            continue

        if word in STOP_WORDS:
            continue

        if word.isdigit():
            continue

        if word not in keywords:

            keywords.append(
                word
            )

    return keywords[:12]


# ======================================================
# BUILD SEARCH QUERY FROM LINKEDIN IDENTITY
# ======================================================

def build_candidate_query(
    candidate
):

    identity = (
        candidate.get(
            "linkedin_identity"
        )
        or {}
    )

    name = (
        identity.get(
            "name"
        )
        or candidate.get(
            "name"
        )
        or ""
    ).strip()

    company = (
        identity.get(
            "current_company"
        )
        or ""
    ).strip()

    location = (
        identity.get(
            "location"
        )
        or ""
    ).strip()

    headline = (
        identity.get(
            "headline"
        )
        or candidate.get(
            "headline"
        )
        or ""
    ).strip()

    parts = []

    # Exact person name
    if name:

        parts.append(
            f'"{name}"'
        )

    # Company is one of our strongest
    # identity disambiguators.
    if company:

        parts.append(
            f'"{company}"'
        )

    # Location helps distinguish common names.
    if location:

        parts.append(
            f'"{location}"'
        )

    # Add the professional context.
    if headline:

        parts.append(
            headline
        )

    parts.append(
        "professional biography career "
        "company role projects expertise"
    )

    return " ".join(
        parts
    )


# ======================================================
# BUILD RESULT TEXT FOR MATCHING
# ======================================================

def build_result_text(
    source
):

    pieces = []

    title = source.get(
        "title"
    )

    author = source.get(
        "author"
    )

    domain = source.get(
        "domain"
    )

    highlights = (
        source.get(
            "highlights"
        )
        or []
    )

    if title:

        pieces.append(
            title
        )

    if author:

        pieces.append(
            author
        )

    if domain:

        pieces.append(
            domain
        )

    pieces.extend(
        highlights
    )

    return normalize_text(
        " ".join(
            pieces
        )
    )


# ======================================================
# NAME MATCH
# ======================================================

def score_name_match(
    name,
    result_text
):

    normalized_name = normalize_text(
        name
    )

    if (
        not normalized_name
        or not result_text
    ):

        return (
            0,
            False,
            "name_missing"
        )

    # Exact full-name phrase.
    if (
        normalized_name
        in result_text
    ):

        return (
            35,
            True,
            "exact_name"
        )

    name_tokens = [
        token
        for token
        in normalized_name.split()
        if len(token) >= 2
    ]

    if not name_tokens:

        return (
            0,
            False,
            "name_missing"
        )

    matched = [
        token
        for token
        in name_tokens
        if token in result_text
    ]

    ratio = (
        len(matched)
        /
        len(name_tokens)
    )

    if ratio == 1:

        return (
            25,
            True,
            "all_name_tokens"
        )

    if ratio >= 0.75:

        return (
            15,
            True,
            "partial_name"
        )

    return (
        0,
        False,
        "name_mismatch"
    )


# ======================================================
# COMPANY MATCH
# ======================================================

def score_company_match(
    company,
    result_text
):

    normalized_company = normalize_text(
        company
    )

    if not normalized_company:

        return (
            0,
            False,
            "company_unavailable"
        )

    if (
        normalized_company
        in result_text
    ):

        return (
            30,
            True,
            "exact_company"
        )

    tokens = [
        token
        for token
        in normalized_company.split()
        if (
            len(token) >= 4
            and token not in {
                "inc",
                "ltd",
                "limited",
                "company",
                "corp",
                "corporation"
            }
        )
    ]

    if not tokens:

        return (
            0,
            False,
            "company_unavailable"
        )

    matches = [
        token
        for token
        in tokens
        if token in result_text
    ]

    ratio = (
        len(matches)
        /
        len(tokens)
    )

    if ratio >= 0.75:

        return (
            20,
            True,
            "company_token_match"
        )

    return (
        0,
        False,
        "company_mismatch"
    )


# ======================================================
# LOCATION MATCH
# ======================================================

def score_location_match(
    location,
    result_text
):

    normalized_location = normalize_text(
        location
    )

    if not normalized_location:

        return (
            0,
            False,
            "location_unavailable"
        )

    if (
        normalized_location
        in result_text
    ):

        return (
            20,
            True,
            "exact_location"
        )

    location_parts = [
        normalize_text(
            part
        )
        for part
        in str(location).split(",")
    ]

    location_parts = [
        part
        for part
        in location_parts
        if len(part) >= 4
    ]

    for part in location_parts:

        if part in result_text:

            return (
                15,
                True,
                f"location_part:{part}"
            )

    return (
        0,
        False,
        "location_mismatch"
    )


# ======================================================
# PROFESSIONAL CONTEXT MATCH
# ======================================================

def score_context_match(
    headline,
    result_text
):

    keywords = (
        get_headline_keywords(
            headline
        )
    )

    if not keywords:

        return (
            0,
            0,
            []
        )

    matched = []

    for keyword in keywords:

        if keyword in result_text:

            matched.append(
                keyword
            )

    # Three points per matched meaningful
    # professional keyword, maximum 15.
    score = min(
        len(matched) * 3,
        15
    )

    return (
        score,
        len(matched),
        matched
    )


# ======================================================
# VERIFY ONE EXA RESULT
# ======================================================

def verify_source_identity(
    candidate,
    source
):

    identity = (
        candidate.get(
            "linkedin_identity"
        )
        or {}
    )

    name = (
        identity.get(
            "name"
        )
        or candidate.get(
            "name"
        )
    )

    company = (
        identity.get(
            "current_company"
        )
    )

    location = (
        identity.get(
            "location"
        )
    )

    headline = (
        identity.get(
            "headline"
        )
        or candidate.get(
            "headline"
        )
    )

    result_text = (
        build_result_text(
            source
        )
    )

    (
        name_score,
        name_match,
        name_reason
    ) = score_name_match(
        name,
        result_text
    )

    (
        company_score,
        company_match,
        company_reason
    ) = score_company_match(
        company,
        result_text
    )

    (
        location_score,
        location_match,
        location_reason
    ) = score_location_match(
        location,
        result_text
    )

    (
        context_score,
        context_matches,
        matched_keywords
    ) = score_context_match(
        headline,
        result_text
    )

    total_score = (
        name_score
        +
        company_score
        +
        location_score
        +
        context_score
    )

    # ==================================================
    # HARD IDENTITY GATE
    #
    # A result may not pass simply because it shares
    # generic career words.
    #
    # It MUST match the person's name.
    # Then it needs at least one meaningful secondary
    # identity signal.
    # ==================================================

    secondary_signal = (
        company_match
        or location_match
        or context_matches >= 2
    )

    passed = (
        name_match
        and secondary_signal
        and total_score
        >= IDENTITY_SCORE_THRESHOLD
    )

    verification = {

        "score":
            total_score,

        "threshold":
            IDENTITY_SCORE_THRESHOLD,

        "verified":
            passed,

        "name_match":
            name_match,

        "name_reason":
            name_reason,

        "company_match":
            company_match,

        "company_reason":
            company_reason,

        "location_match":
            location_match,

        "location_reason":
            location_reason,

        "professional_keyword_matches":
            matched_keywords
    }

    source = (
        source.copy()
    )

    source[
        "identity_verification"
    ] = verification

    return source


# ======================================================
# FILTER RAW EXA RESULTS
# ======================================================

def prepare_sources(
    response
):

    sources = []

    seen_urls = set()

    for result in response.results:

        source = (
            exa_result_to_dict(
                result
            )
        )

        url = source.get(
            "url"
        )

        domain = source.get(
            "domain"
        )

        if not url:
            continue

        if domain in SKIP_DOMAINS:
            continue

        normalized_url = (
            url.rstrip("/")
        )

        if normalized_url in seen_urls:
            continue

        seen_urls.add(
            normalized_url
        )

        sources.append(
            source
        )

    return sources


# ======================================================
# RESEARCH ONE CANDIDATE
# ======================================================

def research_candidate(
    candidate
):

    identity = (
        candidate.get(
            "linkedin_identity"
        )
        or {}
    )

    query = build_candidate_query(
        candidate
    )

    print(
        "\nIDENTITY FINGERPRINT"
    )

    print(
        "Name:",
        identity.get(
            "name"
        )
    )

    print(
        "Company:",
        identity.get(
            "current_company"
        )
    )

    print(
        "Location:",
        identity.get(
            "location"
        )
    )

    print(
        "Headline:",
        identity.get(
            "headline"
        )
    )

    print(
        "\nEXA QUERY:"
    )

    print(
        query
    )

    # ==================================================
    # SEARCH
    # ==================================================

    response = exa.search(
        query,
        type="auto",
        num_results=(
            SEARCH_RESULTS_PER_CANDIDATE
        ),
        contents={
            "highlights": True
        }
    )

    raw_sources = (
        prepare_sources(
            response
        )
    )

    verified_sources = []

    rejected_sources = []

    # ==================================================
    # IDENTITY RESOLUTION
    # ==================================================

    for source in raw_sources:

        verified_source = (
            verify_source_identity(
                candidate,
                source
            )
        )

        verification = (
            verified_source.get(
                "identity_verification"
            )
            or {}
        )

        if verification.get(
            "verified"
        ):

            verified_sources.append(
                verified_source
            )

        else:

            rejected_sources.append(
                verified_source
            )

    # Highest confidence first.
    verified_sources.sort(
        key=lambda source:
            (
                source.get(
                    "identity_verification",
                    {}
                ).get(
                    "score",
                    0
                )
            ),
        reverse=True
    )

    rejected_sources.sort(
        key=lambda source:
            (
                source.get(
                    "identity_verification",
                    {}
                ).get(
                    "score",
                    0
                )
            ),
        reverse=True
    )

    verified_sources = (
        verified_sources[
            :MAX_VERIFIED_SOURCES
        ]
    )

    rejected_sources = (
        rejected_sources[
            :MAX_REJECTED_SOURCES_TO_STORE
        ]
    )

    return {

        "query":
            query,

        "researched_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "identity_source":
            "linkedin_profile_fingerprint",

        "linkedin_identity":
            {
                "name":
                    identity.get(
                        "name"
                    ),

                "headline":
                    identity.get(
                        "headline"
                    ),

                "location":
                    identity.get(
                        "location"
                    ),

                "current_company":
                    identity.get(
                        "current_company"
                    )
            },

        "raw_result_count":
            len(
                raw_sources
            ),

        "verified_source_count":
            len(
                verified_sources
            ),

        "verified_sources":
            verified_sources,

        "rejected_sources":
            rejected_sources
    }


# ======================================================
# PRINT RESULT
# ======================================================

def print_research(
    candidate,
    research
):

    print(
        "\n--------------------------------"
    )

    print(
        "IDENTITY-VERIFIED WEB RESEARCH"
    )

    print(
        "--------------------------------"
    )

    print(
        "Candidate:",
        candidate.get(
            "name"
        )
    )

    print(
        "Raw Exa results:",
        research.get(
            "raw_result_count"
        )
    )

    print(
        "Verified sources:",
        research.get(
            "verified_source_count"
        )
    )

    verified_sources = (
        research.get(
            "verified_sources"
        )
        or []
    )

    # ==================================================
    # VERIFIED
    # ==================================================

    for number, source in enumerate(
        verified_sources,
        start=1
    ):

        verification = (
            source.get(
                "identity_verification"
            )
            or {}
        )

        print(
            f"\nVERIFIED SOURCE {number}"
        )

        print(
            "Score:",
            verification.get(
                "score"
            )
        )

        print(
            "Title:",
            source.get(
                "title"
            )
        )

        print(
            "Domain:",
            source.get(
                "domain"
            )
        )

        print(
            "URL:",
            source.get(
                "url"
            )
        )

        print(
            "Company match:",
            verification.get(
                "company_match"
            )
        )

        print(
            "Location match:",
            verification.get(
                "location_match"
            )
        )

        print(
            "Professional keywords:",
            verification.get(
                "professional_keyword_matches"
            )
        )

        highlights = (
            source.get(
                "highlights"
            )
            or []
        )

        for highlight in highlights[
            :3
        ]:

            print(
                "Evidence:",
                highlight[:500]
            )

    # ==================================================
    # BEST REJECTED RESULTS
    # ==================================================

    rejected_sources = (
        research.get(
            "rejected_sources"
        )
        or []
    )

    if rejected_sources:

        print(
            "\nTop rejected results:"
        )

    for number, source in enumerate(
        rejected_sources[
            :3
        ],
        start=1
    ):

        verification = (
            source.get(
                "identity_verification"
            )
            or {}
        )

        print(
            f"\nREJECTED {number}"
        )

        print(
            "Score:",
            verification.get(
                "score"
            )
        )

        print(
            "Title:",
            source.get(
                "title"
            )
        )

        print(
            "Name match:",
            verification.get(
                "name_match"
            )
        )

        print(
            "Company match:",
            verification.get(
                "company_match"
            )
        )

        print(
            "Location match:",
            verification.get(
                "location_match"
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
        "VERIFIED EXA ENRICHMENT"
    )

    print(
        "================================"
    )

    candidates = (
        load_candidates()
    )

    print(
        "\nCandidates in file:",
        len(
            candidates
        )
    )

    # ==================================================
    # FIND ELIGIBLE CANDIDATES
    # ==================================================

    candidate_indexes = []

    skipped_identity = 0

    for index, candidate in enumerate(
        candidates
    ):

        identity_status = (
            candidate.get(
                "identity_status"
            )
            or ""
        ).lower()

        if identity_status not in {
            "success",
            "partial"
        }:

            skipped_identity += 1
            continue

        if candidate_is_ready(
            candidate
        ):

            candidate_indexes.append(
                index
            )

    print(
        "Candidates ready for verified research:",
        len(
            candidate_indexes
        )
    )

    print(
        "Candidates skipped because identity "
        "was not verified:",
        skipped_identity
    )

    if not candidate_indexes:

        print(
            "\nNothing needs verified Exa research."
        )

        return

    candidate_indexes = (
        candidate_indexes[
            :MAX_CANDIDATES_PER_RUN
        ]
    )

    print(
        "Candidates being researched this run:",
        len(
            candidate_indexes
        )
    )

    # ==================================================
    # COUNTERS
    # ==================================================

    verified_count = 0
    no_match_count = 0
    failed_count = 0

    # ==================================================
    # RESEARCH
    # ==================================================

    for position, candidate_index in enumerate(
        candidate_indexes,
        start=1
    ):

        candidate = (
            candidates[
                candidate_index
            ]
        )

        print(
            "\n\n================================"
        )

        print(
            f"CANDIDATE {position}/"
            f"{len(candidate_indexes)}"
        )

        print(
            "================================"
        )

        print(
            "Name:",
            candidate.get(
                "name"
            )
        )

        try:

            research = (
                research_candidate(
                    candidate
                )
            )

            print_research(
                candidate,
                research
            )

            # ==================================================
            # PRESERVE OLD UNVERIFIED RESEARCH
            #
            # If you ran the earlier Exa script, do not throw
            # those records away silently. Store them once as
            # an audit/debug backup.
            # ==================================================

            old_research = (
                candidate.get(
                    "public_research"
                )
            )

            if (
                old_research
                and
                not candidate.get(
                    "unverified_public_research_backup"
                )
            ):

                candidate[
                    "unverified_public_research_backup"
                ] = old_research

            # ==================================================
            # SAVE ONLY NEW VERIFIED RESEARCH AS CURRENT
            # ==================================================

            candidate[
                "public_research"
            ] = research

            candidate[
                "research_verification_version"
            ] = 1

            verified_source_count = (
                research.get(
                    "verified_source_count",
                    0
                )
            )

            if (
                verified_source_count
                > 0
            ):

                candidate[
                    "research_status"
                ] = "verified"

                candidate[
                    "status"
                ] = "researched"

                verified_count += 1

            else:

                candidate[
                    "research_status"
                ] = "no_verified_match"

                # Keep the discovery candidate,
                # but do not pretend research succeeded.
                if (
                    candidate.get(
                        "status"
                    )
                    == "researched"
                ):

                    candidate[
                        "status"
                    ] = "new"

                no_match_count += 1

            # Save after every candidate.
            save_candidates(
                candidates
            )

            print(
                "\nCandidate research saved."
            )

        except Exception as error:

            failed_count += 1

            print(
                "\nVERIFIED EXA RESEARCH FAILED"
            )

            print(
                error
            )

            candidate[
                "research_status"
            ] = "failed"

            candidate[
                "research_error"
            ] = str(
                error
            )

            candidate[
                "research_attempted_at"
            ] = datetime.now(
                timezone.utc
            ).isoformat()

            save_candidates(
                candidates
            )

    # ==================================================
    # FINAL SAVE
    # ==================================================

    save_candidates(
        candidates
    )

    # ==================================================
    # SUMMARY
    # ==================================================

    print(
        "\n\n================================"
    )

    print(
        "VERIFIED EXA ENRICHMENT COMPLETE"
    )

    print(
        "================================"
    )

    print(
        "Candidates with verified evidence:",
        verified_count
    )

    print(
        "Candidates with no verified web match:",
        no_match_count
    )

    print(
        "Research failures:",
        failed_count
    )

    print(
        "\nCandidate file:"
    )

    print(
        CANDIDATE_FILE
    )


if __name__ == "__main__":

    run()