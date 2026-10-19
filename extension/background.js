const RECEIPTS_KEY =
    "networkScoutActionReceipts";


const API_BASE_URL =
    "http://127.0.0.1:8000";


const ACCEPTANCE_ALARM =
    "networkScoutAcceptanceMonitor";


const ACCEPTANCE_CHECK_INTERVAL_MINUTES =
    60;


const MAX_ACCEPTANCE_CHECKS_PER_RUN =
    25;


let acceptanceMonitorRunning =
    false;


// ======================================================
// INSTALL / STARTUP
// ======================================================

chrome.runtime.onInstalled.addListener(
    () => {

        chrome.sidePanel
            .setPanelBehavior({
                openPanelOnActionClick:
                    true
            })
            .catch(
                (error) => {

                    console.warn(
                        "Side panel setup failed:",
                        error
                    );
                }
            );


        ensureAcceptanceAlarm()
            .catch(
                (error) => {

                    console.warn(
                        "Could not create acceptance alarm:",
                        error
                    );
                }
            );
    }
);


chrome.runtime.onStartup.addListener(
    () => {

        ensureAcceptanceAlarm()
            .catch(
                (error) => {

                    console.warn(
                        "Acceptance alarm startup failed:",
                        error
                    );
                }
            );


        runAcceptanceMonitor()
            .catch(
                (error) => {

                    console.warn(
                        "Startup acceptance check failed:",
                        error
                    );
                }
            );
    }
);


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
        .replace(/\s+/g, " ")
        .trim();
}


