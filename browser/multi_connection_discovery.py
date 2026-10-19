import hashlib
import json
import re

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright


# ======================================================
# PROJECT PATHS
# ======================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

BROWSER_PROFILE = (
    PROJECT_ROOT
    / "browser_data"
    / "lawyer_profile"
)

CANDIDATE_FILE = (
    PROJECT_ROOT
    / "data"
    / "candidates.json"
)

TRACKED_CONNECTIONS_FILE = (
    PROJECT_ROOT
    / "data"
    / "tracked_connections.json"
)

OLD_SEED_BACKUP_FILE = (
    PROJECT_ROOT
    / "data"
    / "tracked_connections_before_15_seed.json"
)


# ======================================================
# LINKEDIN URLS
# ======================================================

CONNECTIONS_URL = (
    "https://www.linkedin.com/"
    "mynetwork/invite-connect/connections/"
)


# ======================================================
# SETTINGS
# ======================================================

# We now seed / process 15 connections.
INITIAL_CONNECTION_COUNT = 10

MAX_CONNECTIONS_PER_RUN = 10

# For candidate discovery, inspect at most
# the first 10 recent activity posts.
MAX_DISCOVERY_POSTS_PER_CONNECTION = 10

# New seed version because we have moved from
# the 10-connection design to the 15-connection design.
CURRENT_SEED_VERSION = 3

PAGE_LOAD_WAIT_MS = 4500

CONNECTION_SCROLL_WAIT_MS = 1500

MAX_CONNECTION_SCROLL_ROUNDS = 12

ACTIVITY_LOAD_WAIT_MS = 1800

MAX_ACTIVITY_LOAD_ROUNDS = 8

MAX_ACTIVITY_STAGNANT_ROUNDS = 2

MAX_COMMENT_LOAD_ROUNDS = 20

MAX_STAGNANT_ROUNDS = 4

COMMENT_LOAD_WAIT_MS = 1600


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
# URL HELPERS
# ======================================================

def clean_url(
    url
):

    if not url:
        return None

    url = urljoin(
        "https://www.linkedin.com",
        url
    )

    url = url.split(
        "?"
    )[0]

    url = url.split(
        "#"
    )[0]

    return url


