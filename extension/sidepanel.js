const API_BASE_URL =
    "http://127.0.0.1:8000";


const SAVED_CANDIDATES_KEY =
    "networkScoutSavedCandidates";

const RECEIPTS_KEY =
    "networkScoutActionReceipts";

const CONNECTION_COOLDOWNS_KEY =
    "networkScoutConnectionCooldowns";


/*
    You said the LinkedIn withdrawal message
    you're receiving uses a 3-day waiting period.

    If LinkedIn explicitly returns a different
    number of days/weeks, that exact value will
    override this fallback.
*/
const DEFAULT_WITHDRAWAL_COOLDOWN_DAYS =
    3;


// ======================================================
// DOM
// ======================================================

const statusDot =
    document.getElementById(
        "statusDot"
    );

const connectionBadge =
    document.getElementById(
        "connectionBadge"
    );

const connectionMessage =
    document.getElementById(
        "connectionMessage"
    );

const candidateCount =
    document.getElementById(
        "candidateCount"
    );

const countLabel =
    document.getElementById(
        "countLabel"
    );

const candidateList =
    document.getElementById(
        "candidateList"
    );

const refreshButton =
    document.getElementById(
        "refreshButton"
    );

const weeklyTab =
    document.getElementById(
        "weeklyTab"
    );

const trackedTab =
    document.getElementById(
        "trackedTab"
    );

const notificationsTab =
    document.getElementById(
        "notificationsTab"
    );

const notificationUnreadBadge =
    document.getElementById(
        "notificationUnreadBadge"
    );

const sectionLabel =
    document.getElementById(
        "sectionLabel"
    );

const sectionTitle =
    document.getElementById(
        "sectionTitle"
    );


// ======================================================
// STATE
// ======================================================

let savedCandidates = {};
let actionReceipts = {};
let connectionCooldowns = {};

let weeklyCandidates = [];
let trackedConnections = [];
let notifications = [];

let unreadNotificationCount = 0;

let currentView =
    "weekly";

let isLoading =
    false;


// ======================================================
// API
// ======================================================

async function apiFetch(
    path,
    options = {},
    timeoutMs = 8000
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

    } catch (error) {

        if (
            error.name ===
            "AbortError"
        ) {

            throw new Error(
                `${path} timed out.`
            );
        }


        throw error;

    } finally {

        clearTimeout(timeout);
    }
}


// ======================================================
// CONNECTION INDICATOR
// ======================================================

function setCheckingState() {

    statusDot?.classList.remove(
        "connected"
    );

    statusDot?.classList.add(
        "disconnected"
    );


    if (connectionBadge) {

        connectionBadge.classList.remove(
            "connected"
        );

        connectionBadge.classList.add(
            "disconnected"
        );

        connectionBadge.textContent =
            "CHECKING";
    }


    if (connectionMessage) {

        connectionMessage.textContent =
            "Connecting to Network Scout...";
    }
}


function setConnectedState(
    connected,
    message
) {

    statusDot?.classList.toggle(
        "connected",
        connected
    );

    statusDot?.classList.toggle(
        "disconnected",
        !connected
    );


    if (connectionBadge) {

        connectionBadge.classList.toggle(
            "connected",
            connected
        );

        connectionBadge.classList.toggle(
            "disconnected",
            !connected
        );

        connectionBadge.textContent =
            connected
                ? "CONNECTED"
                : "OFFLINE";
    }


    if (connectionMessage) {

        connectionMessage.textContent =
            message;
    }
}


// ======================================================
// HELPERS
// ======================================================

function createTextElement(
    tagName,
    className,
    text
) {

    const element =
        document.createElement(
            tagName
        );


    if (className) {

        element.className =
            className;
    }


    element.textContent =
        text ?? "";


    return element;
}


