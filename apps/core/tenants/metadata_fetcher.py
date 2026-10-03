import re
import json
import logging
import requests
from urllib.parse import urlparse, parse_qs, unquote
from html import unescape

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

def extract_hotel_metadata(raw_url: str, hotel_name: str = "", city: str = "") -> dict:
    """
    Extracts structured hotel information (star rating, description, photos, reviews, amenities)
    from a website URL, Google Maps link, or OTA link.
    """
    if not raw_url:
        return {"success": False, "error": "No URL provided"}

    url = raw_url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    result = {
        "success": True,
        "source": "website",
        "url": url,
        "name": hotel_name or "",
        "star_category": "4",
        "star_rating_num": 4,
        "rating": 4.5,
        "review_count": 0,
        "description": "",
        "tagline": "",
        "phone": "",
        "email": "",
        "address": "",
        "city": city or "",
        "state": "",
        "country": "India",
        "postal_code": "",
        "hero_image": "",
        "photos": [],
        "amenities": [],
        "reviews": [],
    }

    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

        resp = session.get(url, timeout=10, allow_redirects=True)
        final_url = resp.url
        html_content = resp.text

        is_google = "google.com/maps" in final_url or "maps.app.goo.gl" in final_url or "goo.gl/maps" in final_url

        if is_google:
            result["source"] = "google_maps"
            _parse_google_maps_html(html_content, final_url, result)
        else:
            _parse_website_html(html_content, final_url, result)

    except Exception as e:
        logger.warning(f"Error fetching metadata from {url}: {e}")
        result["fetch_warning"] = str(e)
        # Still return partial fallback if name/city were provided
        if not result["description"] and hotel_name:
            result["description"] = f"Experience exceptional hospitality and comfort at {hotel_name}, located in {city or 'a prime destination'}."

    # Final cleanup & normalization
    if not result["name"] and hotel_name:
        result["name"] = hotel_name
    if not result["city"] and city:
        result["city"] = city

    # Normalize star_category to string 1-5
    try:
        s_val = int(round(float(result["star_rating_num"] or 4)))
        result["star_category"] = str(max(1, min(5, s_val)))
    except Exception:
        result["star_category"] = "4"

    return result


def _parse_website_html(html: str, url: str, result: dict):
    # 1. Parse JSON-LD Schema.org blocks
    json_ld_matches = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL | re.IGNORECASE
    )

    found_schema = False
    for block in json_ld_matches:
        try:
            clean_block = block.strip()
            data = json.loads(clean_block)
            if _extract_from_json_ld(data, result):
                found_schema = True
                result["source"] = "schema_json_ld"
                break
        except Exception:
            continue

    # 2. Extract OpenGraph & Meta tags
    og_title = _get_meta_tag(html, "og:title") or _get_title(html)
    og_desc = _get_meta_tag(html, "og:description") or _get_meta_tag(html, "description")
    og_image = _get_meta_tag(html, "og:image") or _get_meta_tag(html, "twitter:image")

    if og_title and not result["name"]:
        clean_title = re.sub(r'[\-|\|•].*', '', og_title).strip()
        result["name"] = clean_title or og_title

    if og_desc and not result["description"]:
        result["description"] = unescape(og_desc.strip())

    if og_image:
        if not og_image.startswith("http"):
            from urllib.parse import urljoin
            og_image = urljoin(url, og_image)
        if not result["hero_image"]:
            result["hero_image"] = og_image
        if og_image not in result["photos"]:
            result["photos"].append(og_image)

    # 3. Detect Star Rating from Text if not found in Schema
    if not found_schema or result["star_rating_num"] == 4:
        star_match = re.search(r'(\d)\s*[- ]*(?:star|Star|STAR|\★)', html)
        if star_match:
            try:
                num = int(star_match.group(1))
                if 1 <= num <= 5:
                    result["star_rating_num"] = num
            except Exception:
                pass

    # 4. Detect Amenities from HTML content
    _detect_amenities(html, result)

    # 5. Extract additional gallery photos
    _extract_gallery_images(html, url, result)


