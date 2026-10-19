import json
import re

from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright


# ======================================================
# SETTINGS
# ======================================================

CONNECTIONS_URL = (
    "https://www.linkedin.com/mynetwork/invite-connect/connections/"
)

# Which visible connection to inspect.
# 0 = first visible connection.
PROFILE_INDEX = 0

# Number of recent posts to inspect.
POST_SCAN_LIMIT = 10

# Maximum lazy-loading attempts for comments.
MAX_COMMENT_LOAD_ROUNDS = 30

# Stop after this many consecutive rounds with
# no new authors and no growth in the comment area.
MAX_STAGNANT_ROUNDS = 4

# Wait after each jump to the bottom of comments.
COMMENT_LOAD_WAIT_MS = 2500

# Local candidate storage.
CANDIDATE_FILE = "data/candidates.json"


# ======================================================
# URL HELPERS
# ======================================================

def clean_url(href):

    if not href:
        return None

    full_url = urljoin(
        "https://www.linkedin.com",
        href
    )

    full_url = full_url.split("?")[0]
    full_url = full_url.split("#")[0]

    return full_url


def normalize_profile_url(url):

    if not url:
        return None

    url = clean_url(url)

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


# ======================================================
# TEXT HELPERS
# ======================================================

def normalize_text_key(value):

    if not value:
        return ""

    value = (
        str(value)
        .replace("\u200b", "")
        .replace("\xa0", " ")
        .strip()
        .lower()
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    value = re.sub(
        r"[^\w\s]",
        "",
        value
    )

    return value.strip()


def clean_context_lines(text):

    if not text:
        return []

    cleaned = []

    for line in text.splitlines():

        line = (
            line
            .replace("\u200b", "")
            .replace("\xa0", " ")
            .strip()
        )

        line = re.sub(
            r"\s+",
            " ",
            line
        )

        if line:
            cleaned.append(
                line
            )

    return cleaned


def clean_person_name(name):

    if not name:
        return None

    name = name.strip()

    badge_patterns = [
        r"\bOpen to work\b",
        r"\bPremium Profile\b",
        r"\bPremium\b"
    ]

    for pattern in badge_patterns:

        name = re.sub(
            pattern,
            "",
            name,
            flags=re.IGNORECASE
        )

    name = re.sub(
        r"\s+",
        " ",
        name
    )

    name = name.strip(
        " ,•|-"
    )

    if not name:
        return None

    return name


# ======================================================
# LINKEDIN LABEL HELPERS
# ======================================================

def is_degree_line(text):

    if not text:
        return False

    return bool(
        re.match(
            r"^(?:•\s*)?"
            r"(1st|2nd|3rd\+?)$",
            text.strip(),
            re.IGNORECASE
        )
    )


def is_time_label(text):

    if not text:
        return False

    text = text.strip()

    patterns = [
        r"^\d+m$",
        r"^\d+h$",
        r"^\d+d$",
        r"^\d+w$",
        r"^\d+mo$",
        r"^\d+y$",
        r"^\d+m\s*•",
        r"^\d+h\s*•",
        r"^\d+d\s*•",
        r"^\d+w\s*•",
        r"^\d+mo\s*•",
        r"^\d+y\s*•"
    ]

    for pattern in patterns:

        if re.match(
            pattern,
            text,
            re.IGNORECASE
        ):
            return True

    return False


# ======================================================
# EXTRACT NAME + CONNECTION DEGREE
# ======================================================

def extract_name_and_degree(lines):

    standalone_degree_pattern = re.compile(
        r"^(?:•\s*)?"
        r"(1st|2nd|3rd\+?)$",
        re.IGNORECASE
    )

    combined_pattern = re.compile(
        r"^(.*?)\s*(?:•\s*)?"
        r"(1st|2nd|3rd\+?)$",
        re.IGNORECASE
    )

    # --------------------------------------------------
    # Example:
    #
    # Matt Hamilton
    # • 3rd+
    # --------------------------------------------------

    for index, line in enumerate(
        lines[:10]
    ):

        match = (
            standalone_degree_pattern
            .match(line)
        )

        if not match:
            continue

        degree = (
            match.group(1)
            .strip()
        )

        for previous_index in range(
            index - 1,
            -1,
            -1
        ):

            previous_line = (
                lines[
                    previous_index
                ]
            )

            if is_degree_line(
                previous_line
            ):
                continue

            if is_time_label(
                previous_line
            ):
                continue

            if previous_line.lower() in {
                "follow",
                "following"
            }:
                continue

            name = clean_person_name(
                previous_line
            )

            if name:

                return (
                    name,
                    degree,
                    index
                )

    # --------------------------------------------------
    # Example:
    #
    # Josephine Opondo • 3rd+
    # --------------------------------------------------

    for index, line in enumerate(
        lines[:10]
    ):

        match = (
            combined_pattern
            .match(line)
        )

        if not match:
            continue

        name = clean_person_name(
            match.group(1)
        )

        degree = (
            match.group(2)
            .strip()
        )

        if name:

            return (
                name,
                degree,
                index
            )

    return (
        None,
        None,
        None
    )


# ======================================================
# PARSE RAW COMMENT INTO STRUCTURED CANDIDATE
# ======================================================

def parse_candidate_context(candidate):

    raw_context = (
        candidate.get(
            "comment_context",
            ""
        )
    )

    lines = clean_context_lines(
        raw_context
    )

    (
        name,
        degree,
        identity_index
    ) = extract_name_and_degree(
        lines
    )

    # ==================================================
    # HEADLINE
    # ==================================================

    headline = None

    start_index = 0

    if identity_index is not None:

        start_index = (
            identity_index + 1
        )

    for index in range(
        start_index,
        len(lines)
    ):

        line = lines[index]

        lower_line = (
            line.lower()
        )

        if (
            name
            and clean_person_name(
                line
            ) == name
        ):
            continue

        if is_degree_line(
            line
        ):
            continue

        if is_time_label(
            line
        ):
            continue

        if lower_line in {
            "follow",
            "following"
        }:
            continue

        if line == "… more":
            continue

        if line.isdigit():
            continue

        if re.match(
            r"^\d+\s+reactions?$",
            line,
            re.IGNORECASE
        ):
            continue

        headline = line
        break

    # ==================================================
    # COMMENT START
    # ==================================================

    comment_start = None

    for index, line in enumerate(
        lines
    ):

        if line.lower() in {
            "follow",
            "following"
        }:

            comment_start = (
                index + 1
            )

            break

    if comment_start is None:

        for index, line in enumerate(
            lines
        ):

            if is_time_label(
                line
            ):

                comment_start = (
                    index + 1
                )

                break

    # ==================================================
    # COMMENT TEXT
    # ==================================================

    comment_lines = []

    if comment_start is not None:

        for line in lines[
            comment_start:
        ]:

            lower_line = (
                line.lower()
            )

            if line == "… more":
                break

            if re.match(
                r"^\d+\s+reactions?$",
                line,
                re.IGNORECASE
            ):
                break

            if line.isdigit():
                break

            if lower_line in {
                "like",
                "reply",
                "repost",
                "send"
            }:
                break

            comment_lines.append(
                line
            )

    comment_text = " ".join(
        comment_lines
    ).strip()

    return {

        "name":
            name,

        "connection_degree":
            degree,

        "headline":
            headline,

        "comment_text":
            comment_text,

        "profile_url":
            normalize_profile_url(
                candidate.get(
                    "profile_url"
                )
            ),

        "source_connection":
            normalize_profile_url(
                candidate.get(
                    "source_connection"
                )
            ),

        "source_post_number":
            candidate.get(
                "source_post_number"
            ),

        "source_post_url":
            candidate.get(
                "source_post_url"
            ),

        "visible_comment_count":
            candidate.get(
                "visible_comment_count"
            ),

        "raw_comment_context":
            raw_context
    }


# ======================================================
# DUPLICATE DETECTION
# ======================================================

def same_candidate(
    candidate_a,
    candidate_b
):

    url_a = normalize_profile_url(
        candidate_a.get(
            "profile_url"
        )
    )

    url_b = normalize_profile_url(
        candidate_b.get(
            "profile_url"
        )
    )

    # Strongest identifier
    if (
        url_a
        and url_b
        and url_a == url_b
    ):
        return True

    name_a = normalize_text_key(
        candidate_a.get(
            "name"
        )
    )

    name_b = normalize_text_key(
        candidate_b.get(
            "name"
        )
    )

    headline_a = normalize_text_key(
        candidate_a.get(
            "headline"
        )
    )

    headline_b = normalize_text_key(
        candidate_b.get(
            "headline"
        )
    )

    if (
        name_a
        and name_b
        and name_a == name_b
        and headline_a
        and headline_b
        and headline_a == headline_b
    ):
        return True

    return False


# ======================================================
# MERGE DUPLICATE CANDIDATES
# ======================================================

def merge_two_candidates(
    existing,
    new
):

    merged = (
        existing.copy()
    )

    rich_fields = [
        "name",
        "headline",
        "comment_text",
        "comment_context",
        "raw_comment_context"
    ]

    for field in rich_fields:

        old_value = (
            existing.get(field)
            or ""
        )

        new_value = (
            new.get(field)
            or ""
        )

        if (
            len(str(new_value))
            >
            len(str(old_value))
        ):

            merged[
                field
            ] = new_value

    normal_fields = [
        "connection_degree",
        "profile_url",
        "source_connection",
        "source_post_number",
        "source_post_url",
        "visible_comment_count"
    ]

    for field in normal_fields:

        if not merged.get(
            field
        ):

            merged[
                field
            ] = new.get(
                field
            )

    # Preserve previous human workflow status
    if existing.get(
        "status"
    ):

        merged[
            "status"
        ] = existing[
            "status"
        ]

    elif new.get(
        "status"
    ):

        merged[
            "status"
        ] = new[
            "status"
        ]

    else:

        merged[
            "status"
        ] = "new"

    return merged


def deduplicate_candidates(
    candidates
):

    unique = []

    for candidate in candidates:

        candidate = (
            candidate.copy()
        )

        matched_index = None

        for index, existing in enumerate(
            unique
        ):

            if same_candidate(
                existing,
                candidate
            ):

                matched_index = (
                    index
                )

                break

        if matched_index is None:

            unique.append(
                candidate
            )

        else:

            unique[
                matched_index
            ] = merge_two_candidates(
                unique[
                    matched_index
                ],
                candidate
            )

    return unique


# ======================================================
# FILTER NEW-NETWORK CANDIDATES
# ======================================================

def filter_eligible_candidates(
    candidates,
    visible_connections
):

    visible_connections = {
        normalize_profile_url(url)
        for url in visible_connections
        if normalize_profile_url(url)
    }

    eligible = []

    for candidate in candidates:

        candidate = (
            candidate.copy()
        )

        profile_url = (
            normalize_profile_url(
                candidate.get(
                    "profile_url"
                )
            )
        )

        if not profile_url:
            continue

        degree = (
            candidate.get(
                "connection_degree"
            )
            or ""
        ).lower()

        # Already directly connected
        if degree == "1st":
            continue

        if (
            profile_url
            in visible_connections
        ):
            continue

        candidate[
            "profile_url"
        ] = profile_url

        candidate[
            "status"
        ] = candidate.get(
            "status",
            "new"
        )

        eligible.append(
            candidate
        )

    return deduplicate_candidates(
        eligible
    )


# ======================================================
# SAVE CANDIDATES
# ======================================================

def save_candidates_to_json(
    candidates,
    file_path=CANDIDATE_FILE
):

    path = Path(
        file_path
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    existing = []

    if path.exists():

        try:

            with path.open(
                "r",
                encoding="utf-8"
            ) as file:

                loaded = json.load(
                    file
                )

                if isinstance(
                    loaded,
                    list
                ):

                    existing = loaded

        except (
            json.JSONDecodeError,
            OSError
        ):

            existing = []

    combined = (
        existing
        + candidates
    )

    final_candidates = (
        deduplicate_candidates(
            combined
        )
    )

    with path.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            final_candidates,
            file,
            indent=4,
            ensure_ascii=False
        )

    return final_candidates


# ======================================================
# FIND ONE POST CONTAINER
# ======================================================

def find_post_container(
    feed_heading
):

    handle = (
        feed_heading
        .evaluate_handle(
            """
            heading => {

                function countFeedHeadings(element) {

                    let count = 0;

                    if (
                        element.tagName === "H2"
                        &&
                        (
                            element.innerText
                            || ""
                        ).trim()
                        === "Feed post"
                    ) {
                        count++;
                    }


                    const headings =
                        element.querySelectorAll(
                            "h2"
                        );


                    for (
                        const h
                        of headings
                    ) {

                        if (
                            (
                                h.innerText
                                || ""
                            ).trim()
                            === "Feed post"
                        ) {
                            count++;
                        }
                    }


                    return count;
                }


                let current =
                    heading;

                let candidate =
                    null;

                let level = 0;


                while (
                    current
                    &&
                    level < 25
                ) {

                    const text =
                        (
                            current.innerText
                            || ""
                        ).trim();


                    const feedCount =
                        countFeedHeadings(
                            current
                        );


                    if (
                        feedCount === 1
                        &&
                        text.length >= 100
                        &&
                        text.length <= 30000
                    ) {

                        candidate =
                            current;
                    }


                    if (
                        feedCount > 1
                    ) {
                        break;
                    }


                    current =
                        current.parentElement;

                    level++;
                }


                return candidate;
            }
            """
        )
    )

    return handle.as_element()


# ======================================================
# FIND NUMERIC COMMENT COUNT BUTTON
# ======================================================

def find_numeric_comment_button(
    post_container
):

    buttons = (
        post_container
        .query_selector_all(
            "button"
        )
    )

    for button in buttons:

        try:

            aria = (
                button
                .get_attribute(
                    "aria-label"
                )
                or ""
            ).strip()

            text = (
                button
                .inner_text()
                or ""
            ).strip()

            if (
                aria.lower()
                == "comment"
                and text.isdigit()
            ):

                return {

                    "button":
                        button,

                    "count":
                        int(text)
                }

        except Exception:

            continue

    return None


# ======================================================
# FIND DIRECT POST URL
# ======================================================

def find_activity_url(
    post_container
):

    return post_container.evaluate(
        """
        post => {

            const elements = [
                post,
                ...post.querySelectorAll("*")
            ];


            for (
                const element
                of elements
            ) {

                for (
                    const attribute
                    of element.attributes
                ) {

                    const value =
                        attribute.value
                        || "";


                    if (
                        value.includes(
                            "/feed/update/urn:li:activity:"
                        )
                    ) {

                        if (
                            value.startsWith(
                                "http"
                            )
                        ) {
                            return value;
                        }


                        return (
                            "https://www.linkedin.com"
                            + value
                        );
                    }
                }
            }


            return null;
        }
        """
    )


# ======================================================
# SWITCH COMMENTS TO MOST RECENT
# ======================================================

def switch_comment_sort_to_most_recent(
    page
):

    print(
        "\nChecking comment sort..."
    )

    controls = page.locator(
        "button, [role='button']"
    )

    most_relevant_control = None

    count = min(
        controls.count(),
        600
    )

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
                control.inner_text()
                or ""
            ).strip()

            aria = (
                control.get_attribute(
                    "aria-label"
                )
                or ""
            ).strip()

            combined = (
                text
                + " "
                + aria
            ).strip().lower()

            if (
                "most recent"
                in combined
                and
                "most relevant"
                not in combined
            ):

                print(
                    "Comments already sorted by "
                    "Most recent."
                )

                return True

            if (
                "most relevant"
                in combined
            ):

                most_relevant_control = (
                    control
                )

                break

        except Exception:

            continue

    if (
        most_relevant_control
        is None
    ):

        print(
            "Could not locate comment "
            "sorting control."
        )

        return False

    print(
        "Current sort: Most relevant"
    )

    try:

        most_relevant_control.scroll_into_view_if_needed()

        page.wait_for_timeout(
            400
        )

        most_relevant_control.click()

        page.wait_for_timeout(
            1000
        )

    except Exception as error:

        print(
            "Could not open sorting menu:"
        )

        print(
            error
        )

        return False

    options = page.locator(
        "button, "
        "[role='menuitem'], "
        "[role='option'], "
        "[role='radio'], "
        "li"
    )

    count = min(
        options.count(),
        800
    )

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
                option.inner_text()
                or ""
            ).strip()

            aria = (
                option.get_attribute(
                    "aria-label"
                )
                or ""
            ).strip()

            combined = (
                text
                + " "
                + aria
            ).strip().lower()

            if (
                "most recent"
                not in combined
            ):
                continue

            option.click()

            page.wait_for_timeout(
                3000
            )

            print(
                "Comments switched to Most recent."
            )

            return True

        except Exception:

            continue

    print(
        "Most recent option was not available."
    )

    try:

        page.keyboard.press(
            "Escape"
        )

    except Exception:

        pass

    return False