function normalizeProfileUrl(value) {
    try {
        const url = new URL(value);
        if (url.protocol !== "https:" ||
            !["www.linkedin.com", "linkedin.com"].includes(url.hostname.toLowerCase())) {
            return "";
        }
        const match = url.pathname.match(/^\/in\/([^/?#]+)\/?$/i);
        return match ? `https://www.linkedin.com/in/${match[1].toLowerCase()}/` : "";
    } catch (_) {
        return "";
    }
}


function getInitials(
    name
) {

    if (!name) {

        return "NS";
    }


    const parts =
        String(name)
            .trim()
            .split(/\s+/)
            .filter(Boolean);


    if (
        parts.length === 1
    ) {

        return parts[0]
            .slice(0, 2)
            .toUpperCase();
    }


    return (
        parts[0][0]
        +
        parts[
            parts.length - 1
        ][0]
    )
        .toUpperCase();
}


function formatDate(
    value
) {

    if (!value) {

        return "—";
    }


    try {

        return new Date(value)
            .toLocaleDateString(
                undefined,
                {
                    month: "short",
                    day: "numeric",
                    year: "numeric"
                }
            );

    } catch (error) {

        return "—";
    }
}


function formatDateTime(
    value
) {

    if (!value) {

        return "";
    }


    try {

        return new Date(value)
            .toLocaleString(
                undefined,
                {
                    month: "short",
                    day: "numeric",
                    year: "numeric",
                    hour: "numeric",
                    minute: "2-digit"
                }
            );

    } catch (error) {

        return "";
    }
}


function truncateText(
    value,
    maxLength = 450
) {

    const text =
        String(value || "")
            .replace(/\s+/g, " ")
            .trim();


    if (
        text.length <=
        maxLength
    ) {

        return text;
    }


    return (
        text.slice(
            0,
            maxLength - 3
        )
        +
        "..."
    );
}


function renderLoading(
    text = "Loading Network Scout..."
) {

    if (!candidateList) {

        return;
    }


    candidateList.innerHTML = "";


    candidateList.appendChild(
        createTextElement(
            "div",
            "loading-card",
            text
        )
    );
}


function renderError(
    message
) {

    if (!candidateList) {

        return;
    }


    candidateList.innerHTML = "";


    candidateList.appendChild(
        createTextElement(
            "div",
            "empty-card",
            message
        )
    );
}


// ======================================================
// COOLDOWN
// ======================================================

function addDays(
    date,
    days
) {

    return new Date(
        date.getTime()
        +
        (
            days
            *
            24
            *
            60
            *
            60
            *
            1000
        )
    );
}


function inferCooldownUntilFromText(
    message
) {

    const text =
        String(message || "");


    const dayMatch =
        text.match(
            /(\d+)\s*(?:day|days)\b/i
        );


    if (dayMatch) {

        const days =
            Number(
                dayMatch[1]
            );


        if (
            Number.isFinite(days)
            &&
            days > 0
        ) {

            return addDays(
                new Date(),
                days
            ).toISOString();
        }
    }


    const weekMatch =
        text.match(
            /(\d+)\s*(?:week|weeks)\b/i
        );


    if (weekMatch) {

        const weeks =
            Number(
                weekMatch[1]
            );


        if (
            Number.isFinite(weeks)
            &&
            weeks > 0
        ) {

            return addDays(
                new Date(),
                weeks * 7
            ).toISOString();
        }
    }


    return null;
}


async function persistCooldowns() {

    try {

        await chrome.storage.local.set(
            {
                [
                    CONNECTION_COOLDOWNS_KEY
                ]:
                    connectionCooldowns
            }
        );

    } catch (error) {

        console.error(
            "Could not save cooldown state:",
            error
        );
    }
}


async function loadCooldowns() {

    try {

        const result =
            await chrome.storage.local.get(
                CONNECTION_COOLDOWNS_KEY
            );


        connectionCooldowns =
            result[
                CONNECTION_COOLDOWNS_KEY
            ]
            || {};


        let changed =
            false;


        const now =
            Date.now();


        for (
            const [
                profileUrl,
                cooldown
            ]
            of Object.entries(
                connectionCooldowns
            )
        ) {

            const until =
                Date.parse(
                    cooldown?.until
                    || ""
                );


            if (
                !Number.isFinite(until)
                ||
                until <= now
            ) {

                delete connectionCooldowns[
                    profileUrl
                ];

                changed =
                    true;
            }
        }


        if (changed) {

            await persistCooldowns();
        }

    } catch (error) {

        console.error(
            "Could not load cooldowns:",
            error
        );


        connectionCooldowns = {};
    }
}


function getActiveCooldown(
    profileUrl
) {

    const normalized =
        normalizeProfileUrl(
            profileUrl
        );


    if (!normalized) {

        return null;
    }


    const cooldown =
        connectionCooldowns[
            normalized
        ];


    if (!cooldown) {

        return null;
    }


    const until =
        Date.parse(
            cooldown.until
            || ""
        );


    if (
        !Number.isFinite(until)
        ||
        until <= Date.now()
    ) {

        delete connectionCooldowns[
            normalized
        ];


        persistCooldowns()
            .catch(
                () => {}
            );


        return null;
    }


    return cooldown;
}


async function setConnectionCooldown(
    profileUrl,
    {
        message = null,
        until = null,
        source = null
    } = {}
) {

    const normalized =
        normalizeProfileUrl(
            profileUrl
        );


    if (!normalized) {

        return;
    }


    const finalUntil =
        until
        ||
        inferCooldownUntilFromText(
            message
        )
        ||
        addDays(
            new Date(),
            DEFAULT_WITHDRAWAL_COOLDOWN_DAYS
        ).toISOString();


    connectionCooldowns[
        normalized
    ] = {
        profile_url:
            normalized,

        detected_at:
            new Date()
                .toISOString(),

        until:
            finalUntil,

        message:
            message
            ||
            (
                "A previous invitation was withdrawn. "
                +
                "LinkedIn requires a waiting period "
                +
                "before another invitation can be sent."
            ),

        source:
            source
            || "network_scout"
    };


    await persistCooldowns();
}


async function clearConnectionCooldown(
    profileUrl
) {

    const normalized =
        normalizeProfileUrl(
            profileUrl
        );


    if (
        !normalized
        ||
        !connectionCooldowns[
            normalized
        ]
    ) {

        return;
    }


    delete connectionCooldowns[
        normalized
    ];


    await persistCooldowns();
}


function formatCooldownStatus(
    cooldown
) {

    if (!cooldown) {

        return "";
    }


    const until =
        new Date(
            cooldown.until
        );


    const remainingMs =
        until.getTime()
        -
        Date.now();


    const remainingHours =
        Math.max(
            1,
            Math.ceil(
                remainingMs
                /
                (
                    60
                    *
                    60
                    *
                    1000
                )
            )
        );


    let remainingText;


    if (
        remainingHours >= 24
    ) {

        const days =
            Math.ceil(
                remainingHours / 24
            );


        remainingText =
            (
                `${days} day`
                +
                (
                    days === 1
                        ? ""
                        : "s"
                )
            );

    } else {

        remainingText =
            (
                `${remainingHours} hour`
                +
                (
                    remainingHours === 1
                        ? ""
                        : "s"
                )
            );
    }


    const dateText =
        until.toLocaleDateString(
            undefined,
            {
                month: "short",
                day: "numeric"
            }
        );


    return (
        `Invite cooldown — about ${remainingText} remaining. `
        +
        `Try again after ${dateText}.`
    );
}


// ======================================================
// AVATAR
// ======================================================

function resolveProfilePhotoUrl(
    value
) {

    if (!value) {
        return "";
    }

    const text = String(value).trim();

    if (!text) {
        return "";
    }

    if (
        text.startsWith("http://")
        || text.startsWith("https://")
        || text.startsWith("data:")
        || text.startsWith("blob:")
    ) {
        return text;
    }

    if (text.startsWith("/")) {
        return API_BASE_URL + text;
    }

    const normalized = text.replace(/\\/g, "/");
    const marker = "profile_photos/";
    const index = normalized.toLowerCase().lastIndexOf(marker);

    if (index >= 0) {
        const filename = normalized.slice(index + marker.length);
        if (filename) {
            return API_BASE_URL + "/profile-photos/" + filename.split("/").map(encodeURIComponent).join("/");
        }
    }

    return text;
}


function getLinkedInProfileSlug(
    profileUrl
) {

    const normalized = normalizeProfileUrl(profileUrl);

    if (!normalized) {
        return "";
    }

    const match = normalized.match(/linkedin\.com\/in\/([^/?#]+)/i);
    return match?.[1] || "";
}


function getProfilePhotoCandidates(
    person
) {

    const profile = (
        person?.linkedin_profile_data
        && typeof person.linkedin_profile_data === "object"
    )
        ? person.linkedin_profile_data
        : {};

    const output = [];
    const seen = new Set();

    const add = (value) => {
        const resolved = resolveProfilePhotoUrl(value);
        if (!resolved || seen.has(resolved)) {
            return;
        }
        seen.add(resolved);
        output.push(resolved);
    };

    for (const value of [
        person?.profile_photo_url,
        person?.profile_photo_local_url,
        person?.profile_photo_served_url,
        person?.profile_photo_api_url,
        profile.profile_photo_url,
        profile.profile_photo_local_url,
        profile.profile_photo_served_url,
        profile.profile_photo_api_url
    ]) {
        add(value);
    }

    const normalizedUrl = normalizeProfileUrl(person?.profile_url);
    if (profile.profile_url && normalizeProfileUrl(profile.profile_url) !== normalizedUrl) {
        return output;
    }

    if (normalizedUrl) {
        const weeklyMatch = weeklyCandidates.find(
            (candidate) => normalizeProfileUrl(candidate?.profile_url) === normalizedUrl
        );

        if (weeklyMatch && weeklyMatch !== person) {
            const weeklyProfile = (
                weeklyMatch.linkedin_profile_data
                && typeof weeklyMatch.linkedin_profile_data === "object"
            )
                ? weeklyMatch.linkedin_profile_data
                : {};

            for (const value of [
                weeklyMatch.profile_photo_url,
                weeklyMatch.profile_photo_local_url,
                weeklyProfile.profile_photo_url,
                weeklyProfile.profile_photo_local_url
            ]) {
                add(value);
            }
        }

        const saved = savedCandidates[normalizedUrl];
        if (saved) {
            add(saved.profile_photo_url);
            add(saved.profile_photo_local_url);
        }
    }

    /*
        weekly_profile_photos.py saves portraits as:
        data/profile_photos/<linkedin-slug>.png

        Trying this local FastAPI URL costs no browser tab and prevents
        photo loading from interfering with Connect / Follow actions.
    */
    const slug = getLinkedInProfileSlug(normalizedUrl);
    if (slug) {
        add(
            API_BASE_URL
            + "/profile-photos/"
            + encodeURIComponent(slug)
            + ".png"
        );
    }

    return output;
}


function createAvatar(
    person
) {

    const wrapper = document.createElement("div");
    wrapper.className = "avatar";

    const initials = createTextElement(
        "span",
        "avatar-initials",
        getInitials(person?.name)
    );

    wrapper.appendChild(initials);

    const candidates = getProfilePhotoCandidates(person);

    if (candidates.length === 0) {
        return wrapper;
    }

    const image = document.createElement("img");
    image.className = "profile-photo";
    image.alt = person?.name
        ? `${person.name} profile photo`
        : "LinkedIn profile photo";
    image.referrerPolicy = "no-referrer";

    let index = 0;

    image.addEventListener("load", () => {
        initials.style.display = "none";
    });

    image.addEventListener("error", () => {
        index += 1;

        if (index < candidates.length) {
            image.src = candidates[index];
            return;
        }

        image.remove();
        initials.style.display = "flex";
    });

    image.src = candidates[index];
    wrapper.appendChild(image);

    return wrapper;
}


// ======================================================
// STORAGE
// ======================================================

async function loadSavedCandidates() {

    try {

        const result =
            await chrome.storage.local.get(
                SAVED_CANDIDATES_KEY
            );


        savedCandidates =
            result[
                SAVED_CANDIDATES_KEY
            ]
            || {};

    } catch (error) {

        console.error(
            "Could not load saved candidates:",
            error
        );


        savedCandidates = {};
    }
}


async function loadActionReceipts() {

    try {

        const result =
            await chrome.storage.local.get(
                RECEIPTS_KEY
            );


        actionReceipts =
            result[
                RECEIPTS_KEY
            ]
            || {};

    } catch (error) {

        console.error(
            "Could not load receipts:",
            error
        );


        actionReceipts = {};
    }
}


async function saveSavedCandidates() {

    await chrome.storage.local.set(
        {
            [
                SAVED_CANDIDATES_KEY
            ]:
                savedCandidates
        }
    );
}


async function clearCandidateReceipt(
    profileUrl
) {

    const normalized =
        normalizeProfileUrl(
            profileUrl
        );


    if (!normalized) {

        return;
    }


    delete actionReceipts[
        normalized
    ];


    await chrome.storage.local.set(
        {
            [
                RECEIPTS_KEY
            ]:
                actionReceipts
        }
    );
}


// ======================================================
// SAVED
// ======================================================

function candidateIsSaved(
    candidate
) {

    const profileUrl =
        normalizeProfileUrl(
            candidate?.profile_url
        );


    return Boolean(
        profileUrl
        &&
        savedCandidates[
            profileUrl
        ]
    );
}


function updateSaveButtonState(
    button,
    candidate
) {

    const saved =
        candidateIsSaved(
            candidate
        );


    button.textContent =
        saved
            ? "Saved"
            : "Save";


    button.classList.toggle(
        "primary",
        saved
    );
}


async function toggleSavedCandidate(
    candidate,
    button
) {

    const profileUrl =
        normalizeProfileUrl(
            candidate.profile_url
        );


    if (!profileUrl) {

        return;
    }


    button.disabled =
        true;


    if (
        savedCandidates[
            profileUrl
        ]
    ) {

        delete savedCandidates[
            profileUrl
        ];

    } else {

        savedCandidates[
            profileUrl
        ] = {
            ...candidate,

            profile_url:
                profileUrl,

            saved_at:
                new Date()
                    .toISOString()
        };
    }


    await saveSavedCandidates();


    updateSaveButtonState(
        button,
        candidate
    );


    button.disabled =
        false;
}


// ======================================================
// RECEIPTS
// ======================================================

function normalizePersonNameForComparison(
    value
) {

    return String(value || "")
        .normalize("NFKD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^a-zA-Z0-9 ]+/g, " " )
        .replace(/\s+/g, " " )
        .trim()
        .toLowerCase();
}


function extractInvitationTargetName(
    verificationText
) {

    const text = String(verificationText || "")
        .replace(/\s+/g, " " )
        .trim();

    if (!text) {
        return "";
    }

    const match = text.match(
        /(?:invitation\s+)?sent\s+to\s+(.+?)(?:[.!]|$)/i
    );

    return (match?.[1] || "").trim();
}


function verificationTextMatchesCandidate(
    verificationText,
    candidateName
) {

    const target = extractInvitationTargetName(verificationText);

    if (!target) {
        return true;
    }

    const candidate = normalizePersonNameForComparison(candidateName);
    const targetName = normalizePersonNameForComparison(target);

    if (!candidate || !targetName) {
        return false;
    }

    if (
        candidate === targetName
        || candidate.includes(targetName)
        || targetName.includes(candidate)
    ) {
        return true;
    }

    const candidateParts = candidate.split(" " ).filter(Boolean);
    const targetParts = targetName.split(" " ).filter(Boolean);

    if (candidateParts.length < 2 || targetParts.length < 2) {
        return false;
    }

    return (
        candidateParts[0] === targetParts[0]
        && candidateParts[candidateParts.length - 1] === targetParts[targetParts.length - 1]
    );
}


function receiptMatchesProfile(receipt, profileUrl) {
    const normalized = normalizeProfileUrl(profileUrl);
    return Boolean(normalized && receipt?.verified === true &&
        normalizeProfileUrl(receipt.profile_url) === normalized);
}

function getCandidateReceipt(candidate) {
    const profileUrl = normalizeProfileUrl(candidate?.profile_url);
    const receipt = profileUrl ? actionReceipts[profileUrl] : null;
    if (!receiptMatchesProfile(receipt, profileUrl)) return null;
    if (["verified_pending", "already_pending"].includes(receipt.status) &&
        !verificationTextMatchesCandidate(
            receipt.verification_text || receipt.message || "",
            candidate?.name || receipt.candidate_name || ""
        )) return null;
    return receipt;
}

function receiptIsTrackable(receipt) {
    return Boolean(receiptMatchesProfile(receipt, receipt?.profile_url) &&
        ["verified_pending", "already_pending", "already_connected"].includes(receipt.status) &&
        (!receipt.relationship || ["pending_connection", "connected"].includes(receipt.relationship)));
}

function receiptIsFollowing(receipt) {
    return Boolean(receiptMatchesProfile(receipt, receipt?.profile_url) &&
        receipt.status === "verified_following" &&
        receipt.relationship === "following");
}


async function saveRelationshipReceipt(
    profileUrl,
    receipt
) {

    const normalized = normalizeProfileUrl(profileUrl);

    if (!normalized) {
        return;
    }

    actionReceipts[normalized] = {
        ...receipt,
        profile_url: normalized
    };

    await chrome.storage.local.set(
        { [RECEIPTS_KEY]: actionReceipts }
    );
}


function personIsFollowing(
    person
) {

    if (!person) {
        return false;
    }

    if (
        person.relationship_status === "following"
        || person.connection_status === "following"
        || person.relationship_action === "follow"
        || person.lawyer_action === "follow"
        || person._synthetic_follow === true
    ) {
        return true;
    }

    const status = person.relationship_status || person.connection_status;
    if (status === "pending_connection" || status === "connected") return false;
    const receipt = actionReceipts[normalizeProfileUrl(person.profile_url)];
    return receiptIsFollowing(receipt);
}


async function cleanupInvalidTrackedRecord(person, reason) {
    // A mismatching label is not proof that LinkedIn withdrew an invitation.
    // Never tell the backend an unperformed withdrawal was verified.
    console.warn("Quarantined suspicious tracked record:", person?.profile_url, reason);
}


// ======================================================
// API DATA
// ======================================================

async function fetchWeeklyCandidates() {

    const data = await apiFetch("/weekly-picks", {}, 7000);

    weeklyCandidates = Array.isArray(data?.candidates)
        ? data.candidates
        : [];
}


async function fetchTrackedConnections() {

    const data = await apiFetch("/tracked-connections", {}, 7000);

    const backendConnections = Array.isArray(data?.connections)
        ? data.connections
        : [];

    const byProfile = new Map();

    for (const person of backendConnections) {
        const profileUrl = normalizeProfileUrl(person?.profile_url);

        if (!profileUrl) {
            continue;
        }

        const status = String(
            person?.relationship_status
            || person?.connection_status
            || ""
        ).toLowerCase();

        if (
            status === "pending_connection"
            && !verificationTextMatchesCandidate(
                person?.connection_request?.verification_text || "",
                person?.name || person?.connection_name || ""
            )
        ) {
            await clearCandidateReceipt(profileUrl);
            cleanupInvalidTrackedRecord(
                { ...person, profile_url: profileUrl },
                "Removed invalid pending record because LinkedIn verification named a different person."
            );
            continue;
        }

        if (
            person?.removed_from_tracked === true
            || status === "removed"
            || person?.tracking_status === "removed"
        ) {
            continue;
        }

        if (!["following", "connected", "pending_connection"].includes(status)) {
            console.warn("Unknown relationship state (not tracked):", profileUrl, status);
            continue;
        }
        if (status === "pending_connection" && person?.connection_request?.verified !== true) {
            console.warn("Unverified pending record (not displayed):", profileUrl);
            continue;
        }
        byProfile.set(profileUrl, {
            ...person,
            profile_url: profileUrl
        });
    }

    const candidateLookup = new Map();

    for (const candidate of weeklyCandidates) {
        const profileUrl = normalizeProfileUrl(candidate?.profile_url);
        if (profileUrl) {
            candidateLookup.set(profileUrl, candidate);
        }
    }

    for (const [profileUrl, saved] of Object.entries(savedCandidates)) {
        const normalized = normalizeProfileUrl(profileUrl);
        if (normalized && saved) {
            candidateLookup.set(normalized, saved);
        }
    }

    for (const [profileUrl, receipt] of Object.entries(actionReceipts)) {
        const normalized = normalizeProfileUrl(profileUrl);

        if (!normalized || !receiptIsFollowing(receipt)) {
            continue;
        }

        if (!receiptMatchesProfile(receipt, normalized)) continue;
        const candidate = candidateLookup.get(normalized) || {};
        const existing = byProfile.get(normalized) || {};
        if (existing.relationship_status === "connected" || existing.relationship_status === "pending_connection") {
            continue;
        }

        byProfile.set(normalized, {
            ...existing,
            profile_url: normalized,
            name: candidate.name || existing.name || receipt.candidate_name || "Tracked professional",
            headline: candidate.headline || existing.headline || null,
            current_role: candidate.current_role || existing.current_role || null,
            current_company: candidate.current_company || existing.current_company || null,
            location: candidate.location || existing.location || null,
            profile_photo_url: candidate.profile_photo_url || existing.profile_photo_url || null,
            profile_photo_local_url: candidate.profile_photo_local_url || existing.profile_photo_local_url || null,
            relationship_status: "following",
            connection_status: "following",
            relationship_action: "follow",
            lawyer_action: "follow",
            followed_at: receipt.verified_at || receipt.performed_at || receipt.requested_at || null,
            tracking_active: true,
            removed_from_tracked: false,
            _synthetic_follow: true
        });
    }

    trackedConnections = [...byProfile.values()];
}


async function fetchNotifications() {

    const data = await apiFetch("/notifications", {}, 12000);

    notifications = Array.isArray(data?.notifications)
        ? data.notifications
        : [];

    unreadNotificationCount = Number(data?.unread_count || 0);
    updateNotificationBadge();
}


// ======================================================
// TRACK CONNECT
// ======================================================

async function recordTrackedConnection(
    candidate,
    receipt
) {

    if (
        !receiptIsTrackable(
            receipt
        )
    ) {

        return false;
    }


    const profileUrl =
        normalizeProfileUrl(
            candidate?.profile_url
            ||
            receipt.profile_url
        );


    if (!profileUrl || !receiptMatchesProfile(receipt, profileUrl)) {
        return false;
    }

    try {
        await apiFetch(
            "/tracked-connections/connect",
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
                                profileUrl,

                            name:
                                candidate?.name
                                ||
                                receipt.candidate_name
                                ||
                                null,

                            headline:
                                candidate?.headline
                                || null,

                            current_role:
                                candidate?.current_role
                                || null,

                            current_company:
                                candidate?.current_company
                                || null,

                            location:
                                candidate?.location
                                || null,

                            ai_score:
                                candidate?.ai_score
                                ?? null,

                            why_relevant:
                                candidate?.why_relevant
                                || null,

                            action_id:
                                receipt.action_id
                                || null,

                            requested_at:
                                receipt.requested_at
                                || null,

                            performed_at:
                                receipt.performed_at
                                || null,

                            verified_at:
                                receipt.verified_at
                                || null,

                            status:
                                receipt.status,

                            verification_text:
                                receipt.verification_text
                                || null,

                            verified:
                                Boolean(
                                    receipt.verified
                                )
                        }
                    )
            },
            7000
        );


        return true;

    } catch (error) {

        console.warn(
            "Tracked sync failed:",
            error
        );


        return false;
    }
}


async function syncStoredVerifiedReceipts() {

    const lookup = {};

    for (const candidate of weeklyCandidates) {
        const profileUrl = normalizeProfileUrl(candidate?.profile_url);
        if (profileUrl) {
            lookup[profileUrl] = candidate;
        }
    }

    for (const [profileUrl, receipt] of Object.entries(actionReceipts)) {
        if (!receiptIsTrackable(receipt)) {
            continue;
        }

        const normalized = normalizeProfileUrl(profileUrl || receipt.profile_url);

        if (!normalized) {
            continue;
        }

        const candidate = lookup[normalized];
        if (!candidate || !receiptMatchesProfile(receipt, normalized)) continue;

        if (
            ["verified_pending", "already_pending"].includes(receipt.status)
            && !verificationTextMatchesCandidate(
                receipt.verification_text || receipt.message || "",
                candidate?.name || receipt.candidate_name || ""
            )
        ) {
            await clearCandidateReceipt(normalized);
            continue;
        }

        try {
            await recordTrackedConnection(candidate, receipt);
        } catch (error) {
            console.warn("Receipt sync skipped:", error);
        }
    }
}


// ======================================================
// NOTIFICATION BADGE
// ======================================================

function updateNotificationBadge() {

    if (!notificationUnreadBadge) {

        return;
    }


    if (
        unreadNotificationCount > 0
    ) {

        notificationUnreadBadge
            .classList
            .remove(
                "hidden"
            );


        notificationUnreadBadge.textContent =
            unreadNotificationCount > 99
                ? "99+"
                : String(
                    unreadNotificationCount
                );

    } else {

        notificationUnreadBadge
            .classList
            .add(
                "hidden"
            );


        notificationUnreadBadge.textContent =
            "0";
    }
}


async function markAllNotificationsRead() {

    if (
        unreadNotificationCount <= 0
    ) {

        return;
    }


    try {

        await apiFetch(
            "/notifications/mark-all-read",
            {
                method:
                    "POST"
            },
            6000
        );


        unreadNotificationCount = 0;


        notifications =
            notifications.map(
                (notification) => ({
                    ...notification,
                    is_read: true
                })
            );


        updateNotificationBadge();

    } catch (error) {

        console.warn(
            "Could not mark notifications read:",
            error
        );
    }
}


// ======================================================
// ENGAGEMENT LOG
// ======================================================

async function recordEngagementDecision(
    notification,
    decision,
    extra = {}
) {

    try {

        await apiFetch(
            "/engagement-actions",
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
                            notification_id:
                                notification.notification_id
                                || null,

                            person_name:
                                notification.person_name
                                || null,

                            profile_url:
                                notification.profile_url
                                || null,

                            post_url:
                                notification.post_url
                                || null,

                            decision:
                                decision,

                            comment_text:
                                extra.comment_text
                                || null,

                            verification_text:
                                extra.verification_text
                                || null,

                            verified:
                                Boolean(
                                    extra.verified
                                )
                        }
                    )
            },
            6000
        );


        return true;

    } catch (error) {

        console.warn(
            "Engagement logging failed:",
            error
        );


        return false;
    }
}


// ======================================================
// STATUS
// ======================================================

function setActionStatus(
    element,
    status,
    message
) {

    if (!element) {
        return;
    }

    element.dataset.status = status;
    element.textContent = message;
}


function renderStoredReceipt(
    candidate,
    statusElement
) {

    const cooldown = getActiveCooldown(candidate.profile_url);

    if (cooldown) {
        setActionStatus(statusElement, "attention", formatCooldownStatus(cooldown));
        return;
    }

    const receipt = getCandidateReceipt(candidate);

    if (!receipt) {
        setActionStatus(
            statusElement,
            "idle",
            "Network Scout will Connect when available, otherwise Follow."
        );
        return;
    }

    if (["verified_pending", "already_pending"].includes(receipt.status)) {
        setActionStatus(statusElement, "verified", "✓ Invitation verified on LinkedIn — Pending");
        return;
    }

    if (receipt.status === "already_connected" && receipt.verified === true) {
        setActionStatus(statusElement, "verified", "✓ Already connected on LinkedIn");
        return;
    }

    if (receiptIsFollowing(receipt)) {
        setActionStatus(statusElement, "verified", "✓ Following on LinkedIn");
        return;
    }

    if (receipt.status === "invite_cooldown") {
        setActionStatus(
            statusElement,
            "attention",
            receipt.message || "LinkedIn connection cooldown is active."
        );
        return;
    }

    if (receipt.status === "needs_attention") {
        setActionStatus(statusElement, "attention", "LinkedIn needs your attention.");
        return;
    }

    setActionStatus(
        statusElement,
        "failed",
        receipt.message || "Previous LinkedIn action was not verified."
    );
}


function connectIsUnavailable(
    result
) {

    if (!result) {
        return false;
    }

    if ([
        "connect_unavailable",
        "connect_not_available",
        "no_connect_action"
    ].includes(result.status)) {
        return true;
    }

    const message = String(
        result.message || result.verification_text || ""
    ).toLowerCase();

    return [
        "connect is not currently available",
        "connect not currently available",
        "connect is unavailable",
        "connect unavailable",
        "connect button not found",
        "no connect button",
        "no connect action"
    ].some((phrase) => message.includes(phrase));
}


function isTemporaryChromeTabError(
    error
) {

    const message = String(error?.message || error || "").toLowerCase();

    return (
        message.includes("tabs cannot be edited right now")
        || message.includes("user may be dragging a tab")
    );
}


async function delay(
    milliseconds
) {

    await new Promise((resolve) => setTimeout(resolve, milliseconds));
}


async function createBackgroundLinkedInTab(
    profileUrl
) {

    let lastError = null;

    for (let attempt = 0; attempt < 4; attempt += 1) {
        try {
            return await chrome.tabs.create({
                url: profileUrl,
                active: false
            });
        } catch (error) {
            lastError = error;

            if (!isTemporaryChromeTabError(error)) {
                throw error;
            }

            await delay(700 + (attempt * 500));
        }
    }

    throw lastError || new Error("Could not open LinkedIn background tab.");
}


async function injectLinkedInContentScript(
    tabId
) {

    await chrome.scripting.executeScript({
        target: { tabId },
        files: ["linkedin_content.js"]
    });

    await delay(250);
}


async function sendLinkedInRelationshipMessage(
    tabId,
    message,
    attempts = 12
) {

    let lastResult = null;

    for (let attempt = 0; attempt < attempts; attempt += 1) {
        try {
            const result = await chrome.tabs.sendMessage(tabId, message);
            lastResult = result || null;

            if (
                result
                && !["profile_loading", "controls_loading"].includes(result.status)
            ) {
                return result;
            }
        } catch (error) {
            const text = String(error?.message || error || "").toLowerCase();

            if (!text.includes("receiving end does not exist")) {
                throw error;
            }

            await injectLinkedInContentScript(tabId);
        }

        await delay(900);
    }

    return lastResult || {
        status: "profile_loading",
        message: "LinkedIn did not finish loading the profile controls in time."
    };
}


async function followCandidate(
    candidate,
    button,
    statusElement
) {

    const profileUrl = normalizeProfileUrl(candidate?.profile_url);

    if (!profileUrl) {
        setActionStatus(statusElement, "failed", "Invalid LinkedIn profile.");
        return false;
    }

    button.disabled = true;
    button.textContent = "Following…";
    setActionStatus(statusElement, "working", "Opening the exact LinkedIn profile and following…");

    let tabId = null;

    try {
        const tab = await createBackgroundLinkedInTab(profileUrl);
        tabId = tab?.id || null;

        if (!tabId) {
            throw new Error("Could not create the LinkedIn background tab.");
        }

        await waitForTabComplete(tabId, 30000);
        await delay(1400);
        await injectLinkedInContentScript(tabId);

        const result = await sendLinkedInRelationshipMessage(
            tabId,
            {
                type: "NETWORK_SCOUT_FOLLOW",
                profileUrl,
                candidateName: candidate?.name || ""
            }
        );

        if (!result) {
            throw new Error("No response from LinkedIn profile agent.");
        }

        if (result.status === "needs_attention") {
            button.textContent = "Try Again";
            button.disabled = false;
            setActionStatus(statusElement, "attention", result.message || "LinkedIn needs your attention.");
            return false;
        }

        let confirmation = result;
        if (result.status === "follow_clicked" || result.status === "already_following" ||
            (result.status === "verified_following" && result.verified !== true)) {
            confirmation = await sendLinkedInRelationshipMessage(tabId, {
                type: "NETWORK_SCOUT_VERIFY_FOLLOW", profileUrl
            });
        }
        if (confirmation?.status === "verified_following" && confirmation.verified === true &&
            normalizeProfileUrl(confirmation.profile_url) === profileUrl &&
            normalizePersonNameForComparison(confirmation.profile_name) === normalizePersonNameForComparison(candidate?.name)) {
            const now = new Date().toISOString();
            await saveRelationshipReceipt(profileUrl, {
                status: "verified_following",
                relationship: "following",
                candidate_name: candidate?.name || null,
                requested_at: now,
                performed_at: now,
                verified_at: now,
                verified: true,
                verification_text: confirmation.verification_text || "Following on exact LinkedIn profile"
            });
            button.textContent = "Following";
            button.disabled = true;
            setActionStatus(statusElement, "verified", "Following verified on LinkedIn · Added to Tracked");
            await fetchTrackedConnections().catch(() => {});
            return true;
        }

        button.textContent = "Try Again";
        button.disabled = false;
        setActionStatus(
            statusElement,
            "failed",
            result.message || "LinkedIn did not expose a Follow action on this profile."
        );
        return false;

    } catch (error) {
        console.error("Follow failed:", error);
        button.textContent = "Try Again";
        button.disabled = false;
        setActionStatus(
            statusElement,
            "failed",
            isTemporaryChromeTabError(error)
                ? "Chrome was briefly busy. Network Scout stopped safely; click Try Again."
                : (error.message || "Follow failed.")
        );
        return false;

    } finally {
        if (tabId) {
            try {
                await chrome.tabs.remove(tabId);
            } catch (error) {
                console.warn("Could not close LinkedIn tab:", error);
            }
        }
    }
}


async function unfollowTrackedPerson(
    person,
    button,
    statusElement
) {

    const profileUrl = normalizeProfileUrl(person?.profile_url);

    if (!profileUrl) {
        setActionStatus(statusElement, "failed", "Invalid LinkedIn profile.");
        return;
    }

    button.disabled = true;
    button.textContent = "Unfollowing…";
    setActionStatus(statusElement, "working", "Unfollowing on the exact LinkedIn profile…");

    let tabId = null;

    try {
        const tab = await createBackgroundLinkedInTab(profileUrl);
        tabId = tab?.id || null;

        if (!tabId) {
            throw new Error("Could not create the LinkedIn background tab.");
        }

        await waitForTabComplete(tabId, 30000);
        await delay(1400);
        await injectLinkedInContentScript(tabId);

        const result = await sendLinkedInRelationshipMessage(
            tabId,
            {
                type: "NETWORK_SCOUT_UNFOLLOW",
                profileUrl,
                candidateName: person?.name || ""
            }
        );

        if (!result) {
            throw new Error("No response from LinkedIn profile agent.");
        }

        if (result.status === "needs_attention") {
            button.textContent = "Unfollow";
            button.disabled = false;
            setActionStatus(statusElement, "attention", result.message || "LinkedIn needs your attention.");
            return;
        }

        if (["already_not_following", "verified_unfollowed"].includes(result.status) &&
            result.verified === true &&
            normalizeProfileUrl(result.profile_url) === profileUrl) {
            await clearCandidateReceipt(profileUrl);

            try {
                await apiFetch(
                    "/tracked-connections/remove",
                    {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            profile_url: profileUrl,
                            removal_action: "unfollow",
                            verification_text: result.verification_text || "Unfollow clicked on the selected profile.",
                            verified: true
                        })
                    },
                    7000
                );
            } catch (error) {
                /* Synthetic follow records do not have to exist in the backend. */
                console.warn("Backend follow removal skipped:", error);
            }

            await fetchTrackedConnections().catch(() => {});
            renderTrackedView();
            return;
        }

        button.textContent = "Unfollow";
        button.disabled = false;
        setActionStatus(statusElement, "failed", result.message || "Could not unfollow this profile.");

    } catch (error) {
        console.error("Unfollow failed:", error);
        button.textContent = "Unfollow";
        button.disabled = false;
        setActionStatus(statusElement, "failed", error.message || "Unfollow failed.");

    } finally {
        if (tabId) {
            try {
                await chrome.tabs.remove(tabId);
            } catch (error) {
                console.warn("Could not close LinkedIn tab:", error);
            }
        }
    }
}


