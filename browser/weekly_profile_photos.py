from __future__ import annotations

import argparse
import json
import io
import shutil
import re
import time
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from playwright.sync_api import sync_playwright


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
BROWSER_PROFILE_DIR = PROJECT_ROOT / "browser_data" / "lawyer_profile"

WEEKLY_SHORTLIST_FILE = DATA_DIR / "weekly_shortlist.json"
CANDIDATES_FILE = DATA_DIR / "candidates.json"
TRACKED_CONNECTIONS_FILE = DATA_DIR / "tracked_connections.json"
PROFILE_PHOTOS_DIR = DATA_DIR / "profile_photos"

PAGE_TIMEOUT_MS = 60_000
PAGE_SETTLE_MS = 3_000
BETWEEN_PROFILES_MS = 700


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    tmp.replace(path)


def normalize_profile_url(value: str | None) -> str | None:
    if not value:
        return None

    match = re.search(
        r"https://(?:www\.)?linkedin\.com/in/([^/?#]+)",
        str(value),
        re.IGNORECASE,
    )

    if not match:
        return None

    slug = match.group(1).strip().lower()
    if not slug:
        return None

    return f"https://www.linkedin.com/in/{slug}/"


def profile_slug(profile_url: str) -> str:
    normalized = normalize_profile_url(profile_url)
    if not normalized:
        return "profile"

    match = re.search(r"/in/([^/]+)/", normalized, re.IGNORECASE)
    if not match:
        return "profile"

    slug = match.group(1)
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", slug).strip("-") or "profile"


def is_linkedin_attention_page(page) -> bool:
    try:
        text = (page.locator("body").inner_text(timeout=3_000) or "").lower()
    except Exception:
        return False

    phrases = [
        "sign in to linkedin",
        "let's do a quick security check",
        "verify your identity",
        "security verification",
        "checkpoint",
    ]

    return any(phrase in text for phrase in phrases)


def pick_profile_photo_element(page, expected_name: str | None):
    """
    Pick the actual profile portrait from the current LinkedIn profile.

    We never match by another person's name or by a feed/sidebar card.
    The page URL is verified first, then candidates are scored using:
    - LinkedIn profile-photo CDN patterns
    - square portrait dimensions
    - top-of-page position
    - expected person's name in alt text
    """

    expected_tokens = {
        token.lower()
        for token in re.findall(r"[A-Za-zÀ-ÿ0-9]+", expected_name or "")
        if len(token) >= 2
    }

    try:
        page.evaluate("window.scrollTo(0, 0)")
    except Exception:
        pass

    handles = page.query_selector_all("main img")
    scored: list[tuple[int, Any, str]] = []

    for handle in handles:
        try:
            box = handle.bounding_box()
            if not box:
                continue

            width = float(box.get("width") or 0)
            height = float(box.get("height") or 0)
            y = float(box.get("y") or 0)

            # Skip tiny icons/logos and huge banners.
            if width < 80 or height < 80:
                continue
            if width > 500 or height > 500:
                continue

            src = handle.evaluate("el => el.currentSrc || el.src || ''") or ""
            alt = handle.get_attribute("alt") or ""

            lower_src = src.lower()
            lower_alt = alt.lower()

            if not src:
                continue

            # LinkedIn placeholder/ghost images are not real profile photos.
            if any(
                bad in lower_src
                for bad in [
                    "ghost-person",
                    "ghost_person",
                    "default-avatar",
                    "default_avatar",
                ]
            ):
                continue

            score = 0

            if "media.licdn.com" in lower_src:
                score += 25

            if "profile-displayphoto" in lower_src:
                score += 120
            elif "profile-framedphoto" in lower_src:
                score += 115
            elif "profile" in lower_src and "photo" in lower_src:
                score += 70

            ratio = width / height if height else 0
            if 0.80 <= ratio <= 1.25:
                score += 35

            if 95 <= width <= 260 and 95 <= height <= 260:
                score += 30

            if y < 650:
                score += 30
            elif y < 1000:
                score += 10

            alt_tokens = {
                token.lower()
                for token in re.findall(r"[A-Za-zÀ-ÿ0-9]+", lower_alt)
                if len(token) >= 2
            }

            overlap = expected_tokens & alt_tokens
            if overlap:
                score += 25 + (5 * len(overlap))

            if any(
                bad in lower_src
                for bad in [
                    "company-logo",
                    "organization-logo",
                    "cover-image",
                    "background-image",
                    "feedshare",
                ]
            ):
                score -= 120

            scored.append((score, handle, src))

        except Exception:
            continue

    if not scored:
        return None, None

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_handle, best_src = scored[0]

    # Be conservative rather than saving a random image.
    if best_score < 55:
        return None, None

    return best_handle, best_src




