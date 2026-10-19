import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from dotenv import load_dotenv
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


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

CANDIDATES_FILE = (
    PROJECT_ROOT
    / "data"
    / "candidates.json"
)

load_dotenv(
    PROJECT_ROOT
    / ".env"
)


# ======================================================
# SETTINGS
# ======================================================

PAGE_TIMEOUT_MS = 60000
PAGE_SETTLE_MS = 4000
BETWEEN_PROFILES_MS = 1500


PROFILE_ENRICHMENT_LIMIT = int(
    os.getenv(
        "PROFILE_ENRICHMENT_LIMIT",
        "0",
    )
)


# v4 fixes an important v3 issue:
#
# v3 could accidentally capture the logged-in
# user's LinkedIn navigation avatar.
#
# v4 restricts profile-photo extraction to the
# viewed person's MAIN profile content and uses
# their name as a strong identity signal.

ENRICHMENT_VERSION = (
    "linkedin_profile_v4_targeted_photo"
)


# ======================================================
# TIME
# ======================================================

def utc_now():

    return datetime.now(
        timezone.utc
    ).isoformat()


# ======================================================
# JSON
# ======================================================

def load_candidates():

    if not CANDIDATES_FILE.exists():

        return []

    with CANDIDATES_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:

        data = json.load(
            file
        )

    if not isinstance(
        data,
        list,
    ):

        raise ValueError(
            "data/candidates.json must contain a list."
        )

    return data


def save_candidates(
    candidates,
):

    CANDIDATES_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_file = (
        CANDIDATES_FILE
        .with_suffix(
            ".json.tmp"
        )
    )

    with temporary_file.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            candidates,
            file,
            indent=4,
            ensure_ascii=False,
        )

    temporary_file.replace(
        CANDIDATES_FILE
    )


# ======================================================
# URL HELPERS
# ======================================================

def clean_url(
    url,
):

    if not url:

        return None

    url = urljoin(
        "https://www.linkedin.com",
        str(
            url
        ).strip(),
    )

    url = (
        url
        .split("?")[0]
        .split("#")[0]
    )

    return url


def normalize_profile_url(
    url,
):

    if not url:

        return None

    url = clean_url(
        url
    )

    match = re.search(
        r"linkedin\.com/in/([^/?#]+)",
        url,
        re.IGNORECASE,
    )

    if not match:

        return None

    slug = (
        match.group(1)
        .strip()
    )

    return (
        "https://www.linkedin.com/in/"
        + slug
        + "/"
    )


# ======================================================
# TEXT HELPERS
# ======================================================

