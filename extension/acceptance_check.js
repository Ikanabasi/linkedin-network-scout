(() => {

    if (window.__NETWORK_SCOUT_ACCEPTANCE_CHECK__) {
        return;
    }

    window.__NETWORK_SCOUT_ACCEPTANCE_CHECK__ = true;


    const PROFILE_TIMEOUT_MS = 20000;
    const POLL_MS = 350;


    // ======================================================
    // HELPERS
    // ======================================================

    function sleep(ms) {

        return new Promise(
            (resolve) => setTimeout(resolve, ms)
        );
    }


    function normalizeText(value) {

        return String(value || "")
            .replace(/\u200b/g, "")
            .replace(/\u00a0/g, " ")
            .replace(/\s+/g, " ")
            .trim();
    }


    function lowerText(value) {

        return normalizeText(value)
            .toLowerCase();
    }


    function isVisible(element) {

        if (!element) {
            return false;
        }


        try {

            const style =
                window.getComputedStyle(
                    element
                );


            if (
                style.display === "none"
                ||
                style.visibility === "hidden"
                ||
                Number(style.opacity) === 0
            ) {

                return false;
            }


            const rect =
                element.getBoundingClientRect();


            return (
                rect.width > 0
                &&
                rect.height > 0
            );

        } catch (error) {

            return false;
        }
    }


    function visibleText(element) {

        return normalizeText(
            element?.innerText
            ||
            element?.textContent
            ||
            ""
        );
    }


    function ariaText(element) {

        return normalizeText(
            element?.getAttribute?.(
                "aria-label"
            )
            ||
            ""
        );
    }


    function elementLabel(element) {

        return normalizeText(
            [
                visibleText(element),
                ariaText(element),
                element?.getAttribute?.(
                    "title"
                )
                || ""
            ]
                .filter(Boolean)
                .join(" ")
        );
    }


    function normalizeProfileUrl(value) {

        try {

            const url =
                new URL(value);


            if (
                url.hostname !==
                "www.linkedin.com"
            ) {

                return null;
            }


            const match =
                url.pathname.match(
                    /^\/in\/([^/]+)\/?/
                );


            if (!match) {
                return null;
            }


            return (
                "https://www.linkedin.com/in/"
                +
                match[1].toLowerCase()
                +
                "/"
            );

        } catch (error) {

            return null;
        }
    }


    // ======================================================
    // SECURITY
    // ======================================================

    function detectNeedsAttention() {

        const url =
            window.location.href
                .toLowerCase();


        if (
            url.includes("/login")
            ||
            url.includes("/checkpoint/")
            ||
            url.includes("/challenge/")
            ||
            url.includes("/authwall")
        ) {

            return (
                "LinkedIn requires login "
                +
                "or security verification."
            );
        }


        const body =
            lowerText(
                document.body?.innerText
            );


        const signals = [
            "security verification",
            "verify your identity",
            "quick security check",
            "captcha"
        ];


        for (const signal of signals) {

            if (
                body.includes(signal)
            ) {

                return (
                    "LinkedIn requires "
                    +
                    "security verification."
                );
            }
        }


        return null;
    }


    // ======================================================
    // PROFILE READY
    // ======================================================

    async function waitForProfileReady() {

        const started =
            Date.now();


        while (
            Date.now() - started
            <
            PROFILE_TIMEOUT_MS
        ) {

            const attention =
                detectNeedsAttention();


            if (attention) {

                return {
                    ready: false,
                    attention
                };
            }


            if (
                !normalizeProfileUrl(
                    window.location.href
                )
            ) {

                await sleep(POLL_MS);

                continue;
            }


            const body =
                normalizeText(
                    document.body?.innerText
                );


            if (
                (
                    document.readyState ===
                        "interactive"
                    ||
                    document.readyState ===
                        "complete"
                )
                &&
                body.length > 600
            ) {

                await sleep(500);


                return {
                    ready: true,
                    attention: null
                };
            }


            await sleep(POLL_MS);
        }


        return {
            ready:
                Boolean(
                    normalizeProfileUrl(
                        window.location.href
                    )
                ),

            attention: null
        };
    }


    // ======================================================
    // PROFILE TOP AREA
    // ======================================================

    function findProfileHeading() {

        const selectors = [
            "main h1",
            "main section h1",
            "[class*='top-card'] h1",
            "[class*='profile'] h1",
            "h1"
        ];


        for (const selector of selectors) {

            const headings =
                Array.from(
                    document.querySelectorAll(
                        selector
                    )
                );


            for (const heading of headings) {

                if (
                    isVisible(heading)
                    &&
                    visibleText(heading)
                ) {

                    return heading;
                }
            }
        }


        return null;
    }


    function getProfileTopArea() {

        const heading =
            findProfileHeading();


        if (heading) {

            const section =
                heading.closest("section");


            if (
                section
                &&
                isVisible(section)
            ) {

                return section;
            }


            let current =
                heading;


            for (
                let i = 0;
                i < 7;
                i += 1
            ) {

                const parent =
                    current?.parentElement;


                if (!parent) {

                    break;
                }


                const textLength =
                    visibleText(parent)
                        .length;


                if (
                    textLength >= 20
                    &&
                    textLength <= 7000
                ) {

                    return parent;
                }


                current =
                    parent;
            }
        }


        return (
            document.querySelector("main")
            ||
            document.body
        );
    }


    function getTopControls() {

        const root =
            getProfileTopArea();


        if (!root) {
            return [];
        }


        return Array.from(
            root.querySelectorAll(
                [
                    "button",
                    "a",
                    "[role='button']",
                    "[role='menuitem']"
                ].join(",")
            )
        )
            .filter(isVisible)
            .filter(
                (element) => {

                    try {

                        const rect =
                            element
                                .getBoundingClientRect();


                        return (
                            rect.top > -250
                            &&
                            rect.top < 1700
                        );

                    } catch (error) {

                        return false;
                    }
                }
            );
    }


    // ======================================================
    // 1ST-DEGREE VERIFICATION
    // ======================================================

    function detectFirstDegree() {

        const root =
            getProfileTopArea();


        if (!root) {
            return null;
        }


        const elements =
            Array.from(
                root.querySelectorAll(
                    [
                        "[aria-label]",
                        "span",
                        "div"
                    ].join(",")
                )
            )
                .filter(isVisible);


        for (const element of elements) {

            const aria =
                lowerText(
                    ariaText(element)
                );


            if (
                aria.includes(
                    "1st degree"
                )
                ||
                aria.includes(
                    "first degree connection"
                )
            ) {

                return ariaText(element);
            }
        }


        for (const element of elements) {

            const text =
                lowerText(
                    visibleText(element)
                );


            if (
                text === "1st"
                ||
                text === "1st degree"
                ||
                text === "1st-degree"
                ||
                text ===
                    "1st degree connection"
            ) {

                return visibleText(element);
            }
        }


        return null;
    }


    // ======================================================
    // PENDING
    // ======================================================

    function findPendingControl() {

        for (
            const control
            of getTopControls()
        ) {

            const text =
                lowerText(
                    visibleText(control)
                );


            const aria =
                lowerText(
                    ariaText(control)
                );


            if (
                text === "pending"
                ||
                text ===
                    "invitation pending"
                ||
                text ===
                    "pending invitation"
                ||
                aria === "pending"
                ||
                aria.startsWith(
                    "pending,"
                )
                ||
                aria.startsWith(
                    "pending "
                )
                ||
                aria.includes(
                    "pending invitation"
                )
                ||
                (
                    aria.includes("pending")
                    &&
                    aria.includes("withdraw")
                )
            ) {

                return control;
            }
        }


        return null;
    }


    // ======================================================
    // MORE -> WITHDRAW
    // ======================================================

    function findMoreButtons() {

        return getTopControls()
            .filter(
                (control) => {

                    const text =
                        lowerText(
                            visibleText(control)
                        );


                    const aria =
                        lowerText(
                            ariaText(control)
                        );


                    return (
                        text === "more"
                        ||
                        aria === "more"
                        ||
                        aria === "more actions"
                        ||
                        aria.startsWith(
                            "more actions"
                        )
                    );
                }
            )
            .slice(0, 6);
    }


    function getVisibleMenus() {

        const selectors = [
            "[role='menu']",
            ".artdeco-dropdown__content",
            ".artdeco-dropdown__content-inner",
            "[class*='popover']",
            "[data-popper-placement]"
        ];


        const results = [];


        for (const selector of selectors) {

            const elements =
                Array.from(
                    document.querySelectorAll(
                        selector
                    )
                )
                    .filter(isVisible);


            for (const element of elements) {

                if (
                    !results.includes(
                        element
                    )
                ) {

                    results.push(element);
                }
            }
        }


        return results;
    }


    function findWithdrawInRoot(root) {

        if (!root) {
            return null;
        }


        const elements =
            Array.from(
                root.querySelectorAll(
                    [
                        "button",
                        "a",
                        "[role='button']",
                        "[role='menuitem']",
                        "span",
                        "div",
                        "li"
                    ].join(",")
                )
            )
                .filter(isVisible);


        for (const element of elements) {

            const label =
                lowerText(
                    elementLabel(element)
                );


            if (
                label.includes(
                    "withdraw invitation"
                )
                ||
                label.includes(
                    "withdraw connection request"
                )
            ) {

                return element;
            }
        }


        return null;
    }


    async function findWithdrawAction() {

        const moreButtons =
            findMoreButtons();


        for (const more of moreButtons) {

            try {

                document.body.click();

            } catch (error) {
                // Ignore.
            }


            await sleep(150);


            try {

                more.click();

            } catch (error) {

                continue;
            }


            for (
                let attempt = 0;
                attempt < 8;
                attempt += 1
            ) {

                await sleep(250);


                const controlledId =
                    more.getAttribute(
                        "aria-controls"
                    );


                if (controlledId) {

                    const controlled =
                        document.getElementById(
                            controlledId
                        );


                    if (
                        controlled
                        &&
                        isVisible(controlled)
                    ) {

                        const withdraw =
                            findWithdrawInRoot(
                                controlled
                            );


                        if (withdraw) {

                            return withdraw;
                        }
                    }
                }


                for (
                    const menu
                    of getVisibleMenus()
                ) {

                    const withdraw =
                        findWithdrawInRoot(
                            menu
                        );


                    if (withdraw) {

                        return withdraw;
                    }
                }
            }
        }


        return null;
    }


    // ======================================================
    // CONNECT AVAILABLE?
    // ======================================================

    function findConnectControl() {

        for (
            const control
            of getTopControls()
        ) {

            const text =
                lowerText(
                    visibleText(control)
                );


            const aria =
                lowerText(
                    ariaText(control)
                );


            if (
                text === "connect"
                ||
                aria === "connect"
                ||
                aria.startsWith(
                    "connect with "
                )
                ||
                (
                    aria.startsWith("invite ")
                    &&
                    aria.includes(
                        " to connect"
                    )
                )
            ) {

                return control;
            }
        }


        return null;
    }


    // ======================================================
    // CHECK
    // ======================================================

    async function checkAcceptance(
        requestedProfileUrl
    ) {

        const requested =
            normalizeProfileUrl(
                requestedProfileUrl
            );


        const current =
            normalizeProfileUrl(
                window.location.href
            );


        if (
            !requested
            ||
            !current
            ||
            requested !== current
        ) {

            return {
                verified: false,
                status: "wrong_profile",
                message:
                    (
                        "LinkedIn opened a "
                        +
                        "different profile."
                    )
            };
        }


        const ready =
            await waitForProfileReady();


        if (!ready.ready) {

            return {
                verified: false,

                status:
                    ready.attention
                        ? "needs_attention"
                        : "profile_not_ready",

                message:
                    ready.attention
                    ||
                    (
                        "LinkedIn profile "
                        +
                        "did not finish loading."
                    )
            };
        }


        /*
            ACCEPTED.

            This is the only state that causes
            Network Scout to mark the relationship
            connected.
        */

        const firstDegree =
            detectFirstDegree();


        if (firstDegree) {

            return {
                verified: true,

                status:
                    "connected",

                verificationText:
                    firstDegree,

                message:
                    (
                        "LinkedIn now shows this "
                        +
                        "person as a 1st-degree "
                        +
                        "connection."
                    )
            };
        }


        /*
            STILL PENDING.
        */

        const pending =
            findPendingControl();


        if (pending) {

            return {
                verified: true,

                status:
                    "pending",

                verificationText:
                    elementLabel(pending)
                    ||
                    "Pending",

                message:
                    (
                        "LinkedIn still shows "
                        +
                        "the invitation as Pending."
                    )
            };
        }


        /*
            Withdraw invitation is also strong
            proof that the outbound invitation
            is still pending.
        */

        const withdraw =
            await findWithdrawAction();


        if (withdraw) {

            try {

                document.body.click();

            } catch (error) {
                // Ignore.
            }


            return {
                verified: true,

                status:
                    "pending",

                verificationText:
                    "Withdraw invitation is available.",

                message:
                    (
                        "LinkedIn still has "
                        +
                        "a pending invitation."
                    )
            };
        }


        /*
            Connect has reappeared.

            This could mean the invitation was
            withdrawn/rejected/expired. We DO NOT
            guess what happened and we DO NOT
            mark Connected.
        */

        const connect =
            findConnectControl();


        if (connect) {

            return {
                verified: true,

                status:
                    "not_pending",

                verificationText:
                    "LinkedIn currently offers Connect.",

                message:
                    (
                        "LinkedIn no longer shows "
                        +
                        "this invitation as Pending."
                    )
            };
        }


        return {
            verified: false,

            status:
                "unknown",

            message:
                (
                    "LinkedIn did not expose enough "
                    +
                    "relationship information to "
                    +
                    "determine the current state."
                )
        };
    }


    // ======================================================
    // LISTENER
    // ======================================================

    chrome.runtime.onMessage.addListener(
        (
            message,
            sender,
            sendResponse
        ) => {

            if (
                message?.type ===
                "NETWORK_SCOUT_CHECK_ACCEPTANCE"
            ) {

                checkAcceptance(
                    message.profileUrl
                )
                    .then(sendResponse)
                    .catch(
                        (error) => {

                            sendResponse({
                                verified: false,
                                status: "failed",
                                message:
                                    error.message
                                    ||
                                    (
                                        "Acceptance "
                                        +
                                        "check failed."
                                    )
                            });
                        }
                    );


                return true;
            }


            return false;
        }
    );

})();