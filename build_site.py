#!/usr/bin/env python3
"""
Génère le site vitrine Learning Trip à partir de data/destinations.json :

  - index.html, sejours/<slug>.html, mentions-legales.html, 404.html
                                  (depuis templates/ ; CSS minifié inliné)
  - assets/opt/…                  variantes AVIF / WebP / JPEG|PNG des images,
                                  aux largeurs utiles (cf. IMAGE_WIDTHS)
  - assets/js/site.min.js         assets/js/site.js minifié
  - assets/js/destinations.js     données cartes + simulateur, côté client
  - site.webmanifest, sitemap.xml, robots.txt
  - assets/brochure/brochure.html

Chaque URL d'asset reçoit une empreinte (?v=…) : l'hébergeur peut la mettre
en cache un an sans risque de servir une version périmée (cf. netlify.toml).

Usage :  python3 build_site.py      (Pillow requis : pip install -r requirements.txt)
"""

import hashlib
import html
import json
import re
from datetime import date
from pathlib import Path

try:
    from PIL import Image, ImageOps, features
except ImportError:  # le site se construit quand même, sans variantes d'images
    Image = None


def _avif_supported() -> bool:
    try:
        return Image is not None and features.check("avif")
    except (ValueError, AttributeError):  # Pillow < 11.2 : pas d'AVIF
        return False


# Formats modernes proposés au navigateur, du plus léger au plus compatible
MODERN = ("avif", "webp") if _avif_supported() else ("webp",)

ROOT = Path(__file__).parent
DATA = json.loads((ROOT / "data" / "destinations.json").read_text())
SITE = DATA["site"]
DESTS = DATA["destinations"]
CREDITS_FILE = ROOT / "assets" / "img" / "destinations" / "credits.json"
SITEMAP_STATE = ROOT / "data" / "sitemap-state.json"
OPT_DIR = ROOT / "assets" / "opt"

# Largeurs générées par famille d'images (px). Une variante n'est jamais plus
# large que l'original. Ajouter ici toute nouvelle famille d'images.
IMAGE_WIDTHS = {
    "assets/img/destinations/": (240, 480, 800, 1200, 1800),
    "assets/img/sejours/": (480, 800, 1100, 1600),
    "assets/img/team/": (128, 256, 384),
    "assets/img/referents/": (128, 256, 384),
    "assets/img/logo.png": (80, 160, 240),
    "assets/logo/": (160, 320),
    "assets/brochure/cover.jpg": (300, 500, 750),
}
ENCODERS = {
    "avif": ("AVIF", {"quality": 45, "speed": 6}),
    "webp": ("WEBP", {"quality": 70, "method": 6}),
    "jpg": ("JPEG", {"quality": 78, "optimize": True, "progressive": True}),
    "png": ("PNG", {"optimize": True}),
}
# Fond des vignettes « brochure » (CSS background) : largeur servie
BG_WIDTH = 800
# Polices préchargées : celles qui s'affichent au-dessus de la ligne de flottaison
PRELOAD_FONTS = ("poppins-700-latin.woff2", "poppins-600-latin.woff2", "inter-latin.woff2")

TODAY = date.today().isoformat()
WARNINGS = []


def render(template: str, mapping: dict) -> str:
    out = template
    for key, value in mapping.items():
        out = out.replace("{{" + key + "}}", str(value))
    return out


def attr(text: str) -> str:
    """Texte → valeur d'attribut HTML (guillemets doubles)."""
    return html.escape(text, quote=False).replace('"', "&quot;")


# ---------------------------------------------------------------------------
#  Empreintes d'assets (cache-busting)
# ---------------------------------------------------------------------------

_HASHES = {}


def file_hash(path: Path) -> str:
    key = str(path)
    if key not in _HASHES:
        _HASHES[key] = hashlib.sha1(path.read_bytes()).hexdigest()[:10]
    return _HASHES[key]


def v(rel: str) -> str:
    """'assets/x.png' → 'assets/x.png?v=<empreinte>' (si le fichier existe)."""
    path = ROOT / rel
    return f"{rel}?v={file_hash(path)}" if path.is_file() else rel


# ---------------------------------------------------------------------------
#  Images : variantes responsives AVIF / WebP / JPEG|PNG
# ---------------------------------------------------------------------------

_VARIANTS = {}


def image_widths(rel: str, orig_w: int):
    for prefix, widths in IMAGE_WIDTHS.items():
        if rel.startswith(prefix):
            out = [w for w in widths if w < orig_w]
            if max(widths) >= orig_w:
                out.append(orig_w)
            return out
    return None


_USED_OPT = set()  # variantes utilisées par ce build (les autres sont supprimées)
# Empreinte (image source + réglages) de chaque famille de variantes : on ne
# réencode que si la source ou les réglages changent (indépendant des dates
# de fichiers, qui ne veulent rien dire après un git clone).
MANIFEST = OPT_DIR / "sources.json"
_MANIFEST = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
_MANIFEST_NEW = {}


