import json
import re
import webbrowser

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st


# ======================================================
# PAGE CONFIG
# ======================================================

st.set_page_config(
    page_title="Network Scout",
    page_icon="🔎",
    layout="wide",
)


# ======================================================
# PROJECT PATHS
# ======================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CANDIDATES_FILE = PROJECT_ROOT / "data" / "candidates.json"
WEEKLY_SHORTLIST_FILE = PROJECT_ROOT / "data" / "weekly_shortlist.json"
TRACKED_CONNECTIONS_FILE = PROJECT_ROOT / "data" / "tracked_connections.json"
ENGAGEMENT_OPPORTUNITIES_FILE = (
    PROJECT_ROOT / "data" / "engagement_opportunities.json"
)


# ======================================================
# GENERAL HELPERS
# ======================================================

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_json_list(path):
    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list):
            return data

    except Exception as error:
        st.error(
            f"Could not read {path.name}: {error}"
        )

    return []


def load_json_object(path):
    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, dict):
            return data

    except Exception as error:
        st.error(
            f"Could not read {path.name}: {error}"
        )

    return {}


def save_json_list(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_file = path.with_suffix(
        path.suffix + ".tmp"
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

    temporary_file.replace(path)


def safe_text(
    value,
    fallback="Not available",
):
    if value is None:
        return fallback

    value = str(value).strip()

    if not value:
        return fallback

    return value


def summarize_about(
    value,
    max_sentences=3,
    max_characters=450,
):
    """
    Keep the full About text internally,
    but show only a short lawyer-facing summary/excerpt.
    """

    if not value:
        return "Not available"

    text = re.sub(
        r"\s+",
        " ",
        str(value).strip(),
    )

    if not text:
        return "Not available"

    sentences = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    selected_sentences = []

    for sentence in sentences:
        sentence = sentence.strip()

        if not sentence:
            continue

        if len(selected_sentences) >= max_sentences:
            break

        proposed_summary = " ".join(
            selected_sentences + [sentence]
        )

        if len(proposed_summary) > max_characters:
            break

        selected_sentences.append(
            sentence
        )

    summary = " ".join(
        selected_sentences
    ).strip()

    if not summary:
        summary = text[:max_characters]

        if len(text) > max_characters:
            summary = summary.rsplit(
                " ",
                1,
            )[0]

    if len(summary) < len(text):
        summary += "..."

    return summary


def make_widget_key(value):
    return re.sub(
        r"[^a-zA-Z0-9_]",
        "_",
        str(
            value
            or "unknown"
        ),
    )


# ======================================================
# LINKEDIN URL HELPERS
# ======================================================

def normalize_profile_url(url):
    if not url:
        return None

    match = re.search(
        r"linkedin\.com/in/([^/?#]+)",
        str(url),
        re.IGNORECASE,
    )

    if not match:
        return None

    slug = (
        match.group(1)
        .strip()
        .lower()
    )

    return (
        "https://www.linkedin.com/in/"
        + slug
        + "/"
    )


def is_safe_linkedin_url(url):
    if not url:
        return False

    try:
        parsed = urlparse(
            str(url).strip()
        )

        if parsed.scheme not in {
            "http",
            "https",
        }:
            return False

        hostname = (
            parsed.hostname
            or ""
        ).lower()

        return (
            hostname == "linkedin.com"
            or hostname.endswith(
                ".linkedin.com"
            )
        )

    except Exception:
        return False


# ======================================================
# CANDIDATE HELPERS
# ======================================================

def get_ai_assessment(candidate):
    assessment = (
        candidate.get(
            "ai_assessment"
        )
        or {}
    )

    if not isinstance(
        assessment,
        dict,
    ):
        return {}

    return assessment


def get_profile_data(candidate):
    profile = (
        candidate.get(
            "linkedin_profile_data"
        )
        or {}
    )

    if not isinstance(
        profile,
        dict,
    ):
        return {}

    return profile


def get_total_score(candidate):
    assessment = get_ai_assessment(
        candidate
    )

    try:
        return int(
            assessment.get(
                "total_score",
                0,
            )
            or 0
        )

    except Exception:
        return 0


def get_recommendation(candidate):
    assessment = get_ai_assessment(
        candidate
    )

    return (
        assessment.get(
            "recommendation"
        )
        or "unscored"
    )


# ======================================================
# CANDIDATE DECISION STATUS
# ======================================================

def get_decision_status(candidate):
    status = str(
        candidate.get(
            "decision_status"
        )
        or ""
    ).strip().lower()

    old_mapping = {
        "connect":
            "connect_selected",

        "connect_approved":
            "connect_selected",

        "connected_confirmed":
            "connect_selected",

        "follow":
            "follow_selected",

        "save":
            "saved",

        "reject":
            "not_relevant",
    }

    status = old_mapping.get(
        status,
        status,
    )

    valid_statuses = {
        "pending_review",
        "connect_selected",
        "follow_selected",
        "saved",
        "not_relevant",
    }

    if status not in valid_statuses:
        return "pending_review"

    return status


def decision_label(status):
    labels = {
        "pending_review":
            "Pending Review",

        "connect_selected":
            "Connect Chosen",

        "follow_selected":
            "Follow Chosen",

        "saved":
            "Saved",

        "not_relevant":
            "Not Relevant",
    }

    return labels.get(
        status,
        status,
    )


# ======================================================
# UPDATE CANDIDATE DECISION
# ======================================================

def update_candidate_decision(
    candidate_profile_url,
    new_status,
):
    candidates = load_json_list(
        CANDIDATES_FILE
    )

    target_url = normalize_profile_url(
        candidate_profile_url
    )

    if not target_url:
        return False

    for candidate in candidates:
        profile_url = normalize_profile_url(
            candidate.get(
                "profile_url"
            )
        )

        if profile_url != target_url:
            continue

        now = utc_now()

        candidate[
            "decision_status"
        ] = new_status

        candidate[
            "decision_updated_at"
        ] = now

        if new_status == "connect_selected":
            candidate[
                "connect_selected_at"
            ] = now

        elif new_status == "follow_selected":
            candidate[
                "follow_selected_at"
            ] = now

        elif new_status == "saved":
            candidate[
                "saved_at"
            ] = now

        elif new_status == "not_relevant":
            candidate[
                "not_relevant_at"
            ] = now

        save_json_list(
            CANDIDATES_FILE,
            candidates,
        )

        return True

    return False


# ======================================================
# ADD / UPDATE TRACKED PERSON
# ======================================================

def add_candidate_to_tracking(
    candidate,
    relationship_action,
):
    """
    The person becomes actively tracked immediately.

    relationship_action:
        "connect" -> lawyer chose Connect on LinkedIn
        "follow"  -> lawyer chose Follow on LinkedIn

    There is no later Connected Confirmed step.
    """

    if relationship_action not in {
        "connect",
        "follow",
    }:
        return (
            False,
            "Invalid relationship action.",
        )

    tracked_connections = load_json_list(
        TRACKED_CONNECTIONS_FILE
    )

    candidate_url = normalize_profile_url(
        candidate.get(
            "profile_url"
        )
    )

    if not candidate_url:
        return (
            False,
            "Candidate does not have a valid LinkedIn URL.",
        )

    profile = get_profile_data(
        candidate
    )

    name = (
        profile.get(
            "name"
        )
        or candidate.get(
            "name"
        )
        or "Unknown"
    )

    timestamp = utc_now()

    # If the person is already tracked,
    # update the relationship action instead
    # of creating a duplicate.

    for tracked in tracked_connections:
        tracked_url = normalize_profile_url(
            tracked.get(
                "profile_url"
            )
        )

        if tracked_url != candidate_url:
            continue

        tracked[
            "name"
        ] = (
            tracked.get(
                "name"
            )
            or name
        )

        tracked[
            "tracking_status"
        ] = "active"

        tracked[
            "monitor_posts"
        ] = True

        tracked[
            "discover_from_comments"
        ] = True

        tracked[
            "relationship_action"
        ] = relationship_action

        tracked[
            "relationship_action_at"
        ] = timestamp

        tracked[
            "relationship_source"
        ] = "network_scout_weekly_pick"

        save_json_list(
            TRACKED_CONNECTIONS_FILE,
            tracked_connections,
        )

        return (
            True,
            "Tracking updated.",
        )

    # New tracked record

    new_record = {
        "name":
            name,

        "profile_url":
            candidate_url,

        "source":
            "network_scout_weekly_pick",

        "tracking_status":
            "active",

        "relationship_action":
            relationship_action,

        "relationship_action_at":
            timestamp,

        "relationship_source":
            "network_scout_weekly_pick",

        "monitor_posts":
            True,

        "discover_from_comments":
            True,

        "added_at":
            timestamp,

        "last_checked_at":
            None,

        "last_post_status":
            None,

        "last_seen_post_key":
            None,

        "last_seen_post_key_version":
            None,

        "last_seen_post_url":
            None,

        "last_seen_post_urn":
            None,

        "last_seen_post_text":
            None,

        "last_seen_post_comment_count":
            None,

        "last_discovery_status":
            None,

        "last_discovery_post_key":
            None,

        "last_discovery_post_url":
            None,

        "last_discovery_post_urn":
            None,

        "last_discovery_post_position":
            None,

        "last_discovery_post_comment_count":
            None,
    }

    tracked_connections.append(
        new_record
    )

    save_json_list(
        TRACKED_CONNECTIONS_FILE,
        tracked_connections,
    )

    return (
        True,
        "Added to tracked network.",
    )


# ======================================================
# CONNECT / FOLLOW ON LINKEDIN
# ======================================================

def start_linkedin_relationship_action(
    candidate,
    relationship_action,
):
    """
    One dashboard click:

    1. Add/update person in tracked_connections.json.
    2. Mark candidate decision as Connect Chosen
       or Follow Chosen.
    3. Open the exact LinkedIn profile.
    4. Lawyer uses LinkedIn's native Connect or Follow button.

    Network Scout does NOT click the native LinkedIn
    relationship button itself.
    """

    profile_url = normalize_profile_url(
        candidate.get(
            "profile_url"
        )
    )

    if not profile_url:
        return (
            False,
            "This candidate does not have a valid LinkedIn profile URL.",
        )

    if not is_safe_linkedin_url(
        profile_url
    ):
        return (
            False,
            "The stored profile URL is not a valid LinkedIn URL.",
        )

    success, message = (
        add_candidate_to_tracking(
            candidate,
            relationship_action,
        )
    )

    if not success:
        return (
            False,
            message,
        )

    decision_status = (
        "connect_selected"
        if relationship_action == "connect"
        else "follow_selected"
    )

    decision_saved = (
        update_candidate_decision(
            profile_url,
            decision_status,
        )
    )

    if not decision_saved:
        return (
            False,
            (
                "The person was added to tracking, "
                "but the candidate decision could not be updated."
            ),
        )

    try:
        webbrowser.open(
            profile_url,
            new=2,
        )

    except Exception as error:
        return (
            True,
            (
                "The person was added to tracking, "
                "but the LinkedIn profile could not be opened automatically: "
                f"{error}"
            ),
        )

    action_label = (
        "Connect"
        if relationship_action == "connect"
        else "Follow"
    )

    return (
        True,
        (
            f"Added to tracked network and opened LinkedIn. "
            f"Use LinkedIn's {action_label} button there."
        ),
    )


# ======================================================
# CANDIDATE SOURCES
# ======================================================

def get_sources(candidate):
    sources = (
        candidate.get(
            "sources"
        )
        or []
    )

    if (
        isinstance(
            sources,
            list,
        )
        and sources
    ):
        return sources

    if (
        candidate.get(
            "source_connection"
        )
        or candidate.get(
            "source_post_url"
        )
    ):
        return [
            {
                "source_connection":
                    candidate.get(
                        "source_connection"
                    ),

                "source_post_url":
                    candidate.get(
                        "source_post_url"
                    ),

                "visible_comment_count":
                    candidate.get(
                        "visible_comment_count"
                    ),
            }
        ]

    return []


# ======================================================
# CANDIDATE SEARCH
# ======================================================

def candidate_matches_search(
    candidate,
    search_term,
):
    if not search_term:
        return True

    profile = get_profile_data(
        candidate
    )

    values = [
        candidate.get(
            "name"
        ),

        candidate.get(
            "headline"
        ),

        profile.get(
            "headline"
        ),

        profile.get(
            "current_role"
        ),

        profile.get(
            "current_company"
        ),

        profile.get(
            "location"
        ),
    ]

    combined = " ".join(
        str(value)
        for value in values
        if value
    ).lower()

    return (
        search_term.lower()
        in combined
    )


# ======================================================
# WEEKLY SHORTLIST HELPERS
# ======================================================

def get_weekly_shortlist_candidates(
    all_candidates,
    weekly_shortlist,
):
    shortlist_records = (
        weekly_shortlist.get(
            "candidates"
        )
        or []
    )

    if not isinstance(
        shortlist_records,
        list,
    ):
        return []

    candidate_lookup = {}

    for candidate in all_candidates:
        profile_url = normalize_profile_url(
            candidate.get(
                "profile_url"
            )
        )

        if profile_url:
            candidate_lookup[
                profile_url
            ] = candidate

    resolved = []

    for shortlist_record in shortlist_records:
        profile_url = normalize_profile_url(
            shortlist_record.get(
                "profile_url"
            )
        )

        if not profile_url:
            continue

        candidate = candidate_lookup.get(
            profile_url
        )

        if not candidate:
            candidate = {
                "name":
                    shortlist_record.get(
                        "name"
                    ),

                "profile_url":
                    profile_url,

                "headline":
                    shortlist_record.get(
                        "headline"
                    ),

                "decision_status":
                    "pending_review",

                "ai_assessment": {
                    "total_score":
                        shortlist_record.get(
                            "ai_score",
                            0,
                        ),

                    "recommendation":
                        shortlist_record.get(
                            "recommendation"
                        ),

                    "confidence":
                        shortlist_record.get(
                            "confidence"
                        ),

                    "why_relevant":
                        shortlist_record.get(
                            "why_relevant"
                        ),

                    "networking_angle":
                        shortlist_record.get(
                            "networking_angle"
                        ),

                    "shared_interests":
                        shortlist_record.get(
                            "shared_interests"
                        )
                        or [],
                },

                "linkedin_profile_data": {
                    "headline":
                        shortlist_record.get(
                            "headline"
                        ),

                    "current_role":
                        shortlist_record.get(
                            "current_role"
                        ),

                    "current_company":
                        shortlist_record.get(
                            "current_company"
                        ),

                    "location":
                        shortlist_record.get(
                            "location"
                        ),
                },
            }

        candidate_copy = dict(
            candidate
        )

        candidate_copy[
            "_weekly_rank"
        ] = shortlist_record.get(
            "rank"
        )

        candidate_copy[
            "_weekly_score"
        ] = shortlist_record.get(
            "ai_score"
        )

        resolved.append(
            candidate_copy
        )

    resolved.sort(
        key=lambda candidate:
            candidate.get(
                "_weekly_rank",
                999,
            )
    )

    return resolved


# ======================================================
# ENGAGEMENT HELPERS
# ======================================================

def get_engagement_assessment(
    opportunity
):
    assessment = (
        opportunity.get(
            "ai_relevance_assessment"
        )
        or {}
    )

    if not isinstance(
        assessment,
        dict,
    ):
        return {}

    return assessment


def get_engagement_score(
    opportunity
):
    assessment = get_engagement_assessment(
        opportunity
    )

    try:
        return int(
            assessment.get(
                "total_score",
                0,
            )
            or 0
        )

    except Exception:
        return 0


def get_engagement_recommendation(
    opportunity
):
    assessment = get_engagement_assessment(
        opportunity
    )

    recommendation = (
        assessment.get(
            "recommendation"
        )
    )

    if recommendation:
        return recommendation

    ai_status = (
        opportunity.get(
            "ai_relevance_status"
        )
        or "pending"
    )

    if ai_status == "pending":
        return "pending"

    return "unscored"


# ======================================================
# UPDATE ENGAGEMENT RECORD
# ======================================================

def update_engagement_opportunity(
    alert_id,
    updates,
):
    opportunities = load_json_list(
        ENGAGEMENT_OPPORTUNITIES_FILE
    )

    for opportunity in opportunities:
        if (
            opportunity.get(
                "alert_id"
            )
            != alert_id
        ):
            continue

        opportunity.update(
            updates
        )

        save_json_list(
            ENGAGEMENT_OPPORTUNITIES_FILE,
            opportunities,
        )

        return True

    return False


# ======================================================
# ENGAGE ON LINKEDIN POST
# ======================================================

def engage_on_linkedin(
    opportunity
):
    alert_id = (
        opportunity.get(
            "alert_id"
        )
    )

    post_url = (
        opportunity.get(
            "post_url"
        )
    )

    if not alert_id:
        return (
            False,
            "This opportunity has no alert ID.",
        )

    if not post_url:
        return (
            False,
            "This opportunity does not have a LinkedIn post URL.",
        )

    if not is_safe_linkedin_url(
        post_url
    ):
        return (
            False,
            "The stored post URL is not a valid LinkedIn URL.",
        )

    timestamp = utc_now()

    updated = (
        update_engagement_opportunity(
            alert_id,
            {
                "lawyer_action":
                    "engage",

                "lawyer_action_updated_at":
                    timestamp,

                "status":
                    "completed",

                "completed_at":
                    timestamp,

                "completion_reason":
                    "opened_linkedin_post_for_engagement",

                "opened_for_comment_at":
                    timestamp,

                "opened_post_url":
                    post_url,
            },
        )
    )

    if not updated:
        return (
            False,
            "Could not update the engagement opportunity.",
        )

    try:
        webbrowser.open(
            post_url,
            new=2,
        )

    except Exception as error:
        return (
            True,
            (
                "The opportunity was marked completed, "
                "but the browser could not be opened automatically: "
                f"{error}"
            ),
        )

    return (
        True,
        "Marked completed and opened the LinkedIn post.",
    )


# ======================================================
# NOT NOW
# ======================================================

def mark_not_now(
    opportunity
):
    alert_id = (
        opportunity.get(
            "alert_id"
        )
    )

    if not alert_id:
        return False

    return (
        update_engagement_opportunity(
            alert_id,
            {
                "lawyer_action":
                    "not_now",

                "lawyer_action_updated_at":
                    utc_now(),

                "status":
                    "deferred",
            },
        )
    )


# ======================================================
# REOPEN OPPORTUNITY
# ======================================================

def reopen_opportunity(
    opportunity
):
    alert_id = (
        opportunity.get(
            "alert_id"
        )
    )

    if not alert_id:
        return False

    return (
        update_engagement_opportunity(
            alert_id,
            {
                "status":
                    "pending_review",

                "lawyer_action":
                    "pending",

                "lawyer_action_updated_at":
                    utc_now(),
            },
        )
    )


# ======================================================
# LOAD DATA
# ======================================================

candidates = load_json_list(
    CANDIDATES_FILE
)

weekly_shortlist = load_json_object(
    WEEKLY_SHORTLIST_FILE
)

weekly_candidates = (
    get_weekly_shortlist_candidates(
        candidates,
        weekly_shortlist,
    )
)

tracked_connections = load_json_list(
    TRACKED_CONNECTIONS_FILE
)

engagement_opportunities = load_json_list(
    ENGAGEMENT_OPPORTUNITIES_FILE
)


# ======================================================
# COUNTS
# ======================================================

weekly_candidate_count = len(
    weekly_candidates
)

weekly_pending_count = sum(
    1
    for candidate in weekly_candidates
    if (
        get_decision_status(
            candidate
        )
        == "pending_review"
    )
)

weekly_connect_count = sum(
    1
    for candidate in weekly_candidates
    if (
        get_decision_status(
            candidate
        )
        == "connect_selected"
    )
)

weekly_follow_count = sum(
    1
    for candidate in weekly_candidates
    if (
        get_decision_status(
            candidate
        )
        == "follow_selected"
    )
)

active_tracked_count = sum(
    1
    for connection in tracked_connections
    if (
        connection.get(
            "tracking_status",
            "active",
        )
        == "active"
    )
)

pending_engagement_count = sum(
    1
    for opportunity in engagement_opportunities
    if (
        opportunity.get(
            "status",
            "pending_review",
        )
        == "pending_review"
    )
)

completed_engagement_count = sum(
    1
    for opportunity in engagement_opportunities
    if (
        opportunity.get(
            "status"
        )
        == "completed"
    )
)


# ======================================================
# SIDEBAR
# ======================================================

with st.sidebar:

    st.title(
        "Network Scout"
    )

    st.caption(
        "Professional networking intelligence"
    )

    st.divider()

    page_choice = st.radio(
        "Navigation",
        [
            "This Week's Picks",
            "Tracked Network",
            "Engagement Opportunities",
        ],
    )

    st.divider()

    if st.button(
        "Refresh Data",
        use_container_width=True,
    ):
        st.rerun()

    st.caption(
        "Network Scout finds and ranks opportunities. "
        "The lawyer only sees the strongest weekly picks "
        "and relevant engagement opportunities."
    )


# ======================================================
# HEADER
# ======================================================

st.title(
    "Network Scout"
)

st.write(
    "Focused professional networking without the noise."
)


# ======================================================
# GLOBAL METRICS
# ======================================================

metric_columns = st.columns(
    7
)

metric_columns[
    0
].metric(
    "This Week's Picks",
    weekly_candidate_count,
)

metric_columns[
    1
].metric(
    "Awaiting Review",
    weekly_pending_count,
)

metric_columns[
    2
].metric(
    "Connect Chosen",
    weekly_connect_count,
)

metric_columns[
    3
].metric(
    "Follow Chosen",
    weekly_follow_count,
)

metric_columns[
    4
].metric(
    "Tracked Network",
    active_tracked_count,
)

metric_columns[
    5
].metric(
    "Posts to Review",
    pending_engagement_count,
)

metric_columns[
    6
].metric(
    "Engagements Completed",
    completed_engagement_count,
)

st.divider()


# ======================================================
# PAGE 1 — THIS WEEK'S PICKS
# ======================================================

if (
    page_choice
    == "This Week's Picks"
):

    st.subheader(
        "This Week's Networking Picks"
    )

    st.write(
        "The strongest new professional networking "
        "opportunities selected for this week."
    )

    if not weekly_shortlist:

        st.info(
            "No weekly shortlist has been created yet. "
            "Run ranking/weekly_shortlist.py after the "
            "discovery, enrichment and AI-ranking pipeline."
        )

        st.stop()

    week_key = (
        weekly_shortlist.get(
            "week_key"
        )
    )

    created_at = (
        weekly_shortlist.get(
            "created_at"
        )
    )

    eligible_count = (
        weekly_shortlist.get(
            "eligible_candidate_count",
            0,
        )
    )

    maximum_candidates = (
        weekly_shortlist.get(
            "maximum_candidates",
            10,
        )
    )

    minimum_ai_score = (
        weekly_shortlist.get(
            "minimum_ai_score"
        )
    )

    info_columns = st.columns(
        4
    )

    info_columns[
        0
    ].metric(
        "Week",
        safe_text(
            week_key,
            "Current",
        ),
    )

    info_columns[
        1
    ].metric(
        "Selected",
        weekly_candidate_count,
    )

    info_columns[
        2
    ].metric(
        "Qualified Pool",
        eligible_count,
    )

    info_columns[
        3
    ].metric(
        "Maximum",
        maximum_candidates,
    )

    if created_at:

        st.caption(
            f"Shortlist created: {created_at}"
        )

    if minimum_ai_score is not None:

        st.caption(
            f"Only candidates scoring at least "
            f"{minimum_ai_score}/100 were eligible."
        )

    st.divider()

    if not weekly_candidates:

        st.info(
            "No candidates met this week's quality threshold. "
            "Network Scout will not show weak filler recommendations."
        )

        st.stop()

    filter_columns = st.columns(
        [
            2,
            3,
        ]
    )

    decision_filter = (
        filter_columns[
            0
        ].selectbox(
            "Decision",
            [
                "All",
                "Pending Review",
                "Connect Chosen",
                "Follow Chosen",
                "Saved",
                "Not Relevant",
            ],
        )
    )

    search_term = (
        filter_columns[
            1
        ].text_input(
            "Search this week's picks",
            placeholder=(
                "Name, role, company, location..."
            ),
        )
    )

    decision_mapping = {
        "Pending Review":
            "pending_review",

        "Connect Chosen":
            "connect_selected",

        "Follow Chosen":
            "follow_selected",

        "Saved":
            "saved",

        "Not Relevant":
            "not_relevant",
    }

    filtered_candidates = []

    for candidate in weekly_candidates:

        if (
            decision_filter
            != "All"
        ):

            if (
                get_decision_status(
                    candidate
                )
                != decision_mapping[
                    decision_filter
                ]
            ):

                continue

        if not candidate_matches_search(
            candidate,
            search_term,
        ):

            continue

        filtered_candidates.append(
            candidate
        )

    st.write(
        f"Showing **{len(filtered_candidates)}** "
        f"of this week's **{weekly_candidate_count}** picks."
    )

    if not filtered_candidates:

        st.info(
            "No weekly picks match the current filters."
        )

    for candidate_index, candidate in enumerate(
        filtered_candidates,
        start=1,
    ):

        profile = get_profile_data(
            candidate
        )

        assessment = get_ai_assessment(
            candidate
        )

        decision_status = get_decision_status(
            candidate
        )

        weekly_rank = (
            candidate.get(
                "_weekly_rank"
            )
            or candidate_index
        )

        name = (
            profile.get(
                "name"
            )
            or candidate.get(
                "name"
            )
            or "Unknown Candidate"
        )

        profile_url = (
            candidate.get(
                "profile_url"
            )
        )

        headline = (
            profile.get(
                "headline"
            )
            or candidate.get(
                "headline"
            )
        )

        role = (
            profile.get(
                "current_role"
            )
        )

        company = (
            profile.get(
                "current_company"
            )
        )

        location = (
            profile.get(
                "location"
            )
        )

        score = get_total_score(
            candidate
        )

        recommendation = get_recommendation(
            candidate
        )

        confidence = (
            assessment.get(
                "confidence"
            )
            or "Not available"
        )

        candidate_key = make_widget_key(
            normalize_profile_url(
                profile_url
            )
            or f"candidate_{candidate_index}"
        )

        with st.container(
            border=True
        ):

            title_columns = st.columns(
                [
                    1,
                    5,
                    1,
                    1,
                    2,
                ]
            )

            with title_columns[
                0
            ]:

                st.metric(
                    "Rank",
                    f"#{weekly_rank}",
                )

            with title_columns[
                1
            ]:

                st.subheader(
                    name
                )

                if headline:

                    st.write(
                        headline
                    )

                details = [
                    value
                    for value
                    in [
                        role,
                        company,
                        location,
                    ]
                    if value
                ]

                if details:

                    st.caption(
                        " • ".join(
                            details
                        )
                    )

            with title_columns[
                2
            ]:

                st.metric(
                    "AI Score",
                    f"{score}/100",
                )

            with title_columns[
                3
            ]:

                st.metric(
                    "Confidence",
                    (
                        confidence.title()
                        if confidence
                        != "Not available"
                        else "N/A"
                    ),
                )

            with title_columns[
                4
            ]:

                st.write(
                    "**Recommendation**"
                )

                st.write(
                    recommendation
                    .replace(
                        "_",
                        " ",
                    )
                    .title()
                )

                st.write(
                    "**Decision**"
                )

                st.write(
                    decision_label(
                        decision_status
                    )
                )

            # ==================================================
            # WHY SELECTED
            # ==================================================

            if assessment:

                st.markdown(
                    "#### Why Network Scout selected this person"
                )

                st.write(
                    safe_text(
                        assessment.get(
                            "why_relevant"
                        )
                    )
                )

                networking_angle = (
                    assessment.get(
                        "networking_angle"
                    )
                )

                if networking_angle:

                    st.markdown(
                        "**Potential networking angle**"
                    )

                    st.write(
                        networking_angle
                    )

                shared_interests = (
                    assessment.get(
                        "shared_interests"
                    )
                    or []
                )

                if shared_interests:

                    st.markdown(
                        "**Shared interests**"
                    )

                    st.write(
                        " • ".join(
                            shared_interests
                        )
                    )

            # ==================================================
            # LINKEDIN PROFILE DETAILS
            #
            # ABOUT SUMMARY ONLY
            # ==================================================

            with st.expander(
                "LinkedIn profile details"
            ):

                st.markdown(
                    "**About summary**"
                )

                st.write(
                    summarize_about(
                        profile.get(
                            "about"
                        )
                    )
                )

            # ==================================================
            # AI EVIDENCE
            # ==================================================

            if assessment:

                with st.expander(
                    "AI evidence and concerns"
                ):

                    evidence = (
                        assessment.get(
                            "evidence"
                        )
                        or []
                    )

                    concerns = (
                        assessment.get(
                            "concerns"
                        )
                        or []
                    )

                    st.markdown(
                        "**Evidence**"
                    )

                    if evidence:

                        for item in evidence:

                            st.write(
                                f"• {item}"
                            )

                    else:

                        st.write(
                            "No evidence list available."
                        )

                    st.markdown(
                        "**Concerns**"
                    )

                    if concerns:

                        for item in concerns:

                            st.write(
                                f"• {item}"
                            )

                    else:

                        st.write(
                            "No major concerns recorded."
                        )

            # ==================================================
            # HOW THIS PERSON ENTERED THE NETWORK
            #
            # COMMENT TEXT IS HIDDEN
            # ==================================================

            sources = get_sources(
                candidate
            )

            if sources:

                with st.expander(
                    "How this person entered the network"
                ):

                    for source_number, source in enumerate(
                        sources,
                        start=1,
                    ):

                        if (
                            len(
                                sources
                            )
                            > 1
                        ):

                            st.markdown(
                                f"**Source {source_number}**"
                            )

                        st.write(
                            "Discovered around:",
                            safe_text(
                                source.get(
                                    "source_connection"
                                )
                            ),
                        )

                        source_post_url = (
                            source.get(
                                "source_post_url"
                            )
                        )

                        if (
                            source_post_url
                            and is_safe_linkedin_url(
                                source_post_url
                            )
                        ):

                            st.link_button(
                                "Open Source Post",
                                source_post_url,
                            )

                        if (
                            source_number
                            < len(
                                sources
                            )
                        ):

                            st.divider()

            # ==================================================
            # PROFILE LINK
            # ==================================================

            if (
                profile_url
                and is_safe_linkedin_url(
                    profile_url
                )
            ):

                st.link_button(
                    "Open LinkedIn Profile",
                    profile_url,
                )

            st.divider()

            # ==================================================
            # LAWYER ACTIONS
            # ==================================================

            action_columns = st.columns(
                4
            )

            if action_columns[
                0
            ].button(
                "Connect on LinkedIn",
                key=(
                    f"connect_{candidate_key}"
                ),
                type="primary",
                use_container_width=True,
            ):

                success, message = (
                    start_linkedin_relationship_action(
                        candidate,
                        "connect",
                    )
                )

                if success:

                    st.success(
                        message
                    )

                    st.rerun()

                else:

                    st.error(
                        message
                    )

            if action_columns[
                1
            ].button(
                "Follow on LinkedIn",
                key=(
                    f"follow_{candidate_key}"
                ),
                use_container_width=True,
            ):

                success, message = (
                    start_linkedin_relationship_action(
                        candidate,
                        "follow",
                    )
                )

                if success:

                    st.success(
                        message
                    )

                    st.rerun()

                else:

                    st.error(
                        message
                    )

            if action_columns[
                2
            ].button(
                "Save",
                key=(
                    f"save_{candidate_key}"
                ),
                use_container_width=True,
            ):

                update_candidate_decision(
                    profile_url,
                    "saved",
                )

                st.rerun()

            if action_columns[
                3
            ].button(
                "Not Relevant",
                key=(
                    f"reject_{candidate_key}"
                ),
                use_container_width=True,
            ):

                update_candidate_decision(
                    profile_url,
                    "not_relevant",
                )

                st.rerun()

            if decision_status in {
                "connect_selected",
                "follow_selected",
                "saved",
                "not_relevant",
            }:

                if st.button(
                    "Reset Decision",
                    key=(
                        f"reset_{candidate_key}"
                    ),
                ):

                    update_candidate_decision(
                        profile_url,
                        "pending_review",
                    )

                    st.rerun()

            if (
                decision_status
                == "connect_selected"
            ):

                st.success(
                    "Connect chosen. This person is now actively tracked."
                )

            elif (
                decision_status
                == "follow_selected"
            ):

                st.success(
                    "Follow chosen. This person is now actively tracked."
                )


# ======================================================
# PAGE 2 — TRACKED NETWORK
# ======================================================

elif (
    page_choice
    == "Tracked Network"
):

    st.subheader(
        "Tracked Network"
    )

    st.write(
        "Professionals Network Scout monitors "
        "for meaningful new LinkedIn activity."
    )

    active_tracked = [
        record
        for record
        in tracked_connections
        if (
            record.get(
                "tracking_status",
                "active",
            )
            == "active"
        )
    ]

    seed_count = sum(
        1
        for record
        in active_tracked
        if (
            record.get(
                "source"
            )
            == "existing_connection_seed"
        )
    )

    network_scout_count = sum(
        1
        for record
        in active_tracked
        if (
            record.get(
                "source"
            )
            == "network_scout_weekly_pick"
        )
    )

    tracked_metrics = st.columns(
        3
    )

    tracked_metrics[
        0
    ].metric(
        "Total Tracked",
        len(
            active_tracked
        ),
    )

    tracked_metrics[
        1
    ].metric(
        "Starting Network",
        seed_count,
    )

    tracked_metrics[
        2
    ].metric(
        "Added by Network Scout",
        network_scout_count,
    )

    st.divider()

    if not active_tracked:

        st.info(
            "No tracked connections yet."
        )

    for record_index, record in enumerate(
        active_tracked,
        start=1,
    ):

        with st.container(
            border=True
        ):

            columns = st.columns(
                [
                    4,
                    2,
                    2,
                ]
            )

            with columns[
                0
            ]:

                st.subheader(
                    safe_text(
                        record.get(
                            "name"
                        ),
                        "Unknown",
                    )
                )

                profile_url = (
                    record.get(
                        "profile_url"
                    )
                )

                if (
                    profile_url
                    and is_safe_linkedin_url(
                        profile_url
                    )
                ):

                    st.link_button(
                        "Open LinkedIn Profile",
                        profile_url,
                    )

            with columns[
                1
            ]:

                source = (
                    record.get(
                        "source"
                    )
                    or ""
                )

                if (
                    source
                    == "existing_connection_seed"
                ):

                    source_label = (
                        "Starting Connection"
                    )

                elif (
                    source
                    == "network_scout_weekly_pick"
                ):

                    source_label = (
                        "Network Scout"
                    )

                else:

                    source_label = (
                        source
                        .replace(
                            "_",
                            " ",
                        )
                        .title()
                    )

                st.write(
                    "**Source**"
                )

                st.write(
                    source_label
                )

                relationship_action = (
                    record.get(
                        "relationship_action"
                    )
                )

                if relationship_action:

                    st.write(
                        "**Chosen action**"
                    )

                    st.write(
                        relationship_action.title()
                    )

            with columns[
                2
            ]:

                st.write(
                    "**Monitoring**"
                )

                if record.get(
                    "monitor_posts",
                    True,
                ):

                    st.write(
                        "Active"
                    )

                else:

                    st.write(
                        "Off"
                    )

            last_status = (
                record.get(
                    "last_post_status"
                )
            )

            last_checked = (
                record.get(
                    "last_checked_at"
                )
            )

            if (
                last_status
                or last_checked
            ):

                st.caption(
                    f"Last post status: "
                    f"{safe_text(last_status)} "
                    f"| Last checked: "
                    f"{safe_text(last_checked)}"
                )


# ======================================================
# PAGE 3 — ENGAGEMENT OPPORTUNITIES
# ======================================================

elif (
    page_choice
    == "Engagement Opportunities"
):

    st.subheader(
        "Engagement Opportunities"
    )

    st.write(
        "Relevant new posts from people already "
        "in the lawyer's tracked professional network."
    )

    if not engagement_opportunities:

        st.info(
            "No engagement opportunities yet. "
            "This section will populate after "
            "post_monitor.py detects a genuinely new post."
        )

        st.stop()

    filter_columns = st.columns(
        3
    )

    ai_filter = (
        filter_columns[
            0
        ].selectbox(
            "AI Recommendation",
            [
                "All",
                "Engage",
                "Consider",
                "Skip",
                "Pending",
            ],
        )
    )

    action_filter = (
        filter_columns[
            1
        ].selectbox(
            "Status",
            [
                "Needs Review",
                "All",
                "Deferred",
                "Completed",
            ],
        )
    )

    engagement_search = (
        filter_columns[
            2
        ].text_input(
            "Search",
            placeholder=(
                "Connection name or post topic..."
            ),
        )
    )

    filtered_opportunities = []

    for opportunity in engagement_opportunities:

        recommendation = (
            get_engagement_recommendation(
                opportunity
            )
        )

        status = (
            opportunity.get(
                "status"
            )
            or "pending_review"
        )

        if (
            ai_filter
            != "All"
        ):

            if (
                recommendation
                != ai_filter.lower()
            ):

                continue

        if (
            action_filter
            == "Needs Review"
        ):

            if (
                status
                != "pending_review"
            ):

                continue

        elif (
            action_filter
            == "Deferred"
        ):

            if (
                status
                != "deferred"
            ):

                continue

        elif (
            action_filter
            == "Completed"
        ):

            if (
                status
                != "completed"
            ):

                continue

        if engagement_search:

            assessment = (
                get_engagement_assessment(
                    opportunity
                )
            )

            searchable = " ".join(
                [
                    safe_text(
                        opportunity.get(
                            "connection_name"
                        ),
                        "",
                    ),

                    safe_text(
                        opportunity.get(
                            "post_text"
                        ),
                        "",
                    ),

                    safe_text(
                        assessment.get(
                            "post_summary"
                        ),
                        "",
                    ),

                    " ".join(
                        assessment.get(
                            "key_topics"
                        )
                        or []
                    ),
                ]
            ).lower()

            if (
                engagement_search.lower()
                not in searchable
            ):

                continue

        filtered_opportunities.append(
            opportunity
        )

    filtered_opportunities.sort(
        key=get_engagement_score,
        reverse=True,
    )

    st.write(
        f"Showing **{len(filtered_opportunities)}** "
        "engagement opportunities."
    )

    if not filtered_opportunities:

        st.info(
            "No engagement opportunities match these filters."
        )

    for opportunity_index, opportunity in enumerate(
        filtered_opportunities,
        start=1,
    ):

        assessment = (
            get_engagement_assessment(
                opportunity
            )
        )

        connection_name = (
            opportunity.get(
                "connection_name"
            )
            or "Unknown Connection"
        )

        connection_profile_url = (
            opportunity.get(
                "connection_profile_url"
            )
        )

        post_url = (
            opportunity.get(
                "post_url"
            )
        )

        post_text = (
            opportunity.get(
                "post_text"
            )
        )

        detected_at = (
            opportunity.get(
                "detected_at"
            )
        )

        ai_status = (
            opportunity.get(
                "ai_relevance_status"
            )
            or "pending"
        )

        recommendation = (
            get_engagement_recommendation(
                opportunity
            )
        )

        score = get_engagement_score(
            opportunity
        )

        confidence = (
            assessment.get(
                "confidence"
            )
            or "Not available"
        )

        status = (
            opportunity.get(
                "status"
            )
            or "pending_review"
        )

        alert_id = (
            opportunity.get(
                "alert_id"
            )
            or f"opportunity_{opportunity_index}"
        )

        opportunity_key = make_widget_key(
            alert_id
        )

        with st.container(
            border=True
        ):

            header_columns = st.columns(
                [
                    5,
                    1,
                    1,
                    2,
                ]
            )

            with header_columns[
                0
            ]:

                st.subheader(
                    connection_name
                )

                if detected_at:

                    st.caption(
                        f"New post detected: {detected_at}"
                    )

            with header_columns[
                1
            ]:

                if (
                    ai_status
                    == "success"
                ):

                    st.metric(
                        "AI Score",
                        f"{score}/100",
                    )

                else:

                    st.metric(
                        "AI Score",
                        "Pending",
                    )

            with header_columns[
                2
            ]:

                st.metric(
                    "Confidence",
                    (
                        confidence.title()
                        if confidence
                        != "Not available"
                        else "N/A"
                    ),
                )

            with header_columns[
                3
            ]:

                st.write(
                    "**Recommendation**"
                )

                st.write(
                    recommendation.title()
                )

                st.write(
                    "**Status**"
                )

                st.write(
                    status
                    .replace(
                        "_",
                        " ",
                    )
                    .title()
                )

            link_columns = st.columns(
                2
            )

            if (
                connection_profile_url
                and is_safe_linkedin_url(
                    connection_profile_url
                )
            ):

                with link_columns[
                    0
                ]:

                    st.link_button(
                        "Open Connection Profile",
                        connection_profile_url,
                        use_container_width=True,
                    )

            if (
                post_url
                and is_safe_linkedin_url(
                    post_url
                )
            ):

                with link_columns[
                    1
                ]:

                    st.link_button(
                        "Preview LinkedIn Post",
                        post_url,
                        use_container_width=True,
                    )

            if (
                ai_status
                == "success"
                and assessment
            ):

                st.markdown(
                    "#### What the post is about"
                )

                st.write(
                    safe_text(
                        assessment.get(
                            "post_summary"
                        )
                    )
                )

                st.markdown(
                    "#### Why it may matter"
                )

                st.write(
                    safe_text(
                        assessment.get(
                            "why_it_matters"
                        )
                    )
                )

                engagement_angle = (
                    assessment.get(
                        "engagement_angle"
                    )
                )

                if engagement_angle:

                    st.markdown(
                        "**Potential engagement angle**"
                    )

                    st.write(
                        engagement_angle
                    )

                topics = (
                    assessment.get(
                        "key_topics"
                    )
                    or []
                )

                if topics:

                    st.markdown(
                        "**Key topics**"
                    )

                    st.write(
                        " • ".join(
                            topics
                        )
                    )

            elif (
                ai_status
                == "failed"
            ):

                st.warning(
                    "AI relevance evaluation failed for this post."
                )

                error = (
                    opportunity.get(
                        "ai_relevance_error"
                    )
                )

                if error:

                    st.caption(
                        error
                    )

            else:

                st.info(
                    "This post has not yet been evaluated by "
                    "post_relevance_ranker.py."
                )

            with st.expander(
                "View captured post"
            ):

                st.write(
                    safe_text(
                        post_text
                    )
                )

                st.write(
                    "Visible comments:",
                    opportunity.get(
                        "visible_comment_count",
                        0,
                    ),
                )

            if assessment:

                with st.expander(
                    "AI scoring details"
                ):

                    score_columns = st.columns(
                        4
                    )

                    score_columns[
                        0
                    ].metric(
                        "Professional",
                        (
                            f"{assessment.get('professional_relevance', 0)}/35"
                        ),
                    )

                    score_columns[
                        1
                    ].metric(
                        "Relationship",
                        (
                            f"{assessment.get('relationship_value', 0)}/25"
                        ),
                    )

                    score_columns[
                        2
                    ].metric(
                        "Contribution",
                        (
                            f"{assessment.get('contribution_opportunity', 0)}/25"
                        ),
                    )

                    score_columns[
                        3
                    ].metric(
                        "Evidence",
                        (
                            f"{assessment.get('evidence_quality', 0)}/15"
                        ),
                    )

                    evidence = (
                        assessment.get(
                            "evidence"
                        )
                        or []
                    )

                    concerns = (
                        assessment.get(
                            "concerns"
                        )
                        or []
                    )

                    if evidence:

                        st.markdown(
                            "**Evidence**"
                        )

                        for item in evidence:

                            st.write(
                                f"• {item}"
                            )

                    if concerns:

                        st.markdown(
                            "**Concerns**"
                        )

                        for item in concerns:

                            st.write(
                                f"• {item}"
                            )

            st.divider()

            if (
                status
                == "pending_review"
            ):

                action_columns = st.columns(
                    2
                )

                if action_columns[
                    0
                ].button(
                    "Engage on LinkedIn",
                    key=(
                        f"engage_{opportunity_key}"
                    ),
                    type="primary",
                    use_container_width=True,
                ):

                    success, message = (
                        engage_on_linkedin(
                            opportunity
                        )
                    )

                    if success:

                        st.success(
                            message
                        )

                        st.rerun()

                    else:

                        st.error(
                            message
                        )

                if action_columns[
                    1
                ].button(
                    "Not Now",
                    key=(
                        f"not_now_{opportunity_key}"
                    ),
                    use_container_width=True,
                ):

                    if mark_not_now(
                        opportunity
                    ):

                        st.rerun()

                    else:

                        st.error(
                            "Could not update this opportunity."
                        )

            elif (
                status
                == "deferred"
            ):

                st.info(
                    "This opportunity was marked Not Now."
                )

                deferred_columns = st.columns(
                    2
                )

                if deferred_columns[
                    0
                ].button(
                    "Engage on LinkedIn",
                    key=(
                        f"deferred_engage_{opportunity_key}"
                    ),
                    type="primary",
                    use_container_width=True,
                ):

                    success, message = (
                        engage_on_linkedin(
                            opportunity
                        )
                    )

                    if success:

                        st.success(
                            message
                        )

                        st.rerun()

                    else:

                        st.error(
                            message
                        )

                if deferred_columns[
                    1
                ].button(
                    "Return to Review Queue",
                    key=(
                        f"reopen_{opportunity_key}"
                    ),
                    use_container_width=True,
                ):

                    if reopen_opportunity(
                        opportunity
                    ):

                        st.rerun()

                    else:

                        st.error(
                            "Could not reopen this opportunity."
                        )

            elif (
                status
                == "completed"
            ):

                st.success(
                    "Completed — this opportunity was opened "
                    "on LinkedIn for the lawyer to engage."
                )

                completed_at = (
                    opportunity.get(
                        "completed_at"
                    )
                )

                if completed_at:

                    st.caption(
                        f"Completed: {completed_at}"
                    )

                if (
                    post_url
                    and is_safe_linkedin_url(
                        post_url
                    )
                ):

                    st.link_button(
                        "Open LinkedIn Post Again",
                        post_url,
                    )