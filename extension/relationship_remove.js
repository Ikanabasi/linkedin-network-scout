(() => {

    if (window.__NETWORK_SCOUT_RELATIONSHIP_REMOVE__) {
        return;
    }

    window.__NETWORK_SCOUT_RELATIONSHIP_REMOVE__ = true;

    const PROFILE_TIMEOUT_MS = 20000;
    const POLL_INTERVAL_MS = 400;


    // ======================================================
    // BASIC HELPERS
    // ======================================================

    function sleep(ms) {
        return new Promise(
            (resolve) => setTimeout(resolve, ms)
        );
    }


    function normalizeText(value) {
        return String(value || "")
            .replace(/\u200b/g, "")
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
                window.getComputedStyle(element);

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


    function elementLabel(element) {

        if (!element) {
            return "";
        }

        return normalizeText(
            [
                element.innerText,
                element.textContent,
                element.getAttribute("aria-label"),
                element.getAttribute("title")
            ]
                .filter(Boolean)
                .join(" ")
        );
    }


    function clickElement(element) {

        if (!element) {
            return false;
        }

        try {

            element.scrollIntoView({
                block: "center",
                inline: "center"
            });

        } catch (error) {
            // Optional.
        }

        try {

            element.click();

            return true;

        } catch (error) {

            console.warn(
                "Native click failed:",
                error
            );
        }

        try {

            element.dispatchEvent(
                new MouseEvent(
                    "click",
                    {
                        bubbles: true,
                        cancelable: true,
                        view: window
                    }
                )
            );

            return true;

        } catch (error) {

            console.error(
                "Fallback click failed:",
                error
            );

            return false;
        }
    }


    function normalizeProfileUrl(value) {

        try {

            const url =
                new URL(value);

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
    // SECURITY / LOGIN
    // ======================================================

    function detectNeedsAttention() {

        const currentUrl =
            window.location.href.toLowerCase();

        if (
            currentUrl.includes("/login")
            ||
            currentUrl.includes("/checkpoint/")
            ||
            currentUrl.includes("/challenge/")
            ||
            currentUrl.includes("/authwall")
        ) {

            return (
                "LinkedIn requires login "
                +
                "or security verification."
            );
        }

        const bodyText =
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
                bodyText.includes(signal)
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
    // PROFILE
    // ======================================================

    function getMain() {

        const main =
            document.querySelector("main");

        if (
            main
            &&
            isVisible(main)
        ) {
            return main;
        }

        return null;
    }


    function findHeading() {

        const headings =
            Array.from(
                document.querySelectorAll(
                    "main h1, h1"
                )
            );

        for (const heading of headings) {

            if (!isVisible(heading)) {
                continue;
            }

            const text =
                normalizeText(
                    heading.innerText
                    ||
                    heading.textContent
                );

            if (text) {
                return heading;
            }
        }

        return null;
    }


    function getVisibleControls(
        root = document
    ) {

        if (!root) {
            return [];
        }

        return Array.from(
            root.querySelectorAll(
                [
                    "button",
                    "a[role='button']",
                    "a[aria-label]",
                    "[role='button']",
                    "[role='menuitem']",
                    "[aria-label]"
                ].join(",")
            )
        )
            .filter(isVisible);
    }


    async function waitForProfile() {

        const startedAt =
            Date.now();

        while (
            Date.now() - startedAt
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

            const main =
                getMain();

            if (
                main
                &&
                (
                    findHeading()
                    ||
                    getVisibleControls(main).length > 0
                )
            ) {

                return {
                    ready: true,
                    attention: null
                };
            }

            await sleep(
                POLL_INTERVAL_MS
            );
        }

        return {
            ready: false,
            attention: null
        };
    }


    // ======================================================
    // GENERIC CONTROL SEARCH
    // ======================================================

    function findControl(
        labels,
        root = document
    ) {

        const wanted =
            labels.map(lowerText);

        const controls =
            getVisibleControls(root);

        // Exact match first.
        for (const control of controls) {

            const label =
                lowerText(
                    elementLabel(control)
                );

            if (
                wanted.includes(label)
            ) {
                return control;
            }
        }

        // Prefix match.
        for (const control of controls) {

            const label =
                lowerText(
                    elementLabel(control)
                );

            for (const wantedLabel of wanted) {

                if (
                    label.startsWith(
                        wantedLabel + " "
                    )
                ) {
                    return control;
                }
            }
        }

        // Contains match.
        for (const control of controls) {

            const label =
                lowerText(
                    elementLabel(control)
                );

            for (const wantedLabel of wanted) {

                if (
                    label.includes(
                        wantedLabel
                    )
                ) {
                    return control;
                }
            }
        }

        return null;
    }


    // ======================================================
    // TOP PROFILE
    // ======================================================

    // Scope relationship decisions to the first profile action group.
    // Some LinkedIn layouts do not use H1, and the page title may include
    // relationship badges or other text. Neither is a reliable anchor.
    function getTopProfileContainer() {
        // LinkedIn may render the top profile controls outside an H1 or section.
        // Prefer the first tightly grouped row of primary profile actions.
        // A recommendation card farther down the page must never qualify.
        const main = getMain() || document.querySelector("[role='main']");
        if (!main || !isVisible(main)) return null;

        const mainRect = main.getBoundingClientRect();
        const mainTop = mainRect.top + window.scrollY;
        const leafButtons = Array.from(main.querySelectorAll(
            "button, a[role='button'], a[aria-label], [role='button']"
        )).filter(isVisible).filter(el =>
            !el.querySelector("button, a[role='button'], [role='button']")
        );

        function kind(el) {
            const labels = [
                el.getAttribute("aria-label"), el.getAttribute("title"),
                el.innerText, el.textContent
            ].map(lowerText).filter(Boolean);
            if (labels.some(v => /^message(?:\s|$)/.test(v))) return "message";
            if (labels.some(v => /^pending(?:\s|$)/.test(v))) return "pending";
            if (labels.some(v => /^connect(?:\s|$)/.test(v) || v.includes("invite to connect"))) return "connect";
            if (labels.some(v => /^following(?:\s|$)/.test(v))) return "following";
            if (labels.some(v => /^follow(?:\s|$)/.test(v))) return "follow";
            if (labels.some(v => v === "more" || /^more actions(?:\s|$)/.test(v))) return "more";
            return null;
        }

        const actions = leafButtons.map(el => ({ el, type: kind(el), rect: el.getBoundingClientRect() }))
            .filter(item => item.type && item.rect.width > 0 && item.rect.height > 0)
            .filter(item => {
                const y = item.rect.top + window.scrollY;
                return y >= mainTop - 120 && y < mainTop + 1100;
            })
            .sort((a, b) => a.rect.top - b.rect.top);

        // A genuine top-card row normally has Message plus a relationship
        // action, or a relationship action alongside More. Require two
        // DIFFERENT controls on the SAME row to prevent unrelated Pending.
        for (const anchor of actions) {
            if (!["message", "pending", "connect", "follow", "following"].includes(anchor.type)) continue;
            const row = actions.filter(item =>
                Math.abs(item.rect.top - anchor.rect.top) <= 60
                && Math.abs(item.rect.left - anchor.rect.left) <= 850
            );
            const types = new Set(row.map(item => item.type));
            const containsRelationship = [...types].some(type =>
                ["pending", "connect", "follow", "following"].includes(type));
            if (!containsRelationship || row.length < 2) continue;
            if (!types.has("message") && !types.has("more")) continue;

            // Smallest common ancestor of the two visible top-row controls.
            // Never broaden to main/body: those contain unrelated profiles.
            let node = anchor.el.parentElement;
            while (node && node !== main) {
                if (row.every(item => node.contains(item.el))) {
                    const text = normalizeText(node.innerText || "");
                    if (text.length <= 6000) return node;
                    break;
                }
                node = node.parentElement;
            }

            // Some LinkedIn layouts put Message / Pending / More in
            // separate nested containers. Their common ancestor can be
            // the whole page or a giant section. Keep the ORIGINAL live
            // buttons scoped to the verified top action row instead of
            // rejecting the profile or broadening searches to all of main.
            const safeRow = row.filter(item =>
                Math.abs(item.rect.top - anchor.rect.top) <= 60
            ).map(item => item.el);
            return {
                querySelectorAll(selector) {
                    // This virtual scope holds the original clickable elements.
                    // Avoid scanning descendant text across other profile cards.
                    if (selector === "*") return [];
                    return safeRow.filter(el => {
                        try { return el.matches(selector); }
                        catch (_) { return false; }
                    });
                }
            };
        }
        return null;
    }

    function findProfileControl(labels) {
        const root = getTopProfileContainer();
        return root ? findControl(labels, root) : null;
    }

    // ======================================================
    // RELATIONSHIP STATE
    // ======================================================

    function findPendingControl() {
        const root = getTopProfileContainer();
        if (!root) return null;
        const expected = normalizeProfileUrl(window.location.href);
        const controls = getVisibleControls(root);
        return controls.find(control => {
            const label = lowerText(elementLabel(control));
            const aria = lowerText(control.getAttribute('aria-label'));
            const isPending = label === 'pending'
                || label.startsWith('pending ')
                || label === 'invitation pending'
                || label.startsWith('invitation pending ')
                || aria.includes('click to withdraw invitation');
            if (!isPending) return false;
            if (control.matches('a[href]')) {
                // LinkedIn renders Pending as an ordinary <a> without role=button.
                // Do not accept an unrelated person's Pending link.
                return normalizeProfileUrl(control.href) === expected;
            }
            return true;
        }) || null;
    }

    function detectFirstDegree() {

        const container =
            getTopProfileContainer();

        if (!container) {
            return null;
        }

        const elements =
            Array.from(
                container.querySelectorAll("*")
            )
                .filter(isVisible);


        for (const element of elements) {

            const aria =
                lowerText(
                    element.getAttribute(
                        "aria-label"
                    )
                );

            if (
                aria.includes("1st degree")
                ||
                aria.includes(
                    "first degree connection"
                )
            ) {

                return normalizeText(
                    element.getAttribute(
                        "aria-label"
                    )
                );
            }
        }


        for (const element of elements) {

            const text =
                lowerText(
                    element.innerText
                    ||
                    element.textContent
                );

            if (
                text === "1st"
                ||
                text === "1st degree"
                ||
                text === "1st-degree"
                ||
                text === "1st degree connection"
            ) {

                return normalizeText(
                    element.innerText
                    ||
                    element.textContent
                );
            }
        }

        return null;
    }


    function findDirectConnect() {
        const root = getTopProfileContainer();
        if (!root) return null;

        // Inspect each action's labels separately. elementLabel() joins the
        // button text, textContent and aria-label, yielding strings such as
        // "connect connect invite to connect" that fail exact comparisons.
        const controls = getVisibleControls(root).filter(element =>
            element.matches("button, a[role='button'], a[aria-label], [role='button']")
        );

        for (const control of controls) {
            // Do not allow a wrapper to borrow the text of a nested button.
            if (control.querySelector("button, a[role='button'], a[aria-label], [role='button']")) {
                continue;
            }

            const labels = [
                control.getAttribute("aria-label"),
                control.innerText,
                control.textContent,
                control.getAttribute("title")
            ].map(lowerText).filter(Boolean);

            const isConnect = labels.some(label =>
                label === "connect"
                || /^connect\s+(with\s+)?[\p{L}\p{N}]/u.test(label)
                || /^invite\s+.+\s+to\s+connect(?:\b|$)/u.test(label)
                || label === "invite to connect"
            );

            if (isConnect) return control;
        }

        return null;
    }

    function findFollowingButton() {
        const root = getTopProfileContainer();
        if (!root) return null;
        return getVisibleControls(root).find(element => {
            const label = lowerText(elementLabel(element));
            return label === 'following' || label.startsWith('following ');
        }) || null;
    }

    function findFollowButton() {
        const root = getTopProfileContainer();
        if (!root) return null;
        return getVisibleControls(root).find(element => {
            const label = lowerText(elementLabel(element));
            return label === 'follow' || label.startsWith('follow ');
        }) || null;
    }

    // ======================================================
    // MORE MENU
    // ======================================================

    function findMoreButton() {
        return findProfileControl(['More', 'More actions']);
    }

    function getVisibleMenu() {

        const menus =
            Array.from(
                document.querySelectorAll(
                    [
                        "[role='menu']",
                        ".artdeco-dropdown__content",
                        ".artdeco-dropdown__content-inner"
                    ].join(",")
                )
            )
                .filter(isVisible);

        if (!menus.length) {
            return null;
        }

        return menus[
            menus.length - 1
        ];
    }


    async function openMoreMenu() {

        const more =
            findMoreButton();

        if (!more) {
            return null;
        }

        clickElement(more);

        for (
            let attempt = 0;
            attempt < 10;
            attempt += 1
        ) {

            await sleep(250);

            const menu =
                getVisibleMenu();

            if (menu) {
                return menu;
            }
        }

        return null;
    }


    function closeMenu() {

        try {
            document.body.click();
        } catch (error) {
            // Ignore.
        }
    }


    async function inspectMoreMenu() {

        const menu =
            await openMoreMenu();

        if (!menu) {

            return {
                menu: null,
                withdraw: null,
                connect: null,
                unfollow: null,
                follow: null
            };
        }

        return {
            menu,

            withdraw:
                findControl(
                    [
                        "Withdraw invitation",
                        "Withdraw",
                        "Cancel invitation",
                        "Withdraw connection request"
                    ],
                    menu
                ),

            connect:
                findControl(
                    ["Connect"],
                    menu
                ),

            unfollow:
                findControl(
                    ["Unfollow"],
                    menu
                ),

            follow:
                findControl(
                    ["Follow"],
                    menu
                )
        };
    }


    // ======================================================
    // DIALOG
    // ======================================================

    function getVisibleDialog() {

        const dialogs =
            Array.from(
                document.querySelectorAll(
                    [
                        "[role='dialog']",
                        ".artdeco-modal"
                    ].join(",")
                )
            )
                .filter(isVisible);

        if (!dialogs.length) {
            return null;
        }

        return dialogs[
            dialogs.length - 1
        ];
    }


    function findWithdrawAction(
        root = document
    ) {

        return findControl(
            [
                "Withdraw invitation",
                "Withdraw",
                "Cancel invitation",
                "Withdraw connection request"
            ],
            root
        );
    }


    // ======================================================
    // SUBMIT WITHDRAW
    // ======================================================

    async function clickFinalWithdraw(
        withdraw
    ) {

        if (!withdraw) {

            return {
                submitted: false
            };
        }


        const wasInsideDialog =
            Boolean(
                withdraw.closest(
                    [
                        "[role='dialog']",
                        ".artdeco-modal"
                    ].join(",")
                )
            );


        if (
            !clickElement(withdraw)
        ) {

            return {
                submitted: false
            };
        }


        await sleep(650);


        /*
            Sometimes the first Withdraw option
            opens another confirmation dialog.
        */
        if (!wasInsideDialog) {

            const dialog =
                getVisibleDialog();

            if (dialog) {

                const confirmation =
                    findWithdrawAction(
                        dialog
                    );

                if (confirmation) {

                    if (
                        !clickElement(
                            confirmation
                        )
                    ) {

                        return {
                            submitted: false
                        };
                    }

                    await sleep(650);
                }
            }
        }


        /*
            IMPORTANT:

            Do not verify against this DOM.

            The page may still contain stale
            Pending state.

            Tell the extension controller that
            the action was submitted. It will
            reload LinkedIn and verify the fresh
            server state.
        */

        return {
            submitted: true
        };
    }


    // ======================================================
    // ACTION: CANCEL INVITE
    // ======================================================

    async function submitCancelInvite() {

        if (!getTopProfileContainer()) {
            return {
                verified: false,
                status: "profile_header_unverified",
                message: "Could not identify the selected profile header. No relationship change was recorded."
            };
        }


        const firstDegree =
            detectFirstDegree();

        if (firstDegree) {

            return {
                verified: false,

                status:
                    "state_changed_connected",

                verificationText:
                    firstDegree,

                message:
                    (
                        "This person has already "
                        +
                        "accepted the invitation."
                    )
            };
        }


        // --------------------------------------------------
        // DIRECT PENDING
        // --------------------------------------------------

        const pending =
            findPendingControl();

        if (pending) {

            clickElement(pending);

            await sleep(650);

            const withdraw =
                findWithdrawAction();

            if (withdraw) {

                const result =
                    await clickFinalWithdraw(
                        withdraw
                    );

                if (result.submitted) {

                    return {
                        verified: false,

                        status:
                            "withdraw_submitted",

                        verificationText:
                            null,

                        message:
                            (
                                "Withdraw was submitted. "
                                +
                                "Network Scout will reload "
                                +
                                "LinkedIn to verify it."
                            )
                    };
                }

                return {
                    verified: false,

                    status:
                        "withdraw_click_failed",

                    verificationText:
                        null,

                    message:
                        (
                            "Network Scout found Withdraw "
                            +
                            "but could not activate it."
                        )
                };
            }
        }


        closeMenu();

        await sleep(250);


        // --------------------------------------------------
        // MORE -> WITHDRAW
        // --------------------------------------------------

        const menuState =
            await inspectMoreMenu();

        if (menuState.withdraw) {

            const result =
                await clickFinalWithdraw(
                    menuState.withdraw
                );

            if (result.submitted) {

                return {
                    verified: false,

                    status:
                        "withdraw_submitted",

                    verificationText:
                        null,

                    message:
                        (
                            "Withdraw was submitted. "
                            +
                            "Network Scout will reload "
                            +
                            "LinkedIn to verify it."
                        )
                };
            }

            return {
                verified: false,

                status:
                    "withdraw_click_failed",

                verificationText:
                    null,

                message:
                    (
                        "Network Scout found Withdraw "
                        +
                        "but could not activate it."
                    )
            };
        }


        /*
            The invitation may already have been
            withdrawn during a previous attempt.

            Do not fail yet.

            Ask the controller to reload and verify.
        */
        if (
            menuState.connect
            ||
            findDirectConnect()
        ) {

            closeMenu();

            return {
                verified: false,

                status:
                    "fresh_verification_required",

                verificationText:
                    null,

                message:
                    (
                        "No pending invitation is "
                        +
                        "currently visible. Network Scout "
                        +
                        "will reload LinkedIn to verify."
                    )
            };
        }


        closeMenu();


        /*
            Still do a fresh reload before declaring
            failure. This handles the exact case we
            have right now: the invitation was already
            successfully withdrawn during the previous
            attempt, while the Tracked card remained stale.
        */

        return {
            verified: false,

            status:
                "fresh_verification_required",

            verificationText:
                null,

            message:
                (
                    "Network Scout will reload "
                    +
                    "LinkedIn and inspect the "
                    +
                    "current invitation state."
                )
        };
    }


    // ======================================================
    // VERIFY CANCEL INVITE AFTER FRESH RELOAD
    // ======================================================

    async function verifyCancelledAfterReload() {

        if (!getTopProfileContainer()) {
            return {
                verified: false,
                status: "profile_header_unverified",
                message: "Could not identify the selected profile header. No relationship change was recorded."
            };
        }


        const attention =
            detectNeedsAttention();

        if (attention) {

            return {
                verified: false,

                status:
                    "needs_attention",

                verificationText:
                    attention,

                message:
                    attention
            };
        }


        const firstDegree =
            detectFirstDegree();

        if (firstDegree) {

            return {
                verified: false,

                status:
                    "state_changed_connected",

                verificationText:
                    firstDegree,

                message:
                    (
                        "LinkedIn now shows this person "
                        +
                        "as a 1st-degree connection."
                    )
            };
        }


        /*
            This is now a FRESH LinkedIn page.

            If Pending exists after the reload,
            withdrawal definitely did not stick.
        */

        const pending =
            findPendingControl();

        if (pending) {

            return {
                verified: false,

                status:
                    "still_pending",

                verificationText:
                    elementLabel(pending),

                message:
                    (
                        "LinkedIn still shows the "
                        +
                        "invitation as Pending after "
                        +
                        "a fresh reload."
                    )
            };
        }


        /*
            Look for a direct Connect signal.
        */

        const directConnect =
            findDirectConnect();

        if (directConnect) {

            return {
                verified: true,

                status:
                    "verified_cancelled",

                verificationText:
                    (
                        "Fresh LinkedIn reload shows "
                        +
                        "Connect and no Pending invitation."
                    ),

                message:
                    (
                        "LinkedIn verified that the "
                        +
                        "invitation was withdrawn."
                    )
            };
        }


        /*
            Look inside More.

            If Withdraw still exists, it is still pending.

            If Connect exists, cancellation is confirmed.
        */

        const menuState =
            await inspectMoreMenu();

        if (menuState.withdraw) {

            closeMenu();

            return {
                verified: false,

                status:
                    "still_pending",

                verificationText:
                    elementLabel(
                        menuState.withdraw
                    ),

                message:
                    (
                        "LinkedIn still exposes "
                        +
                        "Withdraw invitation after "
                        +
                        "the fresh reload."
                    )
            };
        }


        if (menuState.connect) {

            closeMenu();

            return {
                verified: true,

                status:
                    "verified_cancelled",

                verificationText:
                    (
                        "Fresh LinkedIn reload shows "
                        +
                        "Connect in the profile menu."
                    ),

                message:
                    (
                        "LinkedIn verified that the "
                        +
                        "invitation was withdrawn."
                    )
            };
        }


        /*
            A withdrawn invitation does not always bring back Connect.
            Some LinkedIn profiles still offer only Follow. After a fresh
            reload, accept that as confirmation ONLY if the selected
            profile header visibly offers Follow, does not offer Pending,
            and its own opened More menu contains no Withdraw invitation.
            Never use a Follow button in a recommendation card.
        */
        const targetFollow = findFollowButton();
        const targetProfileMenuWasInspected = Boolean(menuState.menu);

        if (targetFollow && targetProfileMenuWasInspected && !menuState.withdraw) {
            closeMenu();
            return {
                verified: true,
                status: "verified_cancelled",
                verificationText:
                    "Fresh target profile shows Follow with no Pending, and its More menu has no Withdraw invitation.",
                message:
                    "LinkedIn confirmed that the invitation is no longer pending."
            };
        }

        closeMenu();


        // No positive target-profile action proves the withdrawal here.
        // Do not equate absence of Pending with success.
        return {
            verified: false,
            status: "cancellation_not_verified",
            message: "No Pending was found in this profile header, but LinkedIn did not show Connect. Cancellation needs further verification."
        };
    }


    // ======================================================
    // ACTION: UNFOLLOW
    // ======================================================

    async function submitUnfollow() {

        const pending =
            findPendingControl();

        if (pending) {

            return {
                verified: false,

                status:
                    "state_changed_pending",

                verificationText:
                    elementLabel(pending),

                message:
                    (
                        "This relationship is still "
                        +
                        "Pending. Use Cancel Invite."
                    )
            };
        }


        const firstDegree =
            detectFirstDegree();

        if (!firstDegree) {

            return {
                verified: false,

                status:
                    "connection_not_verified",

                verificationText:
                    null,

                message:
                    (
                        "Network Scout could not "
                        +
                        "verify a 1st-degree connection."
                    )
            };
        }


        const following =
            findFollowingButton();

        if (following) {

            clickElement(following);

            await sleep(600);

            const unfollow =
                findControl(
                    ["Unfollow"]
                );

            if (unfollow) {

                clickElement(unfollow);

                await sleep(600);
            }

            return {
                verified: false,

                status:
                    "unfollow_submitted",

                verificationText:
                    null,

                message:
                    (
                        "Unfollow was submitted. "
                        +
                        "Network Scout will reload "
                        +
                        "LinkedIn to verify it."
                    )
            };
        }


        const menuState =
            await inspectMoreMenu();

        if (menuState.unfollow) {

            clickElement(
                menuState.unfollow
            );

            await sleep(600);

            return {
                verified: false,

                status:
                    "unfollow_submitted",

                verificationText:
                    null,

                message:
                    (
                        "Unfollow was submitted. "
                        +
                        "Network Scout will reload "
                        +
                        "LinkedIn to verify it."
                    )
            };
        }


        if (menuState.follow) {

            closeMenu();

            return {
                verified: false,

                status:
                    "fresh_verification_required",

                verificationText:
                    null,

                message:
                    (
                        "LinkedIn currently shows Follow. "
                        +
                        "Network Scout will reload "
                        +
                        "to verify the state."
                    )
            };
        }


        closeMenu();

        return {
            verified: false,

            status:
                "fresh_verification_required",

            verificationText:
                null,

            message:
                (
                    "Network Scout will reload "
                    +
                    "LinkedIn before determining "
                    +
                    "the final follow state."
                )
        };
    }


    // ======================================================
    // VERIFY UNFOLLOW AFTER FRESH RELOAD
    // ======================================================

    async function verifyUnfollowAfterReload() {

        const attention =
            detectNeedsAttention();

        if (attention) {

            return {
                verified: false,

                status:
                    "needs_attention",

                verificationText:
                    attention,

                message:
                    attention
            };
        }


        const firstDegree =
            detectFirstDegree();

        if (!firstDegree) {

            return {
                verified: false,

                status:
                    "connection_not_verified",

                verificationText:
                    null,

                message:
                    (
                        "After reloading, Network Scout "
                        +
                        "could not verify the profile as "
                        +
                        "a 1st-degree connection."
                    )
            };
        }


        const following =
            findFollowingButton();

        if (following) {

            return {
                verified: false,

                status:
                    "still_following",

                verificationText:
                    elementLabel(following),

                message:
                    (
                        "LinkedIn still shows Following "
                        +
                        "after the fresh reload."
                    )
            };
        }


        const follow =
            findFollowButton();

        if (follow) {

            return {
                verified: true,

                status:
                    "verified_unfollowed",

                verificationText:
                    (
                        "Fresh LinkedIn reload "
                        +
                        "shows Follow."
                    ),

                message:
                    (
                        "LinkedIn verified that "
                        +
                        "this connection is no "
                        +
                        "longer followed."
                    )
            };
        }


        const menuState =
            await inspectMoreMenu();

        if (menuState.unfollow) {

            closeMenu();

            return {
                verified: false,

                status:
                    "still_following",

                verificationText:
                    (
                        "Fresh LinkedIn reload "
                        +
                        "still shows Unfollow."
                    ),

                message:
                    (
                        "LinkedIn still indicates "
                        +
                        "that this person is followed."
                    )
            };
        }


        if (menuState.follow) {

            closeMenu();

            return {
                verified: true,

                status:
                    "verified_unfollowed",

                verificationText:
                    (
                        "Fresh LinkedIn reload "
                        +
                        "shows Follow in More."
                    ),

                message:
                    (
                        "LinkedIn verified that "
                        +
                        "this connection is no "
                        +
                        "longer followed."
                    )
            };
        }


        closeMenu();

        return {
            verified: false,

            status:
                "unfollow_unverified",

            verificationText:
                null,

            message:
                (
                    "The fresh LinkedIn page did "
                    +
                    "not expose enough information "
                    +
                    "to verify the unfollow."
                )
        };
    }


    // ======================================================
    // COMMON VALIDATION
    // ======================================================

    async function prepareAction(
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
                ok: false,

                result: {
                    verified: false,

                    status:
                        "wrong_profile",

                    verificationText:
                        window.location.href,

                    message:
                        (
                            "Network Scout stopped because "
                            +
                            "LinkedIn opened a different profile."
                        )
                }
            };
        }


        const ready =
            await waitForProfile();

        if (!ready.ready) {

            return {
                ok: false,

                result: {
                    verified: false,

                    status:
                        ready.attention
                            ? "needs_attention"
                            : "profile_not_ready",

                    verificationText:
                        ready.attention
                        || null,

                    message:
                        ready.attention
                        ||
                        (
                            "LinkedIn profile controls "
                            +
                            "did not finish loading."
                        )
                }
            };
        }


        return {
            ok: true,
            result: null
        };
    }


    // ======================================================
    // ACTION REQUEST
    // ======================================================

    async function performRemoval(
        requestedProfileUrl,
        action
    ) {

        const prepared =
            await prepareAction(
                requestedProfileUrl
            );

        if (!prepared.ok) {
            return prepared.result;
        }


        if (
            action ===
            "cancel_invite"
        ) {

            return await submitCancelInvite();
        }


        if (
            action ===
            "unfollow"
        ) {

            return await submitUnfollow();
        }


        return {
            verified: false,

            status:
                "invalid_action",

            verificationText:
                null,

            message:
                "Unknown relationship action."
        };
    }


    // ======================================================
    // FRESH-RELOAD VERIFICATION REQUEST
    // ======================================================

    async function verifyRemoval(
        requestedProfileUrl,
        action
    ) {

        const prepared =
            await prepareAction(
                requestedProfileUrl
            );

        if (!prepared.ok) {
            return prepared.result;
        }


        if (
            action ===
            "cancel_invite"
        ) {

            return await verifyCancelledAfterReload();
        }


        if (
            action ===
            "unfollow"
        ) {

            return await verifyUnfollowAfterReload();
        }


        return {
            verified: false,

            status:
                "invalid_action",

            verificationText:
                null,

            message:
                "Unknown relationship action."
        };
    }


    // ======================================================
    // MESSAGE LISTENER
    // ======================================================

    chrome.runtime.onMessage.addListener(
        (
            message,
            sender,
            sendResponse
        ) => {

            if (
                message?.type ===
                "NETWORK_SCOUT_REMOVE_RELATIONSHIP"
            ) {

                performRemoval(
                    message.profileUrl,
                    message.action
                )
                    .then(sendResponse)
                    .catch(
                        (error) => {

                            console.error(
                                "Relationship action failed:",
                                error
                            );

                            sendResponse({
                                verified: false,
                                status: "failed",
                                verificationText: null,
                                message:
                                    error.message
                                    ||
                                    "LinkedIn relationship action failed."
                            });
                        }
                    );

                return true;
            }


            if (
                message?.type ===
                "NETWORK_SCOUT_VERIFY_RELATIONSHIP_REMOVAL"
            ) {

                verifyRemoval(
                    message.profileUrl,
                    message.action
                )
                    .then(sendResponse)
                    .catch(
                        (error) => {

                            console.error(
                                "Relationship verification failed:",
                                error
                            );

                            sendResponse({
                                verified: false,
                                status: "failed",
                                verificationText: null,
                                message:
                                    error.message
                                    ||
                                    "LinkedIn relationship verification failed."
                            });
                        }
                    );

                return true;
            }


            return false;
        }
    );

})();