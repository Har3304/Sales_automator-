import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 12
MAX_CHARS = 4000

NOISE_TAGS = [
    "script", "style", "noscript", "header", "footer", "nav",
    "aside", "form", "iframe", "svg", "img", "button",
    "cookie", "advertisement",
]

BOILERPLATE_PATTERNS = re.compile(
    r"(cookie|gdpr|banner|popup|modal|nav|menu|sidebar|footer|header|"
    r"breadcrumb|newsletter|subscribe|social|share|ad-|ads-|promo)",
    re.I,
)


def _looks_like_url(text):
    return text.startswith("http://") or text.startswith("https://") or "." in text.split()[0]


def _normalize_url(text):
    text = text.strip()
    if not text.startswith("http"):
        text = "https://" + text
    return text


def _guess_url(company_name):
    slug = re.sub(r"[^a-z0-9]+", "", company_name.lower().split("\u2013")[0].split("-")[0].strip())
    if slug:
        return "https://www." + slug + ".com"
    return None


def _fetch(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code == 200 and "text/html" in resp.headers.get("Content-Type", ""):
            return resp.text
    except Exception:
        pass
    return None


def _is_boilerplate(tag):
    if tag is None or not hasattr(tag, "attrs") or tag.attrs is None:
        return False
    for attr in ("class", "id", "aria-label"):
        val = tag.get(attr, "")
        if isinstance(val, list):
            val = " ".join(val)
        if val and BOILERPLATE_PATTERNS.search(val):
            return True
    return False


def _clean(html):
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(NOISE_TAGS):
        tag.decompose()

    for tag in soup.find_all(True):
        if _is_boilerplate(tag):
            tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    lines = [l.strip() for l in text.splitlines() if l.strip() and len(l.strip()) > 20]
    return "\n".join(lines)[:MAX_CHARS]


def _scrape_url(url):
    html = _fetch(url)
    if not html:
        return {"url": url, "content": "", "success": False}

    content = _clean(html)

    if len(content) < 300:
        about_html = _fetch(urljoin(url, "/about"))
        if about_html:
            content = (content + "\n" + _clean(about_html))[:MAX_CHARS]

    return {"url": url, "content": content, "success": bool(content)}


def scrape_lead(lead):
    lead = lead.strip()

    if _looks_like_url(lead):
        result = _scrape_url(_normalize_url(lead))
        result["source_type"] = "url"
        result["original_input"] = lead
        return result

    guessed = _guess_url(lead)
    if guessed:
        result = _scrape_url(guessed)
        if result["success"]:
            result["source_type"] = "name_guessed_url"
            result["original_input"] = lead
            return result

    return {
        "url": guessed or "",
        "content": "",
        "success": False,
        "source_type": "name_only",
        "original_input": lead,
    }