def recipe_hash(src: Path, widths) -> str:
    h = hashlib.sha1(src.read_bytes())
    h.update(json.dumps([widths, MODERN, ENCODERS], sort_keys=True).encode())
    return h.hexdigest()[:16]


def variant_rel(rel: str, width: int, ext: str) -> str:
    """Chemin d'une variante. Dans le format d'origine et à la largeur d'origine,
    c'est le fichier source lui-même (inutile d'en stocker une copie)."""
    info = _VARIANTS.get(rel)
    if info and ext == info["fallback"] and width == info["w"]:
        return rel
    stem = rel[len("assets/"):].rsplit(".", 1)[0]
    return f"assets/opt/{stem}-{width}.{ext}"


def ensure_variants(rel: str):
    """Crée au besoin les variantes d'une image source (chemin relatif à la racine).
    Renvoie {w, h, widths, fallback} ou None si l'image n'est pas concernée."""
    if rel in _VARIANTS:
        return _VARIANTS[rel]
    src = ROOT / rel
    info = None
    if Image is not None and src.is_file() and src.suffix.lower() in (".jpg", ".jpeg", ".png"):
        with Image.open(src) as probe:
            orig_w, orig_h = probe.size
        widths = image_widths(rel, orig_w)
        if widths:
            fallback = "png" if src.suffix.lower() == ".png" else "jpg"
            info = {"w": orig_w, "h": orig_h, "widths": widths, "fallback": fallback}
            _VARIANTS[rel] = info
            todo = [(ROOT / variant_rel(rel, w, ext), w, ext)
                    for w in widths for ext in (*MODERN, fallback)
                    if variant_rel(rel, w, ext) != rel]
            key = recipe_hash(src, widths)
            fresh = _MANIFEST.get(rel) == key and all(out.exists() for out, _, _ in todo)
            if not fresh:
                img = ImageOps.exif_transpose(Image.open(src))
                img.load()
                for out, width, ext in todo:
                    out.parent.mkdir(parents=True, exist_ok=True)
                    save_variant(img, width, ext, out)
            _USED_OPT.update(out for out, _, _ in todo)
            _MANIFEST_NEW[rel] = key
    _VARIANTS[rel] = info
    return info


def clean_opt() -> int:
    """Enregistre les empreintes et supprime les variantes orphelines
    (image source retirée ou renommée)."""
    OPT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(dict(sorted(_MANIFEST_NEW.items())), indent=1) + "\n")
    removed = 0
    for path in OPT_DIR.rglob("*"):
        if path.is_file() and path != MANIFEST and path not in _USED_OPT:
            path.unlink()
            removed += 1
    for folder in sorted((p for p in OPT_DIR.rglob("*") if p.is_dir()), reverse=True):
        if not any(folder.iterdir()):
            folder.rmdir()
    return removed


def save_variant(img, width: int, ext: str, out: Path) -> None:
    fmt, opts = ENCODERS[ext]
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    im = img.convert("RGBA" if has_alpha and ext != "jpg" else "RGB")
    if width != im.width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    opts = dict(opts)
    if img.info.get("icc_profile"):
        opts["icc_profile"] = img.info["icc_profile"]
    im.save(out, fmt, **opts)


def srcset(rel: str, info: dict, ext: str, prefix: str) -> str:
    return ", ".join(f"{prefix}{v(variant_rel(rel, w, ext))} {w}w" for w in info["widths"])


def fallback_width(info: dict) -> int:
    fitting = [w for w in info["widths"] if w <= 800]
    return max(fitting) if fitting else min(info["widths"])


def resolve(url: str, page_dir: str):
    """URL d'asset telle qu'écrite dans une page → chemin relatif à la racine."""
    if re.match(r"^[a-z]+:|^//", url) or "?" in url or "#" in url:
        return None
    if url.startswith("/"):
        rel = url[1:]
    else:
        rel = (Path(page_dir) / url).as_posix()
        parts = []
        for part in rel.split("/"):
            if part == "..":
                if parts:
                    parts.pop()
            elif part not in ("", "."):
                parts.append(part)
        rel = "/".join(parts)
    return rel if rel.startswith("assets/") else None


ATTR_RE = re.compile(r'([\w:-]+)(?:="([^"]*)")?')


def parse_attrs(tag: str) -> dict:
    inner = re.sub(r"^<img\s*|\s*/?>$", "", tag)
    return {m.group(1): m.group(2) for m in ATTR_RE.finditer(inner)}


def format_attrs(attrs: dict) -> str:
    return "".join(f" {k}" if val is None else f' {k}="{val}"' for k, val in attrs.items())