# ======================================================
# EXTRACT CURRENT COMMENT BLOCKS
# ======================================================

def extract_comment_blocks(
    page
):

    return page.evaluate(
        """
        () => {

            const results = [];


            const allControls =
                Array.from(
                    document.querySelectorAll(
                        "button, a, [role='button']"
                    )
                );


            const replyControls =
                allControls.filter(
                    control => {

                        const text =
                            (
                                control.innerText
                                || ""
                            )
                            .trim()
                            .toLowerCase();


                        const aria =
                            (
                                control.getAttribute(
                                    "aria-label"
                                )
                                || ""
                            )
                            .trim()
                            .toLowerCase();


                        return (
                            text === "reply"
                            ||
                            aria === "reply"
                            ||
                            aria.startsWith(
                                "reply "
                            )
                        );
                    }
                );


            for (
                const replyControl
                of replyControls
            ) {

                let current =
                    replyControl;

                let comment =
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


                    if (
                        text.length > 3000
                    ) {
                        break;
                    }


                    const profiles =
                        current.querySelectorAll(
                            "a[href*='/in/']"
                        );


                    if (
                        profiles.length >= 1
                        &&
                        profiles.length <= 6
                        &&
                        text.length >= 20
                    ) {

                        comment =
                            current;

                        break;
                    }


                    current =
                        current.parentElement;
                }


                if (!comment) {
                    continue;
                }


                const profileLinks =
                    Array.from(
                        comment.querySelectorAll(
                            "a[href*='/in/']"
                        )
                    );


                if (
                    profileLinks.length
                    === 0
                ) {
                    continue;
                }


                let author =
                    null;


                for (
                    const profile
                    of profileLinks
                ) {

                    const visible =
                        (
                            profile.innerText
                            || ""
                        ).trim();


                    const aria =
                        (
                            profile.getAttribute(
                                "aria-label"
                            )
                            || ""
                        ).trim();


                    if (
                        visible
                        ||
                        aria
                    ) {

                        author =
                            profile;

                        break;
                    }
                }


                if (!author) {

                    author =
                        profileLinks[0];
                }


                results.push({

                    href:
                        author.href,

                    context:
                        (
                            comment.innerText
                            || ""
                        ).trim()
                });
            }


            return results;
        }
        """
    )