def normalize_text(
    value,
):

    if not value:

        return ""

    value = (
        str(
            value
        )
        .replace(
            "\xa0",
            " ",
        )
        .replace(
            "\u200b",
            "",
        )
        .strip()
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value


def clean_lines(
    text,
):

    if not text:

        return []

    lines = []

    for raw_line in str(
        text
    ).splitlines():

        line = normalize_text(
            raw_line
        )

        if line:

            lines.append(
                line
            )

    return lines


def unique_preserve_order(
    values,
):

    result = []
    seen = set()

    for value in values:

        normalized = (
            normalize_text(
                value
            )
            .lower()
        )

        if not normalized:

            continue

        if normalized in seen:

            continue

        seen.add(
            normalized
        )

        result.append(
            value
        )

    return result


def normalized_name_tokens(
    name,
):

    value = (
        normalize_text(
            name
        )
        .lower()
    )

    tokens = re.findall(
        r"[a-z0-9]+",
        value,
    )

    ignored = {
        "dr",
        "mr",
        "mrs",
        "ms",
        "prof",
    }

    return [
        token
        for token in tokens
        if (
            len(token) >= 2
            and
            token not in ignored
        )
    ]


def image_alt_matches_name(
    alt_text,
    profile_name,
):

    alt_tokens = set(
        normalized_name_tokens(
            alt_text
        )
    )

    name_tokens = (
        normalized_name_tokens(
            profile_name
        )
    )

    if not alt_tokens:

        return False

    if not name_tokens:

        return False

    matching_tokens = [
        token
        for token in name_tokens
        if token in alt_tokens
    ]

    # If we know at least two parts of the person's
    # name, require at least two matching tokens.
    #
    # Example:
    # Josephine Smith -> Josephine Smith

    if len(
        name_tokens
    ) >= 2:

        return (
            len(
                matching_tokens
            )
            >= 2
        )

    # For records where discovery only captured
    # one visible name, one match is enough.

    return (
        len(
            matching_tokens
        )
        >= 1
    )


# ======================================================
# LINKEDIN ACCESS
# ======================================================

def linkedin_access_problem(
    page,
):

    url = (
        page.url
        or ""
    ).lower()

    bad_fragments = [
        "/login",
        "/checkpoint",
        "/authwall",
    ]

    return any(
        fragment in url
        for fragment in bad_fragments
    )


# ======================================================
# NAME
# ======================================================

def get_profile_name(
    page,
    fallback=None,
):

    selectors = [
        "main h1",
        "h1",
    ]

    for selector in selectors:

        locator = (
            page.locator(
                selector
            )
        )

        try:

            count = min(
                locator.count(),
                10,
            )

        except Exception:

            continue

        for index in range(
            count
        ):

            item = (
                locator.nth(
                    index
                )
            )

            try:

                if not item.is_visible():

                    continue

                text = normalize_text(
                    item.inner_text()
                )

                if text:

                    return text

            except Exception:

                continue

    return fallback


# ======================================================
# TOP CARD
# ======================================================

def find_top_card_container(
    page,
):

    try:

        headings = (
            page.locator(
                "main h1"
            )
        )

        if headings.count() == 0:

            return None

        heading = (
            headings.first
        )

        if not heading.is_visible():

            return None

    except Exception:

        return None

    current = heading
    best = None

    for _ in range(
        10
    ):

        try:

            parent = (
                current.locator(
                    "xpath=.."
                )
            )

            text = (
                parent.inner_text()
                or ""
            )

            text_length = len(
                text
            )

            # Keep the container reasonably small.
            #
            # The old implementation could walk far
            # enough upward to include unrelated page
            # elements.

            if (
                20
                <= text_length
                <= 2500
            ):

                best = parent

            if (
                text_length
                > 2500
            ):

                break

            current = parent

        except Exception:

            break

    return best


def get_top_card_preview(
    page,
):

    container = (
        find_top_card_container(
            page
        )
    )

    if container is None:

        return None

    try:

        text = (
            container.inner_text()
        )

    except Exception:

        return None

    lines = (
        unique_preserve_order(
            clean_lines(
                text
            )
        )
    )

    if not lines:

        return None

    return (
        "\n".join(
            lines[:40]
        )[:5000]
    )


# ======================================================
# PROFILE PHOTO
# ======================================================

def get_image_source(
    image,
):

    try:

        value = image.evaluate(
            """
            (img) => {
                return (
                    img.currentSrc ||
                    img.src ||
                    img.getAttribute('src') ||
                    img.getAttribute('data-delayed-url') ||
                    img.getAttribute('data-src') ||
                    ''
                );
            }
            """
        )

    except Exception:

        value = None

    value = normalize_text(
        value
    )

    if not value:

        return None

    if value.startswith(
        "data:"
    ):

        return None

    if value.startswith(
        "blob:"
    ):

        return None

    if value.startswith(
        "//"
    ):

        value = (
            "https:"
            + value
        )

    if value.startswith(
        "/"
    ):

        value = urljoin(
            "https://www.linkedin.com",
            value,
        )

    if not value.startswith(
        (
            "http://",
            "https://",
        )
    ):

        return None

    return value


def inspect_image(
    image,
    profile_name,
    top_card=False,
):

    try:

        if not image.is_visible():

            return None

    except Exception:

        return None

    src = get_image_source(
        image
    )

    if not src:

        return None

    try:

        alt = normalize_text(
            image.get_attribute(
                "alt"
            )
        )

    except Exception:

        alt = ""

    try:

        class_name = normalize_text(
            image.get_attribute(
                "class"
            )
        )

    except Exception:

        class_name = ""

    try:

        dimensions = image.evaluate(
            """
            (img) => ({
                width:
                    img.naturalWidth ||
                    img.width ||
                    0,

                height:
                    img.naturalHeight ||
                    img.height ||
                    0
            })
            """
        )

    except Exception:

        dimensions = {
            "width": 0,
            "height": 0,
        }

    width = int(
        (
            dimensions
            or {}
        ).get(
            "width"
        )
        or 0
    )

    height = int(
        (
            dimensions
            or {}
        ).get(
            "height"
        )
        or 0
    )

    lower_src = (
        src.lower()
    )

    lower_alt = (
        alt.lower()
    )

    lower_class = (
        class_name.lower()
    )

    name_match = (
        image_alt_matches_name(
            alt,
            profile_name,
        )
    )

    linkedin_profile_class = any(
        marker in lower_class
        for marker in [
            "pv-top-card-profile-picture",
            "profile-photo",
            "profile-picture",
        ]
    )

    linkedin_profile_src = any(
        marker in lower_src
        for marker in [
            "profile-displayphoto",
            "profile-framedphoto",
        ]
    )

    score = 0

    if name_match:

        score += 30

    if top_card:

        score += 8

    if linkedin_profile_class:

        score += 8

    if linkedin_profile_src:

        score += 4

    if (
        width >= 80
        and
        height >= 80
    ):

        score += 3

    if (
        width > 0
        and
        height > 0
    ):

        ratio = (
            width
            / height
        )

        if (
            0.72
            <= ratio
            <= 1.38
        ):

            score += 5

        if (
            ratio >= 1.8
            or
            ratio <= 0.55
        ):

            score -= 20

    if any(
        marker in lower_alt
        for marker in [
            "logo",
            "banner",
            "background",
            "company",
        ]
    ):

        score -= 20

    if any(
        marker in lower_src
        for marker in [
            "company-logo",
            "school-logo",
            "backgroundimage",
            "cover-image",
        ]
    ):

        score -= 20

    return {
        "url": src,
        "alt": alt,
        "score": score,
        "name_match": name_match,
        "top_card": top_card,
        "profile_class": linkedin_profile_class,
        "profile_src": linkedin_profile_src,
        "width": width,
        "height": height,
    }


def extract_profile_photo_url(
    page,
    profile_name,
):

    """
    Extract ONLY the viewed person's LinkedIn
    profile photo.

    Important:
    Everything is scoped to <main>.

    This prevents the logged-in user's avatar in
    LinkedIn's global navigation bar from being
    selected.
    """

    candidates = []
    seen_urls = set()

    try:

        main = page.locator(
            "main"
        ).first

        if not main.is_visible():

            return None

    except Exception:

        return None

    def collect(
        locator,
        top_card=False,
        limit=30,
    ):

        try:

            count = min(
                locator.count(),
                limit,
            )

        except Exception:

            return

        for index in range(
            count
        ):

            image = (
                locator.nth(
                    index
                )
            )

            result = inspect_image(
                image,
                profile_name,
                top_card=top_card,
            )

            if not result:

                continue

            url = (
                result.get(
                    "url"
                )
            )

            if not url:

                continue

            if url in seen_urls:

                continue

            seen_urls.add(
                url
            )

            candidates.append(
                result
            )

    # ==================================================
    # 1. NAME-MATCHED IMAGES INSIDE MAIN
    # ==================================================
    #
    # This is our strongest approach.
    #
    # Candidate:
    # Josephine Smith
    #
    # Image alt:
    # Josephine Smith
    #
    # Your own nav avatar cannot enter this search
    # because it is outside <main>.

    try:

        collect(
            main.locator(
                "img[alt]"
            ),
            top_card=False,
            limit=100,
        )

    except Exception:

        pass

    # ==================================================
    # 2. ACTUAL TOP CARD
    # ==================================================

    top_card_container = (
        find_top_card_container(
            page
        )
    )

    if top_card_container is not None:

        try:

            collect(
                top_card_container.locator(
                    "img"
                ),
                top_card=True,
                limit=20,
            )

        except Exception:

            pass

    # ==================================================
    # 3. LINKEDIN TOP-CARD SELECTORS
    #    STILL SCOPED TO MAIN
    # ==================================================

    targeted_selectors = [

        "img.pv-top-card-profile-picture__image",

        "img.pv-top-card-profile-picture__image--show",

        "img.profile-photo-edit__preview",

        "img[src*='profile-displayphoto']",

        "img[src*='profile-framedphoto']",
    ]

    for selector in targeted_selectors:

        try:

            collect(
                main.locator(
                    selector
                ),
                top_card=True,
                limit=10,
            )

        except Exception:

            continue

    if not candidates:

        return None

    candidates.sort(
        key=lambda item: (
            item.get(
                "score",
                0,
            )
        ),
        reverse=True,
    )

    best = (
        candidates[0]
    )

    # ==================================================
    # STRICT IDENTITY RULE
    # ==================================================
    #
    # We accept the image when:
    #
    # 1. the alt text identifies the candidate,
    #
    # OR
    #
    # 2. it is a very strong LinkedIn top-card match
    #    inside MAIN.
    #
    # This is deliberately conservative.
    # It is better to show initials than the WRONG
    # person's picture.

    strong_name_match = (
        best.get(
            "name_match"
        )
    )

    strong_top_card_match = (
        best.get(
            "top_card"
        )
        and
        best.get(
            "profile_class"
        )
        and
        best.get(
            "score",
            0,
        )
        >= 16
    )

    if not (
        strong_name_match
        or
        strong_top_card_match
    ):

        return None

    return (
        best.get(
            "url"
        )
    )


# ======================================================
# TOP-CARD PARSING
# ======================================================

def is_top_card_noise(
    line,
):

    value = (
        normalize_text(
            line
        )
        .lower()
    )

    if not value:

        return True

    exact_noise = {
        "contact info",
        "message",
        "connect",
        "follow",
        "more",
        "open to work",
        "premium",
        "premium profile",
        "connections",
        "followers",
    }

    if value in exact_noise:

        return True

    patterns = [
        r"^\d[\d,]*\s+followers?$",
        r"^\d[\d,]*\s+connections?$",
        r"^\d[\d,]*\s+mutual connections?$",
    ]

    for pattern in patterns:

        if re.fullmatch(
            pattern,
            value,
        ):

            return True

    return False


def extract_headline_location(
    name,
    top_card_preview,
):

    lines = (
        unique_preserve_order(
            clean_lines(
                top_card_preview
            )
        )
    )

    if not lines:

        return (
            None,
            None,
        )

    name_key = (
        normalize_text(
            name
        )
        .lower()
    )

    start_index = 0

    for index, line in enumerate(
        lines
    ):

        line_key = (
            normalize_text(
                line
            )
            .lower()
        )

        if (
            line_key == name_key
            or
            line_key.startswith(
                name_key + " "
            )
        ):

            start_index = (
                index + 1
            )

            break

    possible_lines = []

    for line in lines[
        start_index:
        start_index + 15
    ]:

        if is_top_card_noise(
            line
        ):

            continue

        if (
            normalize_text(
                line
            )
            .lower()
            == name_key
        ):

            continue

        possible_lines.append(
            line
        )

    headline = None
    location = None

    if possible_lines:

        headline = (
            possible_lines[0]
        )

    for line in possible_lines[
        1:8
    ]:

        lower = (
            normalize_text(
                line
            )
            .lower()
        )

        if any(
            phrase in lower
            for phrase in [
                "current:",
                "education:",
                "experience:",
            ]
        ):

            continue

        if (
            "," in line
            and
            len(
                line
            )
            <= 140
        ):

            location = (
                line
            )

            break

    return (
        headline,
        location,
    )


# ======================================================
# PROFILE SECTIONS
# ======================================================

def find_profile_section(
    page,
    section_name,
):

    target = (
        section_name
        .strip()
        .lower()
    )

    try:

        sections = (
            page.locator(
                "main section"
            )
        )

        count = min(
            sections.count(),
            80,
        )

        for index in range(
            count
        ):

            section = (
                sections.nth(
                    index
                )
            )

            try:

                if not section.is_visible():

                    continue

                text = (
                    section.inner_text()
                )

            except Exception:

                continue

            lines = (
                clean_lines(
                    text
                )
            )

            first_lines = [
                normalize_text(
                    line
                ).lower()
                for line
                in lines[:6]
            ]

            if target in first_lines:

                return section

    except Exception:

        pass

    for selector in [
        "h2",
        "h3",
        "span",
    ]:

        try:

            elements = (
                page.locator(
                    selector
                )
            )

            count = min(
                elements.count(),
                180,
            )

        except Exception:

            continue

        for index in range(
            count
        ):

            element = (
                elements.nth(
                    index
                )
            )

            try:

                if not element.is_visible():

                    continue

                element_text = (
                    normalize_text(
                        element.inner_text()
                    )
                    .lower()
                )

            except Exception:

                continue

            if (
                element_text
                != target
            ):

                continue

            current = (
                element
            )

            best = None

            for _ in range(
                10
            ):

                try:

                    parent = (
                        current.locator(
                            "xpath=.."
                        )
                    )

                    text = (
                        parent.inner_text()
                        or ""
                    )

                    lines = (
                        clean_lines(
                            text
                        )
                    )

                    heading_occurrences = sum(
                        1
                        for line
                        in lines
                        if (
                            normalize_text(
                                line
                            )
                            .lower()
                            == target
                        )
                    )

                    if (
                        heading_occurrences
                        == 1
                        and
                        20
                        <= len(
                            text
                        )
                        <= 20000
                    ):

                        best = (
                            parent
                        )

                    if (
                        heading_occurrences
                        > 1
                        or
                        len(
                            text
                        )
                        > 20000
                    ):

                        break

                    current = (
                        parent
                    )

                except Exception:

                    break

            if best is not None:

                return best

    return None


def get_section_text(
    page,
    section_name,
):

    section = (
        find_profile_section(
            page,
            section_name,
        )
    )

    if section is None:

        return None

    try:

        text = (
            section.inner_text()
        )

    except Exception:

        return None

    lines = (
        clean_lines(
            text
        )
    )

    if not lines:

        return None

    target = (
        section_name
        .strip()
        .lower()
    )

    cleaned = []
    heading_removed = False

    for line in lines:

        if (
            not heading_removed
            and
            normalize_text(
                line
            )
            .lower()
            == target
        ):

            heading_removed = (
                True
            )

            continue

        cleaned.append(
            line
        )

    if not cleaned:

        return None

    return (
        "\n".join(
            cleaned
        )[:18000]
    )


# ======================================================
# SECTION CHUNKS
# ======================================================

def build_section_chunks(
    section_text,
    max_chunks=15,
):

    lines = (
        clean_lines(
            section_text
        )
    )

    if not lines:

        return []

    ignored = {
        "show all",
        "show all experiences",
        "show all education",
    }

    chunks = []
    current = []

    for line in lines:

        lower = (
            normalize_text(
                line
            )
            .lower()
        )

        if lower in ignored:

            continue

        current.append(
            line
        )

        if (
            len(
                current
            )
            >= 4
            or
            len(
                " | ".join(
                    current
                )
            )
            >= 500
        ):

            chunks.append(
                " | ".join(
                    current
                )
            )

            current = []

        if (
            len(
                chunks
            )
            >= max_chunks
        ):

            break

    if (
        current
        and
        len(
            chunks
        )
        < max_chunks
    ):

        chunks.append(
            " | ".join(
                current
            )
        )

    return chunks


# ======================================================
# CURRENT ROLE / COMPANY
# ======================================================

def extract_current_role_company(
    experience_text,
):

    lines = (
        unique_preserve_order(
            clean_lines(
                experience_text
            )
        )
    )

    if not lines:

        return (
            None,
            None,
        )

    useful = []

    for line in lines:

        lower = (
            normalize_text(
                line
            )
            .lower()
        )

        if lower in {
            "experience",
            "show all experiences",
        }:

            continue

        if re.search(
            r"\b(19|20)\d{2}\b",
            lower,
        ):

            continue

        if re.search(
            r"\b\d+\s+"
            r"(yr|yrs|year|years|mo|mos|month|months)\b",
            lower,
        ):

            continue

        if " · " in line:

            first_part = (
                line
                .split(
                    " · ",
                    1,
                )[0]
                .strip()
            )

            if first_part:

                useful.append(
                    first_part
                )

        else:

            useful.append(
                line
            )

        if (
            len(
                useful
            )
            >= 8
        ):

            break

    if not useful:

        return (
            None,
            None,
        )

    current_role = (
        useful[0]
    )

    current_company = None

    if (
        len(
            useful
        )
        >= 2
    ):

        current_company = (
            useful[1]
        )

    return (
        current_role,
        current_company,
    )


def extract_current_company_url(
    page,
):

    section = (
        find_profile_section(
            page,
            "Experience",
        )
    )

    if section is None:

        return None

    try:

        links = (
            section.locator(
                "a[href*='/company/']"
            )
        )

        count = min(
            links.count(),
            20,
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
                )

                if href:

                    return (
                        clean_url(
                            href
                        )
                    )

            except Exception:

                continue

    except Exception:

        pass

    return None


# ======================================================
# FALLBACK FROM OLD IDENTITY DATA
# ======================================================

def apply_existing_identity_fallback(
    candidate,
    profile_data,
):

    identity = (
        candidate.get(
            "linkedin_identity"
        )
        or {}
    )

    old_profile = (
        candidate.get(
            "linkedin_profile_data"
        )
        or {}
    )

    fallback_sources = [
        identity,
        old_profile,
    ]

    # IMPORTANT:
    #
    # profile_photo_url is intentionally NOT
    # included here.
    #
    # The previous v3 run may have stored the
    # logged-in user's own avatar.
    #
    # We do not trust an old photo during this
    # migration.

    for field in [
        "name",
        "headline",
        "location",
        "current_role",
        "current_company",
        "current_company_url",
        "about",
        "experience_text",
        "education_text",
        "top_card_preview",
    ]:

        if profile_data.get(
            field
        ):

            continue

        for source in fallback_sources:

            value = (
                source.get(
                    field
                )
            )

            if value:

                profile_data[
                    field
                ] = value

                break

    if (
        not profile_data.get(
            "headline"
        )
        and
        candidate.get(
            "headline"
        )
    ):

        profile_data[
            "headline"
        ] = candidate.get(
            "headline"
        )

    return profile_data


# ======================================================
# EXTRACT COMPLETE PROFILE
# ======================================================

def extract_profile_data(
    page,
    candidate,
):

    fallback_name = (
        candidate.get(
            "name"
        )
    )

    name = (
        get_profile_name(
            page,
            fallback=fallback_name,
        )
    )

    top_card_preview = (
        get_top_card_preview(
            page
        )
    )

    (
        headline,
        location,
    ) = (
        extract_headline_location(
            name,
            top_card_preview,
        )
    )

    profile_photo_url = (
        extract_profile_photo_url(
            page,
            name,
        )
    )

    about = (
        get_section_text(
            page,
            "About",
        )
    )

    experience_text = (
        get_section_text(
            page,
            "Experience",
        )
    )

    education_text = (
        get_section_text(
            page,
            "Education",
        )
    )

    experience_chunks = (
        build_section_chunks(
            experience_text
        )
    )

    education_chunks = (
        build_section_chunks(
            education_text
        )
    )

    (
        current_role,
        current_company,
    ) = (
        extract_current_role_company(
            experience_text
        )
    )

    current_company_url = (
        extract_current_company_url(
            page
        )
    )

    profile_data = {

        "name":
            name,

        "profile_url":
            normalize_profile_url(
                candidate.get(
                    "profile_url"
                )
            ),

        "profile_photo_url":
            profile_photo_url,

        "headline":
            headline,

        "location":
            location,

        "current_role":
            current_role,

        "current_company":
            current_company,

        "current_company_url":
            current_company_url,

        "about":
            about,

        "experience_text":
            experience_text,

        "experience_chunks":
            experience_chunks,

        "education_text":
            education_text,

        "education_chunks":
            education_chunks,

        "top_card_preview":
            top_card_preview,

        "captured_at":
            utc_now(),
    }

    profile_data = (
        apply_existing_identity_fallback(
            candidate,
            profile_data,
        )
    )

    if (
        not profile_data.get(
            "experience_chunks"
        )
        and
        profile_data.get(
            "experience_text"
        )
    ):

        profile_data[
            "experience_chunks"
        ] = (
            build_section_chunks(
                profile_data.get(
                    "experience_text"
                )
            )
        )

    if (
        not profile_data.get(
            "education_chunks"
        )
        and
        profile_data.get(
            "education_text"
        )
    ):

        profile_data[
            "education_chunks"
        ] = (
            build_section_chunks(
                profile_data.get(
                    "education_text"
                )
            )
        )

    return profile_data


# ======================================================
# COMPLETENESS / STATUS
# ======================================================

def determine_enrichment_status(
    profile_data,
):

    if not profile_data:

        return "failed"

    if not profile_data.get(
        "name"
    ):

        return "failed"

    useful_fields = [

        profile_data.get(
            "headline"
        ),

        profile_data.get(
            "location"
        ),

        profile_data.get(
            "current_role"
        ),

        profile_data.get(
            "current_company"
        ),

        profile_data.get(
            "about"
        ),

        profile_data.get(
            "experience_text"
        ),

        profile_data.get(
            "education_text"
        ),
    ]

    available = sum(
        1
        for value
        in useful_fields
        if value
    )

    if available >= 3:

        return "success"

    if available >= 1:

        return "partial"

    return "failed"


# ======================================================
# WHICH CANDIDATES NEED ENRICHMENT?
# ======================================================

def candidate_needs_enrichment(
    candidate,
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
            "profile_enrichment_status"
        )
        or ""
    ).lower()

    version = (
        candidate.get(
            "profile_enrichment_version"
        )
        or ""
    )

    if (
        status == "success"
        and
        version == ENRICHMENT_VERSION
    ):

        return False

    return True