// ======================================================
// CONNECT
// ======================================================

async function connectCandidate(
    candidate,
    button,
    statusElement
) {

    const profileUrl = normalizeProfileUrl(candidate?.profile_url);

    if (!profileUrl) {
        setActionStatus(statusElement, "failed", "Invalid LinkedIn profile.");
        return;
    }

    const existingCooldown = getActiveCooldown(profileUrl);

    if (existingCooldown) {
        button.textContent = "Cooldown";
        button.disabled = true;
        setActionStatus(statusElement, "attention", formatCooldownStatus(existingCooldown));
        return;
    }

    button.disabled = true;
    button.textContent = "Connecting…";
    setActionStatus(statusElement, "working", "LinkedIn is working in the background…");

    try {
        const result = await chrome.runtime.sendMessage({
            type: "NETWORK_SCOUT_CONNECT_REQUEST",
            profileUrl,
            candidateName: candidate?.name || "LinkedIn candidate"
        });

        if (!result) {
            throw new Error("No response from browser agent.");
        }

        await loadActionReceipts();

        if (result.status === "invite_cooldown") {
            const inferredUntil = inferCooldownUntilFromText(result.message);
            await setConnectionCooldown(profileUrl, {
                message: result.message,
                until: inferredUntil,
                source: "linkedin"
            });
            button.textContent = "Cooldown";
            button.disabled = true;
            const cooldown = getActiveCooldown(profileUrl);
            setActionStatus(
                statusElement,
                "attention",
                result.message + (cooldown ? " " + formatCooldownStatus(cooldown) : "")
            );
            return;
        }

        if (connectIsUnavailable(result)) {
            await clearCandidateReceipt(profileUrl);
            await followCandidate(candidate, button, statusElement);
            return;
        }

        if (["verified_pending", "already_pending"].includes(result.status) &&
            result.verified === true && normalizeProfileUrl(result.profile_url) === profileUrl) {
            if (!verificationTextMatchesCandidate(
                result.verification_text || result.message || "",
                candidate?.name || ""
            )) {
                await clearCandidateReceipt(profileUrl);
                button.textContent = "Try Again";
                button.disabled = false;
                setActionStatus(
                    statusElement,
                    "failed",
                    "LinkedIn returned another person's invitation state. Network Scout rejected it and did not add this profile to Tracked."
                );
                return;
            }

            await clearConnectionCooldown(profileUrl);
            button.textContent = "Pending";
            button.disabled = true;
            const tracked = await recordTrackedConnection(candidate, result);
            if (!tracked) {
                button.textContent = "Try Again";
                button.disabled = false;
                setActionStatus(statusElement, "failed", "Verified on LinkedIn, but backend tracking failed.");
                return;
            }
            setActionStatus(statusElement, "verified", "Invitation verified on LinkedIn — Pending · Added to Tracked");
            await fetchTrackedConnections().catch(() => {});
            return;
        }

        if (result.status === "already_connected" && result.verified === true &&
            normalizeProfileUrl(result.profile_url) === profileUrl) {
            await clearConnectionCooldown(profileUrl);
            button.textContent = "Connected";
            button.disabled = true;
            const tracked = await recordTrackedConnection(candidate, result);
            if (!tracked) {
                button.textContent = "Try Again";
                button.disabled = false;
                setActionStatus(statusElement, "failed", "Verified on LinkedIn, but backend tracking failed.");
                return;
            }
            setActionStatus(statusElement, "verified", "Already connected · Added to Tracked");
            return;
        }

        if (result.status === "needs_attention") {
            button.textContent = "Try Again";
            button.disabled = false;
            setActionStatus(statusElement, "attention", result.message || "LinkedIn needs your attention.");
            return;
        }

        button.textContent = "Try Again";
        button.disabled = false;
        setActionStatus(
            statusElement,
            "failed",
            result.message || "Network Scout could not verify the LinkedIn action."
        );

    } catch (error) {
        console.error("Connect failed:", error);
        button.textContent = "Try Again";
        button.disabled = false;
        setActionStatus(statusElement, "failed", error.message || "Connect failed.");
    }
}