def picture(tag: str, page_dir: str, prefix: str) -> str:
    """<img src="…jpg" sizes="…"> → <picture> AVIF + WebP + repli, avec
    srcset, dimensions intrinsèques (anti-CLS) et décodage asynchrone."""
    attrs = parse_attrs(tag)
    rel = resolve(attrs.get("src", ""), page_dir)
    info = ensure_variants(rel) if rel else None
    if not info:
        return tag
    sizes = attrs.pop("sizes", None)
    if not sizes:
        sizes = "100vw"
        WARNINGS.append(f"{page_dir or '.'}: <img src={attrs['src']}> sans attribut sizes")
    out = {}
    for key, val in attrs.items():
        if key == "src":
            fb = info["fallback"]
            out["src"] = prefix + v(variant_rel(rel, fallback_width(info), fb))
            out["srcset"] = srcset(rel, info, fb, prefix)
            out["sizes"] = sizes
        else:
            out[key] = val
    out.setdefault("width", str(info["w"]))
    out.setdefault("height", str(info["h"]))
    if out.get("loading") == "lazy":
        out.setdefault("decoding", "async")
    sources = "".join(
        f'<source type="image/{ext}" srcset="{srcset(rel, info, ext, prefix)}" sizes="{sizes}">'
        for ext in MODERN
    )
    return f"<picture>{sources}<img{format_attrs(out)}></picture>"


def background(match, page_dir: str, prefix: str) -> str:
    """style="background-image:url(x.jpg)" → image-set() AVIF / WebP / JPEG."""
    url = match.group(1)
    rel = resolve(url, page_dir)
    info = ensure_variants(rel) if rel else None
    if not info:
        return match.group(0)
    width = max([w for w in info["widths"] if w <= BG_WIDTH] or [min(info["widths"])])
    fb = info["fallback"]
    cands = ",".join(
        f"url({prefix}{v(variant_rel(rel, width, ext))}) type('image/{'jpeg' if ext == 'jpg' else ext}')"
        for ext in (*MODERN, fb)
    )
    return (f"background-image:url({prefix}{v(variant_rel(rel, width, fb))});"
            f"background-image:image-set({cands})")


def version_urls(page: str, page_dir: str, prefix: str) -> str:
    """Ajoute l'empreinte ?v= aux assets locaux (src, href, poster) restants."""
    def repl(m):
        rel = resolve(m.group(2), page_dir)
        if rel and (ROOT / rel).is_file():
            return f'{m.group(1)}="{prefix}{v(rel)}"'
        return m.group(0)
    return re.sub(r'\b(src|href|poster)="([^"]+)"', repl, page)


# ---------------------------------------------------------------------------
#  CSS / JS
# ---------------------------------------------------------------------------

def minify_css(css: str) -> str:
    out, i, n = [], 0, len(css)
    while i < n:
        c = css[i]
        if css.startswith("/*", i):
            end = css.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        if c in "\"'":
            end = i + 1
            while end < n and css[end] != c:
                end += 2 if css[end] == "\\" else 1
            out.append(css[i:end + 1])
            i = end + 1
            continue
        if c.isspace():
            while i < n and css[i].isspace():
                i += 1
            prev = out[-1][-1:] if out else ""
            nxt = css[i:i + 1]
            if prev and prev not in "{};,:>" and nxt not in "{};,>)":
                out.append(" ")
            continue
        out.append(c)
        i += 1
    return "".join(out).replace(";}", "}")


