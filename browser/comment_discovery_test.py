from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from post_monitor import (
    BROWSER_PROFILE_DIR,
    PAGE_SETTLE_MS,
    PAGE_TIMEOUT_MS,
    candidate_profile_urls,
    detect_linkedin_attention,
    extract_recent_posts,
    load_candidate_payload,
    load_monitored_connections,
    load_state,
    load_tracked_profile_urls,
    normalize_profile_url,
    open_posts_activity,
    select_batch,
    utc_now,
    write_json,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "test_comment_discovery.json"
)

DEBUG_FILE = (
    PROJECT_ROOT
    / "data"
    / "comment_discovery_debug.json"
)

DEFAULT_LIMIT = 10

DEFAULT_MAX_COMMENTERS = 20

MAX_LOAD_MORE_CLICKS = 8


# ==========================================================
# HELPERS
# ==========================================================

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
# OPEN COMMENTS
# ==========================================================

def click_comments_entry_point(
    page,
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

        control = controls.nth(
            index
        )

        try:

            if not control.is_visible():
                continue


            text = normalize_text(
                control.inner_text(
                    timeout=250
                )
            )


            aria = normalize_text(
                control.get_attribute(
                    "aria-label"
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
                "view" in lower
                and
                "comment" in lower
            ):

                priority = 1


            elif (
                "show" in lower
                and
                "comment" in lower
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


# ==========================================================
# MOST RECENT COMMENTS
# ==========================================================

def try_most_recent_comments(
    page,
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

        control = controls.nth(
            index
        )


        try:

            if not control.is_visible():
                continue


            text = normalize_text(
                control.inner_text(
                    timeout=250
                )
            ).lower()


            aria = normalize_text(
                control.get_attribute(
                    "aria-label"
                )
            ).lower()


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

        option = options.nth(
            index
        )


        try:

            if not option.is_visible():
                continue


            text = normalize_text(
                option.inner_text(
                    timeout=250
                )
            ).lower()


            aria = normalize_text(
                option.get_attribute(
                    "aria-label"
                )
            ).lower()


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


# ==========================================================
# LOAD MORE COMMENTS
# ==========================================================

def click_more_comments(
    page,
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

        control = controls.nth(
            index
        )


        try:

            if not control.is_visible():
                continue


            text = normalize_text(
                control.inner_text(
                    timeout=250
                )
            ).lower()


            aria = normalize_text(
                control.get_attribute(
                    "aria-label"
                )
            ).lower()


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
                900
            )


            return True


        except Exception:

            continue


    return False


# ==========================================================
# CLEAN COMMENT DATA
# ==========================================================

def clean_name(
    anchor_text: str,
    aria: str,
) -> str | None:

    for raw in [
        anchor_text,
        aria,
    ]:

        value = normalize_text(
            raw
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
            2 <= len(value) <= 120
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

        line = normalize_text(
            raw_line
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


    return normalize_text(
        " ".join(
            output
        )
    )[:1200]


# ==========================================================
# EXTRACT COMMENTERS
# ==========================================================

def extract_commenters(
    page,
) -> list[
    dict[
        str,
        Any,
    ]
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
        dict[
            str,
            Any,
        ]
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
            profile_url in seen
        ):

            continue


        name = clean_name(
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


# ==========================================================
# DEBUG
# ==========================================================

def collect_debug(
    page,
    post_url: str,
) -> dict[
    str,
    Any,
]:

    try:

        labels = page.evaluate(
            r"""
            () => Array.from(
                document.querySelectorAll(
                    (
                        "main button, "
                        +
                        "main [role='button'], "
                        +
                        "main a"
                    )
                )
            )
            .filter(
                (element) => {

                    const rect =
                        element
                            .getBoundingClientRect();


                    return (
                        rect.width > 0
                        &&
                        rect.height > 0
                    );
                }
            )
            .map(
                (element) => (

                    element.getAttribute(
                        "aria-label"
                    )
                    ||
                    element.innerText
                    ||
                    element.textContent
                    ||
                    ""

                )
                    .trim()
            )
            .filter(
                (label) =>

                    /comment|reply|react|like/i
                        .test(
                            label
                        )
            )
            .slice(
                0,
                100
            )
            """
        )


    except Exception:

        labels = []


    try:

        profile_link_count = (
            page.locator(
                "main a[href*='/in/']"
            )
            .count()
        )


    except Exception:

        profile_link_count = 0


    return {
        "captured_at":
            utc_now(),

        "post_url":
            post_url,

        "page_url":
            page.url,

        "profile_link_count":
            profile_link_count,

        "comment_related_controls":
            labels,
    }


# ==========================================================
# DISCOVER COMMENTERS
# ==========================================================

def discover_commenters(
    page,
    post_url: str,
    max_commenters: int,
) -> tuple[
    list[
        dict[
            str,
            Any,
        ]
    ],
    dict[
        str,
        Any,
    ],
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
        dict[
            str,
            Any,
        ],
    ] = {}


    for _ in range(
        MAX_LOAD_MORE_CLICKS
        +
        1
    ):

        current = (
            extract_commenters(
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
                extract_commenters(
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


    debug = (
        collect_debug(
            page,
            post_url,
        )
    )


    debug[
        "commenters_found"
    ] = len(
        discovered
    )


    return (
        list(
            discovered.values()
        )[:max_commenters],
        debug,
    )


# ==========================================================
# FILTER CANDIDATES
# ==========================================================

def filter_eligible(
    commenters: list[
        dict[
            str,
            Any,
        ]
    ],
    source_profile_url: str,
    monitored_urls: set[str],
    tracked_urls: set[str],
    known_candidate_urls: set[str],
) -> tuple[
    list[
        dict[
            str,
            Any,
        ]
    ],
    dict[
        str,
        int,
    ],
]:

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


    eligible = []


    for person in commenters:

        profile_url = (
            normalize_profile_url(
                person.get(
                    "profile_url"
                )
            )
        )


        if not profile_url:

            continue


        if (
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
            person
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
# TEST
# ==========================================================

def run_test(
    limit: int,
    max_commenters: int,
) -> None:

    connections = (
        load_monitored_connections()
    )


    if not connections:

        print(
            "[TEST] No monitored connections found."
        )


        return


    state = (
        load_state()
    )


    (
        batch,
        _,
    ) = (
        select_batch(
            connections,
            state,
            limit,
        )
    )


    monitored_urls = {
        str(
            item[
                "profile_url"
            ]
        )
        for item
        in connections
        if item.get(
            "profile_url"
        )
    }


    tracked_urls = (
        load_tracked_profile_urls()
    )


    (
        _,
        candidate_records,
        _,
    ) = (
        load_candidate_payload()
    )


    known_candidate_urls = (
        candidate_profile_urls(
            candidate_records
        )
    )


    attempts = []


    print(
        (
            "[TEST] Searching up to "
            f"{len(batch)} connections "
            "for a real post with visible comments."
        )
    )


    with sync_playwright() as playwright:

        context = (
            playwright.chromium
            .launch_persistent_context(
                user_data_dir=
                    str(
                        BROWSER_PROFILE_DIR
                    ),

                headless=
                    False,

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
                connection_index,
                connection,
            ) in enumerate(
                batch,
                start=1,
            ):

                name = (
                    connection.get(
                        "name"
                    )
                    or
                    "LinkedIn connection"
                )


                profile_url = str(
                    connection[
                        "profile_url"
                    ]
                )


                print()


                print(
                    (
                        f"[TEST] Connection "
                        f"{connection_index}/"
                        f"{len(batch)}: "
                        f"{name}"
                    )
                )


                try:

                    has_posts = (
                        open_posts_activity(
                            page,
                            profile_url,
                        )
                    )


                    if not has_posts:

                        print(
                            "[TEST]   No Posts tab."
                        )


                        continue


                    posts = (
                        extract_recent_posts(
                            page
                        )
                    )


                    if not posts:

                        print(
                            "[TEST]   No recent posts."
                        )


                        continue


                    for (
                        post_index,
                        post,
                    ) in enumerate(
                        posts,
                        start=1,
                    ):

                        post_url = str(
                            post[
                                "post_url"
                            ]
                        )


                        print(
                            (
                                f"[TEST]   Post "
                                f"{post_index}/"
                                f"{len(posts)}"
                            )
                        )


                        print(
                            f"[TEST]   {post_url}"
                        )


                        (
                            commenters,
                            debug,
                        ) = (
                            discover_commenters(
                                page,
                                post_url,
                                max_commenters,
                            )
                        )


                        attempts.append(
                            {
                                "connection_name":
                                    name,

                                "connection_profile_url":
                                    profile_url,

                                "post_url":
                                    post_url,

                                "debug":
                                    debug,
                            }
                        )


                        print(
                            (
                                "[TEST]   Visible commenters found: "
                                f"{len(commenters)}"
                            )
                        )


                        if not commenters:

                            print(
                                (
                                    "[TEST]   No visible commenters "
                                    "on this post. Trying another post."
                                )
                            )


                            continue


                        (
                            eligible,
                            counts,
                        ) = (
                            filter_eligible(
                                commenters=
                                    commenters,

                                source_profile_url=
                                    profile_url,

                                monitored_urls=
                                    monitored_urls,

                                tracked_urls=
                                    tracked_urls,

                                known_candidate_urls=
                                    known_candidate_urls,
                            )
                        )


                        preview = {
                            "test_mode":
                                True,

                            "created_at":
                                utc_now(),

                            "source_connection": {
                                "name":
                                    name,

                                "profile_url":
                                    profile_url,
                            },

                            "post": {
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
                            },

                            "filter_counts":
                                counts,

                            "commenters_found":
                                commenters,

                            "eligible_new_candidates":
                                eligible,

                            "note":
                                (
                                    "Preview only. "
                                    "No production candidates "
                                    "or notifications were modified."
                                ),
                        }


                        write_json(
                            OUTPUT_FILE,
                            preview,
                        )


                        write_json(
                            DEBUG_FILE,
                            {
                                "attempts":
                                    attempts
                            },
                        )


                        print()


                        print(
                            "===================================="
                        )


                        print(
                            "COMMENT DISCOVERY TEST PASSED"
                        )


                        print(
                            "===================================="
                        )


                        print(
                            (
                                "Commenters found: "
                                f"{len(commenters)}"
                            )
                        )


                        print(
                            (
                                "Eligible new candidates: "
                                f"{len(eligible)}"
                            )
                        )


                        print(
                            (
                                "Existing connections removed: "
                                f"{counts['existing_connections_removed']}"
                            )
                        )


                        print(
                            (
                                "Tracked removed: "
                                f"{counts['tracked_removed']}"
                            )
                        )


                        print(
                            (
                                "Existing candidates removed: "
                                f"{counts['existing_candidates_removed']}"
                            )
                        )


                        print()


                        print(
                            "Sample eligible profiles:"
                        )


                        for person in (
                            eligible[:10]
                        ):

                            print(
                                (
                                    " - "
                                    f"{person.get('name') or 'Unknown'}"
                                    " | "
                                    f"{person.get('profile_url')}"
                                )
                            )


                        print()


                        print(
                            (
                                "Preview saved to: "
                                f"{OUTPUT_FILE}"
                            )
                        )


                        print(
                            (
                                "Debug saved to: "
                                f"{DEBUG_FILE}"
                            )
                        )


                        print(
                            (
                                "Production candidates modified: NO"
                            )
                        )


                        print(
                            (
                                "Production notifications modified: NO"
                            )
                        )


                        return


                except Exception as error:

                    print(
                        (
                            "[TEST]   Failed: "
                            f"{error}"
                        )
                    )


            write_json(
                DEBUG_FILE,
                {
                    "created_at":
                        utc_now(),

                    "result":
                        "no_commenters_found",

                    "attempts":
                        attempts,
                },
            )


            print()


            print(
                "===================================="
            )


            print(
                "COMMENT DISCOVERY TEST INCOMPLETE"
            )


            print(
                "===================================="
            )


            print(
                (
                    "No post with visible commenters was found "
                    "in this test batch."
                )
            )


            print(
                (
                    "Debug saved to: "
                    f"{DEBUG_FILE}"
                )
            )


        finally:

            context.close()


# ==========================================================
# CLI
# ==========================================================

def parse_arguments() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Safely test LinkedIn comment discovery "
            "without changing production candidates "
            "or notifications."
        )
    )


    parser.add_argument(
        "--limit",
        type=int,
        default=
            DEFAULT_LIMIT,
    )


    parser.add_argument(
        "--max-commenters",
        type=int,
        default=
            DEFAULT_MAX_COMMENTERS,
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


    run_test(
        limit=
            max(
                1,
                args.limit,
            ),

        max_commenters=
            max(
                1,
                args.max_commenters,
            ),
    )


if __name__ == "__main__":

    main()