// ======================================================
// WAIT FOR TAB
// ======================================================

async function waitForTabComplete(
    tabId,
    timeoutMs = 30000
) {

    const currentTab =
        await chrome.tabs.get(
            tabId
        );


    if (
        currentTab.status ===
        "complete"
    ) {

        return;
    }


    return new Promise(
        (
            resolve,
            reject
        ) => {

            let finished =
                false;


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


                clearTimeout(
                    timeout
                );


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
// RELATIONSHIP SCRIPT
// ======================================================

async function injectRelationshipScript(
    tabId
) {

    await chrome.scripting.executeScript(
        {
            target: {
                tabId:
                    tabId
            },

            files: [
                "relationship_remove.js"
            ]
        }
    );


    await new Promise(
        (resolve) => {

            setTimeout(
                resolve,
                350
            );
        }
    );
}


// ======================================================
// VERIFY REMOVAL
// ======================================================

async function verifyRelationshipAfterReload(
    tabId,
    profileUrl,
    action
) {

    let reloadCompleted = false;
    for (let attempt = 0; attempt < 4; attempt += 1) {
        try {
            await chrome.tabs.reload(tabId);
            reloadCompleted = true;
            break;
        } catch (error) {
            if (!isTemporaryChromeTabError(error) || attempt === 3) {
                throw error;
            }
            await delay(700 + (attempt * 500));
        }
    }
    if (!reloadCompleted) {
        throw new Error("Could not reload LinkedIn for verification.");
    }


    await waitForTabComplete(
        tabId
    );


    await new Promise(
        (resolve) => {

            setTimeout(
                resolve,
                2000
            );
        }
    );


    await injectRelationshipScript(
        tabId
    );


    return await chrome.tabs.sendMessage(
        tabId,
        {
            type:
                "NETWORK_SCOUT_VERIFY_RELATIONSHIP_REMOVAL",

            profileUrl:
                profileUrl,

            action:
                action
        }
    );
}


// ======================================================
// BACKEND REMOVE
// ======================================================

async function markTrackedRelationshipRemoved(
    person,
    action,
    verificationText
) {

    return await apiFetch(
        "/tracked-connections/remove",
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

                        removal_action:
                            action,

                        verification_text:
                            verificationText
                            || null,

                        verified:
                            true
                    }
                )
        },
        7000
    );
}