def get_pending_candidate_indexes(
    candidates,
):

    indexes = [
        index
        for index, candidate
        in enumerate(
            candidates
        )
        if candidate_needs_enrichment(
            candidate
        )
    ]

    if (
        PROFILE_ENRICHMENT_LIMIT
        > 0
    ):

        indexes = (
            indexes[
                :PROFILE_ENRICHMENT_LIMIT
            ]
        )

    return indexes


# ======================================================
# UPDATE CANDIDATE
# ======================================================

def update_candidate(
    candidate,
    status,
    profile_data=None,
    error=None,
):

    attempts = (
        candidate.get(
            "profile_enrichment_attempts",
            0,
        )
        or 0
    )

    candidate[
        "profile_enrichment_attempts"
    ] = (
        int(
            attempts
        )
        + 1
    )

    candidate[
        "profile_enrichment_last_attempt_at"
    ] = utc_now()

    candidate[
        "profile_enrichment_status"
    ] = status

    candidate[
        "profile_enrichment_version"
    ] = ENRICHMENT_VERSION

    if error:

        candidate[
            "profile_enrichment_error"
        ] = str(
            error
        )

    else:

        candidate.pop(
            "profile_enrichment_error",
            None,
        )

    if profile_data is not None:

        candidate[
            "linkedin_profile_data"
        ] = profile_data

        candidate[
            "profile_enriched_at"
        ] = utc_now()

        if profile_data.get(
            "name"
        ):

            candidate[
                "name"
            ] = (
                profile_data.get(
                    "name"
                )
            )

        if profile_data.get(
            "headline"
        ):

            candidate[
                "headline"
            ] = (
                profile_data.get(
                    "headline"
                )
            )

        # IMPORTANT:
        #
        # Either save the newly VERIFIED photo
        # or remove the old potentially incorrect
        # v3 photo completely.

        if profile_data.get(
            "profile_photo_url"
        ):

            candidate[
                "profile_photo_url"
            ] = (
                profile_data.get(
                    "profile_photo_url"
                )
            )

        else:

            candidate.pop(
                "profile_photo_url",
                None,
            )