# ======================================================
# ADD AUTHORS TO PERMANENT ACCUMULATOR
# ======================================================

def merge_comment_blocks(
    accumulator,
    blocks
):

    new_authors = 0

    for block in blocks:

        profile_url = (
            normalize_profile_url(
                block.get(
                    "href"
                )
            )
        )

        if not profile_url:
            continue

        context = (
            block.get(
                "context"
            )
            or ""
        )

        if (
            profile_url
            not in accumulator
        ):

            accumulator[
                profile_url
            ] = block

            new_authors += 1

            continue

        old_context = (
            accumulator[
                profile_url
            ].get(
                "context"
            )
            or ""
        )

        if (
            len(context)
            >
            len(old_context)
        ):

            accumulator[
                profile_url
            ] = block

    return new_authors


# ======================================================
# FIND CURRENT BEST COMMENT SCROLL CONTAINER
# ======================================================

def inspect_best_comment_container(
    page
):

    return page.evaluate(
        """
        () => {

            const elements =
                Array.from(
                    document.querySelectorAll("*")
                );


            let bestInfo =
                null;

            let bestScore =
                -1;


            for (
                const element
                of elements
            ) {

                const style =
                    window.getComputedStyle(
                        element
                    );


                const overflowY =
                    style.overflowY;


                const scrollable =
                    (
                        overflowY === "auto"
                        ||
                        overflowY === "scroll"
                    )
                    &&
                    element.scrollHeight
                    >
                    element.clientHeight + 100;


                if (!scrollable) {
                    continue;
                }


                const profileCount =
                    element.querySelectorAll(
                        "a[href*='/in/']"
                    ).length;


                if (
                    profileCount === 0
                ) {
                    continue;
                }


                const controls =
                    Array.from(
                        element.querySelectorAll(
                            "button, a, [role='button']"
                        )
                    );


                const replyCount =
                    controls.filter(
                        control => {

                            const text =
                                (
                                    control.innerText
                                    || ""
                                )
                                .trim()
                                .toLowerCase();


                            const aria =
                                (
                                    control.getAttribute(
                                        "aria-label"
                                    )
                                    || ""
                                )
                                .trim()
                                .toLowerCase();


                            return (
                                text === "reply"
                                ||
                                aria === "reply"
                                ||
                                aria.startsWith(
                                    "reply "
                                )
                            );
                        }
                    ).length;


                if (
                    replyCount === 0
                ) {
                    continue;
                }


                const score =
                    (
                        replyCount * 20
                        +
                        profileCount
                    );


                if (
                    score > bestScore
                ) {

                    bestScore =
                        score;


                    bestInfo = {

                        tag:
                            element.tagName,

                        scrollTop:
                            element.scrollTop,

                        scrollHeight:
                            element.scrollHeight,

                        clientHeight:
                            element.clientHeight,

                        profileCount:
                            profileCount,

                        replyCount:
                            replyCount,

                        score:
                            score
                    };
                }
            }


            return bestInfo;
        }
        """
    )


