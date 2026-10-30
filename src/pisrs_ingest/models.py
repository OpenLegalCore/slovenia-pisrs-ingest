"""Source normalization, parsing, deterministic identities, and chunking."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from bs4 import BeautifulSoup

ARTICLE_RE = re.compile(r"^\s*(\d+[a-zA-Z]?)\.\s*člen\s*$", re.IGNORECASE)
QUOTED_ARTICLE_RE = re.compile(r"^\s*[»\"“„']\s*(\d+[a-zA-Z]?)\.\s*člen", re.IGNORECASE)
STOP_CLASSES = {"evidencna_stevilka", "kraj_datum_sprejetja", "podpisnik"}
FINAL_PROVISION_MARKERS = (
    "vsebuje naslednjo končno določbo",
    "vsebuje naslednje končne določbe",
)

TARGET_CHARS = 3200
MAX_CHARS = 4600
LONG_BLOCK_CHARS = 3800
LONG_BLOCK_OVERLAP = 300
PARSER_VERSION = "pisrs_besedilo_html_v1"
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 3072


class SourceInvariantError(RuntimeError):
    """Raised when source identity or version state is ambiguous."""


@dataclass(frozen=True)
class Act:
    register_id: int
    moped_id: str
    sop: str | None
    naziv: str | None
    kratica: str | None
    osnovni: bool | None
    vrsta_akta_id: int | None
    vrsta_akta_naziv: str | None
    datum_sprejetja: str | None
    datum_objave: str | None
    datum_zacetka_veljavnosti: str | None
    datum_prenehanja_veljavnosti: str | None
    seen_in_endpoints: tuple[str, ...]
    raw: dict[str, Any]

    @classmethod
    def from_raw(cls, row: dict[str, Any], endpoint: str) -> Act:
        register_id = row.get("id")
        moped_id = row.get("mopedId") or row.get("moped_id")
        if register_id is None or not moped_id or not _optional_text(row.get("naziv")):
            raise SourceInvariantError(
                "act is missing the established register_id/moped_id identity or required title"
            )
        act_type = row.get("vrstaAkta")
        return cls(
            register_id=int(register_id),
            moped_id=str(moped_id),
            sop=_optional_text(row.get("sop")),
            naziv=_optional_text(row.get("naziv")),
            kratica=_optional_text(row.get("kratica")),
            osnovni=row.get("osnovni") if isinstance(row.get("osnovni"), bool) else None,
            vrsta_akta_id=int(act_type["id"])
            if isinstance(act_type, dict) and act_type.get("id") is not None
            else None,
            vrsta_akta_naziv=_optional_text(act_type.get("naziv"))
            if isinstance(act_type, dict)
            else None,
            datum_sprejetja=_optional_text(row.get("datumSprejetja")),
            datum_objave=_optional_text(row.get("datumObjave")),
            datum_zacetka_veljavnosti=_optional_text(row.get("datumZacetkaVeljavnosti")),
            datum_prenehanja_veljavnosti=_optional_text(row.get("datumPrenehanjaVeljavnosti")),
            seen_in_endpoints=(endpoint,),
            raw=row,
        )

    def merge(self, other: Act) -> Act:
        if self.register_id != other.register_id:
            raise SourceInvariantError("cannot merge different act identities")
        if self.moped_id != other.moped_id:
            raise SourceInvariantError("one register_id maps to multiple moped_id values")
        values: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            left = getattr(self, name)
            right = getattr(other, name)
            values[name] = right if left is None or left == "" else left
        values["seen_in_endpoints"] = tuple(
            dict.fromkeys((*self.seen_in_endpoints, *other.seen_in_endpoints))
        )
        return Act(**values)

    def provenance(self) -> dict[str, Any]:
        """Return the donor-compatible normalized envelope, distinct from raw portal JSON."""

        return {
            "unique_key": f"register_id:{self.register_id}",
            "register_id": self.register_id,
            "moped_id": self.moped_id,
            "sop": self.sop,
            "naziv": self.naziv,
            "kratica": self.kratica,
            "osnovni": self.osnovni,
            "vrsta_akta_id": self.vrsta_akta_id,
            "vrsta_akta_naziv": self.vrsta_akta_naziv,
            "datum_sprejetja": self.datum_sprejetja,
            "datum_objave": self.datum_objave,
            "datum_zacetka_veljavnosti": self.datum_zacetka_veljavnosti,
            "datum_prenehanja_veljavnosti": self.datum_prenehanja_veljavnosti,
            "endpoint": self.seen_in_endpoints[0],
            "seen_in_endpoints": list(self.seen_in_endpoints),
            "raw": self.raw,
        }


@dataclass(frozen=True)
class NpbDocument:
    text_id: int
    naziv: str | None
    datum_dokumenta: str | None
    stevilka_dokumenta: str | None
    sop_from_docno: str | None
    npb_label: str | None
    raw: dict[str, Any]

    @classmethod
    def from_raw(cls, row: dict[str, Any]) -> NpbDocument:
        if row.get("id") is None:
            raise SourceInvariantError("NPB document is missing text_id")
        docno = _optional_text(row.get("stevilkaDokumenta"))
        sop, label = parse_document_number(docno)
        return cls(
            text_id=int(row["id"]),
            naziv=_optional_text(row.get("naziv")),
            datum_dokumenta=_optional_text(row.get("datumDokumenta")),
            stevilka_dokumenta=docno,
            sop_from_docno=sop,
            npb_label=label,
            raw=row,
        )


@dataclass(frozen=True)
class Block:
    index: int
    tag: str
    classes: tuple[str, ...]
    text: str
    block_type: str
    article_no: str | None = None
    article_title: str | None = None

    def raw(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "tag": self.tag,
            "classes": list(self.classes),
            "text": self.text,
        }


@dataclass(frozen=True)
class Article:
    article_no: str
    heading: str
    title: str | None
    start_block_index: int
    end_block_index: int
    block_indexes: tuple[int, ...]
    text: str


@dataclass(frozen=True)
class ParsedText:
    title: str | None
    html: str
    plain_text: str
    blocks: tuple[Block, ...]
    articles: tuple[Article, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class Chunk:
    chunk_index: int
    chunk_text: str
    block_start_index: int
    block_end_index: int
    block_count: int
    token_estimate: int
    content_hash: str


@dataclass(frozen=True)
class VectorRow:
    database_id: int
    point_id: str
    act_id: int | None
    version_id: int
    text_id: int
    sop: str | None
    sop_from_docno: str | None
    npb_label: str
    naziv: str | None
    title: str | None
    chunk_index: int
    chunk_type: str
    chunk_text: str
    chunk_text_len: int
    block_start_index: int | None
    block_end_index: int | None
    block_count: int
    token_estimate: int
    content_hash: str
    is_latest_for_sop: bool
    is_active: bool
    embedding_model: str
    embedding_dimensions: int
    collection_name: str

    def payload(self) -> dict[str, Any]:
        return canonical_payload(self)


MANAGED_PAYLOAD_KEYS = frozenset(
    {
        "source",
        "collection_name",
        "act_id",
        "version_id",
        "text_id",
        "sop",
        "sop_from_docno",
        "npb_label",
        "naziv",
        "title",
        "chunk_index",
        "chunk_type",
        "chunk_text_len",
        "block_start_index",
        "block_end_index",
        "block_count",
        "token_estimate",
        "content_hash",
        "is_latest_for_sop",
        "is_active",
        "embedding_model",
        "embedding_dimensions",
        "text",
    }
)


def canonical_payload(row: VectorRow) -> dict[str, Any]:
    """Build the sole authoritative payload used by PG, Qdrant, and reconciliation."""

    return {
        "source": "pisrs",
        "collection_name": row.collection_name,
        "act_id": row.act_id,
        "version_id": row.version_id,
        "text_id": row.text_id,
        "sop": row.sop,
        "sop_from_docno": row.sop_from_docno,
        "npb_label": row.npb_label,
        "naziv": row.naziv,
        "title": row.title,
        "chunk_index": row.chunk_index,
        "chunk_type": row.chunk_type,
        "chunk_text_len": row.chunk_text_len,
        "block_start_index": row.block_start_index,
        "block_end_index": row.block_end_index,
        "block_count": row.block_count,
        "token_estimate": row.token_estimate,
        "content_hash": row.content_hash,
        "is_latest_for_sop": row.is_latest_for_sop,
        "is_active": row.is_active,
        "embedding_model": row.embedding_model,
        "embedding_dimensions": row.embedding_dimensions,
        "text": row.chunk_text,
    }


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_document_number(docno: str | None) -> tuple[str | None, str | None]:
    value = docno or ""
    lower = value.lower()
    if "-npb" in lower:
        left, tail = lower.split("-npb", 1)
        parts = left.split("-")
        sop = "-".join(parts[-3:]) if len(parts) >= 6 else None
        digits = "".join(char for char in tail if char.isdigit())
        return sop, f"npb{digits.zfill(2)}" if digits else None
    parts = value.split("-")
    if len(parts) == 3:
        return value, "osnovno"
    return None, None


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def canonical_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def qdrant_point_id(collection: str, text_id: int, chunk_index: int) -> str:
    raw = f"{collection}:{text_id}:{chunk_index}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))


def version_rank(label: str) -> int:
    if label == "osnovno":
        return 0
    match = re.fullmatch(r"npb(\d+)", label)
    if not match:
        raise SourceInvariantError(f"unsupported NPB version label: {label!r}")
    return int(match.group(1))


def _block_type(classes: tuple[str, ...], text: str) -> str:
    if "naslov" in classes:
        return "title"
    if "npb" in classes:
        return "npb_label"
    if "opozorilo" in classes:
        return "warning"
    if "clen" in classes:
        return "article_heading"
    if "odstavek" in classes:
        return "paragraph"
    if any(value.startswith("alinea") for value in classes):
        return "bullet"
    if any(value.startswith("stevilcna_tocka") for value in classes):
        return "numbered_point"
    if any(value.startswith("crkovna_tocka") for value in classes):
        return "lettered_point"
    if "tabela" in classes or "MsoNormal" in classes:
        return "table_or_mso"
    if "napaka" in classes:
        return "final_or_note"
    return "text" if text else "unknown"


def parse_html(html: str) -> ParsedText:
    if not html.strip():
        raise SourceInvariantError("PISRS text response is empty")
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.find("title")
    title = normalize_text(title_node.get_text(" ")) if title_node else None
    main = soup.select_one(".mainText") or soup.find("body") or soup
    blocks: list[Block] = []
    for element in main.find_all(
        ["p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"], recursive=True
    ):
        text = normalize_text(element.get_text(" "))
        if not text:
            continue
        raw_classes = element.get("class") or []
        classes = tuple(raw_classes.split() if isinstance(raw_classes, str) else raw_classes)
        block_type = _block_type(classes, text)
        article_no = text if block_type == "article_heading" else None
        blocks.append(
            Block(
                index=len(blocks) + 1,
                tag=element.name,
                classes=classes,
                text=text,
                block_type=block_type,
                article_no=article_no,
                article_title=article_no,
            )
        )
    articles, warnings = _parse_articles(blocks)
    return ParsedText(
        title=title,
        html=html,
        plain_text="\n".join(block.text for block in blocks),
        blocks=tuple(blocks),
        articles=tuple(articles),
        warnings=tuple(warnings),
    )


def _parse_articles(blocks: list[Block]) -> tuple[list[Article], list[str]]:
    articles: list[Article] = []
    warnings: list[str] = []
    current_no: str | None = None
    current_heading: str | None = None
    current_title: str | None = None
    current_start = -1
    current_blocks: list[Block] = []
    in_final_provisions = False
    skipped_quotes = 0

    def close(end_index: int) -> None:
        nonlocal current_no, current_heading, current_title, current_start, current_blocks
        if current_no is None:
            return
        body: list[Block] = []
        for item in current_blocks:
            if any(value in STOP_CLASSES for value in item.classes):
                break
            body.append(item)
        articles.append(
            Article(
                article_no=current_no,
                heading=current_heading or f"{current_no}. člen",
                title=current_title,
                start_block_index=current_start,
                end_block_index=end_index,
                block_indexes=tuple(item.index for item in body),
                text=normalize_text(" ".join(item.text for item in body)),
            )
        )
        current_no = current_heading = current_title = None
        current_start = -1
        current_blocks = []

    index = 0
    while index < len(blocks):
        block = blocks[index]
        if any(marker in block.text.lower() for marker in FINAL_PROVISION_MARKERS):
            in_final_provisions = True
            close(block.index - 1)
            warnings.append(f"final-provisions section starts at block {block.index}")
            index += 1
            continue
        quoted = bool(QUOTED_ARTICLE_RE.match(block.text))
        if quoted:
            skipped_quotes += 1
        match = (
            None
            if in_final_provisions or quoted or "clen" not in block.classes
            else ARTICLE_RE.match(block.text)
        )
        if match:
            close(block.index - 1)
            current_no = match.group(1)
            current_heading = block.text
            current_start = block.index
            if index + 1 < len(blocks):
                candidate = blocks[index + 1]
                if (
                    "clen" in candidate.classes
                    and candidate.text.startswith("(")
                    and candidate.text.endswith(")")
                ):
                    current_title = candidate.text
                    index += 1
            index += 1
            continue
        if current_no is not None:
            current_blocks.append(block)
        index += 1
    close(blocks[-1].index if blocks else -1)
    if skipped_quotes:
        warnings.append(f"skipped quoted article references: {skipped_quotes}")
    return articles, warnings


def _split_long_text(
    text: str, max_chars: int = LONG_BLOCK_CHARS, overlap: int = LONG_BLOCK_OVERLAP
) -> list[str]:
    text = normalize_text(text)
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            cut = text.rfind(". ", start, end)
            if cut < start + int(max_chars * 0.55):
                cut = text.rfind(" ", start, end)
            if cut > start:
                end = cut + 1
        part = text[start:end].strip()
        if part:
            parts.append(part)
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return parts


def make_chunks(blocks: tuple[Block, ...]) -> tuple[Chunk, ...]:
    chunks: list[Chunk] = []
    parts: list[str] = []
    start_index: int | None = None
    end_index: int | None = None
    block_count = 0

    def flush() -> None:
        nonlocal parts, start_index, end_index, block_count
        text = normalize_text("\n".join(parts))
        if text:
            assert start_index is not None and end_index is not None
            chunks.append(
                Chunk(
                    chunk_index=len(chunks) + 1,
                    chunk_text=text,
                    block_start_index=start_index,
                    block_end_index=end_index,
                    block_count=block_count,
                    token_estimate=max(1, int(len(text) / 3.6)),
                    content_hash=canonical_content_hash(text),
                )
            )
        parts = []
        start_index = end_index = None
        block_count = 0

    for block in blocks:
        raw_text = normalize_text(block.text)
        if not raw_text:
            continue
        header_parts = [value for value in (block.article_no, block.article_title) if value]
        if not header_parts and block.block_type:
            header_parts = [block.block_type]
        header = f"[{' | '.join(dict.fromkeys(header_parts))}] " if header_parts else ""
        long_parts = _split_long_text(raw_text)
        for part_number, part_text in enumerate(long_parts, start=1):
            value = header + part_text
            if len(long_parts) > 1:
                value = f"{header}[del {part_number}/{len(long_parts)}] {part_text}"
            subparts = _split_long_text(value) if len(value) > LONG_BLOCK_CHARS + 500 else [value]
            for subpart in subparts:
                current_length = len("\n".join(parts))
                if parts and (
                    current_length + len(subpart) > MAX_CHARS or current_length >= TARGET_CHARS
                ):
                    flush()
                start_index = block.index if start_index is None else start_index
                end_index = block.index
                block_count += 1
                parts.append(subpart)
    flush()
    return tuple(chunks)


def article_json(article: Article) -> dict[str, Any]:
    return asdict(article)
