from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

BROWSER_PROFILE_DIR = (
    PROJECT_ROOT
    / "browser_data"
    / "lawyer_profile"
)

TRACKED_CONNECTIONS_FILE = (
    DATA_DIR
    / "tracked_connections.json"
)

MONITORED_CONNECTIONS_FILE = (
    DATA_DIR
    / "monitored_connections.json"
)

CONNECTIONS_URL = (
    "https://www.linkedin.com/"
    "mynetwork/invite-connect/connections/"
)


# ==========================================================
# SETTINGS
# ==========================================================

MAX_SCROLL_ROUNDS = 120

NO_GROWTH_ROUNDS_TO_STOP = 10

SCROLL_WAIT_MS = 1600

PAGE_TIMEOUT_MS = 30000

MAX_SHOW_MORE_ATTEMPTS = 20


# ==========================================================
# TIME
# ==========================================================

def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


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

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:

            return json.load(file)

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

    temporary_path = (
        path.parent
        / f"{path.name}.tmp"
    )

    with temporary_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )

    temporary_path.replace(
        path
    )


# ==========================================================
# NORMALIZATION
# ==========================================================

def normalize_profile_url(
    value: str | None,
) -> str | None:

    if not value:
        return None

    match = re.search(
        r"https://(?:www\.)?linkedin\.com/in/([^/?#]+)",
        value,
        flags=re.IGNORECASE,
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
        "https://www.linkedin.com/"
        f"in/{slug}/"
    )


# ==========================================================
# FILE FORMAT HELPERS
# ==========================================================