# ======================================================
# JUMP COMMENT CONTAINER TO CURRENT BOTTOM
#
# FIXED VERSION:
# replyCount/profileCount are stored while selecting
# the best container. Nothing references "controls"
# outside its scope anymore.
# ======================================================

def jump_comment_container_to_bottom(
    page
):

    return page.evaluate(
        """
        () => {

            const elements =
                Array.from(
                    document.querySelectorAll("*")
                );


            let best =
                null;

            let bestScore =
                -1;

            let bestProfileCount =
                0;

            let bestReplyCount =
                0;


            for (
                const element
                of elements
            ) {

                const style =
                    window.getComputedStyle(
                        element
                    );


                const overflowY =
                    style.overflowY;


                const scrollable =
                    (
                        overflowY === "auto"
                        ||
                        overflowY === "scroll"
                    )
                    &&
                    element.scrollHeight
                    >
                    element.clientHeight + 100;


                if (!scrollable) {
                    continue;
                }


                const profileCount =
                    element.querySelectorAll(
                        "a[href*='/in/']"
                    ).length;


                if (
                    profileCount === 0
                ) {
                    continue;
                }


                const controls =
                    Array.from(
                        element.querySelectorAll(
                            "button, a, [role='button']"
                        )
                    );


                const replyCount =
                    controls.filter(
                        control => {

                            const text =
                                (
                                    control.innerText
                                    || ""
                                )
                                .trim()
                                .toLowerCase();


                            const aria =
                                (
                                    control.getAttribute(
                                        "aria-label"
                                    )
                                    || ""
                                )
                                .trim()
                                .toLowerCase();


                            return (
                                text === "reply"
                                ||
                                aria === "reply"
                                ||
                                aria.startsWith(
                                    "reply "
                                )
                            );
                        }
                    ).length;


                if (
                    replyCount === 0
                ) {
                    continue;
                }


                const score =
                    (
                        replyCount * 20
                        +
                        profileCount
                    );


                if (
                    score > bestScore
                ) {

                    best =
                        element;

                    bestScore =
                        score;

                    bestProfileCount =
                        profileCount;

                    bestReplyCount =
                        replyCount;
                }
            }


            if (!best) {

                return {

                    found:
                        false
                };
            }


            const beforeTop =
                best.scrollTop;


            const beforeHeight =
                best.scrollHeight;


            const clientHeight =
                best.clientHeight;


            /*
                Move to current bottom.

                LinkedIn can then lazy-load another
                batch and make scrollHeight larger.
            */

            best.scrollTop =
                best.scrollHeight;


            return {

                found:
                    true,

                tag:
                    best.tagName,

                beforeTop:
                    beforeTop,

                afterTop:
                    best.scrollTop,

                beforeHeight:
                    beforeHeight,

                clientHeight:
                    clientHeight,

                profileCount:
                    bestProfileCount,

                replyCount:
                    bestReplyCount
            };
        }
        """
    )