def normalize_profile_url(
    url
):

    if not url:
        return None

    url = clean_url(
        url
    )

    match = re.search(
        r"linkedin\.com/in/([^/?#]+)",
        url,
        re.IGNORECASE
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


def normalize_post_url(
    url
):

    if not url:
        return None

    return clean_url(
        url
    )


# ======================================================
# TEXT HELPERS
# ======================================================

def normalize_text(
    value
):

    if not value:
        return ""

    value = (
        str(value)
        .replace("\xa0", " ")
        .replace("\u200b", "")
        .lower()
        .strip()
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value


def clean_lines(
    text
):

    if not text:
        return []

    result = []

    for line in str(
        text
    ).splitlines():

        line = (
            line
            .replace("\xa0", " ")
            .replace("\u200b", "")
            .strip()
        )

        line = re.sub(
            r"\s+",
            " ",
            line
        )

        if line:

            result.append(
                line
            )

    return result


# ======================================================
# JSON HELPERS
# ======================================================

def load_json_list(
    path
):

    if not path.exists():

        return []

    try:

        with path.open(
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(
                file
            )

        if isinstance(
            data,
            list
        ):

            return data

    except Exception:

        pass

    return []


def save_json_list(
    path,
    data
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with path.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False
        )


# ======================================================
# LINKEDIN ACCESS
# ======================================================

def linkedin_access_problem(
    page
):

    current_url = (
        page.url
        or ""
    ).lower()

    bad_fragments = [
        "/login",
        "/checkpoint",
        "/authwall"
    ]

    return any(
        fragment in current_url
        for fragment
        in bad_fragments
    )


# ======================================================
# CONNECTION NAME
# ======================================================

def clean_connection_name(
    value
):

    if not value:
        return None

    value = (
        str(value)
        .replace("\xa0", " ")
        .replace("\u200b", "")
        .strip()
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    match = re.match(
        r"^View\s+(.+?)(?:'s|’s)\s+profile$",
        value,
        re.IGNORECASE
    )

    if match:

        value = (
            match.group(1)
            .strip()
        )

    value = re.sub(
        r"\s*[•·]\s*(1st|2nd|3rd\+?).*$",
        "",
        value,
        flags=re.IGNORECASE
    )

    value = re.sub(
        r"\s+(1st|2nd|3rd\+?)$",
        "",
        value,
        flags=re.IGNORECASE
    )

    value = re.sub(
        r"\s+Premium Profile.*$",
        "",
        value,
        flags=re.IGNORECASE
    )

    value = re.sub(
        r"\s+Open to work.*$",
        "",
        value,
        flags=re.IGNORECASE
    )

    value = value.strip(
        " ,•·"
    )

    if not value:
        return None

    if len(
        value
    ) > 120:

        return None

    rejected = {
        "message",
        "connect",
        "follow",
        "profile",
        "view profile",
        "linkedin member"
    }

    if (
        normalize_text(
            value
        )
        in rejected
    ):

        return None

    return value


def name_quality_score(
    name
):

    if not name:
        return 0

    score = 0

    words = (
        name.split()
    )

    if (
        2
        <= len(words)
        <= 5
    ):

        score += 5

    if not any(
        character.isdigit()
        for character
        in name
    ):

        score += 2

    if len(
        name
    ) <= 80:

        score += 2

    lowered = (
        normalize_text(
            name
        )
    )

    bad_words = [
        "message",
        "connection",
        "followers",
        "mutual",
        "premium",
        "open to work"
    ]

    if not any(
        bad_word in lowered
        for bad_word
        in bad_words
    ):

        score += 3

    return score


# ======================================================
# CONNECTION CARDS
# ======================================================

def extract_raw_connection_cards(
    page
):

    try:

        return (
            page.evaluate(
                """
                () => {

                    const results = [];

                    const controls =
                        Array.from(
                            document.querySelectorAll(
                                "button, a"
                            )
                        );


                    const messageControls =
                        controls.filter(
                            element => {

                                const text =
                                    (
                                        element.innerText
                                        || ""
                                    )
                                    .trim()
                                    .toLowerCase();


                                const aria =
                                    (
                                        element.getAttribute(
                                            "aria-label"
                                        )
                                        || ""
                                    )
                                    .trim()
                                    .toLowerCase();


                                const rect =
                                    element.getBoundingClientRect();


                                if (
                                    rect.width <= 0
                                    ||
                                    rect.height <= 0
                                ) {

                                    return false;
                                }


                                return (
                                    text === "message"
                                    ||
                                    aria === "message"
                                    ||
                                    aria.startsWith(
                                        "message "
                                    )
                                );
                            }
                        );


                    for (
                        const control
                        of messageControls
                    ) {

                        let current =
                            control.parentElement;

                        let chosen =
                            null;


                        for (
                            let level = 0;
                            level < 12;
                            level++
                        ) {

                            if (!current) {
                                break;
                            }


                            const text =
                                (
                                    current.innerText
                                    || ""
                                ).trim();


                            const profileLinks =
                                Array.from(
                                    current.querySelectorAll(
                                        "a[href*='/in/']"
                                    )
                                );


                            const messageCount =
                                Array.from(
                                    current.querySelectorAll(
                                        "button, a"
                                    )
                                )
                                .filter(
                                    element => {

                                        const t =
                                            (
                                                element.innerText
                                                || ""
                                            )
                                            .trim()
                                            .toLowerCase();


                                        const a =
                                            (
                                                element.getAttribute(
                                                    "aria-label"
                                                )
                                                || ""
                                            )
                                            .trim()
                                            .toLowerCase();


                                        return (
                                            t === "message"
                                            ||
                                            a === "message"
                                            ||
                                            a.startsWith(
                                                "message "
                                            )
                                        );
                                    }
                                )
                                .length;


                            if (
                                profileLinks.length >= 1
                                &&
                                messageCount === 1
                                &&
                                text.length >= 10
                                &&
                                text.length <= 3000
                            ) {

                                chosen =
                                    current;

                                break;
                            }


                            current =
                                current.parentElement;
                        }


                        if (!chosen) {
                            continue;
                        }


                        const links =
                            Array.from(
                                chosen.querySelectorAll(
                                    "a[href*='/in/']"
                                )
                            )
                            .map(
                                link => ({

                                    href:
                                        link.href
                                        || "",

                                    text:
                                        (
                                            link.innerText
                                            || ""
                                        ).trim(),

                                    aria:
                                        (
                                            link.getAttribute(
                                                "aria-label"
                                            )
                                            || ""
                                        ).trim()
                                })
                            );


                        results.push({

                            card_text:
                                (
                                    chosen.innerText
                                    || ""
                                ).trim(),

                            links:
                                links
                        });
                    }


                    return results;
                }
                """
            )
            or []
        )

    except Exception:

        return []


def parse_connection_card(
    raw_card
):

    links = (
        raw_card.get(
            "links"
        )
        or []
    )

    if not links:
        return None

    grouped = {}

    order = []

    for link in links:

        profile_url = (
            normalize_profile_url(
                link.get(
                    "href"
                )
            )
        )

        if not profile_url:
            continue

        if profile_url not in grouped:

            grouped[
                profile_url
            ] = {

                "occurrences":
                    0,

                "names":
                    []
            }

            order.append(
                profile_url
            )

        grouped[
            profile_url
        ][
            "occurrences"
        ] += 1

        for raw_name in [
            link.get(
                "text"
            ),
            link.get(
                "aria"
            )
        ]:

            name = (
                clean_connection_name(
                    raw_name
                )
            )

            if (
                name
                and
                name not in grouped[
                    profile_url
                ][
                    "names"
                ]
            ):

                grouped[
                    profile_url
                ][
                    "names"
                ].append(
                    name
                )

    if not grouped:
        return None

    best_url = None
    best_name = None
    best_score = -1

    for position, profile_url in enumerate(
        order
    ):

        group = (
            grouped[
                profile_url
            ]
        )

        candidate_name = None
        candidate_name_score = 0

        for name in group[
            "names"
        ]:

            score = (
                name_quality_score(
                    name
                )
            )

            if (
                score
                > candidate_name_score
            ):

                candidate_name_score = (
                    score
                )

                candidate_name = (
                    name
                )

        total_score = (
            group[
                "occurrences"
            ]
            * 4
            +
            candidate_name_score
            +
            max(
                0,
                5 - position
            )
        )

        if total_score > best_score:

            best_score = (
                total_score
            )

            best_url = (
                profile_url
            )

            best_name = (
                candidate_name
            )

    if not best_name:

        for line in clean_lines(
            raw_card.get(
                "card_text"
            )
        )[:8]:

            possible_name = (
                clean_connection_name(
                    line
                )
            )

            if (
                possible_name
                and
                name_quality_score(
                    possible_name
                )
                >= 8
            ):

                best_name = (
                    possible_name
                )

                break

    if (
        not best_url
        or not best_name
    ):

        return None

    return {

        "name":
            best_name,

        "profile_url":
            best_url
    }


def collect_real_connection_cards(
    page
):

    connections = []

    seen_urls = set()

    for raw_card in (
        extract_raw_connection_cards(
            page
        )
    ):

        connection = (
            parse_connection_card(
                raw_card
            )
        )

        if not connection:
            continue

        profile_url = (
            connection.get(
                "profile_url"
            )
        )

        if profile_url in seen_urls:
            continue

        seen_urls.add(
            profile_url
        )

        connections.append(
            connection
        )

    return connections


# ======================================================
# SEED VALIDATION
# ======================================================

def seed_needs_rebuild(
    tracked_connections
):

    seed_records = [
        record
        for record
        in tracked_connections
        if (
            record.get(
                "source"
            )
            == "existing_connection_seed"
        )
    ]

    # We now require 15.
    if (
        len(
            seed_records
        )
        < INITIAL_CONNECTION_COUNT
    ):

        return True

    for record in seed_records[
        :INITIAL_CONNECTION_COUNT
    ]:

        if not (
            record.get(
                "name"
            )
            or ""
        ).strip():

            return True

        if not normalize_profile_url(
            record.get(
                "profile_url"
            )
        ):

            return True

        if (
            record.get(
                "seed_version"
            )
            != CURRENT_SEED_VERSION
        ):

            return True

    return False


def backup_old_tracking_file(
    tracked_connections
):

    if OLD_SEED_BACKUP_FILE.exists():
        return

    if not tracked_connections:
        return

    save_json_list(
        OLD_SEED_BACKUP_FILE,
        tracked_connections
    )

    print(
        "\nCurrent tracking file backed up to:"
    )

    print(
        OLD_SEED_BACKUP_FILE
    )


# ======================================================
# REBUILD / EXPAND TO FIRST 15
# ======================================================

def rebuild_initial_connection_seed(
    page,
    tracked_connections
):

    print(
        "\n================================"
    )

    print(
        "BUILDING 15-CONNECTION SEED"
    )

    print(
        "================================"
    )

    backup_old_tracking_file(
        tracked_connections
    )

    # ==================================================
    # Existing seed records.
    #
    # If the same profile is still in the first 15,
    # preserve its monitoring information.
    # ==================================================

    existing_seed_by_url = {}

    for record in tracked_connections:

        if (
            record.get(
                "source"
            )
            != "existing_connection_seed"
        ):

            continue

        profile_url = (
            normalize_profile_url(
                record.get(
                    "profile_url"
                )
            )
        )

        if profile_url:

            existing_seed_by_url[
                profile_url
            ] = record

    # ==================================================
    # Preserve future approved connections and any other
    # non-seed tracking records.
    # ==================================================

    preserved_records = [
        record
        for record
        in tracked_connections
        if (
            record.get(
                "source"
            )
            != "existing_connection_seed"
        )
    ]

    preserved_urls = {
        normalize_profile_url(
            record.get(
                "profile_url"
            )
        )
        for record
        in preserved_records
        if record.get(
            "profile_url"
        )
    }

    page.goto(
        CONNECTIONS_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(
        PAGE_LOAD_WAIT_MS
    )

    if linkedin_access_problem(
        page
    ):

        raise RuntimeError(
            "LinkedIn redirected to login/checkpoint."
        )

    try:

        page.evaluate(
            """
            () => {

                const root =
                    document.scrollingElement
                    || document.documentElement;

                root.scrollTo(
                    0,
                    0
                );
            }
            """
        )

    except Exception:

        pass

    page.wait_for_timeout(
        700
    )

    collected = {}

    order = []

    for round_number in range(
        1,
        MAX_CONNECTION_SCROLL_ROUNDS + 1
    ):

        current = (
            collect_real_connection_cards(
                page
            )
        )

        for connection in current:

            profile_url = (
                connection.get(
                    "profile_url"
                )
            )

            if not profile_url:
                continue

            if profile_url in preserved_urls:
                continue

            if profile_url in collected:
                continue

            collected[
                profile_url
            ] = connection

            order.append(
                profile_url
            )

        print(
            f"Connection card round "
            f"{round_number}: "
            f"{len(order)} valid cards"
        )

        if (
            len(order)
            >= INITIAL_CONNECTION_COUNT
        ):

            break

        page.mouse.wheel(
            0,
            1100
        )

        page.wait_for_timeout(
            CONNECTION_SCROLL_WAIT_MS
        )

    if (
        len(order)
        < INITIAL_CONNECTION_COUNT
    ):

        raise RuntimeError(
            "\nCould not identify "
            f"{INITIAL_CONNECTION_COUNT} "
            "valid connection cards.\n"
            f"Only found: {len(order)}"
        )

    seed_connections = []

    for profile_url in order[
        :INITIAL_CONNECTION_COUNT
    ]:

        connection = (
            collected[
                profile_url
            ]
        )

        old_record = (
            existing_seed_by_url.get(
                profile_url
            )
            or {}
        )

        # Start from old record so we preserve
        # previously observed post information.
        record = dict(
            old_record
        )

        record.update(
            {

                "name":
                    connection.get(
                        "name"
                    ),

                "profile_url":
                    profile_url,

                "source":
                    "existing_connection_seed",

                "seed_version":
                    CURRENT_SEED_VERSION,

                "tracking_status":
                    "active",

                "monitor_posts":
                    True,

                "discover_from_comments":
                    True
            }
        )

        record.setdefault(
            "added_at",
            utc_now()
        )

        record.setdefault(
            "last_checked_at",
            None
        )

        record.setdefault(
            "last_post_status",
            None
        )

        record.setdefault(
            "last_seen_post_key",
            None
        )

        record.setdefault(
            "last_seen_post_url",
            None
        )

        record.setdefault(
            "last_seen_post_urn",
            None
        )

        record.setdefault(
            "last_seen_post_text",
            None
        )

        record.setdefault(
            "last_seen_post_comment_count",
            None
        )

        # Discovery source is intentionally separate
        # from monitoring baseline.
        record.setdefault(
            "last_discovery_status",
            None
        )

        record.setdefault(
            "last_discovery_post_key",
            None
        )

        record.setdefault(
            "last_discovery_post_url",
            None
        )

        record.setdefault(
            "last_discovery_post_urn",
            None
        )

        record.setdefault(
            "last_discovery_post_position",
            None
        )

        record.setdefault(
            "last_discovery_post_comment_count",
            None
        )

        seed_connections.append(
            record
        )

    rebuilt = (
        seed_connections
        +
        preserved_records
    )

    save_json_list(
        TRACKED_CONNECTIONS_FILE,
        rebuilt
    )

    print(
        "\n15-CONNECTION SEED"
    )

    print(
        "--------------------------------"
    )

    for position, record in enumerate(
        seed_connections,
        start=1
    ):

        print(
            f"{position}. "
            f"{record.get('name')}"
        )

        print(
            "   ",
            record.get(
                "profile_url"
            )
        )

    return rebuilt


def ensure_valid_connection_seed(
    page,
    tracked_connections
):

    if seed_needs_rebuild(
        tracked_connections
    ):

        print(
            "\nStored seed needs to be "
            "expanded/rebuilt for 15 connections."
        )

        return (
            rebuild_initial_connection_seed(
                page,
                tracked_connections
            )
        )

    print(
        "\nStored 15-connection seed is valid."
    )

    return tracked_connections


# ======================================================
# PROFILE NAME
# ======================================================

def get_profile_name(
    page,
    fallback=None
):

    headings = (
        page.locator(
            "h1"
        )
    )

    try:

        count = min(
            headings.count(),
            10
        )

        for index in range(
            count
        ):

            heading = (
                headings.nth(
                    index
                )
            )

            try:

                if not heading.is_visible():
                    continue

                text = (
                    heading.inner_text()
                    or ""
                ).strip()

                cleaned = (
                    clean_connection_name(
                        text
                    )
                )

                if cleaned:

                    return cleaned

            except Exception:

                continue

    except Exception:

        pass

    return fallback


# ======================================================
# POST DETECTION
#
# We use the blank post-level Comment action rather than
# relying on the old exact "Feed post" H2 heading.
# ======================================================

def is_blank_comment_button(
    button
):

    try:

        aria = (
            button.get_attribute(
                "aria-label"
            )
            or ""
        ).strip()

        if aria != "Comment":
            return False

        text = (
            button.inner_text()
            or ""
        )

        text = (
            text
            .replace(
                "\u200b",
                ""
            )
            .strip()
        )

        if text:
            return False

        if not button.is_visible():
            return False

        return True

    except Exception:

        return False


# ======================================================
# POST CONTAINER
# ======================================================

def find_post_container_from_comment_button(
    button
):

    current = (
        button
    )

    best = None

    for _ in range(
        16
    ):

        try:

            parent = (
                current.locator(
                    "xpath=.."
                )
            )

            text = (
                parent.inner_text()
                or ""
            ).strip()

            stats = (
                parent.evaluate(
                    """
                    root => {

                        const buttons =
                            Array.from(
                                root.querySelectorAll(
                                    "button[aria-label='Comment']"
                                )
                            );


                        const actionButtons =
                            buttons.filter(
                                button => {

                                    const text =
                                        (
                                            button.innerText
                                            || ""
                                        )
                                        .replace(
                                            /\\u200b/g,
                                            ""
                                        )
                                        .trim();


                                    return text.length === 0;
                                }
                            );


                        return {

                            actionCount:
                                actionButtons.length
                        };
                    }
                    """
                )
            )

            action_count = (
                stats.get(
                    "actionCount",
                    0
                )
            )

            # More than one post-level Comment button
            # means we've climbed above one post.
            if action_count > 1:

                break

            if (
                action_count == 1
                and
                80
                <= len(text)
                <= 30000
            ):

                best = (
                    parent
                )

            current = (
                parent
            )

        except Exception:

            break

    return best


# ======================================================
# POST URN
# ======================================================

def extract_activity_urn(
    post_container
):

    if post_container is None:
        return None

    try:

        return (
            post_container.evaluate(
                """
                root => {

                    const pattern =
                        /urn:li:activity:\\d+/;


                    const elements =
                        [
                            root,
                            ...root.querySelectorAll(
                                "*"
                            )
                        ];


                    for (
                        const element
                        of elements
                    ) {

                        const attributes =
                            Array.from(
                                element.attributes
                                || []
                            );


                        for (
                            const attribute
                            of attributes
                        ) {

                            const value =
                                attribute.value
                                || "";


                            const match =
                                value.match(
                                    pattern
                                );


                            if (match) {

                                return match[0];
                            }
                        }
                    }


                    return null;
                }
                """
            )
        )

    except Exception:

        return None


# ======================================================
# POST URL
# ======================================================

def extract_post_url(
    post_container,
    activity_urn=None
):

    if post_container is None:
        return None

    try:

        url = (
            post_container.evaluate(
                """
                root => {

                    const links =
                        Array.from(
                            root.querySelectorAll(
                                "a[href]"
                            )
                        );


                    const activityLink =
                        links.find(
                            link =>
                                (
                                    link.href
                                    || ""
                                ).includes(
                                    "/feed/update/"
                                )
                        );


                    if (activityLink) {

                        return activityLink.href;
                    }


                    const postsLink =
                        links.find(
                            link =>
                                (
                                    link.href
                                    || ""
                                ).includes(
                                    "/posts/"
                                )
                        );


                    return postsLink
                        ? postsLink.href
                        : null;
                }
                """
            )
        )

        if url:

            return (
                normalize_post_url(
                    url
                )
            )

    except Exception:

        pass

    if activity_urn:

        return (
            "https://www.linkedin.com/"
            "feed/update/"
            + activity_urn
            + "/"
        )

    return None


# ======================================================
# POST TEXT
# ======================================================

def extract_post_text(
    post_container
):

    if post_container is None:
        return None

    try:

        text = (
            post_container.inner_text()
            or ""
        )

    except Exception:

        return None

    lines = (
        clean_lines(
            text
        )
    )

    if not lines:
        return None

    preview = (
        "\n".join(
            lines
        )
    )

    return preview[
        :6000
    ]


# ======================================================
# COMMENT COUNT
# ======================================================

def get_comment_count(
    post_container
):

    if post_container is None:
        return 0

    buttons = (
        post_container.locator(
            "button[aria-label='Comment']"
        )
    )

    try:

        count = (
            buttons.count()
        )

    except Exception:

        return 0

    numbers = []

    for index in range(
        count
    ):

        button = (
            buttons.nth(
                index
            )
        )

        try:

            text = (
                button.inner_text()
                or ""
            )

            text = (
                text
                .replace(
                    "\u200b",
                    ""
                )
                .strip()
            )

            if not text:
                continue

            digits = re.sub(
                r"[^\d]",
                "",
                text
            )

            if not digits:
                continue

            numbers.append(
                int(
                    digits
                )
            )

        except Exception:

            continue

    if not numbers:
        return 0

    return max(
        numbers
    )


# ======================================================
# STABLE POST KEY
# ======================================================

def make_post_key(
    urn,
    url,
    text
):

    if urn:

        return (
            "urn:"
            + urn
        )

    if url:

        return (
            "url:"
            + url.rstrip("/")
        )

    stable_text = (
        normalize_text(
            text
        )
    )

    if not stable_text:
        return None

    digest = (
        hashlib.sha256(
            stable_text[
                :3000
            ].encode(
                "utf-8"
            )
        ).hexdigest()
    )

    return (
        "text:"
        + digest
    )


# ======================================================
# GET ALL CURRENTLY RENDERED POSTS
# ======================================================

def get_visible_posts(
    page
):

    comment_buttons = (
        page.locator(
            "button[aria-label='Comment']"
        )
    )

    posts = []

    seen_keys = set()

    try:

        count = (
            comment_buttons.count()
        )

    except Exception:

        return []

    for index in range(
        count
    ):

        button = (
            comment_buttons.nth(
                index
            )
        )

        if not is_blank_comment_button(
            button
        ):

            continue

        container = (
            find_post_container_from_comment_button(
                button
            )
        )

        if container is None:
            continue

        urn = (
            extract_activity_urn(
                container
            )
        )

        post_url = (
            extract_post_url(
                container,
                urn
            )
        )

        post_text = (
            extract_post_text(
                container
            )
        )

        post_key = (
            make_post_key(
                urn,
                post_url,
                post_text
            )
        )

        if not post_key:
            continue

        if post_key in seen_keys:
            continue

        seen_keys.add(
            post_key
        )

        posts.append(
            {

                # DOM order:
                # 1 = newest/top activity.
                "position":
                    len(posts) + 1,

                "key":
                    post_key,

                "urn":
                    urn,

                "url":
                    post_url,

                "text":
                    post_text,

                "comment_count":
                    get_comment_count(
                        container
                    ),

                "container":
                    container
            }
        )

    return posts


# ======================================================
# LOAD UP TO FIRST 10 RECENT POSTS
#
# Previous version stopped as soon as ANY posts appeared.
#
# Now we keep scrolling until:
# - 10 posts are available, OR
# - repeated scrolling produces no additional posts.
# ======================================================

def load_activity_posts(
    page
):

    best_posts = []

    previous_count = 0

    stagnant_rounds = 0

    for round_number in range(
        1,
        MAX_ACTIVITY_LOAD_ROUNDS + 1
    ):

        posts = (
            get_visible_posts(
                page
            )
        )

        if (
            len(posts)
            > len(best_posts)
        ):

            best_posts = (
                posts
            )

        print(
            f"Activity load round "
            f"{round_number}: "
            f"{len(posts)} detected posts"
        )

        if (
            len(best_posts)
            >= MAX_DISCOVERY_POSTS_PER_CONNECTION
        ):

            print(
                "Enough recent posts loaded "
                "for discovery."
            )

            break

        if (
            len(posts)
            > previous_count
        ):

            stagnant_rounds = 0

        else:

            stagnant_rounds += 1

        previous_count = max(
            previous_count,
            len(posts)
        )

        if (
            stagnant_rounds
            >= MAX_ACTIVITY_STAGNANT_ROUNDS
        ):

            print(
                "No additional recent posts "
                "loaded after repeated scrolling."
            )

            break

        try:

            page.mouse.wheel(
                0,
                1200
            )

        except Exception:

            pass

        page.wait_for_timeout(
            ACTIVITY_LOAD_WAIT_MS
        )

    return (
        best_posts[
            :MAX_DISCOVERY_POSTS_PER_CONNECTION
        ]
    )


# ======================================================
# CHOOSE DISCOVERY POST
#
# Monitoring:
#     always newest detected activity = posts[0]
#
# Candidate discovery:
#     first/newest post among the first 10
#     whose numeric comment count is > 0.
# ======================================================

def choose_discovery_post(
    posts
):

    for post in posts[
        :MAX_DISCOVERY_POSTS_PER_CONNECTION
    ]:

        if (
            post.get(
                "comment_count",
                0
            )
            > 0
        ):

            return post

    return None


# ======================================================
# OPEN COMMENTS
# ======================================================

def open_comments(
    post_container
):

    if post_container is None:
        return False

    try:

        post_container.scroll_into_view_if_needed()

    except Exception:

        pass

    buttons = (
        post_container.locator(
            "button[aria-label='Comment']"
        )
    )

    try:

        count = (
            buttons.count()
        )

    except Exception:

        return False

    # Prefer the numeric comment-count control.
    for index in range(
        count
    ):

        button = (
            buttons.nth(
                index
            )
        )

        try:

            text = (
                button.inner_text()
                or ""
            )

            text = (
                text
                .replace(
                    "\u200b",
                    ""
                )
                .strip()
            )

            if not re.fullmatch(
                r"\d+",
                text
            ):

                continue

            if not button.is_visible():
                continue

            button.click()

            return True

        except Exception:

            continue

    # Fallback to post-level Comment action.
    for index in range(
        count
    ):

        button = (
            buttons.nth(
                index
            )
        )

        if not is_blank_comment_button(
            button
        ):

            continue

        try:

            button.click()

            return True

        except Exception:

            continue

    return False


# ======================================================
# COMMENT SORT
# ======================================================

def switch_comments_to_most_recent(
    page
):

    print(
        "Checking comment sort..."
    )

    try:

        relevant = (
            page.get_by_text(
                "Most relevant",
                exact=True
            )
        )

        for index in range(
            relevant.count()
        ):

            item = (
                relevant.nth(
                    index
                )
            )

            if not item.is_visible():
                continue

            print(
                "Current sort: Most relevant"
            )

            item.click()

            page.wait_for_timeout(
                500
            )

            recent = (
                page.get_by_text(
                    "Most recent",
                    exact=True
                )
            )

            for recent_index in range(
                recent.count()
            ):

                option = (
                    recent.nth(
                        recent_index
                    )
                )

                if not option.is_visible():
                    continue

                option.click()

                page.wait_for_timeout(
                    1000
                )

                print(
                    "Comments switched to Most recent."
                )

                return True

    except Exception:

        pass

    return False


# ======================================================
# FIND SAME POST AFTER COMMENTS ALTER THE DOM
#
# Text-hash keys can change after comments appear.
# Therefore:
# 1. URN
# 2. URL
# 3. stable non-text key
# 4. original position
# ======================================================

def find_post_after_dom_change(
    page,
    target_post
):

    posts = (
        get_visible_posts(
            page
        )
    )

    target_urn = (
        target_post.get(
            "urn"
        )
    )

    if target_urn:

        for post in posts:

            if (
                post.get(
                    "urn"
                )
                == target_urn
            ):

                return post

    target_url = (
        normalize_post_url(
            target_post.get(
                "url"
            )
        )
    )

    if target_url:

        for post in posts:

            if (
                normalize_post_url(
                    post.get(
                        "url"
                    )
                )
                == target_url
            ):

                return post

    target_key = (
        target_post.get(
            "key"
        )
    )

    if (
        target_key
        and
        not target_key.startswith(
            "text:"
        )
    ):

        for post in posts:

            if (
                post.get(
                    "key"
                )
                == target_key
            ):

                return post

    target_position = (
        target_post.get(
            "position"
        )
    )

    if (
        isinstance(
            target_position,
            int
        )
        and
        target_position >= 1
        and
        len(posts)
        >= target_position
    ):

        return (
            posts[
                target_position - 1
            ]
        )

    return None


# ======================================================
# RAW COMMENTS
# ======================================================

def extract_raw_comment_records(
    post_container
):

    if post_container is None:
        return []

    try:

        return (
            post_container.evaluate(
                """
                root => {

                    const result = [];

                    const controls =
                        Array.from(
                            root.querySelectorAll(
                                "button, span"
                            )
                        );


                    const replyControls =
                        controls.filter(
                            element => {

                                const text =
                                    (
                                        element.innerText
                                        || ""
                                    ).trim();


                                const aria =
                                    (
                                        element.getAttribute(
                                            "aria-label"
                                        )
                                        || ""
                                    ).trim();


                                return (
                                    text === "Reply"
                                    ||
                                    aria === "Reply"
                                );
                            }
                        );


                    for (
                        const replyControl
                        of replyControls
                    ) {

                        let current =
                            replyControl.parentElement;

                        let block =
                            null;


                        for (
                            let level = 0;
                            level < 10;
                            level++
                        ) {

                            if (!current) {
                                break;
                            }


                            const text =
                                (
                                    current.innerText
                                    || ""
                                ).trim();


                            const profileLinks =
                                Array.from(
                                    current.querySelectorAll(
                                        "a[href*='/in/']"
                                    )
                                );


                            if (
                                text.length >= 20
                                &&
                                text.length <= 7000
                                &&
                                profileLinks.length >= 1
                            ) {

                                block =
                                    current;

                                break;
                            }


                            current =
                                current.parentElement;
                        }


                        if (!block) {
                            continue;
                        }


                        const profileLinks =
                            Array.from(
                                block.querySelectorAll(
                                    "a[href*='/in/']"
                                )
                            );


                        if (
                            profileLinks.length === 0
                        ) {

                            continue;
                        }


                        const authorLink =
                            profileLinks[0];


                        const href =
                            authorLink.href
                            || "";


                        const authorText =
                            (
                                authorLink.innerText
                                || ""
                            ).trim();


                        const rawText =
                            (
                                block.innerText
                                || ""
                            ).trim();


                        if (
                            !href
                            ||
                            !rawText
                        ) {

                            continue;
                        }


                        result.push({

                            profile_url:
                                href,

                            author_text:
                                authorText,

                            raw_text:
                                rawText
                        });
                    }


                    return result;
                }
                """
            )
            or []
        )

    except Exception:

        return []


# ======================================================
# COMMENTER PARSING
# ======================================================

def extract_connection_degree(
    raw_text
):

    if not raw_text:
        return None

    match = re.search(
        r"(?:^|\s|•)"
        r"(1st|2nd|3rd\+?)"
        r"(?:\s|$)",
        raw_text,
        re.IGNORECASE
    )

    if not match:
        return None

    return (
        match.group(
            1
        )
    )


def clean_candidate_name(
    author_text,
    raw_text
):

    lines = (
        clean_lines(
            author_text
        )
    )

    if lines:

        name = (
            lines[0]
        )

        name = re.sub(
            r",?\s*Open to work.*$",
            "",
            name,
            flags=re.IGNORECASE
        )

        name = re.sub(
            r",?\s*Premium Profile.*$",
            "",
            name,
            flags=re.IGNORECASE
        )

        name = re.sub(
            r"\s+(1st|2nd|3rd\+?)$",
            "",
            name,
            flags=re.IGNORECASE
        )

        name = (
            name.strip(
                " ,•"
            )
        )

        if (
            name
            and
            len(name)
            <= 150
        ):

            return name

    raw_lines = (
        clean_lines(
            raw_text
        )
    )

    for index, line in enumerate(
        raw_lines
    ):

        if not re.fullmatch(
            r"•?\s*(1st|2nd|3rd\+?)",
            line,
            re.IGNORECASE
        ):

            continue

        for backwards in range(
            index - 1,
            -1,
            -1
        ):

            possible_name = (
                raw_lines[
                    backwards
                ]
            )

            possible_name = re.sub(
                r",?\s*Open to work.*$",
                "",
                possible_name,
                flags=re.IGNORECASE
            )

            possible_name = re.sub(
                r",?\s*Premium Profile.*$",
                "",
                possible_name,
                flags=re.IGNORECASE
            )

            possible_name = (
                possible_name.strip(
                    " ,•"
                )
            )

            if (
                possible_name
                and
                len(
                    possible_name
                )
                <= 150
            ):

                return possible_name

    return None


def looks_like_timestamp(
    line
):

    value = (
        line
        .strip()
        .lower()
    )

    patterns = [
        r"^\d+\s*m$",
        r"^\d+\s*h$",
        r"^\d+\s*d$",
        r"^\d+\s*w$",
        r"^\d+\s*mo$",
        r"^\d+\s*y$",
        r"^\d+\s*min$",
        r"^\d+\s*hr$",
        r"^\d+\s*day[s]?$",
        r"^\d+\s*week[s]?$",
        r"^\d+\s*month[s]?$",
        r"^\d+\s*year[s]?$"
    ]

    return any(
        re.match(
            pattern,
            value
        )
        for pattern
        in patterns
    )


def extract_headline(
    name,
    raw_text
):

    lines = (
        clean_lines(
            raw_text
        )
    )

    name_key = (
        normalize_text(
            name
        )
    )

    degree_index = None

    for index, line in enumerate(
        lines
    ):

        if re.fullmatch(
            r"•?\s*(1st|2nd|3rd\+?)",
            line,
            re.IGNORECASE
        ):

            degree_index = (
                index
            )

            break

    if degree_index is not None:

        for line in lines[
            degree_index + 1:
            degree_index + 6
        ]:

            value = (
                normalize_text(
                    line
                )
            )

            if not value:
                continue

            if value == name_key:
                continue

            if value == "follow":
                break

            if looks_like_timestamp(
                line
            ):

                break

            if len(
                line
            ) >= 4:

                return line

    return None


def extract_comment_text(
    raw_text
):

    lines = (
        clean_lines(
            raw_text
        )
    )

    if not lines:
        return None

    start = None

    for index, line in enumerate(
        lines
    ):

        if (
            normalize_text(
                line
            )
            == "follow"
        ):

            start = (
                index + 1
            )

            break

    if start is None:

        for index, line in enumerate(
            lines
        ):

            if looks_like_timestamp(
                line
            ):

                start = (
                    index + 1
                )

                break

    if start is None:
        return None

    comment_lines = []

    for line in lines[
        start:
    ]:

        lowered = (
            normalize_text(
                line
            )
        )

        if lowered in {
            "like",
            "reply",
            "repost",
            "send"
        }:

            continue

        if re.fullmatch(
            r"\d+\s+reactions?",
            lowered
        ):

            break

        if re.fullmatch(
            r"\d+\s+replies?",
            lowered
        ):

            break

        if re.fullmatch(
            r"\d+",
            lowered
        ):

            if comment_lines:
                break

            continue

        if lowered in {
            "… more",
            "... more"
        }:

            break

        comment_lines.append(
            line
        )

        if len(
            " ".join(
                comment_lines
            )
        ) > 2500:

            break

    comment = (
        " ".join(
            comment_lines
        )
        .strip()
    )

    return (
        comment
        or None
    )


def parse_comment_record(
    raw_record
):

    profile_url = (
        normalize_profile_url(
            raw_record.get(
                "profile_url"
            )
        )
    )

    raw_text = (
        raw_record.get(
            "raw_text"
        )
        or ""
    )

    author_text = (
        raw_record.get(
            "author_text"
        )
        or ""
    )

    if not profile_url:
        return None

    name = (
        clean_candidate_name(
            author_text,
            raw_text
        )
    )

    if not name:
        return None

    return {

        "name":
            name,

        "profile_url":
            profile_url,

        "connection_degree":
            extract_connection_degree(
                raw_text
            ),

        "headline":
            extract_headline(
                name,
                raw_text
            ),

        "comment_text":
            extract_comment_text(
                raw_text
            ),

        "raw_comment_context":
            raw_text
    }


# ======================================================
# COMMENT LOADING
# ======================================================

def merge_raw_records(
    accumulated,
    new_records
):

    for record in new_records:

        profile_url = (
            normalize_profile_url(
                record.get(
                    "profile_url"
                )
            )
        )

        if not profile_url:
            continue

        existing = (
            accumulated.get(
                profile_url
            )
        )

        if not existing:

            accumulated[
                profile_url
            ] = record

            continue

        old_text = (
            existing.get(
                "raw_text"
            )
            or ""
        )

        new_text = (
            record.get(
                "raw_text"
            )
            or ""
        )

        if (
            len(
                new_text
            )
            > len(
                old_text
            )
        ):

            accumulated[
                profile_url
            ] = record


def jump_comment_container_to_bottom(
    page
):

    try:

        return (
            page.evaluate(
                """
                () => {

                    const candidates = [];

                    const elements =
                        [
                            document.querySelector(
                                "main"
                            ),
                            ...document.querySelectorAll(
                                "main div"
                            )
                        ]
                        .filter(Boolean);


                    for (
                        const element
                        of elements
                    ) {

                        const profileCount =
                            element.querySelectorAll(
                                "a[href*='/in/']"
                            ).length;


                        const controls =
                            Array.from(
                                element.querySelectorAll(
                                    "button, span"
                                )
                            );


                        const replyCount =
                            controls.filter(
                                control => {

                                    const text =
                                        (
                                            control.innerText
                                            || ""
                                        ).trim();


                                    const aria =
                                        (
                                            control.getAttribute(
                                                "aria-label"
                                            )
                                            || ""
                                        ).trim();


                                    return (
                                        text === "Reply"
                                        ||
                                        aria === "Reply"
                                    );
                                }
                            ).length;


                        if (
                            profileCount === 0
                            ||
                            replyCount === 0
                        ) {

                            continue;
                        }


                        candidates.push({

                            element:
                                element,

                            score:
                                (
                                    replyCount * 20
                                    +
                                    profileCount
                                ),

                            profileCount:
                                profileCount,

                            replyCount:
                                replyCount
                        });
                    }


                    if (
                        candidates.length === 0
                    ) {

                        return null;
                    }


                    candidates.sort(
                        (
                            left,
                            right
                        ) =>
                            right.score
                            - left.score
                    );


                    const best =
                        candidates[0];


                    best.element.scrollTop =
                        best.element.scrollHeight;


                    return {

                        tag:
                            best.element.tagName,

                        scrollHeight:
                            best.element.scrollHeight,

                        clientHeight:
                            best.element.clientHeight,

                        profileCount:
                            best.profileCount,

                        replyCount:
                            best.replyCount
                    };
                }
                """
            )
        )

    except Exception:

        return None


def load_comment_authors(
    page,
    post_container
):

    accumulated = {}

    merge_raw_records(
        accumulated,
        extract_raw_comment_records(
            post_container
        )
    )

    print(
        "Initially visible unique comment authors:",
        len(
            accumulated
        )
    )

    stagnant_rounds = 0

    previous_count = (
        len(
            accumulated
        )
    )

    previous_height = None

    for round_number in range(
        1,
        MAX_COMMENT_LOAD_ROUNDS + 1
    ):

        state = (
            jump_comment_container_to_bottom(
                page
            )
        )

        page.wait_for_timeout(
            COMMENT_LOAD_WAIT_MS
        )

        merge_raw_records(
            accumulated,
            extract_raw_comment_records(
                post_container
            )
        )

        current_count = (
            len(
                accumulated
            )
        )

        current_height = None

        if state:

            current_height = (
                state.get(
                    "scrollHeight"
                )
            )

        print(
            f"Comment load round "
            f"{round_number}: "
            f"{current_count} unique authors"
        )

        if state:

            print(
                "  container:",
                state.get(
                    "tag"
                ),
                "| height:",
                state.get(
                    "scrollHeight"
                ),
                "| profiles:",
                state.get(
                    "profileCount"
                ),
                "| replies:",
                state.get(
                    "replyCount"
                )
            )

        author_progress = (
            current_count
            > previous_count
        )

        height_progress = (
            current_height is not None
            and
            previous_height is not None
            and
            current_height
            > previous_height
        )

        if (
            author_progress
            or height_progress
        ):

            stagnant_rounds = 0

        else:

            stagnant_rounds += 1

        previous_count = (
            current_count
        )

        if current_height is not None:

            previous_height = (
                current_height
            )

        if (
            stagnant_rounds
            >= MAX_STAGNANT_ROUNDS
        ):

            print(
                "No additional comment authors "
                "after repeated attempts."
            )

            break

    return list(
        accumulated.values()
    )


# ======================================================
# CANDIDATE SOURCE
# ======================================================

def build_source_record(
    source_connection,
    post,
    parsed_candidate
):

    return {

        "source_connection":
            source_connection.get(
                "name"
            ),

        "source_connection_profile_url":
            source_connection.get(
                "profile_url"
            ),

        "source_post_position":
            post.get(
                "position"
            ),

        "source_post_key":
            post.get(
                "key"
            ),

        "source_post_urn":
            post.get(
                "urn"
            ),

        "source_post_url":
            post.get(
                "url"
            ),

        "visible_comment_count":
            post.get(
                "comment_count"
            ),

        "comment_text":
            parsed_candidate.get(
                "comment_text"
            ),

        "discovered_at":
            utc_now()
    }


def build_candidate(
    parsed,
    source_record
):

    return {

        "name":
            parsed.get(
                "name"
            ),

        "profile_url":
            parsed.get(
                "profile_url"
            ),

        "connection_degree":
            parsed.get(
                "connection_degree"
            ),

        "headline":
            parsed.get(
                "headline"
            ),

        "comment_text":
            parsed.get(
                "comment_text"
            ),

        "raw_comment_context":
            parsed.get(
                "raw_comment_context"
            ),

        "source_connection":
            source_record.get(
                "source_connection"
            ),

        "source_post_url":
            source_record.get(
                "source_post_url"
            ),

        "visible_comment_count":
            source_record.get(
                "visible_comment_count"
            ),

        "sources":
            [
                source_record
            ],

        "status":
            "new",

        "discovered_at":
            utc_now()
    }


# ======================================================
# CANDIDATE MERGING
# ======================================================

def same_source(
    left,
    right
):

    left_key = (
        left.get(
            "source_post_key"
        )
    )

    right_key = (
        right.get(
            "source_post_key"
        )
    )

    return (
        left_key == right_key
        and
        normalize_profile_url(
            left.get(
                "source_connection_profile_url"
            )
        )
        ==
        normalize_profile_url(
            right.get(
                "source_connection_profile_url"
            )
        )
    )


def merge_candidate(
    existing,
    incoming
):

    # Do not overwrite existing AI scores,
    # enrichment data, lawyer decisions, etc.

    for field in [
        "name",
        "headline",
        "comment_text",
        "raw_comment_context"
    ]:

        old_value = (
            existing.get(
                field
            )
            or ""
        )

        new_value = (
            incoming.get(
                field
            )
            or ""
        )

        if (
            len(
                new_value
            )
            > len(
                old_value
            )
        ):

            existing[
                field
            ] = new_value

    if (
        not existing.get(
            "connection_degree"
        )
        and
        incoming.get(
            "connection_degree"
        )
    ):

        existing[
            "connection_degree"
        ] = incoming.get(
            "connection_degree"
        )

    existing_sources = (
        existing.get(
            "sources"
        )
        or []
    )

    for new_source in (
        incoming.get(
            "sources"
        )
        or []
    ):

        if not any(
            same_source(
                old_source,
                new_source
            )
            for old_source
            in existing_sources
        ):

            existing_sources.append(
                new_source
            )

    existing[
        "sources"
    ] = existing_sources

    return existing


def deduplicate_run_candidates(
    candidates
):

    by_url = {}

    for candidate in candidates:

        profile_url = (
            normalize_profile_url(
                candidate.get(
                    "profile_url"
                )
            )
        )

        if not profile_url:
            continue

        if profile_url not in by_url:

            by_url[
                profile_url
            ] = candidate

        else:

            merge_candidate(
                by_url[
                    profile_url
                ],
                candidate
            )

    return list(
        by_url.values()
    )


def merge_candidates_into_file(
    new_candidates
):

    existing = (
        load_json_list(
            CANDIDATE_FILE
        )
    )

    by_url = {}

    for candidate in existing:

        profile_url = (
            normalize_profile_url(
                candidate.get(
                    "profile_url"
                )
            )
        )

        if profile_url:

            by_url[
                profile_url
            ] = candidate

    added = 0

    updated = 0

    for candidate in new_candidates:

        profile_url = (
            normalize_profile_url(
                candidate.get(
                    "profile_url"
                )
            )
        )

        if not profile_url:
            continue

        if profile_url in by_url:

            merge_candidate(
                by_url[
                    profile_url
                ],
                candidate
            )

            updated += 1

        else:

            existing.append(
                candidate
            )

            by_url[
                profile_url
            ] = candidate

            added += 1

    save_json_list(
        CANDIDATE_FILE,
        existing
    )

    return (
        added,
        updated,
        len(
            existing
        )
    )


# ======================================================
# TRACKED CONNECTION UPDATE
# ======================================================

def update_tracked_connection(
    tracked_connections,
    profile_url,
    **updates
):

    normalized_url = (
        normalize_profile_url(
            profile_url
        )
    )

    for record in tracked_connections:

        if (
            normalize_profile_url(
                record.get(
                    "profile_url"
                )
            )
            != normalized_url
        ):

            continue

        for key, value in (
            updates.items()
        ):

            record[
                key
            ] = value

        return


# ======================================================
# PROCESS ONE CONNECTION
# ======================================================

def process_connection(
    page,
    connection,
    tracked_connections,
    known_connection_urls
):

    profile_url = (
        normalize_profile_url(
            connection.get(
                "profile_url"
            )
        )
    )

    if not profile_url:
        return []

    activity_url = (
        profile_url
        + "recent-activity/all/"
    )

    print(
        "\n================================"
    )

    print(
        "TRACKED CONNECTION"
    )

    print(
        "================================"
    )

    print(
        "Stored name:",
        connection.get(
            "name"
        )
    )

    print(
        "Profile:",
        profile_url
    )

    print(
        "Activity:",
        activity_url
    )

    page.goto(
        activity_url,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(
        PAGE_LOAD_WAIT_MS
    )

    if linkedin_access_problem(
        page
    ):

        print(
            "LinkedIn access problem."
        )

        update_tracked_connection(
            tracked_connections,
            profile_url,
            last_checked_at=utc_now(),
            last_post_status="linkedin_access_problem",
            last_discovery_status="linkedin_access_problem"
        )

        return []

    actual_name = (
        get_profile_name(
            page,
            fallback=connection.get(
                "name"
            )
        )
    )

    # ==================================================
    # LOAD RECENT ACTIVITY
    # ==================================================

    posts = (
        load_activity_posts(
            page
        )
    )

    print(
        "Recent posts available for inspection:",
        len(
            posts
        )
    )

    # ==================================================
    # NO ACTIVITY
    # ==================================================

    if not posts:

        print(
            "No detectable recent post."
        )

        update_tracked_connection(
            tracked_connections,
            profile_url,
            name=actual_name,
            last_checked_at=utc_now(),
            last_post_status="no_recent_post",
            last_discovery_status="no_recent_activity"
        )

        return []

    # ==================================================
    # MONITORING BASELINE
    #
    # Always save the newest activity, whether it has
    # comments or not.
    # ==================================================

    newest_post = (
        posts[0]
    )

    print(
        "\nMONITORING BASELINE — NEWEST POST"
    )

    print(
        "Position:",
        newest_post.get(
            "position"
        )
    )

    print(
        "Key:",
        newest_post.get(
            "key"
        )
    )

    print(
        "URN:",
        newest_post.get(
            "urn"
        )
    )

    print(
        "URL:",
        newest_post.get(
            "url"
        )
    )

    print(
        "Comments:",
        newest_post.get(
            "comment_count"
        )
    )

    update_tracked_connection(
        tracked_connections,
        profile_url,
        name=actual_name,
        last_checked_at=utc_now(),
        last_post_status="post_found",
        last_seen_post_key=newest_post.get(
            "key"
        ),
        last_seen_post_url=newest_post.get(
            "url"
        ),
        last_seen_post_urn=newest_post.get(
            "urn"
        ),
        last_seen_post_text=(
            newest_post.get(
                "text"
            )
            or ""
        )[:6000],
        last_seen_post_comment_count=newest_post.get(
            "comment_count"
        )
    )

    # ==================================================
    # CANDIDATE DISCOVERY POST
    #
    # Search posts from newest → older.
    #
    # First post with >0 comments wins.
    # ==================================================

    discovery_post = (
        choose_discovery_post(
            posts
        )
    )

    if not discovery_post:

        print(
            "\nDISCOVERY"
        )

        print(
            "No post with comments found "
            f"within the first "
            f"{len(posts)} recent posts."
        )

        update_tracked_connection(
            tracked_connections,
            profile_url,
            last_discovery_status=(
                "no_recent_post_with_comments"
            ),
            last_discovery_post_key=None,
            last_discovery_post_url=None,
            last_discovery_post_urn=None,
            last_discovery_post_position=None,
            last_discovery_post_comment_count=None
        )

        return []

    print(
        "\nDISCOVERY POST"
    )

    print(
        "Position:",
        discovery_post.get(
            "position"
        )
    )

    print(
        "Key:",
        discovery_post.get(
            "key"
        )
    )

    print(
        "URN:",
        discovery_post.get(
            "urn"
        )
    )

    print(
        "URL:",
        discovery_post.get(
            "url"
        )
    )

    print(
        "Comments:",
        discovery_post.get(
            "comment_count"
        )
    )

    if (
        discovery_post.get(
            "position"
        )
        == 1
    ):

        print(
            "Newest post is also the discovery post."
        )

    else:

        print(
            "Newest post had no usable discussion, "
            "so discovery moved to the newest "
            "recent post with comments."
        )

    update_tracked_connection(
        tracked_connections,
        profile_url,
        last_discovery_status="discovery_post_found",
        last_discovery_post_key=discovery_post.get(
            "key"
        ),
        last_discovery_post_url=discovery_post.get(
            "url"
        ),
        last_discovery_post_urn=discovery_post.get(
            "urn"
        ),
        last_discovery_post_position=discovery_post.get(
            "position"
        ),
        last_discovery_post_comment_count=discovery_post.get(
            "comment_count"
        )
    )

    # ==================================================
    # OPEN THE DISCOVERY POST
    # ==================================================

    post_container = (
        discovery_post.get(
            "container"
        )
    )

    try:

        post_container.scroll_into_view_if_needed()

        page.wait_for_timeout(
            600
        )

    except Exception:

        pass

    if not open_comments(
        post_container
    ):

        print(
            "Could not open comments "
            "for discovery post."
        )

        update_tracked_connection(
            tracked_connections,
            profile_url,
            last_discovery_status=(
                "discovery_comments_open_failed"
            )
        )

        return []

    page.wait_for_timeout(
        1200
    )

    switch_comments_to_most_recent(
        page
    )

    # ==================================================
    # DOM MAY CHANGE AFTER COMMENTS OPEN.
    #
    # Re-find selected post if possible.
    # ==================================================

    refreshed_post = (
        find_post_after_dom_change(
            page,
            discovery_post
        )
    )

    if refreshed_post:

        post_container = (
            refreshed_post.get(
                "container"
            )
        )

    # ==================================================
    # LOAD COMMENT AUTHORS
    # ==================================================

    raw_records = (
        load_comment_authors(
            page,
            post_container
        )
    )

    print(
        "\nCOMMENT LOADING SUMMARY"
    )

    print(
        "Discovery post position:",
        discovery_post.get(
            "position"
        )
    )

    print(
        "LinkedIn reported comments:",
        discovery_post.get(
            "comment_count"
        )
    )

    print(
        "Unique visible comment authors:",
        len(
            {
                normalize_profile_url(
                    record.get(
                        "profile_url"
                    )
                )
                for record
                in raw_records
                if record.get(
                    "profile_url"
                )
            }
        )
    )

    # ==================================================
    # FILTER CANDIDATES
    # ==================================================

    tracked_urls = {
        normalize_profile_url(
            record.get(
                "profile_url"
            )
        )
        for record
        in tracked_connections
        if record.get(
            "profile_url"
        )
    }

    candidates = []

    for raw_record in raw_records:

        parsed = (
            parse_comment_record(
                raw_record
            )
        )

        if not parsed:
            continue

        candidate_url = (
            parsed.get(
                "profile_url"
            )
        )

        # Don't recommend the post author.
        if candidate_url == profile_url:
            continue

        # Don't recommend obvious 1st-degree people.
        if (
            normalize_text(
                parsed.get(
                    "connection_degree"
                )
            )
            == "1st"
        ):

            continue

        # Don't recommend someone already tracked.
        if candidate_url in tracked_urls:
            continue

        if candidate_url in known_connection_urls:
            continue

        source_record = (
            build_source_record(
                source_connection={
                    "name":
                        actual_name,

                    "profile_url":
                        profile_url
                },
                post=discovery_post,
                parsed_candidate=parsed
            )
        )

        candidates.append(
            build_candidate(
                parsed,
                source_record
            )
        )

    print(
        "Eligible candidate records:",
        len(
            candidates
        )
    )

    return candidates


# ======================================================
# MAIN
# ======================================================

def run(
    playwright
):

    print(
        "\n================================"
    )

    print(
        "LINKEDIN NETWORK SCOUT"
    )

    print(
        "15-CONNECTION DISCOVERY"
    )

    print(
        "================================"
    )

    context = (
        playwright
        .chromium
        .launch_persistent_context(
            str(
                BROWSER_PROFILE
            ),
            headless=False
        )
    )

    if context.pages:

        page = (
            context.pages[0]
        )

    else:

        page = (
            context.new_page()
        )

    tracked_connections = (
        load_json_list(
            TRACKED_CONNECTIONS_FILE
        )
    )

    tracked_connections = (
        ensure_valid_connection_seed(
            page,
            tracked_connections
        )
    )

    known_connection_urls = {
        normalize_profile_url(
            record.get(
                "profile_url"
            )
        )
        for record
        in tracked_connections
        if record.get(
            "profile_url"
        )
    }

    seed_connections = [
        record
        for record
        in tracked_connections
        if (
            record.get(
                "source"
            )
            == "existing_connection_seed"
            and
            record.get(
                "tracking_status",
                "active"
            )
            == "active"
            and
            record.get(
                "monitor_posts",
                True
            )
        )
    ]

    active_connections = (
        seed_connections[
            :MAX_CONNECTIONS_PER_RUN
        ]
    )

    print(
        "\nConnections being processed:",
        len(
            active_connections
        )
    )

    print(
        "\n15-person connection seed:"
    )

    for position, connection in enumerate(
        active_connections,
        start=1
    ):

        print(
            f"{position}. "
            f"{connection.get('name')}"
        )

    # ==================================================
    # RUN COUNTERS
    # ==================================================

    all_candidates = []

    processed = 0

    failed = 0

    connections_with_posts = 0

    connections_with_discovery_posts = 0

    connections_with_candidates = 0

    # ==================================================
    # PROCESS ALL 15
    # ==================================================

    for position, connection in enumerate(
        active_connections,
        start=1
    ):

        print(
            "\n\n################################"
        )

        print(
            f"CONNECTION "
            f"{position}/"
            f"{len(active_connections)}"
        )

        print(
            "################################"
        )

        try:

            candidates = (
                process_connection(
                    page,
                    connection,
                    tracked_connections,
                    known_connection_urls
                )
            )

            processed += 1

            if (
                connection.get(
                    "last_post_status"
                )
                == "post_found"
            ):

                connections_with_posts += 1

            if (
                connection.get(
                    "last_discovery_status"
                )
                == "discovery_post_found"
            ):

                connections_with_discovery_posts += 1

            if candidates:

                connections_with_candidates += 1

                all_candidates.extend(
                    candidates
                )

            # Save after every connection so we do not
            # lose progress if later processing fails.
            save_json_list(
                TRACKED_CONNECTIONS_FILE,
                tracked_connections
            )

        except Exception as error:

            failed += 1

            print(
                "\nCONNECTION PROCESSING FAILED"
            )

            print(
                connection.get(
                    "name"
                )
            )

            print(
                error
            )

            update_tracked_connection(
                tracked_connections,
                connection.get(
                    "profile_url"
                ),
                last_checked_at=utc_now(),
                last_post_status="failed",
                last_discovery_status="failed",
                last_error=str(
                    error
                )
            )

            save_json_list(
                TRACKED_CONNECTIONS_FILE,
                tracked_connections
            )

        page.wait_for_timeout(
            1200
        )

    # ==================================================
    # GLOBAL CANDIDATE DEDUPE
    # ==================================================

    print(
        "\n\n================================"
    )

    print(
        "GLOBAL CANDIDATE DEDUPLICATION"
    )

    print(
        "================================"
    )

    print(
        "Candidate records before dedupe:",
        len(
            all_candidates
        )
    )

    deduplicated = (
        deduplicate_run_candidates(
            all_candidates
        )
    )

    print(
        "Unique candidates after dedupe:",
        len(
            deduplicated
        )
    )

    # ==================================================
    # MERGE INTO CANDIDATES.JSON
    # ==================================================

    (
        added,
        updated,
        total
    ) = merge_candidates_into_file(
        deduplicated
    )

    save_json_list(
        TRACKED_CONNECTIONS_FILE,
        tracked_connections
    )

    # ==================================================
    # SUMMARY
    # ==================================================

    print(
        "\n\n================================"
    )

    print(
        "15-CONNECTION DISCOVERY COMPLETE"
    )

    print(
        "================================"
    )

    print(
        "Tracked connections processed:",
        processed
    )

    print(
        "Connections with detected activity:",
        connections_with_posts
    )

    print(
        "Connections with a usable "
        "discovery post:",
        connections_with_discovery_posts
    )

    print(
        "Connection failures:",
        failed
    )

    print(
        "Connections producing candidates:",
        connections_with_candidates
    )

    print(
        "Unique candidates this run:",
        len(
            deduplicated
        )
    )

    print(
        "New candidates added:",
        added
    )

    print(
        "Existing candidates updated:",
        updated
    )

    print(
        "Total candidates stored:",
        total
    )

    print(
        "\nTracked connections file:"
    )

    print(
        TRACKED_CONNECTIONS_FILE
    )

    print(
        "\nCandidates file:"
    )

    print(
        CANDIDATE_FILE
    )

    input(
        "\nPress Enter to close..."
    )

    context.close()


if __name__ == "__main__":

    with sync_playwright() as playwright:

        run(
            playwright
        )