def extract_connections(
    payload: Any,
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

        possible_lists = [
            payload.get(
                "connections"
            ),
            payload.get(
                "tracked_connections"
            ),
            payload.get(
                "items"
            ),
        ]

        for possible in possible_lists:

            if isinstance(
                possible,
                list,
            ):

                return [
                    item
                    for item in possible
                    if isinstance(
                        item,
                        dict,
                    )
                ]

    return []


def load_tracked_lookup() -> dict[
    str,
    dict[str, Any],
]:

    payload = read_json(
        TRACKED_CONNECTIONS_FILE,
        [],
    )

    lookup: dict[
        str,
        dict[str, Any],
    ] = {}

    for item in extract_connections(
        payload
    ):

        profile_url = (
            normalize_profile_url(
                item.get(
                    "profile_url"
                )
            )
        )

        if not profile_url:
            continue

        lookup[
            profile_url
        ] = item

    return lookup


def load_existing_monitored_lookup() -> dict[
    str,
    dict[str, Any],
]:

    payload = read_json(
        MONITORED_CONNECTIONS_FILE,
        {},
    )

    lookup: dict[
        str,
        dict[str, Any],
    ] = {}

    for item in extract_connections(
        payload
    ):

        profile_url = (
            normalize_profile_url(
                item.get(
                    "profile_url"
                )
            )
        )

        if not profile_url:
            continue

        lookup[
            profile_url
        ] = item

    return lookup


# ==========================================================
# LINKEDIN ATTENTION CHECK
# ==========================================================

def detect_linkedin_attention(
    page: Page,
) -> str | None:

    current_url = (
        page.url
        .lower()
    )

    if any(
        marker in current_url
        for marker in [
            "/login",
            "/checkpoint/",
            "/challenge/",
            "/authwall",
        ]
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
                timeout=3000
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

        if signal in body_text:

            return (
                "LinkedIn requires "
                "security verification."
            )

    return None


# ==========================================================
# NAME / HEADLINE CLEANUP
# ==========================================================

def clean_name(
    anchor_text: str,
    aria_label: str,
    card_text: str,
) -> str | None:

    candidates = [
        anchor_text,
        aria_label,
    ]

    for candidate in candidates:

        value = (
            candidate
            .replace(
                "\n",
                " ",
            )
            .strip()
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        value = re.sub(
            r"^view\s+",
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

    lines = [
        re.sub(
            r"\s+",
            " ",
            line,
        ).strip()
        for line in card_text.splitlines()
        if line.strip()
    ]

    ignored = {
        "message",
        "remove connection",
        "more",
    }

    for line in lines:

        lowered = (
            line.lower()
        )

        if lowered in ignored:
            continue

        if (
            "mutual connection"
            in lowered
        ):
            continue

        if (
            lowered.startswith(
                "connected "
            )
            or
            lowered == "connected"
        ):
            continue

        if (
            2 <= len(line) <= 120
        ):
            return line

    return None


def clean_headline(
    card_text: str,
    name: str | None,
) -> str | None:

    if not card_text:
        return None

    lines = [
        re.sub(
            r"\s+",
            " ",
            line,
        ).strip()
        for line in card_text.splitlines()
        if line.strip()
    ]

    ignored = {
        "message",
        "remove connection",
        "more",
    }

    for line in lines:

        lowered = (
            line.lower()
        )

        if (
            name
            and
            lowered == name.lower()
        ):
            continue

        if lowered in ignored:
            continue

        if (
            "mutual connection"
            in lowered
        ):
            continue

        if (
            lowered.startswith(
                "connected "
            )
            or
            lowered == "connected"
        ):
            continue

        if (
            3 <= len(line) <= 300
        ):
            return line

    return None


# ==========================================================
# EXTRACT CURRENTLY MOUNTED CONNECTIONS
# ==========================================================

def extract_visible_connections(
    page: Page,
) -> dict[
    str,
    dict[str, Any],
]:

    raw_items = (
        page.locator(
            "main a[href*='/in/']"
        )
        .evaluate_all(
            """
            (anchors) => {

                return anchors.map(
                    (anchor) => {

                        const href =
                            anchor.href || "";

                        const text =
                            (
                                anchor.innerText
                                ||
                                anchor.textContent
                                ||
                                ""
                            ).trim();

                        const aria =
                            (
                                anchor.getAttribute(
                                    "aria-label"
                                )
                                ||
                                ""
                            ).trim();

                        let current =
                            anchor;

                        let bestCardText =
                            "";

                        for (
                            let i = 0;
                            i < 10;
                            i += 1
                        ) {

                            if (!current) {
                                break;
                            }

                            const currentText =
                                (
                                    current.innerText
                                    ||
                                    current.textContent
                                    ||
                                    ""
                                ).trim();

                            if (
                                currentText.length >= 10
                                &&
                                currentText.length <= 1800
                            ) {

                                bestCardText =
                                    currentText;

                                const lowered =
                                    currentText
                                        .toLowerCase();

                                const looksLikeConnection =
                                    (
                                        lowered.includes(
                                            "message"
                                        )
                                        ||
                                        lowered.includes(
                                            "connected"
                                        )
                                        ||
                                        lowered.includes(
                                            "remove connection"
                                        )
                                    );

                                if (
                                    looksLikeConnection
                                ) {

                                    break;
                                }
                            }

                            current =
                                current.parentElement;
                        }

                        return {
                            href,
                            text,
                            aria,
                            card_text:
                                bestCardText
                        };
                    }
                );
            }
            """
        )
    )

    results: dict[
        str,
        dict[str, Any],
    ] = {}

    for raw in raw_items:

        if not isinstance(
            raw,
            dict,
        ):
            continue

        profile_url = (
            normalize_profile_url(
                raw.get(
                    "href"
                )
            )
        )

        if not profile_url:
            continue

        name = clean_name(
            str(
                raw.get(
                    "text"
                )
                or ""
            ),
            str(
                raw.get(
                    "aria"
                )
                or ""
            ),
            str(
                raw.get(
                    "card_text"
                )
                or ""
            ),
        )

        headline = clean_headline(
            str(
                raw.get(
                    "card_text"
                )
                or ""
            ),
            name,
        )

        results[
            profile_url
        ] = {
            "profile_url":
                profile_url,

            "name":
                name,

            "headline":
                headline,
        }

    return results


# ==========================================================
# VISIBLE PROFILE LINK COUNT
# ==========================================================

def get_visible_profile_link_count(
    page: Page,
) -> int:

    try:

        return page.locator(
            "main a[href*='/in/']"
        ).count()

    except Exception:

        return 0


# ==========================================================
# SCROLL LAST CONNECTION INTO VIEW
# ==========================================================

def scroll_last_profile_into_view(
    page: Page,
) -> None:

    try:

        links = page.locator(
            "main a[href*='/in/']"
        )

        count = links.count()

        if count <= 0:
            return

        links.nth(
            count - 1
        ).scroll_into_view_if_needed(
            timeout=3000
        )

    except Exception:

        pass


# ==========================================================
# SCROLL INTERNAL LINKEDIN CONTAINERS
# ==========================================================

def scroll_linkedin_containers(
    page: Page,
) -> dict[str, Any]:

    try:

        result = page.evaluate(
            """
            () => {

                const main =
                    document.querySelector(
                        "main"
                    )
                    ||
                    document.body;

                if (!main) {

                    return {
                        containers: 0,
                        windowY: window.scrollY,
                        windowMax: 0
                    };
                }

                const allElements = [
                    main,
                    ...Array.from(
                        main.querySelectorAll(
                            "*"
                        )
                    )
                ];

                const scrollable =
                    allElements.filter(
                        (element) => {

                            try {

                                const style =
                                    window.getComputedStyle(
                                        element
                                    );

                                const overflowY =
                                    style.overflowY;

                                const canScroll =
                                    (
                                        overflowY === "auto"
                                        ||
                                        overflowY === "scroll"
                                    );

                                return (
                                    canScroll
                                    &&
                                    element.clientHeight > 250
                                    &&
                                    element.scrollHeight >
                                        element.clientHeight + 150
                                );

                            } catch (error) {

                                return false;
                            }
                        }
                    );

                for (
                    const element
                    of scrollable.slice(
                        0,
                        10
                    )
                ) {

                    const amount =
                        Math.max(
                            element.clientHeight
                                * 0.85,
                            700
                        );

                    element.scrollTop =
                        Math.min(
                            element.scrollTop
                                + amount,
                            element.scrollHeight
                        );
                }

                window.scrollBy(
                    0,
                    Math.max(
                        window.innerHeight
                            * 0.9,
                        900
                    )
                );

                const profileLinks =
                    Array.from(
                        main.querySelectorAll(
                            "a[href*='/in/']"
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
                        );

                const lastLink =
                    profileLinks[
                        profileLinks.length - 1
                    ];

                if (lastLink) {

                    lastLink.scrollIntoView({
                        block: "end",
                        inline: "nearest",
                        behavior: "instant"
                    });
                }

                const bodyHeight =
                    Math.max(
                        document.body.scrollHeight,
                        document.documentElement.scrollHeight
                    );

                return {
                    containers:
                        scrollable.length,

                    windowY:
                        window.scrollY,

                    windowMax:
                        Math.max(
                            0,
                            bodyHeight
                                - window.innerHeight
                        )
                };
            }
            """
        )

        if isinstance(
            result,
            dict,
        ):
            return result

    except Exception:

        pass

    return {
        "containers": 0,
        "windowY": 0,
        "windowMax": 0,
    }


# ==========================================================
# MOUSE / END KEY SCROLL
# ==========================================================

def aggressive_scroll(
    page: Page,
) -> None:

    try:

        page.mouse.wheel(
            0,
            1800,
        )

    except Exception:

        pass

    try:

        page.keyboard.press(
            "End"
        )

    except Exception:

        pass

    try:

        page.evaluate(
            """
            () => {

                window.scrollTo({
                    top:
                        document.documentElement
                            .scrollHeight,

                    behavior:
                        "instant"
                });
            }
            """
        )

    except Exception:

        pass


# ==========================================================
# SHOW MORE / LOAD MORE
# ==========================================================

def click_show_more(
    page: Page,
) -> bool:

    patterns = {
        "show more results",
        "show more connections",
        "load more",
        "see more results",
    }

    try:

        buttons = page.locator(
            "main button"
        )

        count = min(
            buttons.count(),
            250,
        )

    except Exception:

        return False

    for index in range(
        count
    ):

        button = buttons.nth(
            index
        )

        try:

            if not button.is_visible():
                continue

            text = (
                button.inner_text(
                    timeout=500
                )
                .strip()
                .lower()
            )

            aria = (
                button.get_attribute(
                    "aria-label"
                )
                or ""
            ).strip().lower()

            candidate = (
                text
                or
                aria
            )

            candidate = re.sub(
                r"\s+",
                " ",
                candidate,
            )

            if (
                candidate
                not in patterns
            ):
                continue

            print(
                (
                    "[SYNC] Activating LinkedIn "
                    f"button: {candidate!r}"
                )
            )

            button.scroll_into_view_if_needed(
                timeout=2000
            )

            button.click(
                timeout=3000
            )

            page.wait_for_timeout(
                1500
            )

            return True

        except Exception:

            continue

    return False


# ==========================================================
# ONE SCROLL / LOAD CYCLE
# ==========================================================

def load_next_connection_batch(
    page: Page,
    aggressive: bool = False,
) -> dict[str, Any]:

    scroll_last_profile_into_view(
        page
    )

    snapshot = (
        scroll_linkedin_containers(
            page
        )
    )

    try:

        page.mouse.wheel(
            0,
            1300,
        )

    except Exception:

        pass

    if aggressive:

        aggressive_scroll(
            page
        )

    page.wait_for_timeout(
        SCROLL_WAIT_MS
    )

    clicked_show_more = (
        click_show_more(
            page
        )
    )

    if clicked_show_more:

        page.wait_for_timeout(
            SCROLL_WAIT_MS
        )

    return {
        **snapshot,
        "show_more":
            clicked_show_more,
    }


# ==========================================================
# COLLECT ALL CONNECTIONS
# ==========================================================

def collect_connections(
    page: Page,
) -> dict[
    str,
    dict[str, Any],
]:

    discovered: dict[
        str,
        dict[str, Any],
    ] = {}

    previous_total = 0

    no_growth_rounds = 0

    show_more_attempts = 0


    for round_number in range(
        1,
        MAX_SCROLL_ROUNDS + 1,
    ):

        current = (
            extract_visible_connections(
                page
            )
        )

        visible_count = (
            len(current)
        )

        discovered.update(
            current
        )

        total_count = (
            len(discovered)
        )


        if (
            total_count
            >
            previous_total
        ):

            growth = (
                total_count
                -
                previous_total
            )

            no_growth_rounds = 0

        else:

            growth = 0

            no_growth_rounds += 1


        print(
            (
                f"[SYNC] Round {round_number}: "
                f"{visible_count} currently visible | "
                f"{total_count} unique accumulated | "
                f"+{growth} new"
            )
        )


        if (
            no_growth_rounds
            >=
            NO_GROWTH_ROUNDS_TO_STOP
        ):

            print(
                (
                    "[SYNC] No new connections "
                    f"after {no_growth_rounds} loading rounds."
                )
            )

            break


        previous_total = (
            total_count
        )


        aggressive = (
            no_growth_rounds >= 2
        )


        snapshot = (
            load_next_connection_batch(
                page,
                aggressive=aggressive,
            )
        )


        if (
            snapshot.get(
                "show_more"
            )
        ):

            show_more_attempts += 1


        if (
            show_more_attempts
            >
            MAX_SHOW_MORE_ATTEMPTS
        ):

            print(
                "[SYNC] Show-more safety limit reached."
            )

            break


        if (
            no_growth_rounds > 0
        ):

            visible_links = (
                get_visible_profile_link_count(
                    page
                )
            )

            print(
                (
                    "[SYNC]   loader diagnostics: "
                    f"profile links={visible_links}, "
                    f"scroll containers="
                    f"{snapshot.get('containers', 0)}, "
                    f"show_more="
                    f"{snapshot.get('show_more', False)}"
                )
            )


    return discovered


# ==========================================================
# BUILD MONITORED RECORDS
# ==========================================================

def build_monitored_records(
    discovered: dict[
        str,
        dict[str, Any],
    ],
    previous_lookup: dict[
        str,
        dict[str, Any],
    ],
    tracked_lookup: dict[
        str,
        dict[str, Any],
    ],
) -> list[dict[str, Any]]:

    now = utc_now()

    records: list[
        dict[str, Any]
    ] = []


    for (
        profile_url,
        discovered_person,
    ) in discovered.items():

        previous = (
            previous_lookup.get(
                profile_url,
                {},
            )
        )

        tracked = (
            tracked_lookup.get(
                profile_url
            )
        )

        tracked_status = (
            str(
                tracked.get(
                    "relationship_status"
                )
                if tracked
                else ""
            )
            .lower()
        )

        connected_via_network_scout = (
            tracked is not None
            and
            tracked_status
            == "connected"
        )


        record = {
            **previous,

            "profile_url":
                profile_url,

            "name":
                (
                    discovered_person.get(
                        "name"
                    )
                    or
                    previous.get(
                        "name"
                    )
                ),

            "headline":
                (
                    discovered_person.get(
                        "headline"
                    )
                    or
                    previous.get(
                        "headline"
                    )
                ),

            "relationship_status":
                "connected",

            "tracking_status":
                "active",

            "monitor_posts":
                True,

            "discover_from_comments":
                True,

            "relationship_source":
                (
                    "network_scout_connection"
                    if connected_via_network_scout
                    else
                    "existing_connection"
                ),

            "source":
                (
                    "network_scout_tracked_connection"
                    if connected_via_network_scout
                    else
                    "existing_connection_sync"
                ),

            "network_scout_tracked":
                connected_via_network_scout,

            "last_seen_at":
                now,

            "last_synced_at":
                now,
        }


        if not record.get(
            "added_at"
        ):

            record[
                "added_at"
            ] = now


        # Preserve post-monitoring fields from
        # previous runs when they already exist.

        records.append(
            record
        )


    records.sort(
        key=lambda item: (
            str(
                item.get(
                    "name"
                )
                or ""
            ).lower()
        )
    )


    return records


# ==========================================================
# SYNC
# ==========================================================

def sync_existing_connections(
    headless: bool,
) -> None:

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


    tracked_lookup = (
        load_tracked_lookup()
    )

    previous_lookup = (
        load_existing_monitored_lookup()
    )


    print(
        "[SYNC] Opening LinkedIn connections..."
    )


    with sync_playwright() as playwright:

        context = (
            playwright.chromium
            .launch_persistent_context(
                user_data_dir=str(
                    BROWSER_PROFILE_DIR
                ),

                headless=headless,

                viewport={
                    "width": 1440,
                    "height": 1000,
                },
            )
        )


        try:

            page = (
                context.pages[0]
                if context.pages
                else context.new_page()
            )


            page.goto(
                CONNECTIONS_URL,
                wait_until=
                    "domcontentloaded",
                timeout=
                    PAGE_TIMEOUT_MS,
            )


            page.wait_for_timeout(
                2500
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


            print(
                (
                    "[SYNC] Initial profile links: "
                    f"{get_visible_profile_link_count(page)}"
                )
            )


            discovered = (
                collect_connections(
                    page
                )
            )


            records = (
                build_monitored_records(
                    discovered=
                        discovered,

                    previous_lookup=
                        previous_lookup,

                    tracked_lookup=
                        tracked_lookup,
                )
            )


            payload = {
                "synced_at":
                    utc_now(),

                "count":
                    len(records),

                "connections":
                    records,
            }


            write_json(
                MONITORED_CONNECTIONS_FILE,
                payload,
            )


            network_scout_connected = sum(
                1
                for item in records
                if item.get(
                    "network_scout_tracked"
                )
            )


            old_connections = (
                len(records)
                -
                network_scout_connected
            )


            print()
            print(
                "===================================="
            )

            print(
                "NETWORK SCOUT CONNECTION MONITOR"
            )

            print(
                "===================================="
            )

            print(
                f"Total monitored: {len(records)}"
            )

            print(
                (
                    "Existing/old connections: "
                    f"{old_connections}"
                )
            )

            print(
                (
                    "Network Scout connections: "
                    f"{network_scout_connected}"
                )
            )

            print(
                (
                    "Saved to: "
                    f"{MONITORED_CONNECTIONS_FILE}"
                )
            )

            print()
            print(
                "Tracked tab was NOT modified."
            )


        finally:

            context.close()


# ==========================================================
# CLI
# ==========================================================

def parse_arguments() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Sync existing LinkedIn connections "
            "into Network Scout's separate "
            "monitoring pool."
        )
    )


    parser.add_argument(
        "--headful",
        action="store_true",
        help=(
            "Show Chromium while syncing. "
            "Useful for watching LinkedIn's "
            "lazy loading."
        ),
    )


    return parser.parse_args()


# ==========================================================
# MAIN
# ==========================================================

def main() -> None:

    args = parse_arguments()


    try:

        sync_existing_connections(
            headless=
                not args.headful
        )


    except PlaywrightTimeoutError:

        print(
            "[ERROR] LinkedIn timed out."
        )


    except RuntimeError as error:

        print(
            f"[ERROR] {error}"
        )


    except Exception as error:

        print(
            (
                "[ERROR] Existing connection "
                f"sync failed: {error}"
            )
        )


if __name__ == "__main__":
    main()