JS_KEYWORDS_BEFORE_REGEX = ("return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "throw")


def minify_js(src: str) -> str:
    """Minification prudente : retire commentaires et indentation, garde les
    retours à la ligne (pas de risque avec l'insertion automatique de ;)."""
    out, i, n = [], 0, len(src)
    last = ""  # dernier caractère significatif émis
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            end = src.find("\n", i)
            i = n if end == -1 else end
            continue
        if src.startswith("/*", i):
            end = src.find("*/", i + 2)
            i = n if end == -1 else end + 2
            out.append(" ")
            continue
        if c in "'\"`":
            end = i + 1
            while end < n and src[end] != c:
                end += 2 if src[end] == "\\" else 1
            out.append(src[i:end + 1])
            i, last = end + 1, c
            continue
        if c == "/":
            tail = "".join(out[-12:]).rstrip()
            word = re.search(r"([A-Za-z_$]+)$", tail)
            if last == "" or last in "(,=:[!&|?{};+-*%<>~^" or (word and word.group(1) in JS_KEYWORDS_BEFORE_REGEX):
                end, in_class = i + 1, False
                while end < n:
                    ch = src[end]
                    if ch == "\\":
                        end += 2
                        continue
                    if ch == "[":
                        in_class = True
                    elif ch == "]":
                        in_class = False
                    elif ch == "/" and not in_class:
                        break
                    end += 1
                end += 1
                while end < n and src[end].isalpha():
                    end += 1
                out.append(src[i:end])
                i, last = end, "/"
                continue
        if c in " \t\r\n":
            run_end = i
            while run_end < n and src[run_end] in " \t\r\n":
                run_end += 1
            out.append("\n" if "\n" in src[i:run_end] else " ")
            i = run_end
            continue
        out.append(c)
        last = c
        i += 1
    lines = [line.strip() for line in "".join(out).split("\n")]
    return "\n".join(line for line in lines if line) + "\n"


def build_js() -> None:
    src = (ROOT / "assets" / "js" / "site.js").read_text()
    out = ROOT / "assets" / "js" / "site.min.js"
    out.write_text("/* Généré par build_site.py depuis site.js — ne pas éditer */\n" + minify_js(src))
    print(f"✅ {out.relative_to(ROOT)}  ({len(src) // 1024} Ko → {out.stat().st_size // 1024} Ko)")


_CSS = None
_JS_CLASSES = None


def split_blocks(css: str):
    """CSS minifié → blocs de premier niveau [(prélude, contenu)]."""
    blocks, i, n = [], 0, len(css)
    while i < n:
        start = css.find("{", i)
        if start == -1:
            break
        depth, k = 1, start + 1
        while k < n and depth:
            ch = css[k]
            if ch in "\"'":
                k += 1
                while k < n and css[k] != ch:
                    k += 2 if css[k] == "\\" else 1
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            k += 1
        blocks.append((css[i:start], css[start + 1:k - 1]))
        i = k
    return blocks


def prune_css(css: str, used: set) -> str:
    """Retire les règles dont une classe n'apparaît pas dans la page (ni dans
    le JS) : chaque page n'embarque que le CSS qu'elle utilise."""
    out = []
    for prelude, body in split_blocks(css):
        if prelude.startswith(("@media", "@supports")):
            inner = prune_css(body, used)
            if inner:
                out.append(f"{prelude}{{{inner}}}")
        elif prelude.startswith("@"):
            out.append(f"{prelude}{{{body}}}")
        else:
            kept = [s for s in prelude.split(",")
                    if all(c in used for c in re.findall(r"\.(-?[_a-zA-Z][\w-]*)", s))]
            if kept:
                out.append(f"{','.join(kept)}{{{body}}}")
    return "".join(out)


def classes_used(page: str) -> set:
    """Classes présentes dans la page + toutes celles que le JS peut ajouter
    (tout mot figurant dans une chaîne de site.js ou d'un script inline)."""
    global _JS_CLASSES
    if _JS_CLASSES is None:
        js = (ROOT / "assets" / "js" / "site.js").read_text()
        _JS_CLASSES = {w for s in re.findall(r'"([^"\n]*)"|\'([^\'\n]*)\'', js)
                       for part in s for w in re.findall(r"[\w-]+", part)}
    used = set(_JS_CLASSES)
    for value in re.findall(r'class="([^"]*)"', page):
        used.update(value.split())
    for script in re.findall(r"<script>(.*?)</script>", page, re.S):
        used.update(re.findall(r"[\w-]+", script))
    return used


def page_css(prefix: str, page: str) -> str:
    """fonts.css + site.css minifiés, réduits aux règles utiles à la page,
    URLs de polices réécrites pour la page."""
    global _CSS
    if _CSS is None:
        _CSS = minify_css((ROOT / "assets" / "css" / "fonts.css").read_text() + "\n"
                          + (ROOT / "assets" / "css" / "site.css").read_text())
    css = prune_css(_CSS, classes_used(page))
    return re.sub(r"url\(\.\./fonts/([^)]+)\)",
                  lambda m: f"url({prefix}{v('assets/fonts/' + m.group(1))})", css)


def head_assets(prefix: str, page: str) -> str:
    preloads = "\n".join(
        f'  <link rel="preload" href="{prefix}{v("assets/fonts/" + f)}" as="font" type="font/woff2" crossorigin>'
        for f in PRELOAD_FONTS
    )
    return f"{preloads}\n  <style>{page_css(prefix, page)}</style>"


def finalize(page: str, page_dir: str, prefix: str) -> str:
    """Post-traitement commun : CSS inliné, images responsives, empreintes."""
    page = page.replace("{{HEAD_ASSETS}}", head_assets(prefix, page))
    page = re.sub(r"<img\b[^>]*>", lambda m: picture(m.group(0), page_dir, prefix), page)
    page = re.sub(r"background-image:url\(([^)]+)\)", lambda m: background(m, page_dir, prefix), page)
    return version_urls(page, page_dir, prefix)


# ---------------------------------------------------------------------------
#  Données structurées (JSON-LD schema.org)
# ---------------------------------------------------------------------------

def jsonld(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f'<script type="application/ld+json">{payload}</script>'


def organisation(full: bool = True) -> dict:
    url = SITE["url"]
    node = {
        "@type": "Organization",
        "@id": f"{url}/#organisation",
        "name": SITE["nom"],
        "url": f"{url}/",
        "logo": {"@type": "ImageObject", "url": f"{url}/assets/img/logo.png", "width": 902, "height": 506},
    }
    if not full:
        return node
    if SITE.get("raison_sociale"):
        node["legalName"] = SITE["raison_sociale"]
    node.update({
        "description": SITE["description"],
        "email": SITE["email"],
        "telephone": SITE["telephone_intl"],
        "areaServed": {"@type": "Country", "name": "France"},
        "contactPoint": {
            "@type": "ContactPoint",
            "contactType": "customer service",
            "email": SITE["email"],
            "telephone": SITE["telephone_intl"],
            "areaServed": "FR",
            "availableLanguage": "French",
        },
    })
    if SITE.get("reseaux_sociaux"):
        node["sameAs"] = SITE["reseaux_sociaux"]
    adresse = SITE.get("adresse") or {}
    if adresse.get("streetAddress") or adresse.get("addressLocality"):
        node["address"] = {"@type": "PostalAddress",
                           **{k: val for k, val in adresse.items() if val and not k.startswith("_")}}
    return node


def strip_tags(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", fragment))).strip()


def index_jsonld(template: str) -> str:
    url = SITE["url"]
    faq = [
        {"@type": "Question", "name": strip_tags(q),
         "acceptedAnswer": {"@type": "Answer", "text": strip_tags(a)}}
        for q, a in re.findall(r'<details class="faq-item"><summary>(.*?)</summary><p>(.*?)</p></details>', template)
    ]
    graph = [
        organisation(),
        {"@type": "WebSite", "@id": f"{url}/#site", "url": f"{url}/", "name": SITE["nom"],
         "inLanguage": "fr-FR", "publisher": {"@id": f"{url}/#organisation"}},
    ]
    if faq:
        graph.append({"@type": "FAQPage", "@id": f"{url}/#faq", "mainEntity": faq})
    return jsonld({"@context": "https://schema.org", "@graph": graph})


def sejour_jsonld(d: dict, page_url: str, image_url: str) -> str:
    url = SITE["url"]
    return jsonld({"@context": "https://schema.org", "@graph": [
        organisation(full=False),
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Accueil", "item": f"{url}/"},
                {"@type": "ListItem", "position": 2, "name": "Destinations", "item": f"{url}/#destinations"},
                {"@type": "ListItem", "position": 3, "name": d["ville"], "item": page_url},
            ],
        },
        {
            "@type": "TouristTrip",
            "@id": f"{page_url}#sejour",
            "name": f"Séjour pédagogique à {d['ville']}",
            "description": d["meta_description"],
            "url": page_url,
            "image": image_url,
            "inLanguage": "fr-FR",
            "touristType": ["Apprentis", "Étudiants"],
            "provider": {"@id": f"{url}/#organisation"},
            "itinerary": {
                "@type": "City",
                "name": d["ville"],
                "containedInPlace": {"@type": "Country", "name": d["pays"]},
                "geo": {"@type": "GeoCoordinates", "latitude": d["lat"], "longitude": d["lng"]},
            },
        },
    ]})


def seo_title(d: dict) -> str:
    """Titre de 50 à 60 caractères si possible (sinon le plus long ≤ 60)."""
    if d.get("seo_title"):
        return d["seo_title"]
    candidates = [
        f"Séjour pédagogique à {d['ville']}, {d['pays']} · Learning Trip",
        f"Séjour pédagogique à {d['ville']} pour CFA · Learning Trip",
        f"Séjour pédagogique à {d['ville']} · Learning Trip",
    ]
    for title in candidates:
        if 50 <= len(title) <= 60:
            return title
    fitting = [t for t in candidates if len(t) <= 60]
    return max(fitting, key=len) if fitting else candidates[-1]


def og_image(rel: str):
    """Image de partage : variante JPEG 1200 px (les réseaux ignorent AVIF)."""
    info = ensure_variants(rel)
    if info and 1200 in info["widths"]:
        return variant_rel(rel, 1200, "jpg"), 1200, round(info["h"] * 1200 / info["w"])
    if info:
        return rel, info["w"], info["h"]
    return rel, 1200, 630


# ---------------------------------------------------------------------------
#  Pages
# ---------------------------------------------------------------------------

CARD_SIZES_HOME = "auto, (min-width: 1164px) 376px, (min-width: 767px) 46vw, 92vw"
CARD_SIZES_OTHERS = "auto, (min-width: 1283px) 378px, (min-width: 831px) 31vw, (min-width: 546px) 46vw, 92vw"


def dest_card(d: dict, prefix: str = "", sizes: str = CARD_SIZES_HOME) -> str:
    return (
        f'      <a class="dest-card reveal" href="{prefix}sejours/{d["slug"]}.html" '
        f'data-themes="{" ".join(d["themes"])}">\n'
        f'        <img class="bg" src="{prefix}assets/img/destinations/{d["slug"]}.jpg" '
        f'alt="{d["ville"]}, {d["pays"]}" loading="lazy" sizes="{sizes}">\n'
        f'        <span class="go">→</span>\n'
        f'        <div class="body"><span class="pays">{d["pays"]}</span>'
        f'<h3>{d["ville"]}</h3><span class="baseline">{d["baseline"]}</span></div>\n'
        f"      </a>"
    )


def referent_block(d: dict) -> str:
    """Carte « référent sur place ». Photo si le fichier existe, sinon monogramme."""
    r = d.get("referent")
    if not r:
        return ""
    photo = r.get("photo", "")
    photo_path = ROOT / "assets" / "img" / "referents" / photo if photo else None
    if photo_path and photo_path.exists():
        avatar = (
            f'<img class="ref-avatar" src="../assets/img/referents/{photo}" '
            f'alt="{r["nom"]}, référent Learning Trip" loading="lazy" sizes="124px">'
        )
    else:
        initials = "".join(w[0] for w in r["nom"].split()[:2]).upper() or "LT"
        avatar = f'<span class="ref-avatar ref-avatar--mono" aria-hidden="true">{initials}</span>'
    return (
        '<section class="section" id="referent">\n'
        '  <div class="container">\n'
        '    <div class="referent reveal">\n'
        f'      {avatar}\n'
        '      <div class="ref-body">\n'
        '        <span class="sticker">Votre référent sur place</span>\n'
        f'        <h2>{r["nom"]}</h2>\n'
        f'        <p class="ref-role">{r["role"]}</p>\n'
        f'        <p class="ref-bio">{r.get("bio", "")}</p>\n'
        '      </div>\n'
        '    </div>\n'
        '  </div>\n'
        '</section>'
    )


GALLERY_HERO_SIZES = "(min-width: 1283px) 1180px, 92vw"
GALLERY_ITEM_SIZES = ("auto, (min-width: 1283px) 283px, (min-width: 1096px) 23vw, "
                      "(min-width: 818px) 31vw, (min-width: 540px) 46vw, 92vw")


def gallery_block(d: dict) -> str:
    """Galerie photos « vécu » du séjour. Rendu seulement si des photos existent."""
    g = d.get("gallery")
    if not g:
        return ""
    base = f'../assets/img/sejours/{d["slug"]}/'
    hero = g["hero"]
    hero_html = (
        '    <figure class="gallery-hero reveal">\n'
        f'      <img src="{base}{hero["img"]}" alt="{hero["alt"]}" loading="lazy" sizes="{GALLERY_HERO_SIZES}">\n'
        '      <figcaption>'
        f'<b>{hero.get("kicker", "")}</b><span>{hero["caption"]}</span>'
        '</figcaption>\n'
        '    </figure>'
    )
    items = "\n".join(
        '      <figure class="gallery-item reveal">'
        f'<img src="{base}{p["img"]}" alt="{p["alt"]}" loading="lazy" sizes="{GALLERY_ITEM_SIZES}">'
        f'<figcaption>{p["caption"]}</figcaption></figure>'
        for p in g["photos"]
    )
    return (
        '<section class="section" id="galerie">\n'
        '  <div class="container">\n'
        '    <div class="section-head reveal">\n'
        '      <span class="sticker">En images</span>\n'
        f'      <h2>{g["titre"]}</h2>\n'
        f'      <p>{g.get("intro", "")}</p>\n'
        '    </div>\n'
        f'{hero_html}\n'
        '    <div class="gallery-grid">\n'
        f'{items}\n'
        '    </div>\n'
        '  </div>\n'
        '</section>'
    )


def common_mapping() -> dict:
    return {
        "SITE_URL": SITE["url"],
        "EMAIL": SITE["email"],
        "TEL": SITE["telephone"],
        "TEL_INTL": SITE["telephone_intl"],
    }


def check_meta(page: str, name: str) -> None:
    title = re.search(r"<title>(.*?)</title>", page)
    desc = re.search(r'<meta name="description" content="([^"]*)"', page)
    if title and not 50 <= len(html.unescape(title.group(1))) <= 60:
        WARNINGS.append(f"{name}: <title> de {len(html.unescape(title.group(1)))} caractères (visé : 50–60)")
    if desc and not 140 <= len(html.unescape(desc.group(1))) <= 160:
        WARNINGS.append(f"{name}: meta description de {len(html.unescape(desc.group(1)))} caractères (visé : 140–160)")
    if page.count("<h1") != 1:
        WARNINGS.append(f"{name}: {page.count('<h1')} balises <h1> (attendu : 1)")


PAGES = {}  # URL publique → HTML généré (pour le sitemap)


def build_sejours() -> None:
    template = (ROOT / "templates" / "sejour.html").read_text()
    out_dir = ROOT / "sejours"
    out_dir.mkdir(exist_ok=True)

    for i, d in enumerate(DESTS):
        experiences = "\n".join(
            f'      <article class="exp reveal reveal-d{n % 4}">'
            f'<span class="pilier">{e["pilier"]}</span>'
            f'<h3>{e["titre"]}</h3><p>{e["texte"]}</p></article>'
            for n, e in enumerate(d["experiences"])
        )
        moments = "\n".join(
            f'      <div class="moment reveal"><span class="n">0{n + 1}</span>'
            f'<p>{m}</p></div>'
            for n, m in enumerate(d["moments"])
        )
        # 3 suggestions : les destinations suivantes dans le catalogue
        others = [DESTS[(i + k) % len(DESTS)] for k in (1, 2, 3)]
        others_html = "\n".join(dest_card(o, "../", CARD_SIZES_OTHERS) for o in others)
        # les cartes "autres séjours" pointent vers le même dossier
        others_html = others_html.replace('href="../sejours/', 'href="')

        page_url = f"{SITE['url']}/sejours/{d['slug']}.html"
        img_rel, img_w, img_h = og_image(f"assets/img/destinations/{d['slug']}.jpg")
        title = seo_title(d)
        page = render(template, {
            "SEO_TITLE": attr(title),
            "SLUG": d["slug"],
            "VILLE": d["ville"],
            "PAYS": d["pays"],
            "CONTINENT": d["continent"],
            "BASELINE": d["baseline"],
            "PITCH": d["pitch"],
            "VOL": d["vol"],
            "DECALAGE": d["decalage"],
            "LANGUES": d["langues"],
            "PERIODE": d["periode"],
            "META_DESCRIPTION": attr(d["meta_description"]),
            "OG_IMAGE": f"{SITE['url']}/{img_rel}",
            "OG_IMAGE_W": img_w,
            "OG_IMAGE_H": img_h,
            "JSONLD": sejour_jsonld(d, page_url, f"{SITE['url']}/{img_rel}"),
            "EXPERIENCES_HTML": experiences,
            "MOMENTS_HTML": moments,
            "GALLERY_HTML": gallery_block(d),
            "REFERENT_HTML": referent_block(d),
            "OTHERS_HTML": others_html,
            **common_mapping(),
        })
        page = finalize(page, "sejours", "../")
        check_meta(page, f"sejours/{d['slug']}.html")
        (out_dir / f"{d['slug']}.html").write_text(page)
        PAGES[page_url] = page
    print(f"✅ {len(DESTS)} pages séjour → sejours/")


def build_destinations_js() -> None:
    payload = []
    for d in DESTS:
        rel = f"assets/img/destinations/{d['slug']}.jpg"
        info = ensure_variants(rel)
        # vignette du simulateur (affichée en 86 × 64) : variante 240 px
        thumb = v(variant_rel(rel, 240, "jpg")) if info and 240 in info["widths"] else v(rel)
        payload.append({
            "slug": d["slug"], "ville": d["ville"], "pays": d["pays"],
            "baseline": d["baseline"], "themes": d["themes"], "tier": d["tier"],
            "lat": d["lat"], "lng": d["lng"],
            "img": thumb,
            "url": f"sejours/{d['slug']}.html",
        })
    out = ROOT / "assets" / "js" / "destinations.js"
    out.write_text(
        "window.LT_DESTINATIONS=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n"
    )
    _HASHES.pop(str(out), None)
    print(f"✅ {out.relative_to(ROOT)}")


def build_index() -> None:
    template = (ROOT / "templates" / "index.html").read_text()
    cards = "\n".join(dest_card(d) for d in DESTS)
    page = render(template, {
        "DEST_CARDS": cards,
        "JSONLD": index_jsonld(template),
        **common_mapping(),
    })
    page = finalize(page, "", "")
    check_meta(page, "index.html")
    (ROOT / "index.html").write_text(page)
    PAGES[f"{SITE['url']}/"] = page
    print("✅ index.html")


def build_legal() -> None:
    template_path = ROOT / "templates" / "legal.html"
    if not template_path.exists():
        print("ℹ️  templates/legal.html absent — page légale non régénérée")
        return
    credits = json.loads(CREDITS_FILE.read_text()) if CREDITS_FILE.exists() else {}
    by_slug = {d["slug"]: d["ville"] for d in DESTS}
    items = "\n".join(
        f'      <li>{by_slug.get(slug, slug)} : <a href="{c["page"]}" rel="noopener" target="_blank">'
        f'{c["author"]}</a> — licence {c["license"]} (Wikimedia Commons)</li>'
        for slug, c in sorted(credits.items())
    )
    page = render(template_path.read_text(), {"CREDITS_HTML": items, **common_mapping()})
    page = finalize(page, "", "")
    check_todo(page, "mentions-legales.html")
    (ROOT / "mentions-legales.html").write_text(page)
    print("✅ mentions-legales.html")


def build_cgv() -> None:
    template_path = ROOT / "templates" / "cgv.html"
    if not template_path.exists():
        return
    page = finalize(render(template_path.read_text(), common_mapping()), "", "")
    check_todo(page, "cgv.html")
    (ROOT / "cgv.html").write_text(page)
    print("✅ cgv.html")


def check_todo(page: str, name: str) -> None:
    """Signale les mentions « À compléter » restées dans une page publiée."""
    for todo in re.findall(r"À compléter[^<]*", page):
        WARNINGS.append(f"{name}: {todo.strip()}")


def build_404() -> None:
    """Page d'erreur servie par l'hébergeur à n'importe quelle profondeur
    d'URL : tous les chemins sont absolus (/assets/…)."""
    template_path = ROOT / "templates" / "404.html"
    if not template_path.exists():
        return
    cards = "\n".join(dest_card(d, "/", CARD_SIZES_OTHERS) for d in DESTS[:3])
    page = render(template_path.read_text(), {"DEST_CARDS": cards, **common_mapping()})
    page = finalize(page, "", "/")
    (ROOT / "404.html").write_text(page)
    print("✅ 404.html")


def build_brochure() -> None:
    template_path = ROOT / "templates" / "brochure.html"
    if not template_path.exists():
        return
    out_dir = ROOT / "assets" / "brochure"
    out_dir.mkdir(exist_ok=True)

    # photos compressées pour garder un PDF léger
    ph_dir = out_dir / "ph"
    ph_dir.mkdir(exist_ok=True)
    if Image is not None:
        for d in DESTS:
            src = ROOT / "assets" / "img" / "destinations" / f"{d['slug']}.jpg"
            dst = ph_dir / f"{d['slug']}.jpg"
            if src.exists() and not dst.exists():
                img = Image.open(src).convert("RGB")
                img.thumbnail((640, 640))
                img.save(dst, quality=68, optimize=True)

    pages = []
    chunk = 6                      # 6 destinations par page A4
    for start in range(0, len(DESTS), chunk):
        cards = "\n".join(
            f'    <div class="dest">'
            f'<div class="ph" style="background-image:url(\'ph/{d["slug"]}.jpg\')"></div>'
            f'<div class="tx"><span class="pays">{d["pays"]}</span><h3>{d["ville"]}</h3>'
            f'<p>{d["baseline"]}.</p></div></div>'
            for d in DESTS[start:start + chunk]
        )
        pages.append(
            '<div class="page">\n'
            '  <div class="head"><span class="kicker">Nos destinations</span>'
            '<img src="../img/logo.png" alt=""></div>\n'
            '  <h2 class="title">11 destinations qui donnent envie de partir</h2>\n'
            '  <p class="lead">Chaque séjour dure une semaine et décline nos quatre piliers. '
            'Les programmes détaillés sont présentés lors d\'un échange avec un conseiller.</p>\n'
            f'  <div class="dest-grid">\n{cards}\n  </div>\n'
            '</div>'
        )

    page = render(template_path.read_text(), {
        "DEST_PAGES": "\n\n".join(pages),
        "EMAIL": SITE["email"],
        "TEL": SITE["telephone"],
    })
    (out_dir / "brochure.html").write_text(page)
    print("✅ assets/brochure/brochure.html  (PDF : voir README)")


def build_manifest() -> None:
    icons = [
        {"src": f"/{v('assets/img/icon-192.png')}", "sizes": "192x192", "type": "image/png"},
        {"src": f"/{v('assets/img/icon-512.png')}", "sizes": "512x512", "type": "image/png"},
    ]
    manifest = {
        "name": SITE["nom"],
        "short_name": SITE["nom"],
        "description": SITE["description"],
        "lang": "fr",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#fdfeff",
        "theme_color": "#053c64",
        "icons": icons,
    }
    (ROOT / "site.webmanifest").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print("✅ site.webmanifest")


def content_fingerprint(page: str) -> str:
    """Empreinte du contenu éditorial (texte, titre, méta, JSON-LD) : le
    <lastmod> du sitemap ne bouge que si le contenu change vraiment."""
    head = " ".join(re.findall(r'<title>.*?</title>|<meta name="description"[^>]*>', page))
    ld = " ".join(re.findall(r'<script type="application/ld\+json">.*?</script>', page, re.S))
    body = re.sub(r"<(style|script)\b.*?</\1>", " ", page, flags=re.S)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))
    return hashlib.sha1((head + ld + text).encode()).hexdigest()