def _extract_from_json_ld(data, result: dict) -> bool:
    if isinstance(data, list):
        for item in data:
            if _extract_from_json_ld(item, result):
                return True
        return False

    if not isinstance(data, dict):
        return False

    # Check for @graph
    if "@graph" in data and isinstance(data["@graph"], list):
        for item in data["@graph"]:
            if _extract_from_json_ld(item, result):
                return True

    item_type = str(data.get("@type", "")).lower()
    is_hotel = any(t in item_type for t in ["hotel", "lodging", "resort", "motel", "hostel", "bedandbreakfast", "place"])

    if not is_hotel and not data.get("starRating") and not data.get("aggregateRating"):
        return False

    if data.get("name") and not result["name"]:
        result["name"] = data["name"]

    if data.get("description") and not result["description"]:
        result["description"] = unescape(str(data["description"]))

    # Star Rating
    star_rating = data.get("starRating")
    if isinstance(star_rating, dict):
        val = star_rating.get("ratingValue") or star_rating.get("rating")
        if val:
            try:
                result["star_rating_num"] = float(val)
            except Exception:
                pass
    elif star_rating:
        try:
            result["star_rating_num"] = float(star_rating)
        except Exception:
            pass

    # Aggregate Guest Rating
    agg_rating = data.get("aggregateRating")
    if isinstance(agg_rating, dict):
        r_val = agg_rating.get("ratingValue")
        r_count = agg_rating.get("reviewCount") or agg_rating.get("ratingCount")
        if r_val:
            try:
                result["rating"] = float(r_val)
            except Exception:
                pass
        if r_count:
            try:
                result["review_count"] = int(r_count)
            except Exception:
                pass

    # Contact & Address
    if data.get("telephone"):
        result["phone"] = str(data["telephone"])
    if data.get("email"):
        result["email"] = str(data["email"])

    addr = data.get("address")
    if isinstance(addr, dict):
        result["address"] = addr.get("streetAddress") or ""
        result["city"] = addr.get("addressLocality") or result["city"]
        result["state"] = addr.get("addressRegion") or result["state"]
        result["postal_code"] = addr.get("postalCode") or ""
        result["country"] = addr.get("addressCountry") or result["country"]
    elif isinstance(addr, str):
        result["address"] = addr

    # Images
    images = data.get("image") or data.get("photo") or []
    if isinstance(images, str):
        images = [images]
    if isinstance(images, list):
        for img in images:
            img_url = img if isinstance(img, str) else img.get("url") if isinstance(img, dict) else None
            if img_url and img_url not in result["photos"]:
                result["photos"].append(img_url)
        if result["photos"] and not result["hero_image"]:
            result["hero_image"] = result["photos"][0]

    # Amenities
    amenities = data.get("amenityFeature") or data.get("amenities") or []
    if isinstance(amenities, list):
        for a in amenities:
            a_name = a.get("name") if isinstance(a, dict) else str(a)
            if a_name and a_name not in result["amenities"]:
                result["amenities"].append(a_name)

    return True


def _parse_google_maps_html(html: str, url: str, result: dict):
    # Try extracting rating e.g. 4.6 stars
    rating_match = re.search(r'([1-5]\.[0-9])\s*stars?', html, re.IGNORECASE)
    if rating_match:
        try:
            result["rating"] = float(rating_match.group(1))
            result["star_rating_num"] = int(round(result["rating"]))
        except Exception:
            pass

    # Extract reviews count
    reviews_match = re.search(r'([0-9,]+)\s*reviews?', html, re.IGNORECASE)
    if reviews_match:
        try:
            count_str = reviews_match.group(1).replace(",", "")
            result["review_count"] = int(count_str)
        except Exception:
            pass

    # Meta tags from Google Maps
    og_title = _get_meta_tag(html, "og:title")
    if og_title:
        clean_name = og_title.split(" - Google")[0].split(" · ")[0].strip()
        if clean_name and not result["name"]:
            result["name"] = clean_name

    og_desc = _get_meta_tag(html, "og:description")
    if og_desc and not result["description"]:
        result["description"] = og_desc

    og_image = _get_meta_tag(html, "og:image")
    if og_image:
        result["hero_image"] = og_image
        if og_image not in result["photos"]:
            result["photos"].append(og_image)


def _detect_amenities(html: str, result: dict):
    keywords = {
        "Free High-Speed WiFi": ["wifi", "wi-fi", "internet"],
        "Swimming Pool": ["swimming pool", "infinity pool", "outdoor pool"],
        "Spa & Wellness Center": ["spa", "wellness", "massage", "sauna"],
        "Fine Dining Restaurant": ["restaurant", "dining", "cuisine", "buffet", "cafe"],
        "24/7 Room Service": ["room service", "24-hour room service"],
        "Fitness Center / Gym": ["gym", "fitness center", "workout"],
        "Free Valet Parking": ["parking", "valet parking"],
        "Air Conditioning": ["air conditioning", "ac rooms", "climate control"],
        "Airport Shuttle": ["airport shuttle", "airport transfer"],
        "Bar & Cocktail Lounge": ["bar", "cocktail lounge", "pub"],
        "Banquet & Conference Halls": ["banquet", "conference hall", "meeting room", "event venue"],
    }
    lower_html = html.lower()
    for standard_name, terms in keywords.items():
        if any(term in lower_html for term in terms):
            if standard_name not in result["amenities"]:
                result["amenities"].append(standard_name)


def _extract_gallery_images(html: str, base_url: str, result: dict):
    from urllib.parse import urljoin
    img_matches = re.findall(r'<img[^>]+src=["\']([^"\']+\.(?:jpg|jpeg|png|webp))["\']', html, re.IGNORECASE)
    for img_src in img_matches:
        if len(result["photos"]) >= 8:
            break
        if any(skip in img_src.lower() for skip in ["icon", "logo", "badge", "avatar", "tracking", "pixel", "ad"]):
            continue
        full_url = urljoin(base_url, img_src)
        if full_url not in result["photos"]:
            result["photos"].append(full_url)
    if not result["hero_image"] and result["photos"]:
        result["hero_image"] = result["photos"][0]


def _get_meta_tag(html: str, prop_or_name: str) -> str:
    patterns = [
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop_or_name)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(prop_or_name)}["\']'
    ]
    for pattern in patterns:
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def _get_title(html: str) -> str:
    m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    if m:
        return unescape(m.group(1).strip())
    return ""
