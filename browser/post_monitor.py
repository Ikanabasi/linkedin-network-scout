from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from playwright.sync_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


# ==========================================================
# PATHS
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
BROWSER_PROFILE_DIR = PROJECT_ROOT / "browser_data" / "lawyer_profile"

MONITORED_CONNECTIONS_FILE = DATA_DIR / "monitored_connections.json"
TRACKED_CONNECTIONS_FILE = DATA_DIR / "tracked_connections.json"
CANDIDATES_FILE = DATA_DIR / "candidates.json"
MONITOR_STATE_FILE = DATA_DIR / "post_monitor_state.json"
RAW_OPPORTUNITIES_FILE = DATA_DIR / "engagement_opportunities.json"
RANKED_OPPORTUNITIES_FILE = DATA_DIR / "ranked_engagement_opportunities.json"
TEST_COMMENT_DISCOVERY_FILE = DATA_DIR / "test_comment_discovery.json"
NETWORKING_PREFERENCES_FILE = (
    PROJECT_ROOT / "config" / "networking_preferences.json"
)


# ==========================================================
# SETTINGS
# ==========================================================

PAGE_TIMEOUT_MS = 30000
PAGE_SETTLE_MS = 1800

DEFAULT_BATCH_SIZE = 20

MAX_POSTS_TO_INSPECT = 4

RELEVANCE_THRESHOLD = 75

MAX_COMMENTERS_PER_POST = 40

MAX_COMMENT_LOAD_CLICKS = 8

COMMENT_LOAD_WAIT_MS = 900