# ======================================================
# LOAD ALL CURRENTLY AVAILABLE COMMENT AUTHORS
# ======================================================

def load_available_comments(
    page,
    reported_comment_count
):

    accumulated = {}

    stagnant_rounds = 0

    rounds_completed = 0

    # ==================================================
    # INITIAL CAPTURE
    # ==================================================

    initial_blocks = (
        extract_comment_blocks(
            page
        )
    )

    merge_comment_blocks(
        accumulated,
        initial_blocks
    )

    print(
        "\nInitial comment blocks:",
        len(
            initial_blocks
        )
    )

    print(
        "Initial unique authors:",
        len(
            accumulated
        )
    )

    initial_container = (
        inspect_best_comment_container(
            page
        )
    )

    if initial_container:

        print(
            "\nComment scroll container:"
        )

        print(
            "Tag:",
            initial_container.get(
                "tag"
            )
        )

        print(
            "Scroll height:",
            initial_container.get(
                "scrollHeight"
            )
        )

        print(
            "Client height:",
            initial_container.get(
                "clientHeight"
            )
        )

        print(
            "Profiles in container:",
            initial_container.get(
                "profileCount"
            )
        )

        print(
            "Reply controls:",
            initial_container.get(
                "replyCount"
            )
        )

    else:

        print(
            "\nCould not identify "
            "comment scroll container."
        )

    # ==================================================
    # LAZY-LOADING LOOP
    # ==================================================

    for round_number in range(
        1,
        MAX_COMMENT_LOAD_ROUNDS + 1
    ):

        rounds_completed = (
            round_number
        )

        count_before = (
            len(
                accumulated
            )
        )

        state_before = (
            inspect_best_comment_container(
                page
            )
        )

        print(
            "\n================================"
        )

        print(
            "COMMENT LOAD ROUND:",
            round_number
        )

        print(
            "================================"
        )

        print(
            "Authors before:",
            count_before
        )

        if state_before:

            print(
                "Scroll height before:",
                state_before.get(
                    "scrollHeight"
                )
            )

            print(
                "Scroll position before:",
                state_before.get(
                    "scrollTop"
                )
            )

        # --------------------------------------------------
        # Jump to current bottom
        # --------------------------------------------------

        try:

            jump_result = (
                jump_comment_container_to_bottom(
                    page
                )
            )

        except Exception as error:

            print(
                "Comment-container scroll error:"
            )

            print(
                error
            )

            print(
                "Using page scroll fallback."
            )

            page.mouse.wheel(
                0,
                2000
            )

            page.wait_for_timeout(
                COMMENT_LOAD_WAIT_MS
            )

            continue

        if not jump_result.get(
            "found"
        ):

            print(
                "Could not find a comment "
                "container to scroll."
            )

            break

        print(
            "Jumped container:",
            jump_result.get(
                "tag"
            )
        )

        print(
            "Scroll position:",
            jump_result.get(
                "beforeTop"
            ),
            "→",
            jump_result.get(
                "afterTop"
            )
        )

        # --------------------------------------------------
        # Wait for LinkedIn to append another batch
        # --------------------------------------------------

        page.wait_for_timeout(
            COMMENT_LOAD_WAIT_MS
        )

        # --------------------------------------------------
        # Capture newly rendered comments
        # --------------------------------------------------

        current_blocks = (
            extract_comment_blocks(
                page
            )
        )

        new_authors = (
            merge_comment_blocks(
                accumulated,
                current_blocks
            )
        )

        count_after = (
            len(
                accumulated
            )
        )

        state_after = (
            inspect_best_comment_container(
                page
            )
        )

        print(
            "Comment blocks currently in DOM:",
            len(
                current_blocks
            )
        )

        print(
            "New authors this round:",
            new_authors
        )

        print(
            "Total unique authors:",
            count_after
        )

        if state_after:

            print(
                "Scroll height after:",
                state_after.get(
                    "scrollHeight"
                )
            )

            print(
                "Scroll position after:",
                state_after.get(
                    "scrollTop"
                )
            )

        # --------------------------------------------------
        # Did LinkedIn append content?
        # --------------------------------------------------

        container_grew = False

        if (
            state_before
            and state_after
        ):

            old_height = (
                state_before.get(
                    "scrollHeight"
                )
                or 0
            )

            new_height = (
                state_after.get(
                    "scrollHeight"
                )
                or 0
            )

            if (
                new_height
                >
                old_height
            ):

                container_grew = True

        print(
            "Container grew:",
            container_grew
        )

        # --------------------------------------------------
        # Track progress
        # --------------------------------------------------

        if (
            new_authors > 0
            or container_grew
        ):

            stagnant_rounds = 0

        else:

            stagnant_rounds += 1

        print(
            "Stagnant rounds:",
            stagnant_rounds
        )

        # --------------------------------------------------
        # The reported comment count includes repeat
        # commenters/replies, so this is only an
        # upper-bound safety stop.
        # --------------------------------------------------

        if (
            reported_comment_count
            and count_after
            >= reported_comment_count
        ):

            print(
                "\nUnique author count reached "
                "the reported comment count."
            )

            break

        # --------------------------------------------------
        # Stop when repeated bottom jumps reveal
        # nothing new.
        # --------------------------------------------------

        if (
            stagnant_rounds
            >= MAX_STAGNANT_ROUNDS
        ):

            print(
                "\nLinkedIn stopped revealing "
                "additional unique authors."
            )

            break

    return (
        accumulated,
        rounds_completed
    )