# ======================================================
# ENRICH ONE CANDIDATE
# ======================================================

def enrich_candidate(
    page,
    candidate,
    number,
    total,
):

    candidate_name = (
        candidate.get(
            "name"
        )
        or "Unknown"
    )

    profile_url = (
        normalize_profile_url(
            candidate.get(
                "profile_url"
            )
        )
    )

    print(
        "\n================================"
    )

    print(
        f"PROFILE {number}/{total}"
    )

    print(
        "================================"
    )

    print(
        "Candidate:",
        candidate_name
    )

    print(
        "Profile:",
        profile_url
    )

    if not profile_url:

        update_candidate(
            candidate,
            status="failed",
            error=(
                "Invalid or missing LinkedIn profile URL."
            ),
        )

        print(
            "FAILED: invalid profile URL."
        )

        return

    page.goto(
        profile_url,
        wait_until="domcontentloaded",
        timeout=PAGE_TIMEOUT_MS,
    )

    page.wait_for_timeout(
        PAGE_SETTLE_MS
    )

    if linkedin_access_problem(
        page
    ):

        update_candidate(
            candidate,
            status="failed",
            error=(
                "LinkedIn redirected to login, "
                "checkpoint, or auth wall."
            ),
        )

        print(
            "FAILED: LinkedIn access problem."
        )

        return

    try:

        page.mouse.wheel(
            0,
            1000,
        )

        page.wait_for_timeout(
            1000
        )

        page.mouse.wheel(
            0,
            -1000,
        )

        page.wait_for_timeout(
            500
        )

    except Exception:

        pass

    profile_data = (
        extract_profile_data(
            page,
            candidate,
        )
    )

    status = (
        determine_enrichment_status(
            profile_data
        )
    )

    update_candidate(
        candidate,
        status=status,
        profile_data=profile_data,
    )

    print(
        "Status:",
        status
    )

    print(
        "Name:",
        profile_data.get(
            "name"
        )
    )

    print(
        "Headline:",
        profile_data.get(
            "headline"
        )
    )

    print(
        "Location:",
        profile_data.get(
            "location"
        )
    )

    print(
        "Current role:",
        profile_data.get(
            "current_role"
        )
    )

    print(
        "Current company:",
        profile_data.get(
            "current_company"
        )
    )

    print(
        "Profile photo captured:",
        bool(
            profile_data.get(
                "profile_photo_url"
            )
        )
    )

    print(
        "Profile photo URL:",
        profile_data.get(
            "profile_photo_url"
        )
    )

    print(
        "About captured:",
        bool(
            profile_data.get(
                "about"
            )
        )
    )

    print(
        "Experience captured:",
        bool(
            profile_data.get(
                "experience_text"
            )
        )
    )

    print(
        "Education captured:",
        bool(
            profile_data.get(
                "education_text"
            )
        )
    )


