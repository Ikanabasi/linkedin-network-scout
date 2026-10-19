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

CANDIDATE_FILE = (
    PROJECT_ROOT
    / "data"
    / "candidates.json"
)

BROWSER_PROFILE = (
    PROJECT_ROOT
    / "browser_data"
    / "lawyer_profile"
)


# ======================================================
# SETTINGS
# ======================================================

MAX_PROFILES_PER_RUN = 5

PROFILE_LOAD_WAIT_MS = 6000


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

def normalize_text(value):

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

    return value


def clean_lines(text):

    if not text:
        return []

    result = []

    for line in str(text).splitlines():

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

        if not line:
            continue

        result.append(
            line
        )

    return result


# ======================================================
# LOAD / SAVE
# ======================================================

def load_candidates():

    if not CANDIDATE_FILE.exists():

        raise FileNotFoundError(
            f"Candidate file not found:\n"
            f"{CANDIDATE_FILE}"
        )

    with CANDIDATE_FILE.open(
        "r",
        encoding="utf-8"
    ) as file:

        candidates = json.load(
            file
        )

    if not isinstance(
        candidates,
        list
    ):

        raise ValueError(
            "candidates.json must contain a list."
        )

    return candidates


def save_candidates(
    candidates
):

    with CANDIDATE_FILE.open(
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            candidates,
            file,
            indent=4,
            ensure_ascii=False
        )


# ======================================================
# WHO NEEDS IDENTITY ENRICHMENT?
# ======================================================

def needs_identity_enrichment(
    candidate
):

    profile_url = (
        normalize_profile_url(
            candidate.get(
                "profile_url"
            )
        )
    )

    if not profile_url:
        return False

    status = (
        candidate.get(
            "identity_status"
        )
        or ""
    ).lower()

    if status in {
        "success",
        "partial"
    }:

        return False

    return True


# ======================================================
# LINKEDIN ACCESS CHECK
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

    if any(
        fragment in current_url
        for fragment
        in bad_fragments
    ):

        return True

    return False


# ======================================================
# GET PAGE BODY TEXT
# ======================================================

def get_body_text(
    page
):

    try:

        body = page.locator(
            "body"
        )

        return (
            body.inner_text(
                timeout=15000
            )
            or ""
        )

    except Exception:

        return ""


# ======================================================
# GET H1 TEXTS
# ======================================================