def high_resolution_photo_urls(source_url: str) -> list[str]:
    """Try larger sizes of ONLY the portrait URL already matched to this profile."""
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "media.licdn.com", "media-exp1.licdn.com", "media-exp2.licdn.com"
    }:
        return [source_url]

    urls = []
    # The image ID and path after the size segment stay unchanged. We never
    # substitute another person's picture or search LinkedIn recommendations.
    for size in (800, 400, 200):
        updated = re.sub(
            r"(profile-(?:displayphoto|framedphoto)-shrink_)\d+_\d+",
            rf"\g<1>{size}_{size}",
            source_url,
            count=1,
            flags=re.IGNORECASE,
        )
        if updated not in urls:
            urls.append(updated)
    if source_url not in urls:
        urls.append(source_url)
    return urls


def save_best_available_profile_photo(page, photo_element, source_url: str, local_path: Path) -> tuple[str, str]:
    """Prefer a genuine larger CDN image; fall back to the verified on-page portrait.

    Pillow is optional: without it, we retain the existing screenshot workflow.
    Never overwrite an existing higher-resolution local image with a lower one.
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:
        print("Pillow not installed: using original screenshot method. Run: pip install Pillow")
        photo_element.screenshot(path=str(local_path), type="png", animations="disabled")
        return source_url, "screenshot"

    best_image = None
    best_source = source_url
    best_pixels = 0

    # Check only URLs derived from the photo on the verified exact profile.
    for photo_url in high_resolution_photo_urls(source_url):
        try:
            response = page.context.request.get(photo_url, timeout=12000)
            if not response.ok:
                continue
            payload = response.body()
            if len(payload) > 12_000_000:
                continue
            with Image.open(io.BytesIO(payload)) as opened:
                if opened.format not in {"JPEG", "PNG", "WEBP"}:
                    continue
                width, height = opened.size
                if not (80 <= width <= 2500 and 80 <= height <= 2500):
                    continue
                if not (0.7 <= width / height <= 1.4):
                    continue
                pixels = width * height
                if pixels > best_pixels:
                    best_image = ImageOps.exif_transpose(opened).convert("RGB")
                    best_pixels = pixels
                    best_source = photo_url
        except Exception as exc:
            print("Higher-resolution candidate unavailable:", str(exc)[:140])

    # Compare against any previously saved portrait before replacing it.
    old_pixels = 0
    if local_path.exists():
        try:
            with Image.open(local_path) as old:
                old_pixels = old.width * old.height
        except Exception:
            pass

    # A large screenshot may be an upscaled 150px thumbnail. Pixel count alone
    # must not stop a genuine 400px LinkedIn CDN portrait from replacing it.
    # Only replace an existing photo if we verified a native CDN image at least
    # 400px on each side. Preserve the old file for easy rollback.
    if best_image is not None and (
        not old_pixels or min(best_image.size) >= 400
    ):
        if local_path.exists():
            backup = local_path.with_name(local_path.stem + ".previous.png")
            if not backup.exists():
                shutil.copy2(local_path, backup)
        temp = local_path.with_name(local_path.stem + ".tmp.png")
        best_image.save(temp, format="PNG", optimize=True)
        temp.replace(local_path)
        return best_source, f"native CDN {best_image.width}x{best_image.height}"

    # Do not replace an existing photo with another small thumbnail.
    if old_pixels:
        return source_url, (
            f"kept existing image ({old_pixels} stored pixels); "
            f"largest verified CDN candidate: {best_image.size if best_image is not None else 'none'}"
        )

    photo_element.screenshot(
        path=str(local_path),
        type="png",
        animations="disabled",
    )
    return source_url, "screenshot fallback"


def update_photo_everywhere(
    profile_url: str,
    local_url: str,
    local_path: Path,
    source_url: str | None,
    weekly_shortlist: dict[str, Any],
    candidates: list[dict[str, Any]],
    tracked_connections: list[dict[str, Any]],
) -> None:
    normalized = normalize_profile_url(profile_url)
    if not normalized:
        return

    for record in weekly_shortlist.get("candidates", []):
        if normalize_profile_url(record.get("profile_url")) != normalized:
            continue

        record["profile_photo_url"] = local_url
        record["profile_photo_local_url"] = local_url
        record["profile_photo_local_path"] = str(local_path)
        if source_url:
            record["profile_photo_source_url"] = source_url

    for record in candidates:
        if normalize_profile_url(record.get("profile_url")) != normalized:
            continue

        record["profile_photo_url"] = local_url
        record["profile_photo_local_url"] = local_url
        record["profile_photo_local_path"] = str(local_path)
        if source_url:
            record["profile_photo_source_url"] = source_url

        profile = record.get("linkedin_profile_data")
        if isinstance(profile, dict):
            profile["profile_photo_local_url"] = local_url
            profile["profile_photo_local_path"] = str(local_path)
            if source_url:
                profile["profile_photo_source_url"] = source_url

    for record in tracked_connections:
        if normalize_profile_url(record.get("profile_url")) != normalized:
            continue

        record["profile_photo_url"] = local_url
        record["profile_photo_local_url"] = local_url
        record["profile_photo_local_path"] = str(local_path)
        if source_url:
            record["profile_photo_source_url"] = source_url


def run(headless: bool = False, limit: int = 0) -> None:
    weekly_shortlist = read_json(WEEKLY_SHORTLIST_FILE, {})
    candidates = read_json(CANDIDATES_FILE, [])
    tracked_connections = read_json(TRACKED_CONNECTIONS_FILE, [])

    if not isinstance(weekly_shortlist, dict):
        raise RuntimeError("data/weekly_shortlist.json must contain an object.")

    if not isinstance(candidates, list):
        candidates = []

    if not isinstance(tracked_connections, list):
        tracked_connections = []

    weekly_candidates = [
        item
        for item in weekly_shortlist.get("candidates", [])
        if isinstance(item, dict)
        and normalize_profile_url(item.get("profile_url"))
    ]

    if limit > 0:
        weekly_candidates = weekly_candidates[:limit]

    print("\n================================")
    print("NETWORK SCOUT WEEKLY PHOTOS")
    print("================================")
    print("Weekly candidates:", len(weekly_candidates))
    print("Browser profile:", BROWSER_PROFILE_DIR)

    if not weekly_candidates:
        print("Nothing to process.")
        return

    PROFILE_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

    successful = 0
    failed = 0

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=headless,
            viewport={"width": 1440, "height": 1000},
            device_scale_factor=2,
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        for index, item in enumerate(weekly_candidates, start=1):
            name = str(item.get("name") or "Unknown professional").strip()
            profile_url = normalize_profile_url(item.get("profile_url"))

            print(f"\n{index}/{len(weekly_candidates)}  {name}")
            print("Profile:", profile_url)

            if not profile_url:
                failed += 1
                print("Result: invalid profile URL")
                continue

            try:
                page.goto(
                    profile_url,
                    wait_until="domcontentloaded",
                    timeout=PAGE_TIMEOUT_MS,
                )

                page.wait_for_timeout(PAGE_SETTLE_MS)

                if is_linkedin_attention_page(page):
                    raise RuntimeError(
                        "LinkedIn requires sign-in/security verification in the saved browser profile."
                    )

                expected = normalize_profile_url(profile_url)
                actual = normalize_profile_url(page.url)

                if not actual or actual != expected:
                    raise RuntimeError(
                        f"LinkedIn opened a different profile URL: {page.url}"
                    )

                photo_element, source_url = pick_profile_photo_element(
                    page,
                    name,
                )

                if photo_element is None:
                    raise RuntimeError(
                        "Could not safely identify this profile's portrait."
                    )

                filename = f"{profile_slug(profile_url)}.png"
                local_path = PROFILE_PHOTOS_DIR / filename

                source_url, photo_quality = save_best_available_profile_photo(
                    page, photo_element, source_url, local_path
                )
                print("Photo source quality:", photo_quality)

                local_url = f"/profile-photos/{filename}"

                update_photo_everywhere(
                    profile_url=profile_url,
                    local_url=local_url,
                    local_path=local_path,
                    source_url=source_url,
                    weekly_shortlist=weekly_shortlist,
                    candidates=candidates,
                    tracked_connections=tracked_connections,
                )

                # Save after every successful profile so progress survives interruption.
                write_json(WEEKLY_SHORTLIST_FILE, weekly_shortlist)
                write_json(CANDIDATES_FILE, candidates)
                write_json(TRACKED_CONNECTIONS_FILE, tracked_connections)

                successful += 1
                print("Result: saved", local_url)

            except Exception as error:
                failed += 1
                print("Result: FAILED -", error)

            page.wait_for_timeout(BETWEEN_PROFILES_MS)

        context.close()

    print("\n================================")
    print("WEEKLY PHOTO REFRESH COMPLETE")
    print("================================")
    print("Successful:", successful)
    print("Failed:", failed)
    print("Photos folder:", PROFILE_PHOTOS_DIR)
    print("Weekly shortlist updated:", WEEKLY_SHORTLIST_FILE)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chromium headlessly. Leave off if LinkedIn behaves differently headless.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional number of weekly profiles to process. 0 means all.",
    )
    args = parser.parse_args()

    run(
        headless=args.headless,
        limit=max(0, args.limit),
    )