def build_sitemap() -> None:
    state = json.loads(SITEMAP_STATE.read_text()) if SITEMAP_STATE.exists() else {}
    urls = []
    for url, page in PAGES.items():
        fp = content_fingerprint(page)
        if state.get(url, {}).get("hash") != fp:
            state[url] = {"hash": fp, "lastmod": TODAY}
        urls.append(f"  <url><loc>{url}</loc><lastmod>{state[url]['lastmod']}</lastmod></url>")
    state = {u: s for u, s in state.items() if u in PAGES}
    SITEMAP_STATE.write_text(json.dumps(state, indent=2) + "\n")
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls) + "\n</urlset>\n"
    )
    print(f"✅ sitemap.xml  ({len(urls)} URL)")


def build_robots() -> None:
    (ROOT / "robots.txt").write_text(
        "User-agent: *\n"
        "Allow: /\n\n"
        f"Sitemap: {SITE['url']}/sitemap.xml\n"
    )
    print("✅ robots.txt")


if __name__ == "__main__":
    if Image is None:
        print("⚠️  Pillow absent : images servies sans variantes AVIF/WebP (pip install -r requirements.txt)")
    build_js()
    build_destinations_js()
    build_index()
    build_sejours()
    build_legal()
    build_cgv()
    build_404()
    build_brochure()
    build_manifest()
    build_sitemap()
    build_robots()
    if Image is not None:
        removed = clean_opt()
        print(f"✅ {len(_USED_OPT)} variantes d'images dans assets/opt/"
              + (f" ({removed} orphelines supprimées)" if removed else ""))
    for w in WARNINGS:
        print(f"⚠️  {w}")