def get_h1_texts(
    page
):

    results = []

    headings = page.locator(
        "h1"
    )

    try:

        count = min(
            headings.count(),
            20
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

                text = (
                    heading.inner_text()
                    or ""
                ).strip()

                if text:

                    results.append(
                        text
                    )

            except Exception:

                continue

    except Exception:

        pass

    return results


# ======================================================
# FIND CANDIDATE NAME IN PAGE
# ======================================================

def extract_name(
    page,
    lines,
    candidate_name
):

    candidate_name = (
        candidate_name
        or ""
    ).strip()

    candidate_key = normalize_text(
        candidate_name
    )

    # ==================================================
    # 1. Prefer H1
    # ==================================================

    h1_texts = get_h1_texts(
        page
    )

    for heading in h1_texts:

        heading_key = normalize_text(
            heading
        )

        if (
            candidate_key
            and candidate_key
            in heading_key
        ):

            return candidate_name

    # ==================================================
    # 2. Exact visible body line
    # ==================================================

    for line in lines:

        if (
            normalize_text(
                line
            )
            == candidate_key
        ):

            return candidate_name

    # ==================================================
    # 3. Candidate name at beginning of line
    # ==================================================

    for line in lines:

        line_key = normalize_text(
            line
        )

        if (
            candidate_key
            and line_key.startswith(
                candidate_key
            )
        ):

            return candidate_name

    return None


# ======================================================
# FIND NAME POSITION
# ======================================================

def find_name_index(
    lines,
    candidate_name
):

    candidate_key = normalize_text(
        candidate_name
    )

    for index, line in enumerate(
        lines
    ):

        line_key = normalize_text(
            line
        )

        if (
            line_key == candidate_key
            or
            line_key.startswith(
                candidate_key
            )
        ):

            return index

    return None


# ======================================================
# NOISE CHECK
# ======================================================

def is_profile_noise(
    line
):

    if not line:
        return True

    value = normalize_text(
        line
    )

    exact_noise = {
        "message",
        "follow",
        "following",
        "connect",
        "more",
        "contact info",
        "open to",
        "open to work",
        "premium",
        "premium profile",
        "about",
        "activity",
        "experience",
        "education"
    }

    if value in exact_noise:
        return True

    patterns = [
        r"^(1st|2nd|3rd\+?)$",
        r"^•\s*(1st|2nd|3rd\+?)$",
        r"^\d+\s+followers?$",
        r"^\d+\+?\s+connections?$",
        r"^\d+\s+mutual connections?$"
    ]

    for pattern in patterns:

        if re.match(
            pattern,
            line,
            re.IGNORECASE
        ):

            return True

    if (
        "mutual connection"
        in value
    ):

        return True

    return False


# ======================================================
# HEADLINE
# ======================================================

def extract_headline(
    lines,
    candidate_name,
    discovered_headline
):

    discovered_headline = (
        discovered_headline
        or ""
    ).strip()

    # ==================================================
    # 1. Strongest option:
    # the headline we already captured from LinkedIn
    # comments appears on the profile page too.
    # ==================================================

    if discovered_headline:

        discovered_key = normalize_text(
            discovered_headline
        )

        for line in lines:

            line_key = normalize_text(
                line
            )

            if (
                line_key == discovered_key
                or discovered_key in line_key
            ):

                return discovered_headline

    # ==================================================
    # 2. Look near the candidate's name
    # ==================================================

    name_index = find_name_index(
        lines,
        candidate_name
    )

    if name_index is None:

        return None

    for line in lines[
        name_index + 1:
        name_index + 12
    ]:

        if is_profile_noise(
            line
        ):
            continue

        # Geographic-looking strings are probably
        # location rather than headline.
        if (
            "," in line
            and len(line) < 90
        ):
            continue

        if len(line) < 5:
            continue

        if len(line) > 300:
            continue

        return line

    return None


# ======================================================
# LOCATION
# ======================================================

def extract_location(
    lines,
    candidate_name,
    headline
):

    name_index = find_name_index(
        lines,
        candidate_name
    )

    if name_index is None:

        return None

    headline_key = normalize_text(
        headline
    )

    start_index = (
        name_index + 1
    )

    # Prefer looking after the headline.
    if headline_key:

        for index in range(
            name_index,
            min(
                len(lines),
                name_index + 15
            )
        ):

            if (
                normalize_text(
                    lines[index]
                )
                == headline_key
            ):

                start_index = (
                    index + 1
                )

                break

    possible = []

    for line in lines[
        start_index:
        start_index + 12
    ]:

        if is_profile_noise(
            line
        ):
            continue

        if (
            headline_key
            and normalize_text(
                line
            )
            == headline_key
        ):

            continue

        if len(line) > 120:
            continue

        possible.append(
            line
        )

    # Most LinkedIn locations look like:
    # Toronto, Ontario, Canada
    # Bridgetown, Barbados
    for line in possible:

        if "," in line:

            return line

    # Some profiles only show:
    # Barbados
    # Canada
    # Nigeria
    for line in possible:

        if (
            2
            <= len(line)
            <= 60
        ):

            lowered = normalize_text(
                line
            )

            bad_words = [
                "founder",
                "engineer",
                "manager",
                "director",
                "consultant",
                "specialist",
                "officer",
                "analyst"
            ]

            if not any(
                word in lowered
                for word in bad_words
            ):

                return line

    return None


# ======================================================
# COMPANY FROM HEADLINE
# ======================================================

def company_from_headline(
    headline
):

    if not headline:
        return None

    patterns = [
        r"\b(?:at|@)\s+([^|•]+)",
        r"\bfounder\s+at\s+([^|•]+)",
        r"\bco-founder\s+at\s+([^|•]+)",
        r"\bceo\s+at\s+([^|•]+)",
        r"\bpartner\s+at\s+([^|•]+)"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            headline,
            re.IGNORECASE
        )

        if match:

            company = (
                match.group(1)
                .strip()
            )

            company = re.sub(
                r"\s+",
                " ",
                company
            )

            if company:

                return company

    return None


# ======================================================
# COMPANY LINKS
# ======================================================

def get_company_links(
    page
):

    results = []

    links = page.locator(
        "a[href*='/company/']"
    )

    try:

        count = min(
            links.count(),
            100
        )

        for index in range(
            count
        ):

            link = (
                links.nth(
                    index
                )
            )

            try:

                href = (
                    link.get_attribute(
                        "href"
                    )
                    or ""
                )

                text = (
                    link.inner_text()
                    or ""
                ).strip()

                if not href:
                    continue

                full_url = clean_url(
                    href
                )

                if not full_url:
                    continue

                # Company logo links sometimes have
                # no useful inner text.
                if not text:

                    aria = (
                        link.get_attribute(
                            "aria-label"
                        )
                        or ""
                    ).strip()

                    text = aria

                if (
                    not text
                    and not full_url
                ):

                    continue

                record = {
                    "name":
                        text,

                    "url":
                        full_url
                }

                if (
                    record
                    not in results
                ):

                    results.append(
                        record
                    )

            except Exception:

                continue

    except Exception:

        pass

    return results


# ======================================================
# CHOOSE CURRENT COMPANY
# ======================================================

def choose_current_company(
    headline,
    company_links
):

    headline_company = (
        company_from_headline(
            headline
        )
    )

    # ==================================================
    # Headline gives us an explicit:
    # Founder at Dharach
    # ==================================================

    if headline_company:

        company_key = normalize_text(
            headline_company
        )

        for company in company_links:

            linked_name = (
                company.get(
                    "name"
                )
                or ""
            )

            if (
                company_key
                and company_key
                in normalize_text(
                    linked_name
                )
            ):

                return {
                    "name":
                        headline_company,

                    "url":
                        company.get(
                            "url"
                        ),

                    "source":
                        "linkedin_headline_and_company_link"
                }

        return {
            "name":
                headline_company,

            "url":
                None,

            "source":
                "linkedin_headline"
        }

    # ==================================================
    # Fallback to first usable company link
    # ==================================================

    for company in company_links:

        name = (
            company.get(
                "name"
            )
            or ""
        ).strip()

        if not name:
            continue

        if len(name) > 150:
            continue

        return {
            "name":
                name,

            "url":
                company.get(
                    "url"
                ),

            "source":
                "linkedin_company_link"
        }

    return {
        "name":
            None,

        "url":
            None,

        "source":
            None
    }


# ======================================================
# TOP-CARD EVIDENCE
# ======================================================

def build_top_card_preview(
    lines,
    candidate_name
):

    name_index = find_name_index(
        lines,
        candidate_name
    )

    if name_index is None:
        return ""

    start = max(
        0,
        name_index - 2
    )

    end = min(
        len(lines),
        name_index + 15
    )

    return "\n".join(
        lines[
            start:end
        ]
    )


# ======================================================
# EXPERIENCE PREVIEW
# ======================================================

def build_experience_preview(
    lines
):

    for index, line in enumerate(
        lines
    ):

        if (
            normalize_text(
                line
            )
            == "experience"
        ):

            end = min(
                len(lines),
                index + 35
            )

            return "\n".join(
                lines[
                    index:end
                ]
            )

    return None


# ======================================================
# CAPTURE LINKEDIN IDENTITY
# ======================================================

def capture_linkedin_identity(
    page,
    candidate
):

    profile_url = (
        normalize_profile_url(
            candidate.get(
                "profile_url"
            )
        )
    )

    if not profile_url:

        return {
            "identity_status":
                "failed",

            "identity_error":
                "No valid profile URL."
        }

    print(
        "\nOpening:"
    )

    print(
        profile_url
    )

    # ==================================================
    # OPEN PROFILE
    # ==================================================

    page.goto(
        profile_url,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(
        PROFILE_LOAD_WAIT_MS
    )

    final_url = (
        page.url
    )

    page_title = ""

    try:

        page_title = (
            page.title()
            or ""
        )

    except Exception:

        pass

    # ==================================================
    # CHECK AUTH
    # ==================================================

    if linkedin_access_problem(
        page
    ):

        return {
            "identity_status":
                "failed",

            "identity_error":
                "LinkedIn redirected to login/checkpoint.",

            "debug":
                {
                    "final_url":
                        final_url,

                    "page_title":
                        page_title
                }
        }

    # ==================================================
    # GET VISIBLE PAGE CONTENT
    # ==================================================

    body_text = get_body_text(
        page
    )

    lines = clean_lines(
        body_text
    )

    print(
        "Visible page lines:",
        len(
            lines
        )
    )

    candidate_name = (
        candidate.get(
            "name"
        )
    )

    discovered_headline = (
        candidate.get(
            "headline"
        )
    )

    # ==================================================
    # NAME
    # ==================================================

    name = extract_name(
        page,
        lines,
        candidate_name
    )

    # ==================================================
    # HEADLINE
    # ==================================================

    headline = extract_headline(
        lines,
        candidate_name,
        discovered_headline
    )

    # ==================================================
    # LOCATION
    # ==================================================

    location = extract_location(
        lines,
        candidate_name,
        headline
    )

    # ==================================================
    # COMPANY
    # ==================================================

    company_links = get_company_links(
        page
    )

    company = choose_current_company(
        headline,
        company_links
    )

    # ==================================================
    # EVIDENCE
    # ==================================================

    top_card_text = (
        build_top_card_preview(
            lines,
            candidate_name
        )
    )

    experience_preview = (
        build_experience_preview(
            lines
        )
    )

    # ==================================================
    # QUALITY
    # ==================================================

    if (
        name
        and headline
        and (
            location
            or company.get(
                "name"
            )
        )
    ):

        identity_status = (
            "success"
        )

    elif (
        name
        and headline
    ):

        identity_status = (
            "partial"
        )

    else:

        identity_status = (
            "failed"
        )

    # ==================================================
    # RESULT
    # ==================================================

    fingerprint = {

        "profile_url":
            profile_url,

        "captured_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "name":
            name,

        "headline":
            headline,

        "location":
            location,

        "current_company":
            company.get(
                "name"
            ),

        "current_company_url":
            company.get(
                "url"
            ),

        "current_company_source":
            company.get(
                "source"
            ),

        "top_card_text":
            top_card_text,

        "experience_preview":
            experience_preview
    }

    result = {

        "identity_status":
            identity_status,

        "linkedin_identity":
            fingerprint
    }

    # ==================================================
    # AUTOMATIC DEBUGGING IF IT STILL FAILS
    # ==================================================

    if (
        identity_status
        == "failed"
    ):

        result[
            "identity_debug"
        ] = {

            "final_url":
                final_url,

            "page_title":
                page_title,

            "h1_texts":
                get_h1_texts(
                    page
                ),

            "visible_line_count":
                len(
                    lines
                ),

            "body_preview":
                "\n".join(
                    lines[:80]
                )[:4000]
        }

    return result


# ======================================================
# PRINT RESULT
# ======================================================

def print_identity(
    candidate,
    result
):

    print(
        "\n--------------------------------"
    )

    print(
        "LINKEDIN IDENTITY"
    )

    print(
        "--------------------------------"
    )

    print(
        "Discovery name:",
        candidate.get(
            "name"
        )
    )

    print(
        "Status:",
        result.get(
            "identity_status"
        )
    )

    identity = (
        result.get(
            "linkedin_identity"
        )
        or {}
    )

    print(
        "LinkedIn name:",
        identity.get(
            "name"
        )
    )

    print(
        "Headline:",
        identity.get(
            "headline"
        )
    )

    print(
        "Location:",
        identity.get(
            "location"
        )
    )

    print(
        "Company:",
        identity.get(
            "current_company"
        )
    )

    print(
        "Company URL:",
        identity.get(
            "current_company_url"
        )
    )

    if result.get(
        "identity_debug"
    ):

        print(
            "\nDEBUG INFORMATION WAS SAVED."
        )


# ======================================================
# MAIN
# ======================================================

def run(playwright):

    print(
        "\n================================"
    )

    print(
        "NETWORK SCOUT"
    )

    print(
        "LINKEDIN IDENTITY ENRICHMENT"
    )

    print(
        "================================"
    )

    candidates = (
        load_candidates()
    )

    print(
        "\nCandidates in file:",
        len(
            candidates
        )
    )

    # ==================================================
    # FIND CANDIDATES TO PROCESS
    # ==================================================

    indexes = []

    for index, candidate in enumerate(
        candidates
    ):

        if needs_identity_enrichment(
            candidate
        ):

            indexes.append(
                index
            )

    print(
        "Candidates missing identity:",
        len(
            indexes
        )
    )

    if not indexes:

        print(
            "\nNothing to process."
        )

        return

    indexes = (
        indexes[
            :MAX_PROFILES_PER_RUN
        ]
    )

    print(
        "Profiles being processed:",
        len(
            indexes
        )
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

    success_count = 0
    partial_count = 0
    failed_count = 0

    # ==================================================
    # PROCESS
    # ==================================================

    for position, candidate_index in enumerate(
        indexes,
        start=1
    ):

        candidate = (
            candidates[
                candidate_index
            ]
        )

        print(
            "\n\n================================"
        )

        print(
            f"PROFILE {position}/"
            f"{len(indexes)}"
        )

        print(
            "================================"
        )

        print(
            "Candidate:",
            candidate.get(
                "name"
            )
        )

        try:

            result = (
                capture_linkedin_identity(
                    page,
                    candidate
                )
            )

            candidate[
                "identity_status"
            ] = result.get(
                "identity_status"
            )

            if result.get(
                "linkedin_identity"
            ):

                candidate[
                    "linkedin_identity"
                ] = result[
                    "linkedin_identity"
                ]

            if result.get(
                "identity_debug"
            ):

                candidate[
                    "identity_debug"
                ] = result[
                    "identity_debug"
                ]

            else:

                candidate.pop(
                    "identity_debug",
                    None
                )

            if result.get(
                "identity_error"
            ):

                candidate[
                    "identity_error"
                ] = result[
                    "identity_error"
                ]

            else:

                candidate.pop(
                    "identity_error",
                    None
                )

            print_identity(
                candidate,
                result
            )

            status = (
                result.get(
                    "identity_status"
                )
            )

            if status == "success":

                success_count += 1

            elif status == "partial":

                partial_count += 1

            else:

                failed_count += 1

            save_candidates(
                candidates
            )

            print(
                "\nIdentity saved."
            )

        except Exception as error:

            failed_count += 1

            print(
                "\nPROFILE FAILED"
            )

            print(
                error
            )

            candidate[
                "identity_status"
            ] = "failed"

            candidate[
                "identity_error"
            ] = str(
                error
            )

            candidate[
                "identity_attempted_at"
            ] = datetime.now(
                timezone.utc
            ).isoformat()

            save_candidates(
                candidates
            )

        page.wait_for_timeout(
            1200
        )

    # ==================================================
    # FINAL SAVE
    # ==================================================

    save_candidates(
        candidates
    )

    # ==================================================
    # SUMMARY
    # ==================================================

    print(
        "\n\n================================"
    )

    print(
        "IDENTITY ENRICHMENT COMPLETE"
    )

    print(
        "================================"
    )

    print(
        "Successful:",
        success_count
    )

    print(
        "Partial:",
        partial_count
    )

    print(
        "Failed:",
        failed_count
    )

    print(
        "\nCandidate file:"
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

        run(playwright)