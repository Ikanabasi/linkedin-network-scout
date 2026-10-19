import json
from pathlib import Path

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

TRACKED_CONNECTIONS_FILE = (
    PROJECT_ROOT
    / "data"
    / "tracked_connections.json"
)


# ======================================================
# LOAD TRACKED CONNECTIONS
# ======================================================

def load_tracked_connections():

    if not TRACKED_CONNECTIONS_FILE.exists():

        raise FileNotFoundError(
            f"Tracked connections file not found:\n"
            f"{TRACKED_CONNECTIONS_FILE}"
        )

    with TRACKED_CONNECTIONS_FILE.open(
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(
            file
        )

    if not isinstance(
        data,
        list
    ):

        raise ValueError(
            "tracked_connections.json must contain a list."
        )

    return data


# ======================================================
# PICK A CONNECTION THAT HAD NO POST
# ======================================================

def choose_debug_connection(
    tracked_connections
):

    # First preference:
    # one that our main script labelled no_recent_post.
    for connection in tracked_connections:

        if (
            connection.get(
                "last_post_status"
            )
            == "no_recent_post"
        ):

            if connection.get(
                "profile_url"
            ):

                return connection

    # Fallback:
    # first tracked connection with a profile URL.
    for connection in tracked_connections:

        if connection.get(
            "profile_url"
        ):

            return connection

    return None


# ======================================================
# BUILD ACTIVITY URL
# ======================================================

def build_activity_url(
    profile_url
):

    profile_url = (
        profile_url
        .split("?")[0]
        .split("#")[0]
        .rstrip("/")
    )

    return (
        profile_url
        + "/recent-activity/all/"
    )


# ======================================================
# MAIN
# ======================================================

def run(playwright):

    print(
        "\n================================"
    )

    print(
        "LINKEDIN ACTIVITY DEBUG"
    )

    print(
        "================================"
    )

    tracked_connections = (
        load_tracked_connections()
    )

    connection = (
        choose_debug_connection(
            tracked_connections
        )
    )

    if not connection:

        print(
            "\nNo tracked connection was available."
        )

        return

    name = (
        connection.get(
            "name"
        )
        or "Unknown"
    )

    profile_url = (
        connection.get(
            "profile_url"
        )
    )

    activity_url = (
        build_activity_url(
            profile_url
        )
    )

    print(
        "\nTesting connection:"
    )

    print(
        "Name:",
        name
    )

    print(
        "Profile:",
        profile_url
    )

    print(
        "Activity:",
        activity_url
    )

    # ==================================================
    # OPEN PERSISTENT SESSION
    # ==================================================

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

    # ==================================================
    # OPEN ACTIVITY PAGE
    # ==================================================

    print(
        "\nOpening activity page..."
    )

    page.goto(
        activity_url,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(
        6000
    )

    print(
        "\nCURRENT PAGE:"
    )

    print(
        page.url
    )

    # ==================================================
    # PAGE TITLE
    # ==================================================

    print(
        "\n================================"
    )

    print(
        "PAGE TITLE"
    )

    print(
        "================================"
    )

    try:

        print(
            page.title()
        )

    except Exception as error:

        print(
            "Could not read title:"
        )

        print(
            error
        )

    # ==================================================
    # BODY TEXT
    # ==================================================

    print(
        "\n================================"
    )

    print(
        "BODY TEXT PREVIEW"
    )

    print(
        "================================"
    )

    body_text = ""

    try:

        body_text = (
            page.locator(
                "body"
            )
            .inner_text(
                timeout=15000
            )
        )

        print(
            body_text[
                :8000
            ]
        )

    except Exception as error:

        print(
            "BODY ERROR:"
        )

        print(
            error
        )

    # ==================================================
    # H2 TEXTS
    # ==================================================

    print(
        "\n================================"
    )

    print(
        "H2 TEXTS"
    )

    print(
        "================================"
    )

    try:

        headings = (
            page.locator(
                "h2"
            )
        )

        count = (
            headings.count()
        )

        print(
            "H2 count:",
            count
        )

        for index in range(
            min(
                count,
                50
            )
        ):

            try:

                text = (
                    headings
                    .nth(
                        index
                    )
                    .inner_text()
                    .strip()
                )

                if text:

                    print(
                        index,
                        repr(
                            text
                        )
                    )

            except Exception:

                continue

    except Exception as error:

        print(
            "H2 ERROR:"
        )

        print(
            error
        )

    # ==================================================
    # ALL HEADING TEXTS
    # ==================================================

    print(
        "\n================================"
    )

    print(
        "ALL HEADING TEXTS"
    )

    print(
        "================================"
    )

    try:

        result = page.evaluate(
            """
            () => {

                return Array.from(
                    document.querySelectorAll(
                        "h1, h2, h3, h4"
                    )
                )
                .map(
                    element => ({
                        tag:
                            element.tagName,

                        text:
                            (
                                element.innerText
                                || ""
                            ).trim()
                    })
                )
                .filter(
                    item =>
                        item.text
                )
                .slice(
                    0,
                    100
                );
            }
            """
        )

        for item in result:

            print(
                item.get(
                    "tag"
                ),
                "->",
                repr(
                    item.get(
                        "text"
                    )
                )
            )

    except Exception as error:

        print(
            "HEADING ERROR:"
        )

        print(
            error
        )

    # ==================================================
    # POST-LIKE LINKS
    # ==================================================

    print(
        "\n================================"
    )

    print(
        "POST-LIKE LINKS"
    )

    print(
        "================================"
    )

    try:

        post_links = page.evaluate(
            """
            () => {

                const result = [];

                const links =
                    Array.from(
                        document.querySelectorAll(
                            "a[href]"
                        )
                    );


                for (
                    const link
                    of links
                ) {

                    const href =
                        link.href
                        || "";


                    if (
                        href.includes(
                            "/feed/update/"
                        )
                        ||
                        href.includes(
                            "/posts/"
                        )
                        ||
                        href.includes(
                            "urn:li:activity:"
                        )
                    ) {

                        result.push({

                            href:
                                href,

                            text:
                                (
                                    link.innerText
                                    || ""
                                )
                                .trim()
                                .slice(
                                    0,
                                    700
                                )
                        });
                    }
                }


                return result;
            }
            """
        )

        print(
            "Post-like link count:",
            len(
                post_links
            )
        )

        for index, item in enumerate(
            post_links[
                :30
            ],
            start=1
        ):

            print(
                f"\nPOST LINK {index}"
            )

            print(
                "URL:",
                item.get(
                    "href"
                )
            )

            print(
                "TEXT:",
                repr(
                    item.get(
                        "text"
                    )
                )
            )

    except Exception as error:

        print(
            "POST LINK ERROR:"
        )

        print(
            error
        )

    # ==================================================
    # ACTIVITY URNS IN ATTRIBUTES
    # ==================================================

    print(
        "\n================================"
    )

    print(
        "ACTIVITY URNS IN DOM"
    )

    print(
        "================================"
    )

    try:

        urns = page.evaluate(
            """
            () => {

                const found =
                    new Set();


                const elements =
                    [
                        document.documentElement,
                        ...document.querySelectorAll(
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


                        const matches =
                            value.match(
                                /urn:li:activity:\\d+/g
                            );


                        if (!matches) {

                            continue;
                        }


                        for (
                            const match
                            of matches
                        ) {

                            found.add(
                                match
                            );
                        }
                    }
                }


                return Array.from(
                    found
                );
            }
            """
        )

        print(
            "Unique activity URNs:",
            len(
                urns
            )
        )

        for urn in urns[
            :30
        ]:

            print(
                urn
            )

    except Exception as error:

        print(
            "URN ERROR:"
        )

        print(
            error
        )

    # ==================================================
    # BUTTONS CONTAINING COMMENT
    # ==================================================

    print(
        "\n================================"
    )

    print(
        "COMMENT-RELATED BUTTONS"
    )

    print(
        "================================"
    )

    try:

        comment_buttons = page.evaluate(
            """
            () => {

                return Array.from(
                    document.querySelectorAll(
                        "button"
                    )
                )
                .map(
                    button => ({

                        text:
                            (
                                button.innerText
                                || ""
                            ).trim(),

                        aria:
                            (
                                button.getAttribute(
                                    "aria-label"
                                )
                                || ""
                            ).trim()
                    })
                )
                .filter(
                    item => {

                        const combined =
                            (
                                item.text
                                + " "
                                + item.aria
                            ).toLowerCase();


                        return combined.includes(
                            "comment"
                        );
                    }
                )
                .slice(
                    0,
                    50
                );
            }
            """
        )

        print(
            "Comment-related buttons:",
            len(
                comment_buttons
            )
        )

        for index, item in enumerate(
            comment_buttons,
            start=1
        ):

            print(
                f"\nBUTTON {index}"
            )

            print(
                "TEXT:",
                repr(
                    item.get(
                        "text"
                    )
                )
            )

            print(
                "ARIA:",
                repr(
                    item.get(
                        "aria"
                    )
                )
            )

    except Exception as error:

        print(
            "COMMENT BUTTON ERROR:"
        )

        print(
            error
        )

    # ==================================================
    # END
    # ==================================================

    input(
        "\nPress Enter to close..."
    )

    context.close()


if __name__ == "__main__":

    with sync_playwright() as playwright:

        run(
            playwright
        )