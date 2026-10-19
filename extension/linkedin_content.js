(() => {
    if (globalThis.__NETWORK_SCOUT_LINKEDIN_CONTENT_V9__) {
        return;
    }

    globalThis.__NETWORK_SCOUT_LINKEDIN_CONTENT_V9__ = true;

    const clean = (value) =>
        String(value || "")
            .replace(/\s+/g, " ")
            .trim()
            .toLowerCase();

    // Compare name punctuation consistently (e.g. "Ayomide (Victor) Ibidapo"
    // and "Ayomide Victor Ibidapo"). Do not use partial-name matches.
    const canonicalName = (value) => String(value || "")
        .normalize("NFKD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^\p{L}\p{N}]+/gu, " ")
        .replace(/\s+/g, " ")
        .trim()
        .toLowerCase();

    const normalizeProfileUrl = (value) => {
        if (!value) return null;

        const match = String(value).match(
            /https?:\/\/(?:www\.)?linkedin\.com\/in\/([^/?#]+)/i
        );

        if (!match) return null;

        return `https://www.linkedin.com/in/${match[1].toLowerCase()}/`;
    };

    const currentProfileUrl = () =>
        normalizeProfileUrl(window.location.href);

    const visible = (element) => {
        if (!element) return false;

        const style = window.getComputedStyle(element);
        const rect = element.getBoundingClientRect();

        return (
            style.display !== "none"
            && style.visibility !== "hidden"
            && Number(style.opacity) !== 0
            && rect.width > 0
            && rect.height > 0
        );
    };

    const labelsFor = (element) => {
        const values = [
            element?.innerText,
            element?.textContent,
            element?.getAttribute?.("aria-label"),
            element?.getAttribute?.("title")
        ]
            .map(clean)
            .filter(Boolean);

        return [...new Set(values)];
    };

    const pageNeedsAttention = () => {
        const text = clean(document.body?.innerText);

        return (
            text.includes("sign in to linkedin")
            || text.includes("quick security check")
            || text.includes("verify your identity")
            || text.includes("security verification")
            || text.includes("checkpoint")
        );
    };

    const isConnectLabel = (label) =>
        label === "connect"
        || label.startsWith("connect ")
        || label.includes("invite to connect");

    const isFollowLabel = (label) =>
        (label === "follow" || label.startsWith("follow "))
        && !label.startsWith("following")
        && !label.startsWith("followers")
        && !label.startsWith("unfollow");

    const isFollowingLabel = (label) =>
        label === "following"
        || label.startsWith("following ")
        || label === "unfollow"
        || label.startsWith("unfollow ");

    const isPendingLabel = (label) =>
        label === "pending"
        || label.startsWith("pending ")
        || label.includes("withdraw invitation")
        || label.includes("invitation pending");

    const isMoreLabel = (label) =>
        label === "more"
        || label.startsWith("more ")
        || label.includes("more actions");

    const isProfileActionLabel = (label) =>
        isConnectLabel(label)
        || isFollowLabel(label)
        || isFollowingLabel(label)
        || isPendingLabel(label)
        || isMoreLabel(label)
        || label === "message"
        || label.startsWith("message ");

    const actionElementsInside = (root) =>
        [
            ...root.querySelectorAll("button, [role='button'], a")
        ].filter(visible);

    const hasVisibleProfileAction = (root) =>
        actionElementsInside(root).some((element) =>
            labelsFor(element).some(isProfileActionLabel)
        );

    /*
        LinkedIn changes the top-card markup frequently. The old version
        rejected otherwise-correct profile cards when their rendered height
        exceeded 1000px. That produced the endless "profile controls are
        still loading" state even though the profile was already visible.

        This version anchors every relationship lookup to the target profile's
        visible H1 and then chooses the smallest visible ancestor containing
        that H1 plus profile action controls. It never falls back to body/main,
        so recommendation cards for other people cannot supply Pending/Follow.
    */
    // The current LinkedIn page may display the profile name as a div/span,
    // not an H1. Resolve by the exact candidate name supplied by the sidepanel.
    // Never use the first arbitrary Pending/Follow control on the page.
    let selectedProfileName = "";
    const getProfileTopCard = (candidateName) => {
        selectedProfileName = "";
        const expected = canonicalName(candidateName);
        if (!expected) return null;
        const main = document.querySelector("main, [role='main']");
        if (!main) return null;

        const elements = [...document.querySelectorAll("h1,h2,h3,h4,span,strong,div,p,a")];
        const nameNodes = elements.filter((node) => {
            if (!visible(node) || canonicalName(node.textContent) !== expected) return false;
            // Pick the innermost exact-name node, not a wrapper containing a card.
            return ![...node.children].some((child) => canonicalName(child.textContent) === expected);
        });
        nameNodes.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);

        for (const nameNode of nameNodes) {
            // The profile header precedes the rest of the page. Reject
            // suggestions and People Also Viewed cards farther down.
            if (nameNode.getBoundingClientRect().top + window.scrollY > 1200) continue;
            let node = nameNode.parentElement;
            for (let depth = 0; node && node !== main && node !== document.body && depth < 18; depth++) {
                if (hasVisibleProfileAction(node)) {
                    selectedProfileName = nameNode.textContent.trim().replace(/\s+/g, " ");
                    return node;
                }
                node = node.parentElement;
            }
        }
        return null;
    };

    const profileNameFromRoot = () => selectedProfileName;

    const verifyExpectedProfile = (expectedUrl) => {
        const expected = normalizeProfileUrl(expectedUrl);
        const actual = currentProfileUrl();

        if (!expected || !actual) {
            return {
                ok: false,
                result: {
                    status: "wrong_profile",
                    message: "Network Scout could not verify the exact LinkedIn profile URL."
                }
            };
        }

        if (expected !== actual) {
            return {
                ok: false,
                result: {
                    status: "wrong_profile",
                    message: "LinkedIn opened a different profile, so Network Scout stopped safely."
                }
            };
        }

        return { ok: true };
    };

    const rootState = (root) => {
        if (!root) {
            return {
                status: "profile_loading",
                message: "LinkedIn profile controls are still loading."
            };
        }

        if (!selectedProfileName) {
            return {
                status: "profile_loading",
                message: "LinkedIn profile header is still loading."
            };
        }

        const elements = actionElementsInside(root);
        const allLabels = [];

        for (const element of elements) {
            for (const label of labelsFor(element)) {
                if (!allLabels.includes(label)) allLabels.push(label);
            }
        }

        const has = (predicate) => allLabels.some(predicate);

        const pending = has(isPendingLabel);
        const following = has(isFollowingLabel);
        const followAvailable = has(isFollowLabel);
        const connectAvailable = has(isConnectLabel);

        const rootText = clean(root.innerText || root.textContent);

        const connected = (
            rootText.includes("· 1st")
            || rootText.includes(" 1st ")
            || rootText.includes("1st degree")
        ) && !pending;

        return {
            status: "ready",
            elements,
            labels: allLabels,
            pending,
            following,
            followAvailable,
            connectAvailable,
            connected,
            profileName: profileNameFromRoot(root)
        };
    };

    const wait = (ms) =>
        new Promise((resolve) => setTimeout(resolve, ms));

    const waitForProfileTopCard = async (expectedUrl, candidateName, timeoutMs = 7000) => {
        const started = Date.now();

        while (Date.now() - started < timeoutMs) {
            if (pageNeedsAttention()) {
                return {
                    ok: false,
                    result: {
                        status: "needs_attention",
                        message: "LinkedIn needs sign-in or security verification."
                    }
                };
            }

            const profileCheck = verifyExpectedProfile(expectedUrl);
            if (!profileCheck.ok) return profileCheck;

            const root = getProfileTopCard(candidateName);
            const state = rootState(root);

            if (
                root
                && state.status === "ready"
                && state.profileName
                && (
                    hasVisibleProfileAction(root)
                    || state.connected
                )
            ) {
                return { ok: true, root, state };
            }

            await wait(200);
        }

        return {
            ok: false,
            result: {
                status: "profile_unavailable",
                verified: false,
                message: "The exact candidate name or its profile action bar could not be located. " +
                    "LinkedIn may render the header without an H1; Network Scout refused to inspect unrelated cards."
            }
        };
    };

    const elementMatches = (element, predicate) =>
        labelsFor(element).some(predicate);

    const findTopCardAction = (root, action) => {
        if (!root) return null;

        const elements = actionElementsInside(root);

        if (action === "connect") {
            return elements.find((element) =>
                elementMatches(element, isConnectLabel)
            ) || null;
        }

        if (action === "follow") {
            return elements.find((element) =>
                elementMatches(element, isFollowLabel)
            ) || null;
        }

        if (action === "unfollow") {
            return elements.find((element) =>
                elementMatches(element, isFollowingLabel)
            ) || null;
        }

        if (action === "more") {
            return elements.find((element) =>
                elementMatches(element, isMoreLabel)
            ) || null;
        }

        return null;
    };

    const visibleMenus = () =>
        [
            ...document.querySelectorAll(
                "[role='menu'], [role='dialog'], .artdeco-dropdown__content"
            )
        ].filter(visible);

    const findConnectFromOpenedMore = (moreButton, menusBeforeClick) => {
        const controlsId =
            moreButton?.getAttribute?.("aria-controls")
            || moreButton?.getAttribute?.("aria-owns");

        if (controlsId) {
            const controlled = document.getElementById(controlsId);

            if (controlled && visible(controlled)) {
                const match = [
                    ...controlled.querySelectorAll(
                        "[role='menuitem'], button, [role='button'], a"
                    )
                ]
                    .filter(visible)
                    .find((element) =>
                        elementMatches(element, isConnectLabel)
                    );

                if (match) return match;
            }
        }

        const before = new Set(menusBeforeClick || []);
        const newMenus = visibleMenus().filter((menu) => !before.has(menu));

        for (const menu of newMenus) {
            const match = [
                ...menu.querySelectorAll(
                    "[role='menuitem'], button, [role='button'], a"
                )
            ]
                .filter(visible)
                .find((element) =>
                    elementMatches(element, isConnectLabel)
                );

            if (match) return match;
        }

        return null;
    };

    const findNewConfirmationAction = (
        beforeContainers,
        predicate,
        excludedElement = null
    ) => {
        const before = new Set(beforeContainers || []);

        const containers = visibleMenus()
            .filter((container) => !before.has(container));

        for (const container of containers) {
            const candidate = [
                ...container.querySelectorAll(
                    "button, [role='button'], [role='menuitem'], a"
                )
            ]
                .filter(visible)
                .find((element) =>
                    element !== excludedElement
                    && elementMatches(element, predicate)
                );

            if (candidate) return candidate;
        }

        return null;
    };

    const pollState = async (
        expectedUrl,
        candidateName,
        predicate,
        timeoutMs = 4000
    ) => {
        const started = Date.now();

        while (Date.now() - started < timeoutMs) {
            const profileCheck = verifyExpectedProfile(expectedUrl);
            if (!profileCheck.ok) {
                return {
                    ok: false,
                    result: profileCheck.result
                };
            }

            const root = getProfileTopCard(candidateName);
            const state = rootState(root);

            if (state.status === "ready" && predicate(state)) {
                return { ok: true, root, state };
            }

            await wait(200);
        }

        return { ok: false };
    };

    const handleConnect = async (message) => {
        const loaded = await waitForProfileTopCard(message?.profileUrl, message?.candidateName);
        if (!loaded.ok) return loaded.result;

        const { root, state } = loaded;

        if (state.pending) {
            return {
                status: "already_pending",
                verified: true,
                profile_url: currentProfileUrl(),
                verification_text: "Pending invitation on selected profile",
                profile_name: state.profileName
            };
        }

        if (state.connected) {
            return {
                status: "already_connected",
                verified: true,
                verification_text: "Already connected on selected profile",
                profile_name: state.profileName
            };
        }

        const directConnect = findTopCardAction(root, "connect");

        if (directConnect) {
            directConnect.scrollIntoView({ block: "center", inline: "center" });
            directConnect.click();

            return {
                status: "connect_clicked",
                verified: false,
                profile_name: state.profileName
            };
        }

        /*
            Connect may be inside the selected profile's More menu.
            Capture existing menus first so we only inspect the menu created
            by this exact target profile's More button.
        */
        const moreButton = findTopCardAction(root, "more");

        if (moreButton) {
            const menusBeforeClick = visibleMenus();

            moreButton.click();
            await wait(350);

            const menuConnect =
                findConnectFromOpenedMore(moreButton, menusBeforeClick);

            if (menuConnect) {
                menuConnect.click();

                return {
                    status: "connect_clicked",
                    verified: false,
                    profile_name: state.profileName
                };
            }
        }

        if (state.followAvailable || findTopCardAction(root, "follow")) {
            return {
                status: "connect_unavailable",
                verified: false,
                follow_available: true,
                profile_name: state.profileName,
                message: "Connect is not currently available on this profile; Follow is available."
            };
        }

        return {
            status: "connect_unavailable",
            verified: false,
            follow_available: false,
            profile_name: state.profileName,
            message: "Connect is not currently available on this profile."
        };
    };

    const handleVerifyConnect = async (message) => {
        const loaded = await waitForProfileTopCard(
            message?.profileUrl, message?.candidateName,
            4500
        );

        if (!loaded.ok) return loaded.result;

        const { state } = loaded;

        if (state.pending) {
            return {
                status: "verified_pending",
                verified: true,
                relationship: "pending_connection",
                profile_url: currentProfileUrl(),
                verification_text: "Pending invitation on selected profile",
                profile_name: state.profileName
            };
        }

        if (state.connected) {
            return {
                status: "already_connected",
                verified: true,
                relationship: "connected",
                profile_url: currentProfileUrl(),
                verification_text: "Connected on selected profile",
                profile_name: state.profileName
            };
        }

        return {
            status: "connect_not_verified",
            verified: false,
            follow_available: state.followAvailable,
            connect_available: state.connectAvailable,
            profile_name: state.profileName,
            message: state.followAvailable
                ? "Connect is not currently available on this profile; Follow is available."
                : "LinkedIn did not expose a verified Pending or Connected state on this profile."
        };
    };

    const handleFollow = async (message) => {
        const loaded = await waitForProfileTopCard(message?.profileUrl, message?.candidateName);
        if (!loaded.ok) return loaded.result;

        const { root, state } = loaded;

        if (state.following) {
            return {
                status: "verified_following",
                verified: true,
                relationship: "following",
                profile_url: currentProfileUrl(),
                verification_text: "Already following selected profile",
                profile_name: state.profileName
            };
        }

        const followButton = findTopCardAction(root, "follow");

        if (!followButton) {
            return {
                status: "follow_unavailable",
                verified: false,
                message: "This exact profile does not currently expose a Follow action.",
                profile_name: state.profileName
            };
        }

        followButton.scrollIntoView({ block: "center", inline: "center" });
        followButton.click();

        /*
            A click is NOT relationship verification. Only a visible Following/
            Unfollow state on this exact profile may be recorded as Following.
        */
        const verified = await pollState(
            message?.profileUrl, message?.candidateName,
            (nextState) => nextState.following,
            4000
        );

        if (verified.ok) {
            return {
                status: "verified_following",
                verified: true,
                relationship: "following",
                profile_url: currentProfileUrl(),
                verification_text: "Following selected profile",
                profile_name: verified.state.profileName
            };
        }

        return {
            status: "follow_not_verified",
            verified: false,
            relationship: null,
            profile_name: state.profileName,
            message: "Follow was clicked, but LinkedIn has not yet exposed a verified Following state."
        };
    };

    const handleVerifyFollow = async (message) => {
        const loaded = await waitForProfileTopCard(
            message?.profileUrl, message?.candidateName,
            4500
        );

        if (!loaded.ok) return loaded.result;

        const { state } = loaded;

        return {
            status: state.following
                ? "verified_following"
                : "not_following",
            verified: state.following,
            relationship: state.following ? "following" : null,
            profile_name: state.profileName,
            verification_text: state.following
                ? "Following selected profile"
                : "Selected profile is not showing Following"
        };
    };

    const handleUnfollow = async (message) => {
        const loaded = await waitForProfileTopCard(message?.profileUrl, message?.candidateName);
        if (!loaded.ok) return loaded.result;

        const { root, state } = loaded;

        const unfollowButton = findTopCardAction(root, "unfollow");

        if (!unfollowButton) {
            return {
                status: "already_not_following",
                verified: true,
                verification_text: "Selected profile is not currently followed",
                profile_name: state.profileName
            };
        }

        const containersBeforeClick = visibleMenus();

        unfollowButton.scrollIntoView({
            block: "center",
            inline: "center"
        });

        unfollowButton.click();
        await wait(300);

        const confirmUnfollow = findNewConfirmationAction(
            containersBeforeClick,
            (label) =>
                label === "unfollow"
                || label.startsWith("unfollow "),
            unfollowButton
        );

        if (confirmUnfollow) {
            confirmUnfollow.click();
        }

        const verified = await pollState(
            message?.profileUrl, message?.candidateName,
            (nextState) => !nextState.following,
            3500
        );

        if (verified.ok) {
            return {
                status: "verified_unfollowed",
                verified: true,
                verification_text: "Selected profile is no longer followed",
                profile_name: verified.state.profileName
            };
        }

        return {
            status: "unfollow_not_verified",
            verified: false,
            profile_name: state.profileName,
            message: "Unfollow was clicked, but LinkedIn has not yet exposed a verified unfollowed state."
        };
    };

    const runAsync = (handler, message, sendResponse, fallbackStatus) => {
        Promise.resolve()
            .then(() => handler(message))
            .then(sendResponse)
            .catch((error) =>
                sendResponse({
                    status: fallbackStatus,
                    verified: false,
                    message: error?.message || String(error)
                })
            );

        return true;
    };

    chrome.runtime.onMessage.addListener(
        (message, sender, sendResponse) => {
            const type = message?.type;

            if (type === "NETWORK_SCOUT_CONNECT") {
                return runAsync(
                    handleConnect,
                    message,
                    sendResponse,
                    "connect_failed"
                );
            }

            if (type === "NETWORK_SCOUT_VERIFY_CONNECT") {
                return runAsync(
                    handleVerifyConnect,
                    message,
                    sendResponse,
                    "connect_not_verified"
                );
            }

            if (type === "NETWORK_SCOUT_FOLLOW") {
                return runAsync(
                    handleFollow,
                    message,
                    sendResponse,
                    "follow_failed"
                );
            }

            if (type === "NETWORK_SCOUT_VERIFY_FOLLOW") {
                return runAsync(
                    handleVerifyFollow,
                    message,
                    sendResponse,
                    "not_following"
                );
            }

            if (type === "NETWORK_SCOUT_UNFOLLOW") {
                return runAsync(
                    handleUnfollow,
                    message,
                    sendResponse,
                    "unfollow_failed"
                );
            }

            return false;
        }
    );
})();