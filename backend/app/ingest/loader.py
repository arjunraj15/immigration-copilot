"""Turn the bytes of an upload into pages for the reader.

Ladder per page: the text layer first (pdfplumber, then pypdf). A page whose text layer is too poor and
that is mostly covered by an image is sent to the model as a page image, with unverified values.
An OCR step could be added between these two later. Until then the text source is TEXT_LAYER or IMAGE.
"""

import email.policy
import hashlib
import io
import json
import re
import zipfile
from email.parser import BytesParser
from collections.abc import Callable
from dataclasses import dataclass, field
from xml.etree import ElementTree

import pdfplumber
import pypdfium2
from PIL import Image, ImageOps, ImageSequence, ImageStat
from pypdf import PdfReader

TEXT_LAYER = "TEXT_LAYER"
IMAGE = "IMAGE"

# Same allowlist and limit as frontend fileRules.ts.
MAX_BYTES = 5 * 1024 * 1024
SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "pdf": (b"%PDF",),
    "png": (b"\x89PNG",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "tif": (b"II*\x00", b"MM\x00*"),
    "tiff": (b"II*\x00", b"MM\x00*"),
    "docx": (b"PK\x03\x04",),
}
# Text files for calls and messages have no signature bytes. They must be plain UTF-8 text with the right shape.
TEXT_TYPES = ("txt", "eml", "vtt", "json")
TEXT_PAGE_CHARS = 8000

# Scanned page rule. A page is scanned when its text layer is poor AND one image covers most of the page.
# Poor means fewer than MIN_PAGE_CHARS characters, or no "Label: value" line and fewer than RICH_TEXT_CHARS.
MIN_PAGE_CHARS = 40
RICH_TEXT_CHARS = 300
MIN_LABEL_LINES = 1
IMAGE_COVER_RATIO = 0.6
# A text page with no labels whose reversed lines show at least this many labels is a rotated page.
MIN_REVERSED_LABELS = 2
# A page is turned when at least this share of its characters run sideways or upside down.
TURNED_SHARE = 0.5
# Turned characters whose line position differs by less than this many points are on one line.
LINE_TOLERANCE = 3
# A rendered page whose pixel spread is below this is blank.
BLANK_STDDEV = 2.0
MAX_SIDE_PX = 1800
RENDER_SCALE = 2.0

PROBLEM_BLANK = "BLANK"
PROBLEM_ROTATED = "ROTATED"
PROBLEM_UNREADABLE = "UNREADABLE"

_LABEL = re.compile(r"^\s*([A-Za-z][A-Za-z .]{1,40}):\s*(.*)$")
_OWNER = re.compile(r"^\s*Synthetic Matter:\s*(\S+)", re.IGNORECASE | re.MULTILINE)
_WORD_TEXT = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class RejectedFile(Exception):
    """The file cannot be read. UNREADABLE is a review item and every other code is invalid."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class PageInfo:
    number: int
    text: str = ""
    source: str = TEXT_LAYER
    image: bytes | None = None
    image_sha: str | None = None
    rotation: int = 0
    problem: str | None = None
    scanned_reason: str | None = None
    owner: str | None = None
    corrected: bool = False  # a turned page whose text code rebuilt upright. It stays a ROTATED problem

    @property
    def chars(self) -> int:
        return len(self.text)


@dataclass
class LoadedDoc:
    sha256: str
    file_type: str
    pages: list[PageInfo] = field(default_factory=list)
    occurred_at: str | None = None  # a call or message file states when it happened
    note_text: str | None = None
    note_category: str | None = None  # ZOOM_NOTES, EMAIL_MESSAGE or WHATSAPP_CHAT, known from the file itself


def labels(text: str) -> dict[str, str]:
    """Label: value lines of a page, keys lower case. The first value of a label wins."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        match = _LABEL.match(line)
        if match and match.group(2).strip():
            found.setdefault(match.group(1).strip().lower(), match.group(2).strip())
    return found


def page_owner(text: str) -> str | None:
    match = _OWNER.search(text)
    return match.group(1) if match else None