# ======================================================
# MAIN
# ======================================================

def run(playwright):

    # ==================================================
    # 1. OPEN PERSISTENT BROWSER
    # ==================================================

    context = (
        playwright
        .chromium
        .launch_persistent_context(
            "browser_data/lawyer_profile",
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

    # ==================================================
    # 2. CONNECTIONS
    # ==================================================

    print(
        "\nOpening LinkedIn Connections..."
    )

    page.goto(
        CONNECTIONS_URL,
        wait_until="domcontentloaded"
    )

    page.wait_for_timeout(
        4000
    )

    connection_links = (
        page.locator(
            "a[href*='/in/']"
        )
    )

    visible_connections = []

    for index in range(
        connection_links.count()
    ):

        href = (
            connection_links
            .nth(index)
            .get_attribute(
                "href"
            )
        )

        profile_url = (
            normalize_profile_url(
                href
            )
        )

        if not profile_url:
            continue

        if (
            profile_url
            not in visible_connections
        ):

            visible_connections.append(
                profile_url
            )

    print(
        "\nConnections discovered:",
        len(
            visible_connections
        )
    )

    if not visible_connections:

        print(
            "No connections found."
        )

        context.close()

        return

    if (
        PROFILE_INDEX
        >= len(
            visible_connections
        )
    ):

        print(
            "PROFILE_INDEX is too large."
        )

        context.close()

        return

    # ==================================================
    # 3. SELECT CONNECTION
    # ==================================================

    selected_profile = (
        visible_connections[
            PROFILE_INDEX
        ]
    )

    print(
        "\nSelected connection:"
    )

    print(
        selected_profile
    )

    # ==================================================
    # 4. OPEN ACTIVITY
    # ==================================================

    activity_url = (
        selected_profile.rstrip("/")
        + "/recent-activity/all/"
    )

    page.goto(
        activity_url,
        wait_until="domcontentloaded"
    )

    page.wait_for_timeout(
        5000
    )

    feed_headings = (
        page.get_by_role(
            "heading",
            name="Feed post",
            exact=True
        )
    )

    feed_count = (
        feed_headings.count()
    )

    print(
        "\nFeed posts found:",
        feed_count
    )

    if feed_count == 0:

        print(
            "No posts found."
        )

        context.close()

        return

    # ==================================================
    # 5. FIND POSTS WITH COMMENTS
    # ==================================================

    posts_with_comments = []

    for index in range(
        min(
            feed_count,
            POST_SCAN_LIMIT
        )
    ):

        post_container = (
            find_post_container(
                feed_headings.nth(
                    index
                )
            )
        )

        if post_container is None:
            continue

        comment_info = (
            find_numeric_comment_button(
                post_container
            )
        )

        if not comment_info:
            continue

        posts_with_comments.append(
            {

                "post_number":
                    index + 1,

                "comments":
                    comment_info[
                        "count"
                    ],

                "direct_url":
                    find_activity_url(
                        post_container
                    )
            }
        )

    print(
        "\n================================"
    )

    print(
        "POSTS WITH COMMENTS"
    )

    print(
        "================================"
    )

    for post in posts_with_comments:

        print(
            "\nPost:",
            post[
                "post_number"
            ]
        )

        print(
            "Comments:",
            post[
                "comments"
            ]
        )

        print(
            "URL:",
            post[
                "direct_url"
            ]
        )

    if not posts_with_comments:

        print(
            "No posts with comments."
        )

        context.close()

        return

    # ==================================================
    # 6. SELECT BEST POST
    # ==================================================

    posts_with_urls = [
        post
        for post
        in posts_with_comments
        if post[
            "direct_url"
        ]
    ]

    if posts_with_urls:

        selected_post = max(
            posts_with_urls,
            key=lambda item:
                item[
                    "comments"
                ]
        )

    else:

        selected_post = max(
            posts_with_comments,
            key=lambda item:
                item[
                    "comments"
                ]
        )

    print(
        "\n================================"
    )

    print(
        "SELECTED POST"
    )

    print(
        "================================"
    )

    print(
        "Post:",
        selected_post[
            "post_number"
        ]
    )

    print(
        "LinkedIn reported comments:",
        selected_post[
            "comments"
        ]
    )

    print(
        "URL:",
        selected_post[
            "direct_url"
        ]
    )

    # ==================================================
    # 7. OPEN SELECTED POST
    # ==================================================

    if selected_post[
        "direct_url"
    ]:

        page.goto(
            selected_post[
                "direct_url"
            ],
            wait_until="domcontentloaded"
        )

        page.wait_for_timeout(
            5000
        )

        current_headings = (
            page.get_by_role(
                "heading",
                name="Feed post",
                exact=True
            )
        )

        if (
            current_headings.count()
            == 0
        ):

            print(
                "Could not find direct post."
            )

            context.close()

            return

        post_container = (
            find_post_container(
                current_headings.nth(
                    0
                )
            )
        )

    else:

        original_index = (
            selected_post[
                "post_number"
            ]
            - 1
        )

        post_container = (
            find_post_container(
                feed_headings.nth(
                    original_index
                )
            )
        )

    if post_container is None:

        print(
            "Could not isolate selected post."
        )

        context.close()

        return

    # ==================================================
    # 8. OPEN COMMENTS
    # ==================================================

    comment_info = (
        find_numeric_comment_button(
            post_container
        )
    )

    if comment_info:

        print(
            "\nOpening comments..."
        )

        try:

            comment_info[
                "button"
            ].scroll_into_view_if_needed()

            page.wait_for_timeout(
                700
            )

            comment_info[
                "button"
            ].click()

            page.wait_for_timeout(
                3500
            )

        except Exception as error:

            print(
                "Could not open comments:"
            )

            print(
                error
            )

    # ==================================================
    # 9. SORT BY MOST RECENT
    # ==================================================

    switch_comment_sort_to_most_recent(
        page
    )

    # ==================================================
    # 10. DISCOVER COMMENT AUTHORS
    # ==================================================

    print(
        "\n================================"
    )

    print(
        "COMMENT DISCOVERY"
    )

    print(
        "================================"
    )

    (
        discovered_authors,
        rounds_completed
    ) = load_available_comments(
        page,
        selected_post[
            "comments"
        ]
    )

    # ==================================================
    # 11. SUMMARY
    # ==================================================

    print(
        "\n================================"
    )

    print(
        "COMMENT LOADING SUMMARY"
    )

    print(
        "================================"
    )

    print(
        "LinkedIn reported comments:",
        selected_post[
            "comments"
        ]
    )

    print(
        "Loading rounds:",
        rounds_completed
    )

    print(
        "Unique authors encountered:",
        len(
            discovered_authors
        )
    )

    # ==================================================
    # 12. BUILD RAW CANDIDATES
    # ==================================================

    raw_candidates = []

    selected_profile_normalized = (
        normalize_profile_url(
            selected_profile
        )
    )

    for (
        profile_url,
        block
    ) in discovered_authors.items():

        profile_url = (
            normalize_profile_url(
                profile_url
            )
        )

        if not profile_url:
            continue

        if (
            profile_url
            == selected_profile_normalized
        ):
            continue

        raw_candidates.append(
            {

                "profile_url":
                    profile_url,

                "comment_context":
                    block.get(
                        "context",
                        ""
                    ),

                "source_connection":
                    selected_profile,

                "source_post_number":
                    selected_post[
                        "post_number"
                    ],

                "source_post_url":
                    selected_post[
                        "direct_url"
                    ],

                "visible_comment_count":
                    selected_post[
                        "comments"
                    ]
            }
        )

    print(
        "\nRaw candidate authors:",
        len(
            raw_candidates
        )
    )

    # ==================================================
    # 13. PARSE
    # ==================================================

    structured_candidates = []

    for candidate in (
        raw_candidates
    ):

        structured_candidates.append(
            parse_candidate_context(
                candidate
            )
        )

    print(
        "Parsed candidate records:",
        len(
            structured_candidates
        )
    )

    # ==================================================
    # 14. DEDUPLICATE
    # ==================================================

    structured_candidates = (
        deduplicate_candidates(
            structured_candidates
        )
    )

    print(
        "Unique parsed people:",
        len(
            structured_candidates
        )
    )

    # ==================================================
    # 15. FILTER EXISTING CONNECTIONS
    # ==================================================

    eligible_candidates = (
        filter_eligible_candidates(
            structured_candidates,
            visible_connections
        )
    )

    # ==================================================
    # 16. DISPLAY RESULTS
    # ==================================================

    print(
        "\n================================"
    )

    print(
        "FINAL UNIQUE CANDIDATES"
    )

    print(
        "================================"
    )

    print(
        "\nEligible candidates:",
        len(
            eligible_candidates
        )
    )

    for number, candidate in enumerate(
        eligible_candidates,
        start=1
    ):

        print(
            "\n--------------------------------"
        )

        print(
            "CANDIDATE",
            number
        )

        print(
            "NAME:",
            candidate.get(
                "name"
            )
        )

        print(
            "DEGREE:",
            candidate.get(
                "connection_degree"
            )
        )

        print(
            "HEADLINE:",
            candidate.get(
                "headline"
            )
        )

        print(
            "PROFILE:",
            candidate.get(
                "profile_url"
            )
        )

        print(
            "COMMENT:"
        )

        print(
            (
                candidate.get(
                    "comment_text"
                )
                or ""
            )[:500]
        )

    # ==================================================
    # 17. SAVE
    # ==================================================

    saved_candidates = (
        save_candidates_to_json(
            eligible_candidates
        )
    )

    print(
        "\n================================"
    )

    print(
        "CANDIDATES SAVED"
    )

    print(
        "================================"
    )

    print(
        "Eligible candidates this run:",
        len(
            eligible_candidates
        )
    )

    print(
        "Total unique candidates saved:",
        len(
            saved_candidates
        )
    )

    print(
        "File:",
        CANDIDATE_FILE
    )

    input(
        "\nPress Enter to close..."
    )

    context.close()


with sync_playwright() as playwright:

    run(playwright)