function normalizeProfileUrl(value) {

    try {

        const url =
            new URL(value);


        if (
            url.protocol !== "https:"
            ||
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
// LOCAL API
// ======================================================

async function apiFetch(
    path,
    options = {},
    timeoutMs = 10000
) {

    const controller =
        new AbortController();


    const timeout =
        setTimeout(
            () => {

                controller.abort();

            },
            timeoutMs
        );


    try {

        const response =
            await fetch(
                `${API_BASE_URL}${path}`,
                {
                    ...options,

                    signal:
                        controller.signal
                }
            );


        if (!response.ok) {

            const body =
                await response.text();


            throw new Error(
                `${path} returned ${response.status}: ${body}`
            );
        }


        const contentType =
            response.headers.get(
                "content-type"
            )
            || "";


        if (
            contentType.includes(
                "application/json"
            )
        ) {

            return await response.json();
        }


        return await response.text();

    } finally {

        clearTimeout(timeout);
    }
}


// ======================================================
// WAIT FOR TAB
// ======================================================

async function waitForTabComplete(
    tabId,
    timeoutMs = 30000
) {

    const tab =
        await chrome.tabs.get(
            tabId
        );


    if (
        tab.status ===
        "complete"
    ) {
        return;
    }


    return new Promise(
        (
            resolve,
            reject
        ) => {

            let finished = false;


            const timeout =
                setTimeout(
                    () => {

                        if (finished) {
                            return;
                        }

                        finished = true;

                        chrome.tabs.onUpdated
                            .removeListener(
                                listener
                            );

                        reject(
                            new Error(
                                "LinkedIn tab timed out."
                            )
                        );

                    },
                    timeoutMs
                );


            function listener(
                updatedTabId,
                changeInfo
            ) {

                if (
                    finished
                    ||
                    updatedTabId !== tabId
                    ||
                    changeInfo.status !==
                        "complete"
                ) {

                    return;
                }

                finished = true;

                clearTimeout(timeout);

                chrome.tabs.onUpdated
                    .removeListener(
                        listener
                    );

                resolve();
            }


            chrome.tabs.onUpdated.addListener(
                listener
            );
        }
    );
}


// ======================================================
// RECEIPTS
// ======================================================

async function storeReceipt(
    profileUrl,
    receipt
) {

    const data =
        await chrome.storage.local.get(
            RECEIPTS_KEY
        );


    const receipts =
        data[RECEIPTS_KEY]
        || {};


    receipts[profileUrl] =
        receipt;


    await chrome.storage.local.set({
        [RECEIPTS_KEY]:
            receipts
    });
}


function makeReceipt(
    profileUrl,
    candidateName,
    requestedAt,
    result
) {

    const now =
        new Date()
            .toISOString();


    return {
        action_id:
            crypto.randomUUID(),

        action:
            "CONNECT",

        candidate_name:
            candidateName
            || null,

        profile_url:
            profileUrl,

        requested_at:
            requestedAt,

        performed_at:
            now,

        verified:
            Boolean(
                result?.verified
            ),

        verified_at:
            result?.verified
                ? now
                : null,

        status:
            result?.status
            || "failed",

        verification_text:
            result?.verificationText
            ||
            result?.verification_text
            ||
            null,

        message:
            result?.message
            || null
    };
}


// ======================================================
// CONNECT CONTENT SCRIPT
// ======================================================

async function injectConnectScript(
    tabId
) {

    await chrome.scripting.executeScript({
        target: {
            tabId
        },

        files: [
            "linkedin_content.js"
        ]
    });


    await sleep(300);
}


// ======================================================
// DEBUGGER
// ======================================================

async function attachDebugger(
    tabId
) {

    const target = {
        tabId
    };


    await chrome.debugger.attach(
        target,
        "1.3"
    );


    await chrome.debugger.sendCommand(
        target,
        "Accessibility.enable"
    );


    await chrome.debugger.sendCommand(
        target,
        "DOM.enable"
    );


    return target;
}


async function detachDebugger(
    target
) {

    try {

        await chrome.debugger.detach(
            target
        );

    } catch (error) {

        console.warn(
            "Debugger detach:",
            error
        );
    }
}


// ======================================================
// ACCESSIBILITY TREE
// ======================================================

function axValue(property) {

    return normalizeText(
        property?.value
        ?? ""
    );
}


function sendButtonNameMatches(
    name
) {

    const value =
        normalizeText(name)
            .toLowerCase();


    return (
        value ===
            "send without a note"
        ||
        value ===
            "send without note"
        ||
        value.startsWith(
            "send without a note "
        )
    );
}


async function getAXTree(
    target
) {

    const result =
        await chrome.debugger.sendCommand(
            target,
            "Accessibility.getFullAXTree"
        );


    return result?.nodes
        || [];
}


async function findSendWithoutNoteNode(
    target
) {

    const nodes =
        await getAXTree(
            target
        );


    for (const node of nodes) {

        const name =
            axValue(
                node.name
            );


        const role =
            axValue(
                node.role
            )
                .toLowerCase();


        if (
            sendButtonNameMatches(name)
            &&
            role === "button"
        ) {

            return node;
        }
    }


    for (const node of nodes) {

        const name =
            axValue(
                node.name
            );


        if (
            sendButtonNameMatches(name)
            &&
            node.backendDOMNodeId
        ) {

            return node;
        }
    }


    return null;
}


// ======================================================
// BOX MODEL
// ======================================================

async function getNodeCenter(
    target,
    node
) {

    if (
        !node?.backendDOMNodeId
    ) {

        return null;
    }


    const box =
        await chrome.debugger.sendCommand(
            target,
            "DOM.getBoxModel",
            {
                backendNodeId:
                    node.backendDOMNodeId
            }
        );


    const quad =
        box?.model?.border
        ||
        box?.model?.content;


    if (
        !Array.isArray(quad)
        ||
        quad.length < 8
    ) {

        return null;
    }


    const xs = [
        quad[0],
        quad[2],
        quad[4],
        quad[6]
    ];


    const ys = [
        quad[1],
        quad[3],
        quad[5],
        quad[7]
    ];


    return {
        x:
            (
                Math.min(...xs)
                +
                Math.max(...xs)
            )
            / 2,

        y:
            (
                Math.min(...ys)
                +
                Math.max(...ys)
            )
            / 2
    };
}


// ======================================================
// REAL BROWSER CLICK
// ======================================================

async function browserClick(
    target,
    x,
    y
) {

    await chrome.debugger.sendCommand(
        target,
        "Input.dispatchMouseEvent",
        {
            type:
                "mouseMoved",

            x,
            y
        }
    );


    await sleep(80);


    await chrome.debugger.sendCommand(
        target,
        "Input.dispatchMouseEvent",
        {
            type:
                "mousePressed",

            x,
            y,

            button:
                "left",

            buttons:
                1,

            clickCount:
                1
        }
    );


    await sleep(100);


    await chrome.debugger.sendCommand(
        target,
        "Input.dispatchMouseEvent",
        {
            type:
                "mouseReleased",

            x,
            y,

            button:
                "left",

            buttons:
                0,

            clickCount:
                1
        }
    );
}


// ======================================================
// INSPECT CONNECT PAGE
// ======================================================

async function inspectConnectFlow(
    tabId
) {

    try {

        return await chrome.tabs.sendMessage(
            tabId,
            {
                type:
                    "NETWORK_SCOUT_INSPECT_CONNECT_FLOW"
            }
        );

    } catch (error) {

        return {
            verified: false,
            status: "waiting",
            message:
                "Waiting for LinkedIn."
        };
    }
}


// ======================================================
// COMPLETE INVITATION FLOW
// ======================================================

async function completeInvitationFlow(
    tabId
) {

    const target =
        await attachDebugger(
            tabId
        );


    try {

        let sendNode =
            null;


        for (
            let attempt = 0;
            attempt < 35;
            attempt += 1
        ) {

            const state =
                await inspectConnectFlow(
                    tabId
                );


            if (
                state?.verified
            ) {

                return state;
            }


            if (
                state?.status ===
                    "invite_cooldown"
                ||
                state?.status ===
                    "needs_attention"
            ) {

                return state;
            }


            sendNode =
                await findSendWithoutNoteNode(
                    target
                );


            if (sendNode) {

                break;
            }


            await sleep(350);
        }


        if (!sendNode) {

            return {
                verified: false,

                status:
                    "send_button_ax_not_found",

                message:
                    (
                        "LinkedIn opened the connection flow, "
                        +
                        "but Chrome could not find "
                        +
                        "\"Send without a note\"."
                    )
            };
        }


        const position =
            await getNodeCenter(
                target,
                sendNode
            );


        if (!position) {

            return {
                verified: false,

                status:
                    "send_button_position_failed",

                message:
                    (
                        "Chrome found "
                        +
                        "\"Send without a note\" "
                        +
                        "but could not determine "
                        +
                        "where to click it."
                    )
            };
        }


        await browserClick(
            target,
            position.x,
            position.y
        );


        await sleep(1000);


        for (
            let attempt = 0;
            attempt < 18;
            attempt += 1
        ) {

            const state =
                await inspectConnectFlow(
                    tabId
                );


            if (
                state?.verified
            ) {

                return state;
            }


            if (
                state?.status ===
                    "invite_cooldown"
                ||
                state?.status ===
                    "needs_attention"
            ) {

                return state;
            }


            const stillThere =
                await findSendWithoutNoteNode(
                    target
                );


            if (!stillThere) {

                return {
                    verified: false,

                    status:
                        "connect_submitted",

                    message:
                        (
                            "LinkedIn accepted "
                            +
                            "\"Send without a note\"."
                        )
                };
            }


            await sleep(350);
        }


        const retryNode =
            await findSendWithoutNoteNode(
                target
            );


        if (retryNode) {

            const retryPosition =
                await getNodeCenter(
                    target,
                    retryNode
                );


            if (retryPosition) {

                await browserClick(
                    target,
                    retryPosition.x,
                    retryPosition.y
                );


                await sleep(1200);


                const state =
                    await inspectConnectFlow(
                        tabId
                    );


                if (
                    state?.verified
                    ||
                    state?.status ===
                        "invite_cooldown"
                    ||
                    state?.status ===
                        "needs_attention"
                ) {

                    return state;
                }


                const afterRetry =
                    await findSendWithoutNoteNode(
                        target
                    );


                if (!afterRetry) {

                    return {
                        verified: false,

                        status:
                            "connect_submitted",

                        message:
                            (
                                "LinkedIn accepted "
                                +
                                "the invitation action."
                            )
                    };
                }
            }
        }


        return {
            verified: false,

            status:
                "send_not_accepted",

            message:
                (
                    "Chrome found and clicked "
                    +
                    "\"Send without a note\", "
                    +
                    "but LinkedIn kept the action open."
                )
        };

    } finally {

        await detachDebugger(
            target
        );
    }
}


// ======================================================
// FRESH CONNECT VERIFY
// ======================================================

async function verifyConnectFresh(
    tabId,
    profileUrl,
    candidateName
) {

    await chrome.tabs.reload(
        tabId
    );


    await waitForTabComplete(
        tabId
    );


    await sleep(2200);


    await injectConnectScript(
        tabId
    );


    return await sendConnectMessageWithRetry(
        tabId, profileUrl, "NETWORK_SCOUT_VERIFY_CONNECT", 5, candidateName
    );
}


// ======================================================
// RETRY PROFILE CONTROLS (CONNECT PATH)
// ======================================================

async function sendConnectMessageWithRetry(tabId, profileUrl, type, attempts = 5, candidateName = null) {
    let result = null;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
        const tab = await chrome.tabs.get(tabId);
        const actual = normalizeProfileUrl(tab.url || "");
        if (actual !== profileUrl) {
            return { status: "wrong_profile", verified: false,
                message: "LinkedIn navigated away from the exact requested profile." };
        }
        try {
            result = await chrome.tabs.sendMessage(tabId, { type, profileUrl, candidateName });
        } catch (error) {
            const detail = String(error?.message || error);
            if (!detail.includes("Receiving end does not exist")
                && !detail.includes("message port closed")) throw error;
            await injectConnectScript(tabId);
        }
        if (result && !["profile_loading", "controls_loading"].includes(result.status)) {
            return result;
        }
        await sleep(900);
    }
    return { status: "profile_unavailable", verified: false,
        message: (result?.message || "LinkedIn did not expose this profile's controls.")
            + " Verify that the requested /in/ profile is visible and fully loaded." };
}

function resultMatchesExactProfile(result, profileUrl, candidateName) {
    if (!result || result.verified !== true) return false;
    if (!["verified_pending", "already_pending", "already_connected"].includes(result.status)) return false;
    if (result.profile_url && normalizeProfileUrl(result.profile_url) !== profileUrl) return false;
    const canonicalName = value => String(value || "")
        .normalize("NFKD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^\p{L}\p{N}]+/gu, " ")
        .replace(/\s+/g, " ")
        .trim()
        .toLowerCase();
    const actualName = canonicalName(result.profile_name);
    const expectedName = canonicalName(candidateName);
    return !expectedName || (!!actualName && actualName === expectedName);
}

// ======================================================
// CONNECT REQUEST
// ======================================================

async function handleConnectRequest(
    message
) {

    const profileUrl =
        normalizeProfileUrl(
            message.profileUrl
        );


    const candidateName =
        message.candidateName
        || null;


    const requestedAt =
        new Date()
            .toISOString();


    if (!profileUrl) {

        return {
            verified: false,
            status:
                "invalid_profile_url",
            message:
                "Invalid LinkedIn profile URL."
        };
    }


    let tabId =
        null;


    let keepTabOpen =
        false;


    try {

        const tab =
            await chrome.tabs.create({
                url:
                    profileUrl,

                active:
                    false
            });


        tabId =
            tab.id;


        if (!tabId) {

            throw new Error(
                "Could not create LinkedIn tab."
            );
        }


        await waitForTabComplete(
            tabId
        );


        await sleep(1800);


        await injectConnectScript(
            tabId
        );


        let result = await sendConnectMessageWithRetry(
            tabId, profileUrl, "NETWORK_SCOUT_CONNECT", 5, candidateName
        );


        if (!result) {

            throw new Error(
                "No response from LinkedIn agent."
            );
        }

        // Background tabs can remain unrendered/throttled in Chromium.
        // Retry the same URL as a visible tab only when the exact profile's
        // controls were not found. Do not click on another profile or record
        // a relationship without later verification.
        if (["profile_unavailable", "profile_loading", "controls_loading"].includes(result.status)) {
            await chrome.tabs.update(tabId, { active: true });
            await sleep(2000);
            result = await sendConnectMessageWithRetry(
                tabId, profileUrl, "NETWORK_SCOUT_CONNECT", 2, candidateName
            );
            if (["profile_unavailable", "profile_loading", "controls_loading"].includes(result?.status)) {
                keepTabOpen = true;
                result = {
                    status: "profile_unavailable", verified: false,
                    message: (result?.message || "Profile header controls were not detected.")
                        + " The selected LinkedIn tab has been left open so you can inspect what LinkedIn displayed."
                };
            }
        }


        if (
            result.status ===
            "connect_clicked"
        ) {

            result =
                await completeInvitationFlow(
                    tabId
                );
        }


        if (
            result.status ===
            "needs_attention"
        ) {

            keepTabOpen =
                true;
        }


        if (
            result.verified === true
            && ["already_pending", "verified_pending", "already_connected"].includes(result.status)
        ) {
            // Read a fresh page before saving a relationship receipt.
            result = await verifyConnectFresh(tabId, profileUrl, candidateName);
            if (!resultMatchesExactProfile(result, profileUrl, candidateName)) {
                result = { status: "connect_not_verified", verified: false,
                    message: "A fresh LinkedIn profile check did not confirm this exact person's Pending/Connected state." };
            }

            const receipt =
                makeReceipt(
                    profileUrl,
                    candidateName,
                    requestedAt,
                    result
                );


            await storeReceipt(
                profileUrl,
                receipt
            );


            return receipt;
        }


        if (
            result.status ===
            "invite_cooldown"
        ) {

            const receipt =
                makeReceipt(
                    profileUrl,
                    candidateName,
                    requestedAt,
                    result
                );


            await storeReceipt(
                profileUrl,
                receipt
            );


            return receipt;
        }


        if (
            result.status ===
            "connect_submitted"
        ) {

            const verification =
                await verifyConnectFresh(
                    tabId,
                    profileUrl, candidateName
                );


            if (
                verification?.status ===
                "needs_attention"
            ) {

                keepTabOpen =
                    true;
            }


            const safeVerification = resultMatchesExactProfile(
                verification, profileUrl, candidateName
            ) ? verification : {
                status: "connect_not_verified", verified: false,
                message: verification?.message || "Pending/Connected was not verified on this exact profile."
            };

            const receipt =
                makeReceipt(
                    profileUrl,
                    candidateName,
                    requestedAt,
                    safeVerification
                );


            await storeReceipt(
                profileUrl,
                receipt
            );


            return receipt;
        }


        const receipt =
            makeReceipt(
                profileUrl,
                candidateName,
                requestedAt,
                result
            );


        await storeReceipt(
            profileUrl,
            receipt
        );


        return receipt;

    } catch (error) {

        console.error(
            "Network Scout Connect failed:",
            error
        );


        const failure = {
            verified: false,
            status: "failed",
            message:
                error.message
                ||
                "Connect failed."
        };


        const receipt =
            makeReceipt(
                profileUrl,
                candidateName,
                requestedAt,
                failure
            );


        await storeReceipt(
            profileUrl,
            receipt
        );


        return receipt;

    } finally {

        if (
            tabId
            &&
            !keepTabOpen
        ) {

            try {

                await chrome.tabs.remove(
                    tabId
                );

            } catch (error) {

                console.warn(
                    "Could not close LinkedIn tab:",
                    error
                );
            }
        }
    }
}


// ======================================================
// OPEN LINKEDIN
// ======================================================

async function openLinkedInProfile(
    profileUrl
) {

    const normalized =
        normalizeProfileUrl(
            profileUrl
        );


    if (!normalized) {

        return {
            ok: false
        };
    }


    await chrome.tabs.create({
        url:
            normalized,

        active:
            true
    });


    return {
        ok: true
    };
}


// ======================================================
// ACCEPTANCE MONITOR ALARM
// ======================================================

async function ensureAcceptanceAlarm() {

    const existing =
        await chrome.alarms.get(
            ACCEPTANCE_ALARM
        );


    if (existing) {

        return;
    }


    await chrome.alarms.create(
        ACCEPTANCE_ALARM,
        {
            delayInMinutes:
                1,

            periodInMinutes:
                ACCEPTANCE_CHECK_INTERVAL_MINUTES
        }
    );
}


chrome.alarms.onAlarm.addListener(
    (alarm) => {

        if (
            alarm.name !==
            ACCEPTANCE_ALARM
        ) {

            return;
        }


        runAcceptanceMonitor()
            .catch(
                (error) => {

                    console.warn(
                        "Scheduled acceptance monitor failed:",
                        error
                    );
                }
            );
    }
);


// ======================================================
// ACCEPTANCE SCRIPT
// ======================================================

async function injectAcceptanceScript(
    tabId
) {

    await chrome.scripting.executeScript({
        target: {
            tabId
        },

        files: [
            "acceptance_check.js"
        ]
    });


    await sleep(300);
}


// ======================================================
// GET PENDING TRACKED PEOPLE
// ======================================================

function relationshipLooksPending(
    person
) {

    const relationshipStatus =
        String(
            person?.relationship_status
            ||
            ""
        )
            .toLowerCase();


    if (
        relationshipStatus.includes(
            "pending"
        )
    ) {

        return true;
    }


    const requestStatus =
        String(
            person?.connection_request?.status
            ||
            ""
        )
            .toLowerCase();


    if (
        requestStatus.includes(
            "pending"
        )
    ) {

        return true;
    }


    return (
        Boolean(
            person?.connection_request
        )
        &&
        relationshipStatus !==
            "connected"
    );
}


async function getPendingTrackedConnections() {

    const data =
        await apiFetch(
            "/tracked-connections",
            {},
            8000
        );


    const connections =
        Array.isArray(
            data?.connections
        )
            ? data.connections
            : [];


    return connections
        .filter(
            relationshipLooksPending
        )
        .filter(
            (person) => {

                return Boolean(
                    normalizeProfileUrl(
                        person.profile_url
                    )
                );
            }
        )
        .slice(
            0,
            MAX_ACCEPTANCE_CHECKS_PER_RUN
        );
}


// ======================================================
// MARK CONNECTED
// ======================================================

async function markConnectionAccepted(
    person,
    verification
) {

    return await apiFetch(
        "/tracked-connections/mark-connected",
        {
            method:
                "POST",

            headers: {
                "Content-Type":
                    "application/json"
            },

            body:
                JSON.stringify(
                    {
                        profile_url:
                            person.profile_url,

                        verification_text:
                            verification.verificationText
                            ||
                            verification.verification_text
                            ||
                            "1st-degree connection",

                        verified:
                            true
                    }
                )
        },
        8000
    );
}


// ======================================================
// CHECK ONE PENDING PERSON
// ======================================================

async function checkOneAcceptance(
    person
) {

    const profileUrl =
        normalizeProfileUrl(
            person.profile_url
        );


    if (!profileUrl) {

        return {
            accepted: false,
            status:
                "invalid_profile"
        };
    }


    let tabId =
        null;


    try {

        const tab =
            await chrome.tabs.create({
                url:
                    profileUrl,

                active:
                    false
            });


        tabId =
            tab.id;


        if (!tabId) {

            throw new Error(
                "Could not create acceptance-check tab."
            );
        }


        await waitForTabComplete(
            tabId
        );


        await sleep(1700);


        await injectAcceptanceScript(
            tabId
        );


        const verification =
            await chrome.tabs.sendMessage(
                tabId,
                {
                    type:
                        "NETWORK_SCOUT_CHECK_ACCEPTANCE",

                    profileUrl
                }
            );


        if (!verification) {

            return {
                accepted: false,
                status:
                    "no_response"
            };
        }


        if (
            verification.verified
            &&
            verification.status ===
                "connected"
        ) {

            await markConnectionAccepted(
                person,
                verification
            );


            return {
                accepted: true,

                status:
                    "connected",

                person:
                    person.name
                    ||
                    "LinkedIn connection",

                profile_url:
                    profileUrl,

                verification
            };
        }


        return {
            accepted: false,
            status:
                verification.status,
            verification
        };

    } catch (error) {

        console.warn(
            "Acceptance check failed:",
            profileUrl,
            error
        );


        return {
            accepted: false,
            status: "failed",
            message:
                error.message
        };

    } finally {

        if (tabId) {

            try {

                await chrome.tabs.remove(
                    tabId
                );

            } catch (error) {

                console.warn(
                    "Could not close acceptance tab:",
                    error
                );
            }
        }
    }
}


// ======================================================
// RUN ACCEPTANCE MONITOR
// ======================================================

async function runAcceptanceMonitor() {

    if (
        acceptanceMonitorRunning
    ) {

        return {
            ok: true,
            skipped: true,
            reason:
                "monitor_already_running"
        };
    }


    acceptanceMonitorRunning =
        true;


    try {

        let pendingPeople = [];


        try {

            pendingPeople =
                await getPendingTrackedConnections();

        } catch (error) {

            console.warn(
                "Network Scout backend unavailable for acceptance check:",
                error
            );


            return {
                ok: false,
                reason:
                    "backend_unavailable",
                message:
                    error.message
            };
        }


        const results = [];

        let acceptedCount =
            0;


        for (
            const person
            of pendingPeople
        ) {

            const result =
                await checkOneAcceptance(
                    person
                );


            results.push(
                result
            );


            if (
                result.accepted
            ) {

                acceptedCount +=
                    1;
            }


            /*
                Small gap between LinkedIn page checks.
            */

            await sleep(1200);
        }


        return {
            ok: true,

            checked:
                pendingPeople.length,

            accepted:
                acceptedCount,

            results
        };

    } finally {

        acceptanceMonitorRunning =
            false;
    }
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

        // --------------------------------------------------
        // CONNECT
        // --------------------------------------------------

        if (
            message?.type ===
            "NETWORK_SCOUT_CONNECT_REQUEST"
        ) {

            handleConnectRequest(
                message
            )
                .then(sendResponse)
                .catch(
                    (error) => {

                        sendResponse({
                            verified: false,
                            status: "failed",
                            message:
                                error.message
                        });
                    }
                );


            return true;
        }


        // --------------------------------------------------
        // OPEN LINKEDIN
        // --------------------------------------------------

        if (
            message?.type ===
            "NETWORK_SCOUT_OPEN_LINKEDIN"
        ) {

            openLinkedInProfile(
                message.profileUrl
            )
                .then(sendResponse)
                .catch(
                    (error) => {

                        sendResponse({
                            ok: false,
                            message:
                                error.message
                        });
                    }
                );


            return true;
        }


        // --------------------------------------------------
        // CHECK ALL PENDING ACCEPTANCES NOW
        // --------------------------------------------------

        if (
            message?.type ===
            "NETWORK_SCOUT_CHECK_ACCEPTANCES_NOW"
        ) {

            runAcceptanceMonitor()
                .then(sendResponse)
                .catch(
                    (error) => {

                        sendResponse({
                            ok: false,
                            message:
                                error.message
                        });
                    }
                );


            return true;
        }


        // --------------------------------------------------
        // CHECK ONE PERSON
        // --------------------------------------------------

        if (
            message?.type ===
            "NETWORK_SCOUT_CHECK_ACCEPTANCE"
        ) {

            checkOneAcceptance(
                message.person
            )
                .then(sendResponse)
                .catch(
                    (error) => {

                        sendResponse({
                            accepted: false,
                            status: "failed",
                            message:
                                error.message
                        });
                    }
                );


            return true;
        }


        return false;
    }
);