DEFAULT_OPENAI_MODEL = (
    os.getenv("OPENAI_MODEL")
    or "gpt-5-mini"
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


# ==========================================================
# JSON HELPERS
# ==========================================================

def read_json(
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


def write_json(
    path: Path,
    data: Any,
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp = path.with_name(
        path.name + ".tmp"
    )

    temp.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temp.replace(
        path
    )


def extract_records(
    payload: Any,
    possible_keys: list[str],
) -> list[dict[str, Any]]:

    if isinstance(
        payload,
        list,
    ):
        return [
            item
            for item in payload
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

            value = payload.get(
                key
            )

            if isinstance(
                value,
                list,
            ):

                return [
                    item
                    for item in value
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
        value,
        re.IGNORECASE,
    )

    if not match:
        return None

    slug = (
        match.group(1)
        .strip()
        .lower()
    )

    if not slug:
        return None

    return (
        f"https://www.linkedin.com/in/{slug}/"
    )


def normalize_post_url(
    value: str | None,
) -> str | None:

    if not value:
        return None

    value = value.strip()

    if value.startswith(
        "/"
    ):
        value = (
            "https://www.linkedin.com"
            + value
        )

    if not value.startswith(
        "https://www.linkedin.com/"
    ):
        return None

    value = (
        value
        .split(
            "?",
            1,
        )[0]
        .split(
            "#",
            1,
        )[0]
    )

    if (
        "/posts/"
        not in value
        and
        "/feed/update/urn:li:activity:"
        not in value
    ):
        return None

    return value


def normalize_text(
    value: str | None,
) -> str:

    return re.sub(
        r"\s+",
        " ",
        str(
            value
            or
            ""
        ),
    ).strip()


# ==========================================================
# MONITORED CONNECTIONS
# ==========================================================

def load_monitored_connections() -> list[
    dict[str, Any]
]:

    payload = read_json(
        MONITORED_CONNECTIONS_FILE,
        {},
    )

    items = extract_records(
        payload,
        [
            "connections",
            "items",
        ],
    )

    output: list[
        dict[str, Any]
    ] = []

    seen: set[str] = set()

    for item in items:

        profile_url = (
            normalize_profile_url(
                item.get(
                    "profile_url"
                )
            )
        )

        if not profile_url:
            continue

        if profile_url in seen:
            continue

        if (
            item.get(
                "monitor_posts"
            )
            is False
        ):
            continue

        tracking_status = str(
            item.get(
                "tracking_status"
            )
            or
            "active"
        ).lower()

        if (
            tracking_status
            !=
            "active"
        ):
            continue

        output.append(
            {
                **item,
                "profile_url":
                    profile_url,
            }
        )

        seen.add(
            profile_url
        )

    return output


# ==========================================================
# TRACKED CONNECTIONS
# ==========================================================

def load_tracked_profile_urls() -> set[str]:

    payload = read_json(
        TRACKED_CONNECTIONS_FILE,
        [],
    )

    items = extract_records(
        payload,
        [
            "connections",
            "tracked_connections",
            "items",
        ],
    )

    urls: set[str] = set()

    for item in items:

        profile_url = (
            normalize_profile_url(
                item.get(
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
# CANDIDATES
# ==========================================================

def load_candidate_payload() -> tuple[
    Any,
    list[
        dict[str, Any]
    ],
    str | None,
]:

    payload = read_json(
        CANDIDATES_FILE,
        [],
    )

    if isinstance(
        payload,
        list,
    ):

        records = [
            item
            for item in payload
            if isinstance(
                item,
                dict,
            )
        ]

        return (
            payload,
            records,
            None,
        )

    if isinstance(
        payload,
        dict,
    ):

        for key in [
            "candidates",
            "items",
            "connections",
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

                records = [
                    item
                    for item in value
                    if isinstance(
                        item,
                        dict,
                    )
                ]

                return (
                    payload,
                    records,
                    key,
                )

        return (
            payload,
            [],
            "candidates",
        )

    return (
        [],
        [],
        None,
    )


def save_candidate_records(
    original_payload: Any,
    records: list[
        dict[str, Any]
    ],
    list_key: str | None,
) -> None:

    if isinstance(
        original_payload,
        list,
    ):

        write_json(
            CANDIDATES_FILE,
            records,
        )

        return

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
            "candidates"
        ] = records

        updated[
            "updated_at"
        ] = utc_now()

        write_json(
            CANDIDATES_FILE,
            updated,
        )

        return

    write_json(
        CANDIDATES_FILE,
        records,
    )


def candidate_profile_urls(
    records: list[
        dict[str, Any]
    ],
) -> set[str]:

    urls: set[str] = set()

    for record in records:

        profile_url = (
            normalize_profile_url(
                record.get(
                    "profile_url"
                )
                or
                record.get(
                    "linkedin_url"
                )
            )
        )

        if profile_url:
            urls.add(
                profile_url
            )

    return urls


# ==========================================================
# STATE
# ==========================================================

def load_state() -> dict[
    str,
    Any,
]:

    state = read_json(
        MONITOR_STATE_FILE,
        {},
    )

    if not isinstance(
        state,
        dict,
    ):
        state = {}

    state.setdefault(
        "next_index",
        0,
    )

    state.setdefault(
        "profiles",
        {},
    )

    state.setdefault(
        "posts",
        {},
    )

    if not isinstance(
        state[
            "profiles"
        ],
        dict,
    ):
        state[
            "profiles"
        ] = {}

    if not isinstance(
        state[
            "posts"
        ],
        dict,
    ):
        state[
            "posts"
        ] = {}

    return state


def save_state(
    state: dict[
        str,
        Any,
    ],
) -> None:

    state[
        "updated_at"
    ] = utc_now()

    write_json(
        MONITOR_STATE_FILE,
        state,
    )


# ==========================================================
# LINKEDIN LOGIN / SECURITY
# ==========================================================

def detect_linkedin_attention(
    page: Page,
) -> str | None:

    current_url = (
        page.url.lower()
    )

    blocked_paths = [
        "/login",
        "/checkpoint/",
        "/challenge/",
        "/authwall",
    ]

    if any(
        value
        in current_url
        for value
        in blocked_paths
    ):

        return (
            "LinkedIn requires login "
            "or security verification."
        )

    try:

        body_text = (
            page.locator(
                "body"
            )
            .inner_text(
                timeout=2500
            )
            .lower()
        )

    except Exception:

        return None

    signals = [
        "security verification",
        "verify your identity",
        "quick security check",
        "captcha",
    ]

    for signal in signals:

        if (
            signal
            in body_text
        ):

            return (
                "LinkedIn requires "
                "security verification."
            )

    return None


# ==========================================================
# POSTS TAB
# ==========================================================

def find_posts_tab(
    page: Page,
):

    selectors = [
        "main [role='tab']",
        "main a",
        "main button",
        "[role='tab']",
        "a",
        "button",
    ]

    for selector in selectors:

        try:

            elements = (
                page.locator(
                    selector
                )
            )

            count = min(
                elements.count(),
                250,
            )

        except Exception:

            continue

        for index in range(
            count
        ):

            element = (
                elements.nth(
                    index
                )
            )

            try:

                if not element.is_visible():
                    continue

                text = (
                    element
                    .inner_text(
                        timeout=300
                    )
                    .strip()
                    .lower()
                )

                aria = (
                    element
                    .get_attribute(
                        "aria-label"
                    )
                    or
                    ""
                ).strip().lower()

                if (
                    text == "posts"
                    or
                    aria == "posts"
                ):

                    return element

            except Exception:

                continue

    return None


def open_posts_activity(
    page: Page,
    profile_url: str,
) -> bool:

    activity_url = (
        profile_url
        +
        "recent-activity/all/"
    )

    page.goto(
        activity_url,
        wait_until=
            "domcontentloaded",
        timeout=
            PAGE_TIMEOUT_MS,
    )

    page.wait_for_timeout(
        PAGE_SETTLE_MS
    )

    attention = (
        detect_linkedin_attention(
            page
        )
    )

    if attention:

        raise RuntimeError(
            attention
        )

    posts_tab = (
        find_posts_tab(
            page
        )
    )

    if not posts_tab:
        return False

    try:

        posts_tab.scroll_into_view_if_needed(
            timeout=2000
        )

    except Exception:

        pass

    try:

        posts_tab.click(
            timeout=3000
        )

    except Exception:

        try:

            posts_tab.evaluate(
                "element => element.click()"
            )

        except Exception:

            return False

    page.wait_for_timeout(
        PAGE_SETTLE_MS
    )

    return True


# ==========================================================
# RECENT POSTS
# ==========================================================

def extract_recent_posts(
    page: Page,
) -> list[
    dict[str, Any]
]:

    raw_posts = page.locator(
        (
            "a[href*='/posts/'], "
            "a[href*='/feed/update/urn:li:activity:']"
        )
    ).evaluate_all(
        r"""
        (anchors) => {

            const results = [];

            for (const anchor of anchors) {

                const href =
                    anchor.href || "";

                if (!href) {
                    continue;
                }

                let card =
                    anchor.closest(
                        [
                            "article",
                            "[data-urn]",
                            ".feed-shared-update-v2",
                            "[data-view-name='feed-full-update']"
                        ].join(",")
                    );

                if (!card) {

                    let current =
                        anchor;

                    for (
                        let i = 0;
                        i < 12;
                        i += 1
                    ) {

                        if (!current) {
                            break;
                        }

                        const text =
                            (
                                current.innerText
                                ||
                                current.textContent
                                ||
                                ""
                            ).trim();

                        const lowered =
                            text.toLowerCase();

                        if (
                            text.length >= 80
                            &&
                            text.length <= 8000
                            &&
                            (
                                lowered.includes(
                                    "comment"
                                )
                                ||
                                lowered.includes(
                                    "repost"
                                )
                                ||
                                lowered.includes(
                                    "reaction"
                                )
                                ||
                                lowered.includes(
                                    "like"
                                )
                            )
                        ) {

                            card =
                                current;

                            break;
                        }

                        current =
                            current.parentElement;
                    }
                }

                const text =
                    (
                        card?.innerText
                        ||
                        card?.textContent
                        ||
                        anchor.parentElement?.innerText
                        ||
                        ""
                    ).trim();

                let ageText =
                    "";

                if (card) {

                    const nodes =
                        Array.from(
                            card.querySelectorAll(
                                "time, [aria-hidden='true'], span"
                            )
                        );

                    for (
                        const node
                        of nodes
                    ) {

                        const candidate =
                            (
                                node.innerText
                                ||
                                node.textContent
                                ||
                                ""
                            ).trim();

                        if (
                            /^(?:now|\d+\s*(?:m|h|d|w|mo|yr)s?)$/i
                                .test(candidate)
                            ||
                            /^\d+\s+(?:minute|hour|day|week|month|year)s?$/i
                                .test(candidate)
                        ) {

                            ageText =
                                candidate;

                            break;
                        }
                    }
                }

                results.push(
                    {
                        href,
                        text,
                        age_text:
                            ageText
                    }
                );
            }

            return results;
        }
        """
    )

    posts: list[
        dict[str, Any]
    ] = []

    seen: set[str] = set()

    for raw in raw_posts:

        if not isinstance(
            raw,
            dict,
        ):
            continue

        post_url = (
            normalize_post_url(
                raw.get(
                    "href"
                )
            )
        )

        if not post_url:
            continue

        if post_url in seen:
            continue

        post_text = re.sub(
            r"\s+",
            " ",
            str(
                raw.get(
                    "text"
                )
                or
                ""
            ),
        ).strip()

        if (
            len(post_text)
            <
            40
        ):
            continue

        posts.append(
            {
                "post_url":
                    post_url,

                "post_text":
                    post_text,

                "post_age_text":
                    str(
                        raw.get(
                            "age_text"
                        )
                        or
                        ""
                    ).strip(),
            }
        )

        seen.add(
            post_url
        )

        if (
            len(posts)
            >=
            MAX_POSTS_TO_INSPECT
        ):
            break

    return posts


# ==========================================================
# OPENAI
# ==========================================================

def get_openai_client() -> OpenAI | None:

    api_key = (
        os.getenv(
            "OPENAI_API_KEY"
        )
    )

    if not api_key:
        return None

    return OpenAI(
        api_key=
            api_key
    )


def parse_json_response(
    value: str,
) -> dict[str, Any]:

    text = value.strip()

    if text.startswith(
        "```"
    ):

        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=
                re.IGNORECASE,
        )

        text = re.sub(
            r"\s*```$",
            "",
            text,
        )

    parsed = json.loads(
        text
    )

    if not isinstance(
        parsed,
        dict,
    ):
        raise ValueError(
            "AI response was not a JSON object."
        )

    return parsed


def rank_post(
    client: OpenAI,
    preferences: Any,
    connection: dict[
        str,
        Any,
    ],
    post: dict[
        str,
        Any,
    ],
) -> dict[str, Any]:

    preference_text = (
        json.dumps(
            preferences,
            ensure_ascii=False,
        )[:12000]
    )

    post_text = str(
        post.get(
            "post_text"
        )
        or
        ""
    )[:12000]

    person_name = (
        connection.get(
            "name"
        )
        or
        "LinkedIn connection"
    )

    headline = (
        connection.get(
            "headline"
        )
        or
        ""
    )

    response = (
        client.responses.create(
            model=
                DEFAULT_OPENAI_MODEL,

            input=[
                {
                    "role":
                        "system",

                    "content":
                        (
                            "You are Network Scout, "
                            "a professional networking "
                            "relevance evaluator. "
                            "Decide whether a LinkedIn post "
                            "is meaningfully worth bringing "
                            "to a lawyer's attention for "
                            "relationship building and "
                            "professional networking. "
                            "Do not reward generic motivation, "
                            "simple congratulations, "
                            "repost-only content, "
                            "or weak relevance. "
                            "Return JSON only."
                        ),
                },
                {
                    "role":
                        "user",

                    "content":
                        f"""
NETWORKING PREFERENCES
{preference_text}

CONNECTION
Name: {person_name}
Headline: {headline}
Profile: {connection.get("profile_url", "")}

POST
URL: {post.get("post_url", "")}
Age: {post.get("post_age_text", "")}

Text:
{post_text}

Return exactly one JSON object:

{{
  "relevance_score": 0,
  "relevant": false,
  "post_summary": "1-2 sentence factual summary",
  "why_it_matters": "1-2 sentences explaining the networking value",
  "topics": ["short topic"]
}}

Set relevant=true only when
relevance_score is {RELEVANCE_THRESHOLD}
or higher.
                        """.strip(),
                },
            ],
        )
    )

    parsed = (
        parse_json_response(
            response.output_text
        )
    )

    score = max(
        0,
        min(
            100,
            int(
                parsed.get(
                    "relevance_score",
                    0,
                )
            ),
        ),
    )

    return {
        "relevance_score":
            score,

        "relevant":
            (
                score
                >=
                RELEVANCE_THRESHOLD
            ),

        "post_summary":
            str(
                parsed.get(
                    "post_summary"
                )
                or
                ""
            ).strip(),

        "why_it_matters":
            str(
                parsed.get(
                    "why_it_matters"
                )
                or
                ""
            ).strip(),

        "topics":
            (
                parsed.get(
                    "topics"
                )
                if isinstance(
                    parsed.get(
                        "topics"
                    ),
                    list,
                )
                else
                []
            ),
    }


# ==========================================================
# COMMENT DISCOVERY - PROVEN TEST LOGIC
# ==========================================================

def click_comments_entry_point(
    page: Page,
) -> bool:

    try:

        controls = page.locator(
            (
                "main button, "
                "main [role='button'], "
                "main a"
            )
        )

        count = min(
            controls.count(),
            400,
        )

    except Exception:

        return False

    matches: list[
        tuple[
            int,
            Any,
        ]
    ] = []

    for index in range(
        count
    ):

        control = (
            controls.nth(
                index
            )
        )

        try:

            if not control.is_visible():
                continue

            text = (
                normalize_text(
                    control.inner_text(
                        timeout=250
                    )
                )
            )

            aria = (
                normalize_text(
                    control.get_attribute(
                        "aria-label"
                    )
                )
            )

            label = (
                text
                or
                aria
            )

            lower = (
                label.lower()
            )

            priority = None

            if re.fullmatch(
                r"[\d,.]+\s+comments?",
                lower,
            ):

                priority = 0

            elif (
                "view"
                in lower
                and
                "comment"
                in lower
            ):

                priority = 1

            elif (
                "show"
                in lower
                and
                "comment"
                in lower
            ):

                priority = 1

            elif (
                lower
                ==
                "comment"
            ):

                priority = 2

            if (
                priority
                is not None
            ):

                matches.append(
                    (
                        priority,
                        control,
                    )
                )

        except Exception:

            continue

    matches.sort(
        key=lambda item:
            item[0]
    )

    for (
        _,
        control,
    ) in matches:

        try:

            control.scroll_into_view_if_needed(
                timeout=1500
            )

            control.click(
                timeout=2500
            )

            page.wait_for_timeout(
                800
            )

            return True

        except Exception:

            continue

    return False


def try_most_recent_comments(
    page: Page,
) -> bool:

    try:

        controls = page.locator(
            (
                "main button, "
                "main [role='button']"
            )
        )

        count = min(
            controls.count(),
            350,
        )

    except Exception:

        return False

    sort_control = None

    for index in range(
        count
    ):

        control = (
            controls.nth(
                index
            )
        )

        try:

            if not control.is_visible():
                continue

            text = (
                normalize_text(
                    control.inner_text(
                        timeout=250
                    )
                )
                .lower()
            )

            aria = (
                normalize_text(
                    control.get_attribute(
                        "aria-label"
                    )
                )
                .lower()
            )

            label = (
                text
                or
                aria
            )

            if (
                "most relevant"
                in label
                or
                (
                    "sort"
                    in label
                    and
                    "comment"
                    in label
                )
            ):

                sort_control = (
                    control
                )

                break

        except Exception:

            continue

    if (
        sort_control
        is None
    ):

        return False

    try:

        sort_control.click(
            timeout=2000
        )

        page.wait_for_timeout(
            350
        )

    except Exception:

        return False

    try:

        options = page.locator(
            (
                "[role='menuitem'], "
                "[role='option'], "
                "button"
            )
        )

        count = min(
            options.count(),
            400,
        )

    except Exception:

        return False

    for index in range(
        count
    ):

        option = (
            options.nth(
                index
            )
        )

        try:

            if not option.is_visible():
                continue

            text = (
                normalize_text(
                    option.inner_text(
                        timeout=250
                    )
                )
                .lower()
            )

            aria = (
                normalize_text(
                    option.get_attribute(
                        "aria-label"
                    )
                )
                .lower()
            )

            if (
                "most recent"
                in (
                    text
                    or
                    aria
                )
            ):

                option.click(
                    timeout=2000
                )

                page.wait_for_timeout(
                    700
                )

                return True

        except Exception:

            continue

    return False


def click_more_comments(
    page: Page,
) -> bool:

    patterns = [
        "load more comments",
        "show more comments",
        "view more comments",
        "more comments",
        "load previous comments",
        "previous comments",
        "see more comments",
    ]

    try:

        controls = page.locator(
            (
                "main button, "
                "main [role='button'], "
                "main a"
            )
        )

        count = min(
            controls.count(),
            450,
        )

    except Exception:

        return False

    for index in range(
        count
    ):

        control = (
            controls.nth(
                index
            )
        )

        try:

            if not control.is_visible():
                continue

            text = (
                normalize_text(
                    control.inner_text(
                        timeout=250
                    )
                )
                .lower()
            )

            aria = (
                normalize_text(
                    control.get_attribute(
                        "aria-label"
                    )
                )
                .lower()
            )

            label = (
                text
                or
                aria
            )

            if not any(
                pattern
                in label
                for pattern
                in patterns
            ):

                continue

            control.scroll_into_view_if_needed(
                timeout=1500
            )

            control.click(
                timeout=2500
            )

            page.wait_for_timeout(
                COMMENT_LOAD_WAIT_MS
            )

            return True

        except Exception:

            continue

    return False


def clean_commenter_name(
    anchor_text: str,
    aria_label: str,
) -> str | None:

    for raw in [
        anchor_text,
        aria_label,
    ]:

        value = (
            normalize_text(
                raw
            )
        )

        value = re.sub(
            r"^view\s+",
            "",
            value,
            flags=re.IGNORECASE,
        )

        value = re.sub(
            r"[’']s\s+profile$",
            "",
            value,
            flags=re.IGNORECASE,
        )

        value = re.sub(
            r"\s+profile$",
            "",
            value,
            flags=re.IGNORECASE,
        )

        if (
            2
            <=
            len(value)
            <=
            120
            and
            "linkedin"
            not in value.lower()
        ):

            return value

    return None


def clean_comment_text(
    card_text: str,
    name: str | None,
) -> str:

    ignored = {
        "like",
        "reply",
        "react",
        "more",
        "edited",
        "celebrate",
        "support",
        "love",
        "insightful",
        "funny",
    }

    output: list[str] = []

    for raw_line in str(
        card_text
        or
        ""
    ).splitlines():

        line = (
            normalize_text(
                raw_line
            )
        )

        if not line:
            continue

        lower = (
            line.lower()
        )

        if (
            name
            and
            lower
            ==
            name.lower()
        ):

            continue

        if (
            lower
            in ignored
        ):

            continue

        if re.fullmatch(
            r"\d+\s*(?:m|h|d|w|mo|yr)",
            lower,
        ):

            continue

        if (
            "degree connection"
            in lower
        ):

            continue

        output.append(
            line
        )

    return (
        normalize_text(
            " ".join(
                output
            )
        )[:1200]
    )


def extract_visible_commenters(
    page: Page,
) -> list[
    dict[str, Any]
]:

    raw = page.evaluate(
        r"""
        () => {

            const root =
                document.querySelector(
                    "main"
                )
                ||
                document.body;


            if (!root) {
                return [];
            }


            const visible =
                (element) => {

                    if (!element) {
                        return false;
                    }


                    const rect =
                        element
                            .getBoundingClientRect();


                    const style =
                        window
                            .getComputedStyle(
                                element
                            );


                    return (
                        rect.width > 0
                        &&
                        rect.height > 0
                        &&
                        style.display
                            !==
                            "none"
                        &&
                        style.visibility
                            !==
                            "hidden"
                    );
                };


            const results =
                [];


            const profileAnchors =
                Array.from(
                    root.querySelectorAll(
                        "a[href*='/in/']"
                    )
                )
                    .filter(
                        visible
                    );


            for (
                const anchor
                of profileAnchors
            ) {

                let current =
                    anchor;


                let commentCard =
                    null;


                for (
                    let depth = 0;
                    depth < 12;
                    depth += 1
                ) {

                    if (
                        !current
                        ||
                        current === root
                    ) {

                        break;
                    }


                    const text =
                        (
                            current.innerText
                            ||
                            current.textContent
                            ||
                            ""
                        )
                            .trim();


                    if (
                        text.length < 12
                        ||
                        text.length > 4500
                    ) {

                        current =
                            current.parentElement;


                        continue;
                    }


                    const className =
                        String(
                            current.className
                            ||
                            ""
                        )
                            .toLowerCase();


                    const controls =
                        Array.from(
                            current.querySelectorAll(
                                (
                                    "button, "
                                    +
                                    "[role='button']"
                                )
                            )
                        )
                            .filter(
                                visible
                            );


                    const labels =
                        controls.map(
                            (button) => (

                                button.getAttribute(
                                    "aria-label"
                                )
                                ||
                                button.innerText
                                ||
                                button.textContent
                                ||
                                ""

                            )
                                .trim()
                                .toLowerCase()
                        );


                    const classSignal =
                        className.includes(
                            "comment"
                        );


                    const replySignal =
                        labels.some(
                            (label) =>
                                label.includes(
                                    "reply"
                                )
                        );


                    const reactionSignal =
                        labels.some(
                            (label) =>

                                label.includes(
                                    "react"
                                )
                                ||
                                label.includes(
                                    "like"
                                )
                        );


                    if (
                        classSignal
                        ||
                        replySignal
                        ||
                        reactionSignal
                    ) {

                        commentCard =
                            current;


                        break;
                    }


                    current =
                        current.parentElement;
                }


                if (
                    !commentCard
                ) {

                    continue;
                }


                const anchors =
                    Array.from(
                        commentCard.querySelectorAll(
                            "a[href*='/in/']"
                        )
                    )
                        .filter(
                            visible
                        );


                if (
                    anchors.length === 0
                ) {

                    continue;
                }


                anchors.sort(
                    (
                        first,
                        second
                    ) => {

                        const firstRect =
                            first
                                .getBoundingClientRect();


                        const secondRect =
                            second
                                .getBoundingClientRect();


                        if (
                            Math.abs(
                                firstRect.top
                                -
                                secondRect.top
                            )
                            >
                            4
                        ) {

                            return (
                                firstRect.top
                                -
                                secondRect.top
                            );
                        }


                        return (
                            firstRect.left
                            -
                            secondRect.left
                        );
                    }
                );


                const author =
                    anchors[0];


                results.push(
                    {
                        href:
                            author.href
                            ||
                            "",

                        anchor_text:
                            (
                                author.innerText
                                ||
                                author.textContent
                                ||
                                ""
                            )
                                .trim(),

                        aria:
                            (
                                author.getAttribute(
                                    "aria-label"
                                )
                                ||
                                ""
                            )
                                .trim(),

                        card_text:
                            (
                                commentCard.innerText
                                ||
                                commentCard.textContent
                                ||
                                ""
                            )
                                .trim()
                    }
                );
            }


            return results;
        }
        """
    )

    output: list[
        dict[str, Any]
    ] = []

    seen: set[str] = set()

    if not isinstance(
        raw,
        list,
    ):

        return output

    for item in raw:

        if not isinstance(
            item,
            dict,
        ):

            continue

        profile_url = (
            normalize_profile_url(
                item.get(
                    "href"
                )
            )
        )

        if (
            not profile_url
            or
            profile_url
            in seen
        ):

            continue

        name = (
            clean_commenter_name(
                str(
                    item.get(
                        "anchor_text"
                    )
                    or
                    ""
                ),
                str(
                    item.get(
                        "aria"
                    )
                    or
                    ""
                ),
            )
        )

        output.append(
            {
                "profile_url":
                    profile_url,

                "name":
                    name,

                "comment_text":
                    clean_comment_text(
                        str(
                            item.get(
                                "card_text"
                            )
                            or
                            ""
                        ),
                        name,
                    ),
            }
        )

        seen.add(
            profile_url
        )

    return output


def discover_commenters(
    page: Page,
    post_url: str,
    max_commenters: int,
) -> list[
    dict[str, Any]
]:

    page.goto(
        post_url,
        wait_until=
            "domcontentloaded",
        timeout=
            PAGE_TIMEOUT_MS,
    )

    page.wait_for_timeout(
        PAGE_SETTLE_MS
    )

    attention = (
        detect_linkedin_attention(
            page
        )
    )

    if attention:

        raise RuntimeError(
            attention
        )

    click_comments_entry_point(
        page
    )

    try_most_recent_comments(
        page
    )

    discovered: dict[
        str,
        dict[str, Any],
    ] = {}

    for _ in range(
        MAX_COMMENT_LOAD_CLICKS
        +
        1
    ):

        current = (
            extract_visible_commenters(
                page
            )
        )

        for person in current:

            discovered.setdefault(
                person[
                    "profile_url"
                ],
                person,
            )

            if (
                len(
                    discovered
                )
                >=
                max_commenters
            ):

                break

        if (
            len(
                discovered
            )
            >=
            max_commenters
        ):

            break

        clicked = (
            click_more_comments(
                page
            )
        )

        if not clicked:

            try:

                page.mouse.wheel(
                    0,
                    1000,
                )

            except Exception:

                pass

            page.wait_for_timeout(
                600
            )

            before = len(
                discovered
            )

            for person in (
                extract_visible_commenters(
                    page
                )
            ):

                discovered.setdefault(
                    person[
                        "profile_url"
                    ],
                    person,
                )

            if (
                len(
                    discovered
                )
                ==
                before
            ):

                break

    return list(
        discovered.values()
    )[:max_commenters]


# ==========================================================
# COMMENTER FILTERING
# ==========================================================

def filter_commenters_for_candidates(
    commenters: list[
        dict[str, Any]
    ],
    source_connection: dict[
        str,
        Any,
    ],
    monitored_urls: set[str],
    tracked_urls: set[str],
    known_candidate_urls: set[str],
) -> tuple[
    list[
        dict[str, Any]
    ],
    dict[str, int],
]:

    source_profile_url = (
        normalize_profile_url(
            source_connection.get(
                "profile_url"
            )
        )
    )

    eligible: list[
        dict[str, Any]
    ] = []

    counts = {
        "total_commenters":
            len(
                commenters
            ),

        "post_author_removed":
            0,

        "existing_connections_removed":
            0,

        "tracked_removed":
            0,

        "existing_candidates_removed":
            0,

        "eligible":
            0,
    }

    seen: set[str] = set()

    for commenter in commenters:

        profile_url = (
            normalize_profile_url(
                commenter.get(
                    "profile_url"
                )
            )
        )

        if not profile_url:
            continue

        if profile_url in seen:
            continue

        seen.add(
            profile_url
        )

        if (
            source_profile_url
            and
            profile_url
            ==
            source_profile_url
        ):

            counts[
                "post_author_removed"
            ] += 1

            continue

        if (
            profile_url
            in monitored_urls
        ):

            counts[
                "existing_connections_removed"
            ] += 1

            continue

        if (
            profile_url
            in tracked_urls
        ):

            counts[
                "tracked_removed"
            ] += 1

            continue

        if (
            profile_url
            in known_candidate_urls
        ):

            counts[
                "existing_candidates_removed"
            ] += 1

            continue

        eligible.append(
            {
                **commenter,
                "profile_url":
                    profile_url,
            }
        )

    counts[
        "eligible"
    ] = len(
        eligible
    )

    return (
        eligible,
        counts,
    )


# ==========================================================
# TEST COMMENT DISCOVERY PREVIEW
# ==========================================================

def save_test_discovery_preview(
    source_connection: dict[
        str,
        Any,
    ],
    post: dict[
        str,
        Any,
    ],
    ranking: dict[
        str,
        Any,
    ],
    commenters: list[
        dict[str, Any]
    ],
    eligible_commenters: list[
        dict[str, Any]
    ],
    filter_counts: dict[
        str,
        int,
    ],
) -> None:

    payload = {
        "test_mode":
            True,

        "created_at":
            utc_now(),

        "important":
            (
                "Preview only. "
                "No candidates or notifications "
                "were created from this test."
            ),

        "source_connection": {
            "name":
                source_connection.get(
                    "name"
                ),

            "profile_url":
                source_connection.get(
                    "profile_url"
                ),

            "headline":
                source_connection.get(
                    "headline"
                ),
        },

        "post": {
            "post_url":
                post.get(
                    "post_url"
                ),

            "post_age_text":
                post.get(
                    "post_age_text"
                ),

            "post_text":
                post.get(
                    "post_text"
                ),

            "relevance_score":
                ranking.get(
                    "relevance_score"
                ),

            "post_summary":
                ranking.get(
                    "post_summary"
                ),

            "why_it_matters":
                ranking.get(
                    "why_it_matters"
                ),
        },

        "filter_counts":
            filter_counts,

        "commenters_found":
            commenters,

        "eligible_new_candidates":
            eligible_commenters,
    }

    write_json(
        TEST_COMMENT_DISCOVERY_FILE,
        payload,
    )


# ==========================================================
# REAL CANDIDATE CREATION
# ==========================================================

def stable_candidate_id(
    profile_url: str,
) -> str:

    digest = (
        hashlib.sha1(
            profile_url.encode(
                "utf-8"
            )
        )
        .hexdigest()
    )

    return (
        "candidate_"
        +
        digest[:16]
    )


def build_comment_candidate(
    commenter: dict[
        str,
        Any,
    ],
    source_connection: dict[
        str,
        Any,
    ],
    post: dict[
        str,
        Any,
    ],
    ranking: dict[
        str,
        Any,
    ],
) -> dict[str, Any]:

    now = utc_now()

    profile_url = str(
        commenter[
            "profile_url"
        ]
    )

    source = {
        "discovery_method":
            "relevant_post_commenter",

        "source_connection_name":
            source_connection.get(
                "name"
            ),

        "source_connection_profile_url":
            source_connection.get(
                "profile_url"
            ),

        "source_post_url":
            post.get(
                "post_url"
            ),

        "source_post_summary":
            ranking.get(
                "post_summary"
            ),

        "source_post_relevance_score":
            ranking.get(
                "relevance_score"
            ),

        "source_comment_text":
            commenter.get(
                "comment_text"
            ),

        "discovered_at":
            now,
    }

    return {
        "candidate_id":
            stable_candidate_id(
                profile_url
            ),

        "name":
            (
                commenter.get(
                    "name"
                )
                or
                "LinkedIn commenter"
            ),

        "profile_url":
            profile_url,

        "linkedin_url":
            profile_url,

        "headline":
            None,

        "discovery_method":
            "relevant_post_commenter",

        "source":
            "relevant_post_commenter",

        "sources":
            [
                source
            ],

        "source_connection_name":
            source_connection.get(
                "name"
            ),

        "source_connection_profile_url":
            source_connection.get(
                "profile_url"
            ),

        "source_post_url":
            post.get(
                "post_url"
            ),

        "source_post_summary":
            ranking.get(
                "post_summary"
            ),

        "source_post_relevance_score":
            ranking.get(
                "relevance_score"
            ),

        "source_comment_text":
            commenter.get(
                "comment_text"
            ),

        "discovered_at":
            now,

        "last_discovered_at":
            now,

        "status":
            "pending_enrichment",

        "enrichment_status":
            "pending",

        "ranking_status":
            "pending",
    }


# ==========================================================
# OPPORTUNITIES
# ==========================================================

def load_list_file(
    path: Path,
) -> list[
    dict[str, Any]
]:

    payload = read_json(
        path,
        [],
    )

    return extract_records(
        payload,
        [
            "opportunities",
            "items",
        ],
    )


def stable_opportunity_id(
    post_url: str,
) -> str:

    digest = (
        hashlib.sha1(
            post_url.encode(
                "utf-8"
            )
        )
        .hexdigest()
    )

    return (
        "post_"
        +
        digest[:16]
    )


def build_raw_record(
    connection: dict[
        str,
        Any,
    ],
    post: dict[
        str,
        Any,
    ],
) -> dict[str, Any]:

    now = utc_now()

    person_name = (
        connection.get(
            "name"
        )
        or
        "LinkedIn connection"
    )

    post_url = str(
        post[
            "post_url"
        ]
    )

    return {
        "opportunity_id":
            stable_opportunity_id(
                post_url
            ),

        "type":
            "linkedin_post",

        "notification_type":
            "relevant_post",

        "person_name":
            person_name,

        "name":
            person_name,

        "profile_url":
            connection.get(
                "profile_url"
            ),

        "headline":
            connection.get(
                "headline"
            ),

        "relationship_source":
            connection.get(
                "relationship_source"
            ),

        "post_url":
            post_url,

        "post_text":
            post.get(
                "post_text"
            ),

        "post_age_text":
            post.get(
                "post_age_text"
            ),

        "detected_at":
            now,

        "created_at":
            now,

        "status":
            "detected",
    }


def build_ranked_record(
    raw_record: dict[
        str,
        Any,
    ],
    ranking: dict[
        str,
        Any,
    ],
) -> dict[str, Any]:

    score = int(
        ranking.get(
            "relevance_score",
            0,
        )
    )

    summary = str(
        ranking.get(
            "post_summary"
        )
        or
        ""
    ).strip()

    why_it_matters = str(
        ranking.get(
            "why_it_matters"
        )
        or
        ""
    ).strip()

    return {
        **raw_record,

        "relevance_score":
            score,

        "score":
            score,

        "relevant":
            bool(
                ranking.get(
                    "relevant"
                )
            ),

        "post_summary":
            summary,

        "summary":
            summary,

        "why_it_matters":
            why_it_matters,

        "reason":
            why_it_matters,

        "topics":
            (
                ranking.get(
                    "topics"
                )
                or
                []
            ),

        "status":
            "new",

        "read":
            False,

        "engagement_status":
            "pending",

        "ranked_at":
            utc_now(),
    }


def upsert_by_post_url(
    records: list[
        dict[str, Any]
    ],
    record: dict[
        str,
        Any,
    ],
) -> list[
    dict[str, Any]
]:

    post_url = (
        record.get(
            "post_url"
        )
    )

    output = []

    replaced = False

    for existing in records:

        if (
            post_url
            and
            existing.get(
                "post_url"
            )
            ==
            post_url
        ):

            output.append(
                {
                    **existing,
                    **record,
                }
            )

            replaced = True

        else:

            output.append(
                existing
            )

    if not replaced:

        output.append(
            record
        )

    return output


# ==========================================================
# ROTATING BATCH
# ==========================================================

def select_batch(
    connections: list[
        dict[str, Any]
    ],
    state: dict[
        str,
        Any,
    ],
    limit: int,
) -> tuple[
    list[
        dict[str, Any]
    ],
    int,
]:

    total = len(
        connections
    )

    if total == 0:

        return (
            [],
            0,
        )

    limit = max(
        1,
        min(
            limit,
            total,
        ),
    )

    start = int(
        state.get(
            "next_index",
            0,
        )
    ) % total

    batch = [
        connections[
            (
                start
                +
                offset
            )
            %
            total
        ]
        for offset in range(
            limit
        )
    ]

    next_index = (
        start
        +
        limit
    ) % total

    return (
        batch,
        next_index,
    )


# ==========================================================
# NEW POSTS
# ==========================================================

def choose_new_posts(
    posts: list[
        dict[str, Any]
    ],
    previous_post_url: str | None,
    include_current: bool,
) -> list[
    dict[str, Any]
]:

    if not posts:
        return []

    if not previous_post_url:

        if include_current:

            return [
                posts[0]
            ]

        return []

    new_posts = []

    for post in posts:

        if (
            post.get(
                "post_url"
            )
            ==
            previous_post_url
        ):

            break

        new_posts.append(
            post
        )

    if (
        len(
            new_posts
        )
        ==
        len(
            posts
        )
    ):

        return [
            posts[0]
        ]

    return new_posts


# ==========================================================
# MAIN MONITOR
# ==========================================================

def run_monitor(
    headless: bool,
    limit: int,
    include_current: bool,
    max_commenters: int,
    test_comment_discovery: bool,
) -> None:

    load_dotenv(
        PROJECT_ROOT
        /
        ".env"
    )

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    connections = (
        load_monitored_connections()
    )

    if not connections:

        print(
            "[POSTS] No monitored connections found."
        )

        return

    state = (
        load_state()
    )

    (
        batch,
        next_index,
    ) = (
        select_batch(
            connections,
            state,
            limit,
        )
    )

    raw_records = (
        load_list_file(
            RAW_OPPORTUNITIES_FILE
        )
    )

    ranked_records = (
        load_list_file(
            RANKED_OPPORTUNITIES_FILE
        )
    )

    preferences = (
        read_json(
            NETWORKING_PREFERENCES_FILE,
            {},
        )
    )

    client = (
        get_openai_client()
    )

    monitored_urls = {
        str(
            connection[
                "profile_url"
            ]
        )
        for connection
        in connections
        if connection.get(
            "profile_url"
        )
    }

    tracked_urls = (
        load_tracked_profile_urls()
    )

    (
        candidate_payload,
        candidate_records,
        candidate_list_key,
    ) = (
        load_candidate_payload()
    )

    known_candidate_urls = (
        candidate_profile_urls(
            candidate_records
        )
    )

    print(
        (
            f"[POSTS] Monitoring "
            f"{len(batch)} of "
            f"{len(connections)} "
            "connections this run."
        )
    )

    if test_comment_discovery:

        print(
            (
                "[TEST DISCOVERY] Preview mode ON. "
                "No candidates or notifications "
                "will be permanently created."
            )
        )

    checked = 0

    posts_found = 0

    new_posts_found = 0

    relevant_found = 0

    commenters_seen = 0

    commenter_candidates_added = 0

    test_completed = False


    with sync_playwright() as playwright:

        context = (
            playwright.chromium
            .launch_persistent_context(
                user_data_dir=
                    str(
                        BROWSER_PROFILE_DIR
                    ),

                headless=
                    headless,

                viewport={
                    "width":
                        1440,

                    "height":
                        1000,
                },
            )
        )

        try:

            page = (
                context.pages[0]
                if context.pages
                else
                context.new_page()
            )


            for (
                position,
                connection,
            ) in enumerate(
                batch,
                start=1,
            ):

                profile_url = str(
                    connection[
                        "profile_url"
                    ]
                )

                person_name = (
                    connection.get(
                        "name"
                    )
                    or
                    "LinkedIn connection"
                )

                print()

                print(
                    (
                        f"[POSTS] "
                        f"{position}/"
                        f"{len(batch)} "
                        f"{person_name}"
                    )
                )

                profile_state = (
                    state[
                        "profiles"
                    ]
                    .setdefault(
                        profile_url,
                        {},
                    )
                )

                try:

                    has_posts_tab = (
                        open_posts_activity(
                            page,
                            profile_url,
                        )
                    )

                    checked += 1

                    profile_state[
                        "last_checked_at"
                    ] = utc_now()

                    if not has_posts_tab:

                        print(
                            "[POSTS]   No Posts tab found."
                        )

                        profile_state[
                            "last_result"
                        ] = (
                            "no_posts_tab"
                        )

                        save_state(
                            state
                        )

                        continue

                    posts = (
                        extract_recent_posts(
                            page
                        )
                    )

                    posts_found += (
                        len(
                            posts
                        )
                    )

                    if not posts:

                        print(
                            (
                                "[POSTS]   "
                                "No recent authored posts found."
                            )
                        )

                        profile_state[
                            "last_result"
                        ] = (
                            "no_recent_posts"
                        )

                        save_state(
                            state
                        )

                        continue


                    # ==================================================
                    # TEST MODE
                    # ==================================================

                    if test_comment_discovery:

                        for test_post in posts:

                            print(
                                (
                                    "[TEST DISCOVERY] "
                                    "Trying real post: "
                                    f"{test_post['post_url']}"
                                )
                            )

                            if client:

                                try:

                                    ranking = (
                                        rank_post(
                                            client=
                                                client,

                                            preferences=
                                                preferences,

                                            connection=
                                                connection,

                                            post=
                                                test_post,
                                        )
                                    )

                                except Exception as error:

                                    print(
                                        (
                                            "[TEST DISCOVERY] "
                                            "AI ranking failed: "
                                            f"{error}"
                                        )
                                    )

                                    ranking = {
                                        "relevance_score":
                                            0,

                                        "relevant":
                                            False,

                                        "post_summary":
                                            "",

                                        "why_it_matters":
                                            "",

                                        "topics":
                                            [],
                                    }

                            else:

                                ranking = {
                                    "relevance_score":
                                        0,

                                    "relevant":
                                        False,

                                    "post_summary":
                                        "",

                                    "why_it_matters":
                                        "",

                                    "topics":
                                        [],
                                }

                            print(
                                (
                                    "[TEST DISCOVERY] "
                                    "Post score: "
                                    f"{ranking['relevance_score']}/100"
                                )
                            )

                            commenters = (
                                discover_commenters(
                                    page=
                                        page,

                                    post_url=
                                        str(
                                            test_post[
                                                "post_url"
                                            ]
                                        ),

                                    max_commenters=
                                        max_commenters,
                                )
                            )

                            if not commenters:

                                print(
                                    (
                                        "[TEST DISCOVERY] "
                                        "No visible commenters. "
                                        "Trying another post/profile."
                                    )
                                )

                                continue

                            commenters_seen += (
                                len(
                                    commenters
                                )
                            )

                            (
                                eligible,
                                filter_counts,
                            ) = (
                                filter_commenters_for_candidates(
                                    commenters=
                                        commenters,

                                    source_connection=
                                        connection,

                                    monitored_urls=
                                        monitored_urls,

                                    tracked_urls=
                                        tracked_urls,

                                    known_candidate_urls=
                                        known_candidate_urls,
                                )
                            )

                            print(
                                (
                                    "[TEST DISCOVERY] Found "
                                    f"{len(commenters)} "
                                    "unique visible commenters."
                                )
                            )

                            print(
                                (
                                    "[TEST DISCOVERY] "
                                    f"{len(eligible)} "
                                    "would qualify as new candidates."
                                )
                            )

                            save_test_discovery_preview(
                                source_connection=
                                    connection,

                                post=
                                    test_post,

                                ranking=
                                    ranking,

                                commenters=
                                    commenters,

                                eligible_commenters=
                                    eligible,

                                filter_counts=
                                    filter_counts,
                            )

                            print(
                                (
                                    "[TEST DISCOVERY] Preview saved to: "
                                    f"{TEST_COMMENT_DISCOVERY_FILE}"
                                )
                            )

                            test_completed = True

                            break

                        if test_completed:
                            break

                        continue


                    # ==================================================
                    # PRODUCTION MODE
                    # ==================================================

                    latest_post_url = str(
                        posts[0][
                            "post_url"
                        ]
                    )

                    previous_post_url = (
                        profile_state.get(
                            "last_seen_post_url"
                        )
                    )

                    new_posts = (
                        choose_new_posts(
                            posts=
                                posts,

                            previous_post_url=
                                previous_post_url,

                            include_current=
                                include_current,
                        )
                    )

                    if (
                        previous_post_url
                        is None
                        and
                        not include_current
                    ):

                        print(
                            (
                                "[POSTS]   "
                                "Baseline saved. "
                                "No historical alert created."
                            )
                        )

                    elif not new_posts:

                        print(
                            "[POSTS]   No new post."
                        )

                    for post in reversed(
                        new_posts
                    ):

                        new_posts_found += 1

                        raw_record = (
                            build_raw_record(
                                connection,
                                post,
                            )
                        )

                        raw_records = (
                            upsert_by_post_url(
                                raw_records,
                                raw_record,
                            )
                        )

                        write_json(
                            RAW_OPPORTUNITIES_FILE,
                            raw_records,
                        )

                        print(
                            (
                                "[POSTS]   New post: "
                                f"{post['post_url']}"
                            )
                        )

                        if client is None:

                            print(
                                (
                                    "[AI]      "
                                    "OPENAI_API_KEY is missing. "
                                    "Skipping ranking."
                                )
                            )

                            continue

                        try:

                            ranking = (
                                rank_post(
                                    client=
                                        client,

                                    preferences=
                                        preferences,

                                    connection=
                                        connection,

                                    post=
                                        post,
                                )
                            )

                        except Exception as error:

                            print(
                                (
                                    "[AI]      "
                                    "Ranking failed: "
                                    f"{error}"
                                )
                            )

                            continue

                        score = int(
                            ranking[
                                "relevance_score"
                            ]
                        )

                        print(
                            (
                                "[AI]      "
                                "Relevance score: "
                                f"{score}/100"
                            )
                        )

                        # ==============================================
                        # IMPORTANT:
                        # Comment discovery happens ONLY after
                        # relevance >= 75.
                        # ==============================================

                        if not ranking[
                            "relevant"
                        ]:

                            print(
                                (
                                    "[AI]      "
                                    "Not notification-worthy. "
                                    "Skipping comment discovery."
                                )
                            )

                            continue

                        relevant_found += 1

                        ranked_record = (
                            build_ranked_record(
                                raw_record,
                                ranking,
                            )
                        )

                        ranked_records = (
                            upsert_by_post_url(
                                ranked_records,
                                ranked_record,
                            )
                        )

                        write_json(
                            RANKED_OPPORTUNITIES_FILE,
                            ranked_records,
                        )

                        print(
                            (
                                "[AI]      "
                                "Added to Notifications feed."
                            )
                        )

                        post_url = str(
                            post[
                                "post_url"
                            ]
                        )

                        post_state = (
                            state[
                                "posts"
                            ]
                            .setdefault(
                                post_url,
                                {},
                            )
                        )

                        try:

                            commenters = (
                                discover_commenters(
                                    page=
                                        page,

                                    post_url=
                                        post_url,

                                    max_commenters=
                                        max_commenters,
                                )
                            )

                            commenters_seen += (
                                len(
                                    commenters
                                )
                            )

                            print(
                                (
                                    "[DISCOVERY] Found "
                                    f"{len(commenters)} "
                                    "unique visible commenters."
                                )
                            )

                            (
                                eligible,
                                filter_counts,
                            ) = (
                                filter_commenters_for_candidates(
                                    commenters=
                                        commenters,

                                    source_connection=
                                        connection,

                                    monitored_urls=
                                        monitored_urls,

                                    tracked_urls=
                                        tracked_urls,

                                    known_candidate_urls=
                                        known_candidate_urls,
                                )
                            )

                            added = 0

                            for commenter in eligible:

                                candidate = (
                                    build_comment_candidate(
                                        commenter=
                                            commenter,

                                        source_connection=
                                            connection,

                                        post=
                                            post,

                                        ranking=
                                            ranking,
                                    )
                                )

                                candidate_records.append(
                                    candidate
                                )

                                known_candidate_urls.add(
                                    str(
                                        commenter[
                                            "profile_url"
                                        ]
                                    )
                                )

                                added += 1

                            if added:

                                save_candidate_records(
                                    original_payload=
                                        candidate_payload,

                                    records=
                                        candidate_records,

                                    list_key=
                                        candidate_list_key,
                                )

                            commenter_candidates_added += (
                                added
                            )

                            print(
                                (
                                    "[DISCOVERY] Added "
                                    f"{added} new people "
                                    "to candidates.json."
                                )
                            )

                            print(
                                (
                                    "[DISCOVERY] Filtered: "
                                    f"existing connections="
                                    f"{filter_counts['existing_connections_removed']}, "
                                    f"tracked="
                                    f"{filter_counts['tracked_removed']}, "
                                    f"existing candidates="
                                    f"{filter_counts['existing_candidates_removed']}."
                                )
                            )

                            post_state[
                                "comment_discovery_status"
                            ] = (
                                "completed"
                            )

                            post_state[
                                "commenters_seen"
                            ] = (
                                len(
                                    commenters
                                )
                            )

                            post_state[
                                "new_candidates_added"
                            ] = (
                                added
                            )

                            post_state[
                                "comment_discovered_at"
                            ] = (
                                utc_now()
                            )

                            save_state(
                                state
                            )

                        except RuntimeError:

                            raise

                        except Exception as error:

                            print(
                                (
                                    "[DISCOVERY] "
                                    "Comment discovery failed: "
                                    f"{error}"
                                )
                            )

                            post_state[
                                "comment_discovery_status"
                            ] = (
                                "failed"
                            )

                            post_state[
                                "comment_discovery_error"
                            ] = (
                                str(
                                    error
                                )
                            )

                            post_state[
                                "comment_discovered_at"
                            ] = (
                                utc_now()
                            )

                            save_state(
                                state
                            )

                    profile_state[
                        "last_seen_post_url"
                    ] = (
                        latest_post_url
                    )

                    profile_state[
                        "last_seen_post_at"
                    ] = (
                        utc_now()
                    )

                    profile_state[
                        "last_result"
                    ] = (
                        "new_posts"
                        if new_posts
                        else
                        "no_change"
                    )

                    save_state(
                        state
                    )

                except RuntimeError as error:

                    print(
                        f"[ERROR]   {error}"
                    )

                    profile_state[
                        "last_result"
                    ] = (
                        "needs_attention"
                    )

                    profile_state[
                        "last_error"
                    ] = (
                        str(
                            error
                        )
                    )

                    save_state(
                        state
                    )

                    break

                except PlaywrightTimeoutError:

                    print(
                        (
                            "[ERROR]   "
                            "LinkedIn timed out "
                            "for this profile."
                        )
                    )

                    profile_state[
                        "last_result"
                    ] = (
                        "timeout"
                    )

                    save_state(
                        state
                    )

                except Exception as error:

                    print(
                        (
                            "[ERROR]   "
                            "Post check failed: "
                            f"{error}"
                        )
                    )

                    profile_state[
                        "last_result"
                    ] = (
                        "failed"
                    )

                    profile_state[
                        "last_error"
                    ] = (
                        str(
                            error
                        )
                    )

                    save_state(
                        state
                    )

                page.wait_for_timeout(
                    700
                )

        finally:

            context.close()


    # ======================================================
    # TEST MODE DOES NOT ADVANCE PRODUCTION CURSOR
    # ======================================================

    if not test_comment_discovery:

        state[
            "next_index"
        ] = (
            next_index
        )

        state[
            "last_run_at"
        ] = (
            utc_now()
        )

        state[
            "last_run"
        ] = {
            "monitored_connection_total":
                len(
                    connections
                ),

            "checked":
                checked,

            "posts_found":
                posts_found,

            "new_posts_found":
                new_posts_found,

            "relevant_found":
                relevant_found,

            "commenters_seen":
                commenters_seen,

            "commenter_candidates_added":
                commenter_candidates_added,
        }

        save_state(
            state
        )


    print()

    print(
        "===================================="
    )

    if test_comment_discovery:

        print(
            "NETWORK SCOUT TEST DISCOVERY"
        )

    else:

        print(
            "NETWORK SCOUT POST MONITOR"
        )

    print(
        "===================================="
    )

    print(
        (
            "Total monitored connections: "
            f"{len(connections)}"
        )
    )

    print(
        (
            "Connections checked: "
            f"{checked}"
        )
    )

    if test_comment_discovery:

        print(
            (
                "Test completed: "
                f"{test_completed}"
            )
        )

        print(
            (
                "Commenters seen: "
                f"{commenters_seen}"
            )
        )

        print(
            (
                "Preview file: "
                f"{TEST_COMMENT_DISCOVERY_FILE}"
            )
        )

        print(
            "Production candidates modified: NO"
        )

        print(
            "Production notifications modified: NO"
        )

    else:

        print(
            (
                "Recent posts inspected: "
                f"{posts_found}"
            )
        )

        print(
            (
                "New posts detected: "
                f"{new_posts_found}"
            )
        )

        print(
            (
                "Relevant posts: "
                f"{relevant_found}"
            )
        )

        print(
            (
                "Relevant-post commenters seen: "
                f"{commenters_seen}"
            )
        )

        print(
            (
                "New commenter candidates added: "
                f"{commenter_candidates_added}"
            )
        )

        print(
            (
                "Next connection cursor: "
                f"{next_index}"
            )
        )


# ==========================================================
# CLI
# ==========================================================

def parse_arguments() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Monitor Network Scout connections "
            "for relevant LinkedIn posts and "
            "discover potential new professionals "
            "from relevant comment sections."
        )
    )

    parser.add_argument(
        "--headful",
        action="store_true",
        help=(
            "Show Chromium while monitoring."
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=
            DEFAULT_BATCH_SIZE,
        help=(
            "Number of monitored connections "
            "to check in this run. "
            "This is only the batch size, "
            "not the total number of connections."
        ),
    )

    parser.add_argument(
        "--include-current",
        action="store_true",
        help=(
            "Evaluate the newest current post "
            "during initial testing."
        ),
    )

    parser.add_argument(
        "--max-commenters",
        type=int,
        default=
            MAX_COMMENTERS_PER_POST,
        help=(
            "Maximum unique commenters "
            "to inspect per relevant post."
        ),
    )

    parser.add_argument(
        "--test-comment-discovery",
        action="store_true",
        help=(
            "Preview the proven commenter extractor "
            "using a real post without changing "
            "production candidates or notifications."
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

    run_monitor(
        headless=
            not args.headful,

        limit=
            max(
                1,
                args.limit,
            ),

        include_current=
            args.include_current,

        max_commenters=
            max(
                1,
                args.max_commenters,
            ),

        test_comment_discovery=
            args.test_comment_discovery,
    )


if __name__ == "__main__":
    main()