// ======================================================
// CONFIRM TARGET PROFILE'S WITHDRAWAL DIALOG
// ======================================================

async function confirmPendingInvitationWithdrawal(tabId, profileUrl) {
    const injection = await chrome.scripting.executeScript({
        target: { tabId },
        args: [profileUrl],
        func: (expectedProfileUrl) => {
            const normalize = (value) => {
                try {
                    const url = new URL(value);
                    const match = url.pathname.match(/^\/in\/([^/?#]+)\/?/i);
                    if (!match || !/(^|\.)linkedin\.com$/i.test(url.hostname)) return null;
                    return `https://www.linkedin.com/in/${match[1].toLowerCase()}/`;
                } catch { return null; }
            };
            if (!normalize(expectedProfileUrl) || normalize(location.href) !== normalize(expectedProfileUrl)) {
                return { status: "wrong_profile", message: "Withdrawal stopped: selected LinkedIn profile URL did not match." };
            }
            const visible = (element) => {
                if (!element) return false;
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
            };
            const dialogs = [...document.querySelectorAll(
                '[role="dialog"], [aria-modal="true"], .artdeco-modal, dialog'
            )].filter(visible);
            for (const dialog of dialogs) {
                const text = (dialog.innerText || dialog.textContent || "").replace(/\s+/g, " ").trim();
                if (!/withdraw invitation/i.test(text)) continue;
                const buttons = [...dialog.querySelectorAll('button, [role="button"]')].filter(visible);
                const withdraw = buttons.find((button) => {
                    const label = (button.innerText || button.textContent || button.getAttribute('aria-label') || "").trim().toLowerCase();
                    return label === "withdraw" || label === "withdraw invitation";
                });
                if (!withdraw || withdraw.disabled || withdraw.getAttribute("aria-disabled") === "true") {
                    return { status: "confirmation_not_ready", message: "Withdraw invitation dialog is open but Withdraw is not ready." };
                }
                withdraw.click();
                return { status: "withdraw_confirmation_clicked", warning_text: text };
            }
            return { status: "no_withdraw_dialog" };
        }
    });
    return injection?.[0]?.result || { status: "confirmation_not_ready" };
}

// ======================================================
// REMOVE TRACKED PERSON
// ======================================================

async function removeTrackedPerson(
    person,
    button,
    statusElement
) {

    const profileUrl =
        normalizeProfileUrl(
            person.profile_url
        );


    if (!profileUrl) {

        setActionStatus(
            statusElement,
            "failed",
            "Invalid LinkedIn profile."
        );


        return;
    }


    if (personIsFollowing(person)) {
        await unfollowTrackedPerson(
            person,
            button,
            statusElement
        );
        return;
    }


    const action =
        person.relationship_status ===
        "connected"
            ? "unfollow"
            : "cancel_invite";


    const normalButtonText =
        action === "unfollow"
            ? "Unfollow & Remove"
            : "Cancel Invite";


    button.disabled =
        true;


    button.textContent =
        action === "unfollow"
            ? "Unfollowing…"
            : "Cancelling…";


    setActionStatus(
        statusElement,
        "working",
        (
            "Processing the LinkedIn "
            +
            "relationship change…"
        )
    );


    let tabId =
        null;

    let keepTabOpen =
        false;


    try {

        // Reuse the retry behavior already used by Follow. Chrome can
        // temporarily refuse a tab edit while a tab is being moved.
        const tab = await createBackgroundLinkedInTab(profileUrl);


        tabId =
            tab.id;


        if (!tabId) {

            throw new Error(
                (
                    "Could not create the "
                    +
                    "LinkedIn background tab."
                )
            );
        }


        await waitForTabComplete(
            tabId
        );


        await new Promise(
            (resolve) => {

                setTimeout(
                    resolve,
                    1800
                );
            }
        );


        await injectRelationshipScript(
            tabId
        );


        const actionResult =
            await chrome.tabs.sendMessage(
                tabId,
                {
                    type:
                        "NETWORK_SCOUT_REMOVE_RELATIONSHIP",

                    profileUrl:
                        profileUrl,

                    action:
                        action
                }
            );


        if (!actionResult) {

            throw new Error(
                (
                    "No response from the "
                    +
                    "relationship agent."
                )
            );
        }


        if (
            actionResult.status ===
            "needs_attention"
        ) {

            keepTabOpen =
                true;


            button.disabled =
                false;


            button.textContent =
                normalButtonText;


            setActionStatus(
                statusElement,
                "attention",
                actionResult.message
                ||
                (
                    "LinkedIn needs "
                    +
                    "your attention."
                )
            );


            return;
        }


        if (
            actionResult.status ===
            "state_changed_connected"
        ) {

            button.disabled =
                false;


            button.textContent =
                "Unfollow & Remove";


            setActionStatus(
                statusElement,
                "attention",
                (
                    "The invitation was accepted "
                    +
                    "before it could be cancelled."
                )
            );


            try {

                await chrome.runtime.sendMessage(
                    {
                        type:
                            "NETWORK_SCOUT_CHECK_ACCEPTANCES_NOW"
                    }
                );

            } catch (error) {

                console.warn(error);
            }


            try {

                await fetchTrackedConnections();

            } catch (error) {

                console.warn(error);
            }


            renderTrackedView();


            return;
        }


        const reloadableStatuses = [
            "withdraw_submitted",
            "unfollow_submitted",
            "fresh_verification_required"
        ];


        if (
            !reloadableStatuses.includes(
                actionResult.status
            )
        ) {

            button.disabled =
                false;


            button.textContent =
                normalButtonText;


            setActionStatus(
                statusElement,
                "failed",
                actionResult.message
                ||
                (
                    "Network Scout could not "
                    +
                    "perform the LinkedIn action."
                )
            );


            return;
        }


        // LinkedIn opens a second "Withdraw invitation" modal.
        // Confirm it on the EXACT selected profile BEFORE reloading.
        let withdrawalWarning = null;
        if (action === "cancel_invite") {
            let modalResult = null;
            for (let attempt = 0; attempt < 8; attempt += 1) {
                modalResult = await confirmPendingInvitationWithdrawal(tabId, profileUrl);
                if (modalResult.status !== "no_withdraw_dialog" &&
                    modalResult.status !== "confirmation_not_ready") break;
                await delay(350);
            }
            if (modalResult?.status === "wrong_profile") {
                throw new Error(modalResult.message);
            }
            if (modalResult?.status === "confirmation_not_ready") {
                keepTabOpen = true;
                throw new Error(modalResult.message || "Withdraw confirmation is not ready.");
            }
            if (modalResult?.status === "withdraw_confirmation_clicked") {
                withdrawalWarning = modalResult.warning_text || null;
                await delay(900);
            }
            // If no modal is present, keep the existing fresh verification.
            // Never assume a click or a dismissed dialog proves withdrawal.
        }

        button.textContent =
            "Verifying…";


        setActionStatus(
            statusElement,
            "working",
            (
                "Reloading LinkedIn and "
                +
                "verifying the fresh state…"
            )
        );


        // LinkedIn can briefly render its old Pending state after withdrawal.
        // Re-read the exact profile rather than declaring a failed withdrawal
        // based on a single stale reload. No record is removed on a click alone.
        let verification = null;
        for (let verificationAttempt = 0; verificationAttempt < 5; verificationAttempt += 1) {
            if (verificationAttempt > 0) {
                setActionStatus(
                    statusElement,
                    "working",
                    "Waiting for LinkedIn to update the withdrawal state…"
                );
                await delay(2200 + (verificationAttempt * 700));
            }
            verification = await verifyRelationshipAfterReload(
                tabId,
                profileUrl,
                action
            );
            if (verification?.status === "needs_attention" ||
                verification?.status === "wrong_profile" ||
                (verification?.verified === true &&
                    (verification.status === "verified_cancelled" ||
                     verification.status === "verified_unfollowed"))) {
                break;
            }
            if (action !== "cancel_invite") break;
        }


        if (!verification) {

            throw new Error(
                "No verification result returned."
            );
        }


        if (
            verification.status ===
            "needs_attention"
        ) {

            keepTabOpen =
                true;


            button.disabled =
                false;


            button.textContent =
                normalButtonText;


            setActionStatus(
                statusElement,
                "attention",
                verification.message
                ||
                "LinkedIn needs your attention."
            );


            return;
        }


        const verifiedCancelled =
            (
                action ===
                    "cancel_invite"
                &&
                verification.verified
                &&
                verification.status ===
                    "verified_cancelled"
            );


        const verifiedUnfollowed =
            (
                action ===
                    "unfollow"
                &&
                verification.verified
                &&
                verification.status ===
                    "verified_unfollowed"
            );


        if (
            verifiedCancelled
            ||
            verifiedUnfollowed
        ) {

            await markTrackedRelationshipRemoved(
                person,
                action,
                (
                    verification.verificationText
                    ||
                    verification.verification_text
                    ||
                    verification.message
                )
            );


            /*
                If we withdrew the invitation,
                start Network Scout's own cooldown
                immediately.
            */

            if (
                action ===
                "cancel_invite"
            ) {

                await setConnectionCooldown(
                    profileUrl,
                    {
                        message:
                            (
                                "Invitation withdrawn. "
                                +
                                "LinkedIn requires a "
                                +
                                "waiting period before "
                                +
                                "you can invite this "
                                +
                                "person again."
                            ),

                        until:
                            inferCooldownUntilFromText(withdrawalWarning)
                            || addDays(
                                new Date(),
                                DEFAULT_WITHDRAWAL_COOLDOWN_DAYS
                            ).toISOString(),

                        source:
                            "network_scout_withdrawal"
                    }
                );
            }


            await clearCandidateReceipt(
                profileUrl
            );


            // The server has acknowledged verified removal. Update the
            // local list immediately, then refresh to reconcile with storage.
            trackedConnections = trackedConnections.filter(
                (entry) => normalizeProfileUrl(entry.profile_url) !== profileUrl
            );
            renderTrackedView();
            try {
                await fetchTrackedConnections();
                renderTrackedView();
            } catch (refreshError) {
                console.warn("Tracked list refresh deferred:", refreshError);
            }


            return;
        }


        button.disabled =
            false;


        button.textContent =
            normalButtonText;


        setActionStatus(
            statusElement,
            "failed",
            verification.message
            ||
            (
                "Network Scout could not "
                +
                "verify the final LinkedIn state."
            )
        );

    } catch (error) {

        console.error(
            "Relationship removal failed:",
            error
        );


        button.disabled =
            false;


        button.textContent =
            normalButtonText;


        setActionStatus(
            statusElement,
            "failed",
            error.message
            ||
            "Relationship removal failed."
        );

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
// WEEKLY CARD
// ======================================================

function createCandidateCard(
    candidate
) {

    const card = document.createElement("article");
    card.className = "candidate-card";

    const top = document.createElement("div");
    top.className = "candidate-top";
    top.appendChild(createAvatar(candidate));

    const main = document.createElement("div");
    main.className = "candidate-main";
    main.appendChild(createTextElement(
        "div",
        "candidate-name",
        candidate.name || "Unknown professional"
    ));
    main.appendChild(createTextElement(
        "p",
        "candidate-headline",
        candidate.headline
        || [candidate.current_role, candidate.current_company].filter(Boolean).join(" · " )
        || "Professional profile"
    ));
    top.appendChild(main);

    const score = document.createElement("div");
    score.className = "score";
    score.appendChild(createTextElement("strong", "", candidate.ai_score ?? "—"));
    score.appendChild(createTextElement("span", "", "AI MATCH"));
    top.appendChild(score);
    card.appendChild(top);

    const reason = document.createElement("div");
    reason.className = "reason";
    reason.appendChild(createTextElement(
        "span",
        "reason-label",
        "WHY NETWORK SCOUT SELECTED THEM"
    ));
    reason.appendChild(createTextElement(
        "p",
        "",
        candidate.why_relevant || "Strong professional relevance."
    ));
    card.appendChild(reason);

    const actions = document.createElement("div");
    actions.className = "actions";
    actions.style.gridTemplateColumns = "1fr 1fr";

    const relationshipButton = createTextElement(
        "button",
        "action-button primary",
        "Connect / Follow"
    );
    relationshipButton.type = "button";

    const saveButton = createTextElement(
        "button",
        "action-button save-button",
        "Save"
    );
    saveButton.type = "button";
    updateSaveButtonState(saveButton, candidate);

    const actionStatus = createTextElement("div", "coming-soon", "");
    const cooldown = getActiveCooldown(candidate.profile_url);
    const receipt = getCandidateReceipt(candidate);

    if (cooldown) {
        relationshipButton.textContent = "Cooldown";
        relationshipButton.disabled = true;
    } else if (receipt && ["verified_pending", "already_pending"].includes(receipt.status)) {
        relationshipButton.textContent = "Pending";
        relationshipButton.disabled = true;
    } else if (receipt?.status === "already_connected") {
        relationshipButton.textContent = "Connected";
        relationshipButton.disabled = true;
    } else if (receiptIsFollowing(receipt)) {
        relationshipButton.textContent = "Following";
        relationshipButton.disabled = true;
    }

    renderStoredReceipt(candidate, actionStatus);

    relationshipButton.addEventListener("click", async () => {
        await connectCandidate(candidate, relationshipButton, actionStatus);
    });

    saveButton.addEventListener("click", async () => {
        await toggleSavedCandidate(candidate, saveButton);
    });

    actions.appendChild(relationshipButton);
    actions.appendChild(saveButton);
    card.appendChild(actions);
    card.appendChild(actionStatus);

    return card;
}


// ======================================================
// TRACKED CARD
// ======================================================

function createTrackedCard(
    person
) {

    if (!["following", "connected", "pending_connection"].includes(person.relationship_status)) {
        return document.createDocumentFragment();
    }
    const card = document.createElement("article");
    card.className = "tracked-card";

    const header = document.createElement("div");
    header.className = "tracked-header";
    header.appendChild(createAvatar(person));

    const main = document.createElement("div");
    main.className = "tracked-main";
    main.appendChild(createTextElement(
        "div",
        "candidate-name",
        person.name || "Tracked professional"
    ));
    main.appendChild(createTextElement(
        "p",
        "candidate-headline",
        person.headline
        || [person.current_role, person.current_company].filter(Boolean).join(" · " )
        || "Professional profile"
    ));

    const following = personIsFollowing(person);
    const connected = !following && person.relationship_status === "connected";
    const pending = !following && person.relationship_status === "pending_connection";

    main.appendChild(createTextElement(
        "span",
        "relationship-badge " + ((connected || following) ? "connected" : "pending"),
        following ? "Following" : (connected ? "Connected" : "Pending Connection")
    ));

    header.appendChild(main);
    card.appendChild(header);

    const details = document.createElement("div");
    details.className = "tracked-details";

    const addDetail = (label, value) => {
        if (!value) {
            return;
        }
        const row = document.createElement("div");
        row.className = "tracked-detail";
        row.appendChild(createTextElement("span", "", label));
        row.appendChild(createTextElement("strong", "", value));
        details.appendChild(row);
    };

    if (pending && person.connection_request?.requested_at) {
        addDetail("Requested", formatDate(person.connection_request.requested_at));
    }

    if (following && person.followed_at) {
        addDetail("Followed", formatDate(person.followed_at));
    }

    if (connected && person.connected_at) {
        addDetail("Connected", formatDate(person.connected_at));
    }

    if (person.current_company) {
        addDetail("Company", person.current_company);
    }

    if (details.childElementCount > 0) {
        card.appendChild(details);
    }

    if (connected && person.connection_acceptance?.verified) {
        card.appendChild(createTextElement(
            "div",
            "verified-receipt",
            "✓ Connection verified on LinkedIn"
        ));
    }

    if (following) {
        card.appendChild(createTextElement(
            "div",
            "verified-receipt",
            "✓ Following on LinkedIn"
        ));
    }

    if (pending && person.connection_request?.verified) {
        card.appendChild(createTextElement(
            "div",
            "verified-receipt",
            "✓ Invitation verified on LinkedIn — Pending"
        ));
    }

    const actions = document.createElement("div");
    actions.className = "actions";

    const removeButton = createTextElement(
        "button",
        "action-button",
        following
            ? "Unfollow"
            : (connected ? "Unfollow & Remove" : "Cancel Invite")
    );
    removeButton.type = "button";
    removeButton.style.gridColumn = "1 / -1";

    const removeStatus = createTextElement("div", "coming-soon", "");

    removeButton.addEventListener("click", async () => {
        await removeTrackedPerson(person, removeButton, removeStatus);
    });

    actions.appendChild(removeButton);
    card.appendChild(actions);
    card.appendChild(removeStatus);

    return card;
}


// ======================================================
// COMMENT
// ======================================================

async function submitLinkedInComment(
    notification,
    commentText,
    button,
    statusElement
) {

    const comment =
        String(commentText || "")
            .trim();


    if (!comment) {

        setActionStatus(
            statusElement,
            "failed",
            "Write a comment before posting."
        );


        return;
    }


    if (
        !notification.post_url
    ) {

        setActionStatus(
            statusElement,
            "failed",
            (
                "This notification has "
                +
                "no LinkedIn post URL."
            )
        );


        return;
    }


    button.disabled = true;
    button.textContent = "Posting…";


    setActionStatus(
        statusElement,
        "working",
        (
            "Posting your exact comment "
            +
            "and verifying it…"
        )
    );


    try {

        const result =
            await chrome.runtime.sendMessage(
                {
                    type:
                        "NETWORK_SCOUT_COMMENT_REQUEST",

                    postUrl:
                        notification.post_url,

                    profileUrl:
                        notification.profile_url
                        || null,

                    personName:
                        notification.person_name
                        || null,

                    notificationId:
                        notification.notification_id
                        || null,

                    commentText:
                        comment
                }
            );


        if (
            result?.verified
        ) {

            button.textContent =
                "Posted";

            button.disabled =
                true;


            setActionStatus(
                statusElement,
                "verified",
                (
                    "✓ COMMENT POSTED & "
                    +
                    "VERIFIED ON LINKEDIN"
                )
            );


            const recorded = await recordEngagementDecision(
                notification,
                "posted",
                {
                    comment_text:
                        comment,

                    verification_text:
                        result.verification_text
                        ||
                        result.verificationText
                        ||
                        "Comment verified",

                    verified:
                        true
                }
            );

            if (recorded) {
                // The backend now excludes verified posted opportunities
                // from subsequent Notifications refreshes as well.
                notifications = notifications.filter(
                    (entry) => entry.notification_id !== notification.notification_id
                );
                if (currentView === "notifications") {
                    renderNotificationsView();
                }
            } else {
                setActionStatus(
                    statusElement,
                    "attention",
                    "Comment verified on LinkedIn, but the completed notification could not be saved. Refresh after the backend reconnects."
                );
            }

            return;
        }


        button.textContent =
            "Try Again";

        button.disabled =
            false;


        setActionStatus(
            statusElement,
            "failed",
            result?.message
            ||
            (
                "Network Scout could not "
                +
                "verify the comment."
            )
        );

    } catch (error) {

        console.error(error);


        button.textContent =
            "Try Again";

        button.disabled =
            false;


        setActionStatus(
            statusElement,
            "failed",
            error.message
            ||
            "Could not post comment."
        );
    }
}


// ======================================================
// COMMENT COMPOSER
// ======================================================

async function loadEngagementSuggestions(notification, composer, textarea) {
    const section = document.createElement("div");
    section.className = "engagement-suggestions";
    section.style.marginBottom = "14px";
    section.appendChild(createTextElement(
        "div", "engagement-composer-label", "AI COMMENT SUGGESTIONS"
    ));

    const message = createTextElement(
        "div", "engagement-status", "Generating three suggestions…"
    );
    section.appendChild(message);

    // Display before the manual editor. If generation fails, the manual
    // posting workflow remains fully available.
    composer.insertBefore(section, textarea);

    try {
        const result = await apiFetch("/engagement-suggestions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                notification_id: notification.notification_id,
                profile_url: notification.profile_url,
                post_url: notification.post_url
            })
        }, 30000);

        if (!section.isConnected) return;
        const comments = Array.isArray(result?.comments) ? result.comments : [];
        if (comments.length !== 3) throw new Error("Three suggestions were not returned.");

        message.textContent = "Choose a draft to edit below. Nothing is posted automatically.";
        const names = ["Professional", "Thoughtful", "Conversational"];
        comments.forEach((comment, index) => {
            const selectButton = createTextElement(
                "button", "engagement-secondary-button",
                `${names[index]}: ${comment}`
            );
            selectButton.type = "button";
            selectButton.style.cssText =
                "display:block;width:100%;text-align:left;white-space:normal;" +
                "height:auto;padding:10px;margin-top:8px;line-height:1.45;";
            selectButton.addEventListener("click", () => {
                textarea.value = comment;
                textarea.dispatchEvent(new Event("input", { bubbles: true }));
                textarea.focus();
            });
            section.appendChild(selectButton);
        });
    } catch (error) {
        if (section.isConnected) {
            message.textContent =
                "Suggestions unavailable. You can still write and post your own comment.";
        }
        console.warn("Could not generate comment suggestions:", error);
    }
}


function createEngagementComposer(
    notification,
    card
) {

    const existing =
        card.querySelector(
            ".engagement-composer"
        );


    if (existing) {

        existing.remove();

        return;
    }


    const composer =
        document.createElement(
            "div"
        );


    composer.className =
        "engagement-composer";


    composer.appendChild(
        createTextElement(
            "div",
            "engagement-composer-label",
            "YOUR COMMENT"
        )
    );


    const textarea =
        document.createElement(
            "textarea"
        );


    textarea.className =
        "engagement-textarea";

    textarea.placeholder =
        (
            "Write the comment you want "
            +
            "posted to LinkedIn..."
        );

    textarea.rows = 5;
    textarea.maxLength = 1250;


    composer.appendChild(
        textarea
    );


    const counter =
        createTextElement(
            "span",
            "comment-counter",
            "0 / 1250"
        );


    textarea.addEventListener(
        "input",
        () => {

            counter.textContent =
                (
                    textarea.value.length
                    +
                    " / 1250"
                );
        }
    );


    composer.appendChild(
        counter
    );


    const actions =
        document.createElement(
            "div"
        );


    actions.className =
        "engagement-composer-actions";


    const cancelButton =
        createTextElement(
            "button",
            "engagement-secondary-button",
            "Cancel"
        );


    const postButton =
        createTextElement(
            "button",
            "engagement-primary-button",
            "Post Comment"
        );


    const status =
        createTextElement(
            "div",
            "engagement-status",
            (
                "Network Scout posts exactly "
                +
                "what you type."
            )
        );


    cancelButton.addEventListener(
        "click",
        () => {

            composer.remove();
        }
    );


    postButton.addEventListener(
        "click",
        async () => {

            await submitLinkedInComment(
                notification,
                textarea.value,
                postButton,
                status
            );
        }
    );


    actions.appendChild(
        cancelButton
    );

    actions.appendChild(
        postButton
    );


    composer.appendChild(
        actions
    );

    composer.appendChild(
        status
    );


    card.appendChild(
        composer
    );

    // Suggestions are optional assistance. Posting still uses the original
    // submitLinkedInComment path and requires an explicit click.
    loadEngagementSuggestions(notification, composer, textarea);

    textarea.focus();
}


// ======================================================
// NOTIFICATION CARD
// ======================================================

function createNotificationCard(
    notification
) {

    const isEngagement =
        notification.type ===
        "engagement_opportunity";


    const card =
        document.createElement(
            "article"
        );


    card.className =
        (
            "notification-card"
            +
            (
                notification.is_read
                    ? ""
                    : " unread"
            )
        );


    card.appendChild(
        createTextElement(
            "h4",
            "notification-title",
            notification.title
            ||
            "Network Scout"
        )
    );


    card.appendChild(
        createTextElement(
            "p",
            "notification-message",
            notification.message
            || ""
        )
    );


    if (isEngagement) {

        const summary =
            notification.post_summary
            ||
            notification.summary;


        if (summary) {

            const box =
                document.createElement(
                    "div"
                );


            box.className =
                "reason";


            box.appendChild(
                createTextElement(
                    "span",
                    "reason-label",
                    "POST SUMMARY"
                )
            );


            box.appendChild(
                createTextElement(
                    "p",
                    "",
                    truncateText(
                        summary,
                        500
                    )
                )
            );


            card.appendChild(
                box
            );
        }


        const whyRelevant =
            notification.why_relevant
            ||
            notification.relevance_reason;


        if (whyRelevant) {

            const box =
                document.createElement(
                    "div"
                );


            box.className =
                "reason";


            box.appendChild(
                createTextElement(
                    "span",
                    "reason-label",
                    "WHY THIS MATTERS"
                )
            );


            box.appendChild(
                createTextElement(
                    "p",
                    "",
                    truncateText(
                        whyRelevant,
                        400
                    )
                )
            );


            card.appendChild(
                box
            );
        }


        if (
            notification.score !==
            null
            &&
            notification.score !==
            undefined
        ) {

            card.appendChild(
                createTextElement(
                    "div",
                    "verified-receipt",
                    (
                        "Relevance: "
                        +
                        notification.score
                        +
                        "/100"
                    )
                )
            );
        }


        const actions =
            document.createElement(
                "div"
            );


        actions.className =
            "actions";


        const engage =
            createTextElement(
                "button",
                "action-button primary",
                "Engage"
            );


        const notNow =
            createTextElement(
                "button",
                "action-button",
                "Not Now"
            );


        engage.style.gridColumn =
            "span 2";


        engage.addEventListener(
            "click",
            async () => {

                await recordEngagementDecision(
                    notification,
                    "engage"
                );


                createEngagementComposer(
                    notification,
                    card
                );
            }
        );


        notNow.addEventListener(
            "click",
            async () => {

                await recordEngagementDecision(
                    notification,
                    "not_now"
                );


                notNow.textContent =
                    "Deferred";

                notNow.disabled =
                    true;
            }
        );


        actions.appendChild(
            engage
        );

        actions.appendChild(
            notNow
        );


        card.appendChild(
            actions
        );
    }


    card.appendChild(
        createTextElement(
            "div",
            "notification-time",
            formatDateTime(
                notification.source_detected_at
                ||
                notification.created_at
            )
        )
    );


    return card;
}


// ======================================================
// RENDER
// ======================================================

function renderWeeklyView() {

    currentView =
        "weekly";


    weeklyTab?.classList.add(
        "active"
    );

    trackedTab?.classList.remove(
        "active"
    );

    notificationsTab?.classList.remove(
        "active"
    );


    sectionLabel.textContent =
        "RECOMMENDATIONS";

    sectionTitle.textContent =
        "This Week's Picks";

    candidateCount.textContent =
        weeklyCandidates.length;

    countLabel.textContent =
        "PICKS";


    candidateList.innerHTML =
        "";


    if (
        weeklyCandidates.length ===
        0
    ) {

        candidateList.appendChild(
            createTextElement(
                "div",
                "empty-card",
                (
                    "No weekly recommendations "
                    +
                    "are available yet."
                )
            )
        );


        return;
    }


    for (
        const candidate
        of weeklyCandidates
    ) {

        candidateList.appendChild(
            createCandidateCard(
                candidate
            )
        );
    }
}


function renderTrackedView() {

    currentView =
        "tracked";


    trackedTab?.classList.add(
        "active"
    );

    weeklyTab?.classList.remove(
        "active"
    );

    notificationsTab?.classList.remove(
        "active"
    );


    sectionLabel.textContent =
        "RELATIONSHIPS";

    sectionTitle.textContent =
        "Tracked Network";

    candidateCount.textContent =
        trackedConnections.length;

    countLabel.textContent =
        "TRACKED";


    candidateList.innerHTML =
        "";


    if (
        trackedConnections.length ===
        0
    ) {

        candidateList.appendChild(
            createTextElement(
                "div",
                "empty-card",
                (
                    "No active Network Scout "
                    +
                    "relationships."
                )
            )
        );


        return;
    }


    for (
        const person
        of trackedConnections
    ) {

        candidateList.appendChild(
            createTrackedCard(
                person
            )
        );
    }
}


function renderNotificationsView() {

    currentView =
        "notifications";


    notificationsTab?.classList.add(
        "active"
    );

    weeklyTab?.classList.remove(
        "active"
    );

    trackedTab?.classList.remove(
        "active"
    );


    sectionLabel.textContent =
        "ACTIVITY";

    sectionTitle.textContent =
        "Notifications";

    candidateCount.textContent =
        notifications.length;

    countLabel.textContent =
        "ALERTS";


    candidateList.innerHTML =
        "";


    if (
        notifications.length ===
        0
    ) {

        candidateList.appendChild(
            createTextElement(
                "div",
                "empty-card",
                (
                    "Connection acceptances and "
                    +
                    "relevant posts will appear here."
                )
            )
        );


        return;
    }


    for (
        const notification
        of notifications
    ) {

        candidateList.appendChild(
            createNotificationCard(
                notification
            )
        );
    }
}


function renderCurrentView() {

    if (
        currentView ===
        "tracked"
    ) {

        renderTrackedView();

        return;
    }


    if (
        currentView ===
        "notifications"
    ) {

        renderNotificationsView();

        return;
    }


    renderWeeklyView();
}


// ======================================================
// STARTUP
// ======================================================

async function loadNetworkScout() {

    if (isLoading) {

        return;
    }


    isLoading = true;


    if (refreshButton) {

        refreshButton.disabled =
            true;

        refreshButton.textContent =
            "Loading…";
    }


    setCheckingState();

    renderLoading();


    await Promise.allSettled(
        [
            loadSavedCandidates(),
            loadActionReceipts(),
            loadCooldowns()
        ]
    );


    try {

        const health =
            await apiFetch(
                "/health",
                {},
                5000
            );


        setConnectedState(
            true,
            health?.message
            ||
            (
                "Network Scout backend "
                +
                "is connected."
            )
        );

    } catch (error) {

        console.error(
            "Health check failed:",
            error
        );


        setConnectedState(
            false,
            (
                "Network Scout backend "
                +
                "is unavailable."
            )
        );


        renderError(
            (
                "Network Scout could not connect "
                +
                "to the local backend."
            )
        );


        isLoading = false;


        if (refreshButton) {

            refreshButton.disabled =
                false;

            refreshButton.textContent =
                "Refresh";
        }


        return;
    }


    try {

        await fetchWeeklyCandidates();

    } catch (error) {

        console.error(
            "Weekly picks failed:",
            error
        );


        weeklyCandidates = [];
    }


    /*
        Show the main UI immediately.
    */

    renderCurrentView();


    try {

        await syncStoredVerifiedReceipts();

    } catch (error) {

        console.warn(
            "Receipt sync failed:",
            error
        );
    }


    await Promise.allSettled(
        [
            fetchTrackedConnections(),
            fetchNotifications()
        ]
    );


    renderCurrentView();


    isLoading = false;


    if (refreshButton) {

        refreshButton.disabled =
            false;

        refreshButton.textContent =
            "Refresh";
    }
}


// ======================================================
// EVENTS
// ======================================================

weeklyTab?.addEventListener(
    "click",
    () => {

        renderWeeklyView();
    }
);


trackedTab?.addEventListener(
    "click",
    async () => {

        renderLoading(
            "Loading Tracked Network..."
        );


        try {

            await fetchTrackedConnections();

        } catch (error) {

            console.error(error);
        }


        renderTrackedView();
    }
);


notificationsTab?.addEventListener(
    "click",
    async () => {

        renderLoading(
            "Loading Notifications..."
        );


        try {

            await fetchNotifications();

        } catch (error) {

            console.error(error);
        }


        renderNotificationsView();


        if (
            unreadNotificationCount > 0
        ) {

            await markAllNotificationsRead();
        }
    }
);


refreshButton?.addEventListener(
    "click",
    async () => {

        await loadNetworkScout();
    }
);


// ======================================================
// START
// ======================================================

if (
    document.readyState ===
    "loading"
) {

    document.addEventListener(
        "DOMContentLoaded",
        () => {

            loadNetworkScout()
                .catch(
                    (error) => {

                        console.error(
                            error
                        );


                        setConnectedState(
                            false,
                            (
                                "Network Scout "
                                +
                                "failed to start."
                            )
                        );


                        renderError(
                            error.message
                        );
                    }
                );
        }
    );

} else {

    loadNetworkScout()
        .catch(
            (error) => {

                console.error(
                    error
                );


                setConnectedState(
                    false,
                    (
                        "Network Scout "
                        +
                        "failed to start."
                    )
                );


                renderError(
                    error.message
                );
            }
        );
}