# ======================================================
# MAIN
# ======================================================

def run(
    playwright,
):

    print(
        "\n================================"
    )

    print(
        "LINKEDIN PROFILE ENRICHMENT"
    )

    print(
        "================================"
    )

    candidates = (
        load_candidates()
    )

    print(
        "Total candidate records:",
        len(
            candidates
        )
    )

    pending_indexes = (
        get_pending_candidate_indexes(
            candidates
        )
    )

    print(
        "Profiles needing enrichment:",
        len(
            pending_indexes
        )
    )

    if (
        PROFILE_ENRICHMENT_LIMIT
        > 0
    ):

        print(
            "Run limit:",
            PROFILE_ENRICHMENT_LIMIT
        )

    else:

        print(
            "Run limit: ALL pending profiles"
        )

    if not pending_indexes:

        print(
            "\nNothing to enrich."
        )

        return

    try:

        context = (
            playwright
            .chromium
            .launch_persistent_context(
                str(
                    BROWSER_PROFILE
                ),
                headless=False,
            )
        )

    except Exception as error:

        message = (
            str(
                error
            )
        )

        if (
            "Opening in existing browser session"
            in message
            or
            "profile is already in use"
            in message.lower()
        ):

            print(
                "\nThe Network Scout browser "
                "profile is already open."
            )

            print(
                "Close the other Playwright / "
                "Network Scout Chromium window "
                "and run this file again."
            )

            return

        raise

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

    total_pending = (
        len(
            pending_indexes
        )
    )

    for position, candidate_index in enumerate(
        pending_indexes,
        start=1,
    ):

        candidate = (
            candidates[
                candidate_index
            ]
        )

        try:

            enrich_candidate(
                page,
                candidate,
                position,
                total_pending,
            )

        except PlaywrightTimeoutError as error:

            update_candidate(
                candidate,
                status="failed",
                error=(
                    "Playwright timeout: "
                    + str(
                        error
                    )
                ),
            )

            print(
                "FAILED: page timeout."
            )

        except Exception as error:

            update_candidate(
                candidate,
                status="failed",
                error=str(
                    error
                ),
            )

            print(
                "FAILED:"
            )

            print(
                error
            )

        save_candidates(
            candidates
        )

        status = (
            candidate.get(
                "profile_enrichment_status"
            )
        )

        if status == "success":

            success_count += 1

        elif status == "partial":

            partial_count += 1

        else:

            failed_count += 1

        if (
            position
            < total_pending
        ):

            page.wait_for_timeout(
                BETWEEN_PROFILES_MS
            )

    context.close()

    print(
        "\n================================"
    )

    print(
        "PROFILE ENRICHMENT COMPLETE"
    )

    print(
        "================================"
    )

    print(
        "Attempted:",
        total_pending
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
        "\nCandidates file:"
    )

    print(
        CANDIDATES_FILE
    )


if __name__ == "__main__":

    with sync_playwright() as playwright:

        run(
            playwright
        )