def check_file(data: bytes, filename: str) -> str:
    """The file type when the extension, size and signature bytes agree. Otherwise RejectedFile."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SIGNATURES and ext not in TEXT_TYPES:
        raise RejectedFile("UNSUPPORTED_TYPE", "This file type is not allowed. Use PDF, JPG, PNG, TIFF, DOCX, TXT, EML, VTT or JSON")
    if not data:
        raise RejectedFile("EMPTY_FILE", "The file is empty")
    if len(data) > MAX_BYTES:
        raise RejectedFile("TOO_LARGE", f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB")
    if ext in TEXT_TYPES:
        _check_text(data, ext)
        return ext
    if not data.startswith(SIGNATURES[ext]):
        raise RejectedFile("BAD_SIGNATURE", "The file content does not match its type")
    return "jpg" if ext == "jpeg" else "tif" if ext == "tiff" else ext


def _check_text(data: bytes, ext: str) -> None:
    """Plain UTF-8 text only. A vtt file starts with WEBVTT and a json file must parse."""
    try:
        body = data.decode("utf-8-sig")
        ok = "\x00" not in body
        if ext == "vtt":
            ok = ok and body.lstrip().startswith("WEBVTT")
        if ext == "json":
            json.loads(body)
    except ValueError:
        ok = False
    if not ok:
        raise RejectedFile("BAD_SIGNATURE", "The file content does not match its type")


def _png(img: Image.Image) -> bytes:
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX))
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def _is_blank(png: bytes) -> bool:
    with Image.open(io.BytesIO(png)) as img:
        return max(ImageStat.Stat(img.convert("L")).stddev) < BLANK_STDDEV


def _attach_image(page: PageInfo, png: bytes, reason: str) -> None:
    page.source, page.image, page.scanned_reason = IMAGE, png, reason
    page.image_sha = hashlib.sha256(png).hexdigest()
    if _is_blank(png):
        page.problem = PROBLEM_BLANK


# Text direction of a character (sign of the text matrix a, b) -> sort key of the characters in a line,
# sort key of the lines, and the position that keeps one line together.
_TURNED: dict[tuple[int, int], tuple[Callable[[dict], float], Callable[[dict], float], str]] = {
    (0, 1): (lambda c: -c["top"], lambda c: c["x0"], "x0"),  # turned 90 degrees anticlockwise
    (0, -1): (lambda c: c["top"], lambda c: -c["x0"], "x0"),  # turned 90 degrees clockwise
    (-1, 0): (lambda c: -c["x0"], lambda c: -c["top"], "top"),  # upside down
}


def _sign(value: float) -> int:
    return (value > 0.01) - (value < -0.01)


def _direction(char: dict) -> tuple[int, int]:
    return _sign(char["matrix"][0]), _sign(char["matrix"][1])


def _turned_lines(chars: list[dict], direction: tuple[int, int]) -> list[str]:
    in_line, line_key, position = _TURNED[direction]
    lines: dict[int, list[dict]] = {}
    for char in chars:
        lines.setdefault(round(char[position] / LINE_TOLERANCE), []).append(char)
    ordered = sorted(lines.values(), key=lambda line: line_key(line[0]))
    return ["".join(c["text"] for c in sorted(line, key=in_line)).strip() for line in ordered]


def upright_text(plumber_page: pdfplumber.page.Page) -> str:
    """The page text with its turned characters rebuilt as upright lines, after the upright text.
    Empty when fewer than TURNED_SHARE of the characters are turned."""
    chars = [c for c in plumber_page.chars if c["text"].strip()]
    by_direction: dict[tuple[int, int], list[dict]] = {}
    for char in chars:
        by_direction.setdefault(_direction(char), []).append(char)
    turned = max((d for d in by_direction if d in _TURNED), key=lambda d: len(by_direction[d]), default=None)
    if turned is None or len(by_direction[turned]) < TURNED_SHARE * len(chars):
        return ""
    plain = plumber_page.filter(lambda o: o.get("object_type") != "char" or _direction(o) not in _TURNED)
    turned_chars = [c for c in plumber_page.chars if _direction(c) == turned]
    return "\n".join([(plain.extract_text() or "").strip(), *_turned_lines(turned_chars, turned)]).strip()


def _reversed_labels(text: str) -> int:
    return sum(1 for line in text.splitlines() if _LABEL.match(line[::-1]))


def _is_poor(text: str) -> bool:
    return len(text) < MIN_PAGE_CHARS or (len(labels(text)) < MIN_LABEL_LINES and len(text) < RICH_TEXT_CHARS)


def _cover(plumber_page: pdfplumber.page.Page) -> float:
    area = float(plumber_page.width * plumber_page.height) or 1.0
    best = 0.0
    for img in plumber_page.images:
        width = min(img["x1"], plumber_page.width) - max(img["x0"], 0)
        height = min(img["bottom"], plumber_page.height) - max(img["top"], 0)
        best = max(best, max(width, 0) * max(height, 0) / area)
    return best


def _pdf_text(plumber_page: pdfplumber.page.Page, fallback: object, index: int) -> str:
    text = (plumber_page.extract_text() or "").strip()
    if text:
        return text
    return (fallback.pages[index].extract_text() or "").strip()  # type: ignore[attr-defined]


def _render(doc: pypdfium2.PdfDocument, index: int) -> bytes:
    page = doc[index]
    scale = min(RENDER_SCALE, MAX_SIDE_PX / max(page.get_size()))
    return _png(page.render(scale=scale).to_pil())


def _classify_pdf_page(page: PageInfo, plumber_page: pdfplumber.page.Page) -> bool:
    """Set problem or scanned state from the text. True when the page needs a rendered image."""
    text = page.text
    if _is_poor(text) and _cover(plumber_page) >= IMAGE_COVER_RATIO:
        page.scanned_reason = f"Text layer has {len(text)} characters and an image covers the page"
        return True
    if not text:
        page.problem = PROBLEM_BLANK
    elif upright := upright_text(plumber_page):
        page.problem = PROBLEM_ROTATED
        if len(labels(upright)) >= MIN_REVERSED_LABELS:
            page.text, page.corrected = upright, True
    elif not labels(text) and _reversed_labels(text) >= MIN_REVERSED_LABELS:
        page.problem = PROBLEM_ROTATED
    elif len(text) < MIN_PAGE_CHARS:
        page.problem = PROBLEM_UNREADABLE
    return False


def _load_pdf(data: bytes) -> list[PageInfo]:
    try:
        fallback = PdfReader(io.BytesIO(data))
        render_doc = pypdfium2.PdfDocument(data)
        plumber = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:
        raise RejectedFile("UNREADABLE", "The PDF is damaged and cannot be opened") from exc
    pages: list[PageInfo] = []
    with plumber:
        for index, plumber_page in enumerate(plumber.pages):
            page = PageInfo(index + 1, rotation=plumber_page.rotation or 0)
            try:
                page.text = _pdf_text(plumber_page, fallback, index)
                if _classify_pdf_page(page, plumber_page):
                    _attach_image(page, _render(render_doc, index), page.scanned_reason or "")
            except Exception:
                page.problem = PROBLEM_UNREADABLE
            page.owner = page_owner(page.text)
            pages.append(page)
    return pages


def _load_image(data: bytes) -> list[PageInfo]:
    try:
        with Image.open(io.BytesIO(data)) as img:
            frames = [ImageOps.exif_transpose(f.copy()) for f in ImageSequence.Iterator(img)]
    except Exception as exc:
        raise RejectedFile("UNREADABLE", "The image is damaged and cannot be opened") from exc
    pages = []
    for number, frame in enumerate(frames, 1):
        page = PageInfo(number)
        _attach_image(page, _png(frame), "Image upload")
        pages.append(page)
    return pages


def _load_docx(data: bytes) -> list[PageInfo]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            root = ElementTree.fromstring(zf.read("word/document.xml"))
    except Exception as exc:
        raise RejectedFile("UNREADABLE", "The Word file is damaged and cannot be opened") from exc
    paragraphs = ["".join(t.text or "" for t in p.iter(f"{_WORD_TEXT}t")) for p in root.iter(f"{_WORD_TEXT}p")]
    page = PageInfo(1, text="\n".join(p for p in paragraphs if p).strip())
    page.owner = page_owner(page.text)
    page.problem = None if page.text else PROBLEM_BLANK
    return [page]


def _eml_text(data: bytes) -> str:
    message = BytesParser(policy=email.policy.default).parsebytes(data)
    head = "\n".join(f"{name}: {message[name]}" for name in ("From", "To", "Date", "Subject") if message[name])
    part = message.get_body(preferencelist=("plain", "html"))
    return f"{head}\n\n{part.get_content() if part else ''}".strip()


def _vtt_text(body: str) -> str:
    """Cue text only. The header, cue numbers and timestamps are dropped."""
    lines = [ln.strip() for ln in body.splitlines()]
    keep = [ln for ln in lines if ln and ln != "WEBVTT" and "-->" not in ln and not ln.isdigit()]
    return "\n".join(keep)


def _text_pages(text: str) -> list[PageInfo]:
    """One page, or more when the text is long. Pages break on line ends."""
    chunks, current = [], ""
    for line in text.splitlines():
        if current and len(current) + len(line) > TEXT_PAGE_CHARS:
            chunks.append(current)
            current = ""
        current += line + "\n"
    chunks.append(current)
    pages = []
    for number, chunk in enumerate(chunks, 1):
        page = PageInfo(number, text=chunk.strip())
        page.owner = page_owner(page.text)
        page.problem = None if page.text else PROBLEM_BLANK
        pages.append(page)
    return pages


_MESSAGE_CATEGORY = {"EMAIL": "EMAIL_MESSAGE", "WHATSAPP": "WHATSAPP_CHAT"}


def _comm_file(body: str) -> dict[str, str] | None:
    """What a call or message file says about itself: its category, its text and when it happened. Else None.

    A Zoom intake note has intake_id, recorded_at and summary, and only the summary is read. A message file has a channel
    (EMAIL or WHATSAPP) and a list of messages, and the subject and body of each are read in order. The type comes from these
    fields, so no model is asked what kind of file it is."""
    try:
        data = json.loads(body)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    if "intake_id" in data and isinstance(data.get("summary"), str) and data["summary"].strip():
        return {"category": "ZOOM_NOTES", "text": data["summary"].strip(), "occurred_at": str(data.get("recorded_at") or "")}
    category = _MESSAGE_CATEGORY.get(str(data.get("channel") or "").upper())
    messages = [m for m in data.get("messages") or [] if isinstance(m, dict) and str(m.get("body") or "").strip()]
    if category and messages:
        parts = [(f"Subject: {m['subject']}\n\n" if m.get("subject") and category == "EMAIL_MESSAGE" else "") + str(m["body"]).strip() for m in messages]
        return {"category": category, "text": "\n\n".join(parts), "occurred_at": str(messages[0].get("created_at") or "")}
    return None


def _json_text(body: str) -> str:
    """A call or message file sends only its text. Any other JSON is sent whole."""
    found = _comm_file(body)
    return found["text"] if found else json.dumps(json.loads(body), indent=2, ensure_ascii=False)


def _load_text(data: bytes, file_type: str) -> list[PageInfo]:
    try:
        body = data.decode("utf-8-sig")
        text = {"eml": lambda: _eml_text(data), "vtt": lambda: _vtt_text(body),
                "json": lambda: _json_text(body)}.get(file_type, lambda: body)()
    except Exception as exc:
        raise RejectedFile("UNREADABLE", "The text file is damaged and cannot be opened") from exc
    return _text_pages(text)


def load_bytes(data: bytes, filename: str) -> LoadedDoc:
    """Check the file and split it into pages. Raises RejectedFile when it cannot be read."""
    file_type = check_file(data, filename)
    if file_type in TEXT_TYPES:
        doc = LoadedDoc(hashlib.sha256(data).hexdigest(), file_type, _load_text(data, file_type))
        found = _comm_file(data.decode("utf-8-sig")) if file_type == "json" else None
        if found:
            doc.occurred_at, doc.note_text, doc.note_category = found["occurred_at"] or None, found["text"], found["category"]
        return doc
    loader = {"pdf": _load_pdf, "docx": _load_docx}.get(file_type, _load_image)
    return LoadedDoc(hashlib.sha256(data).hexdigest(), file_type, loader(data))


def first_page_labels(data: bytes, filename: str) -> dict[str, str]:
    """Label: value lines of the first page text layer. Empty when the file has none. Never reads images."""
    try:
        file_type = check_file(data, filename)
        if file_type == "docx":
            return labels(_load_docx(data)[0].text)
        if file_type != "pdf":
            return {}
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return labels(pdf.pages[0].extract_text() or "")
    except Exception:
        return {}
