"""Small public-source discovery and license-gated download; never search-result scraping.

Network is optional and limited to an explicit public-provider allowlist. No private
credentials, cloud vision APIs, bulk archives, or training are used by this module.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..assets import load_asset
from ..r2_common import read_json, seal, write_json_new

JSONDict = dict[str, Any]
ALLOWED_HOSTS = frozenset(
    {
        "commons.wikimedia.org",
        "upload.wikimedia.org",
        "zenodo.org",
        "creativecommons.org",
        "universe.roboflow.com",
    }
)
USER_AGENT = "BlueberryVisionResearch/3.0 (public source and license audit)"
MAX_IMAGE_BYTES = 20_000_000
MAX_PILOT_BYTES = 500_000_000
MAX_PILOT_IMAGES = 100
COMMONS_TITLES = (
    "File:Blueberries-In-Pack.jpg",
    "File:Blueberries on branch.jpg",
    "File:Blueberries ripening on branch.jpg",
    "File:Blueberries on the branches of a bush.jpg",
)
ZENODO_IDS = (14002517, 7813238, 10522314, 6450413)
LICENSES = {
    "CC0": ("CC0-1.0", "/publicdomain/zero/1.0", False),
    "CC BY 2.0": ("CC-BY-2.0", "/licenses/by/2.0", True),
    "CC BY-SA 4.0": ("CC-BY-SA-4.0", "/licenses/by-sa/4.0", True),
}
REGISTRY_PATH = Path(__file__).resolve().parents[1] / "evidence/r3/data_source_registry.json"


class SourceError(ValueError):
    """Stable source-admission reason code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def check_public_url(url: str) -> None:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise SourceError("SOURCE_URL_NOT_ALLOWED") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.username
        or parsed.password
        or port not in (None, 443)
    ):
        raise SourceError("SOURCE_URL_NOT_ALLOWED")


class _PublicRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        check_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_public(url: str, *, max_bytes: int = 3_000_000) -> bytes:
    """Fetch bounded bytes through configured network policy, rejecting host-changing redirects."""
    check_public_url(url)
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_PILOT_BYTES:
        raise SourceError("SOURCE_BYTE_POLICY_INVALID")
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with build_opener(_PublicRedirect()).open(request, timeout=30) as response:
        check_public_url(response.geturl())
        length = response.headers.get("Content-Length")
        if length and int(length) > max_bytes:
            raise SourceError("SOURCE_DOWNLOAD_SIZE_LIMIT")
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise SourceError("SOURCE_DOWNLOAD_SIZE_LIMIT")
    return cast(bytes, data)


def _plain(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def parse_commons(payload: JSONDict) -> list[JSONDict]:
    """Only explicit supported license name + matching CC URI + no restrictions qualify."""
    rows = []
    for page in payload.get("query", {}).get("pages", {}).values():
        info = page.get("imageinfo", [{}])[0]
        meta = info.get("extmetadata", {})

        def val(key: str, metadata: JSONDict = meta) -> str:
            return str(metadata.get(key, {}).get("value", ""))

        license_name, license_url = (
            val("LicenseShortName"),
            val("LicenseUrl").replace("http:", "https:"),
        )
        policy = LICENSES.get(license_name)
        parsed = urlparse(license_url)
        accepted = bool(
            policy
            and parsed.scheme == "https"
            and parsed.hostname == "creativecommons.org"
            and parsed.path.rstrip("/").removesuffix("/deed.en") == policy[1]
            and not val("Restrictions")
        )
        page_id = page.get("pageid")
        rows.append(
            {
                "source_id": f"commons-{page_id}",
                "name": page.get("title"),
                "official_url": info.get("descriptionurl"),
                "publisher": "Wikimedia Commons / individual creator",
                "creator": _plain(val("Artist")),
                "purpose": "PUBLIC_EXTERNAL_BENCHMARK",
                "SYNTHETIC": False,
                "license_id": policy[0] if accepted and policy else None,
                "license_name": license_name,
                "license_url": license_url or None,
                "license_status": "LICENSE_VERIFIED" if accepted else "LICENSE_UNVERIFIED",
                "research_use": True if accepted else None,
                "commercial_use": True if accepted else None,
                "model_training": "PERMITTED_DERIVATIVE_USE_WITH_LICENSE_CONDITIONS"
                if accepted
                else "UNKNOWN",
                "redistribution": True if accepted else None,
                "attribution_required": policy[2] if accepted and policy else None,
                "share_alike_derivatives": license_name == "CC BY-SA 4.0" if accepted else None,
                "license_conditions": (
                    "Credit creator/source/license and indicate modifications; "
                    "BY-SA image derivatives retain BY-SA. Training use does not "
                    "establish any future model license conclusion."
                )
                if accepted
                else "No download or use until license scope verified.",
                "image_count": 1,
                "image_types": ["JPEG"],
                "contains_blueberry": "SOURCE_DESCRIPTION_SUPPORTED_NOT_BUSINESS_TAXONOMY_APPROVED",
                "has_per_fruit_annotations": False,
                "independent_split": False,
                "download_url": info.get("url", "").split("?")[0],
                "asset_size_bytes": info.get("size"),
                "image_width": info.get("width"),
                "image_height": info.get("height"),
                "download_status": "AVAILABLE_NOT_DOWNLOADED"
                if accepted
                else "BLOCKED_LICENSE_UNVERIFIED",
                "download_admission": "ALLOWED_SMALL_PILOT"
                if accepted
                else "BLOCKED_LICENSE_UNVERIFIED",
                "capture_date_source_text": _plain(val("DateTimeOriginal")) or None,
                "observed_at": None,
                "capture_time_status": "UNKNOWN_NO_VERIFIED_TIMEZONE",
                "base_identity": "UNRESOLVED",
                "variety": "UNKNOWN",
                "commons_revision_id": page.get("revisions", [{}])[0].get("revid"),
                "license_evidence": {
                    "provider_license_name": license_name,
                    "provider_license_url": license_url or None,
                    "provider_credit": _plain(val("Credit")),
                    "provider_permission_excerpt": _plain(val("Permission"))[:1200],
                    "restrictions": val("Restrictions"),
                    "metadata_sha256": hashlib.sha256(
                        json.dumps(
                            page, sort_keys=True, ensure_ascii=False, separators=(",", ":")
                        ).encode()
                    ).hexdigest(),
                },
            }
        )
    return sorted(rows, key=lambda item: item["source_id"])


def parse_zenodo(payload: JSONDict) -> JSONDict:
    record_id = payload.get("id")
    meta = payload.get("metadata", {})
    license_id = meta.get("license", {}).get("id")
    cc_by = license_id == "cc-by-4.0"
    cc_nc = license_id == "cc-by-nc-4.0"
    verified = cc_by or cc_nc
    fruit_labels = record_id == 14002517
    code_only = record_id in (10522314, 14205417)
    known_count = (
        {14002517: 140, 7813238: 2000}.get(record_id) if isinstance(record_id, int) else None
    )
    description = _plain(meta.get("description", ""))
    return {
        "source_id": f"zenodo-{record_id}",
        "name": meta.get("title"),
        "official_url": f"https://zenodo.org/records/{record_id}",
        "publisher": "Zenodo / "
        + "; ".join(
            str(creator.get("affiliation") or creator.get("name"))
            for creator in meta.get("creators", [])
        ),
        "creators": meta.get("creators", []),
        "purpose": "PUBLIC_EXTERNAL_BENCHMARK",
        "SYNTHETIC": False,
        "license_id": "CC-BY-4.0" if cc_by else "CC-BY-NC-4.0" if cc_nc else license_id,
        "license_url": "https://creativecommons.org/licenses/by/4.0/"
        if cc_by
        else "https://creativecommons.org/licenses/by-nc/4.0/"
        if cc_nc
        else None,
        "license_status": "LICENSE_VERIFIED_CODE_ONLY"
        if code_only
        else "LICENSE_VERIFIED_USE_RESTRICTED"
        if cc_nc
        else "LICENSE_VERIFIED"
        if cc_by
        else "LICENSE_UNVERIFIED",
        "research_use": "CODE_AND_RESULTS_ONLY"
        if code_only
        else "NONCOMMERCIAL_ONLY"
        if cc_nc
        else True
        if cc_by
        else None,
        "commercial_use": False if cc_nc else True if cc_by else None,
        "model_training": "NONCOMMERCIAL_DERIVATIVE_USE_ONLY"
        if cc_nc
        else "PERMITTED_WITH_ATTRIBUTION_SUBJECT_TO_IMAGE_LICENSE_SCOPE"
        if cc_by
        else "UNKNOWN",
        "redistribution": "NONCOMMERCIAL_WITH_ATTRIBUTION" if cc_nc else True if cc_by else None,
        "attribution_required": True if verified else None,
        "license_scope": "DEPOSIT_CODE_AND_RESULTS_ONLY" if code_only else "DEPOSIT_FILES",
        "image_license_status": "LICENSE_UNVERIFIED"
        if code_only
        else "LICENSE_VERIFIED_USE_RESTRICTED"
        if cc_nc
        else "LICENSE_VERIFIED"
        if cc_by
        else "LICENSE_UNVERIFIED",
        "image_count": known_count,
        "image_types": ["JPEG"]
        if fruit_labels
        else ["PNG"]
        if record_id == 7813238
        else ["UNKNOWN"],
        "contains_blueberry": "REAL_BLUEBERRY_CANOPY"
        if fruit_labels
        else "BLUEBERRY_BUSH_SCENES_NOT_PER_FRUIT_GT"
        if record_id == 7813238
        else "UNKNOWN_ASSET_CONTENT",
        "has_per_fruit_annotations": True
        if fruit_labels
        else False
        if record_id == 7813238
        else None,
        "per_fruit_annotation_count": 17955 if fruit_labels else None,
        "annotation_formats": ["VIA_JSON", "Pascal_VOC_XML", "YOLO_TXT"]
        if fruit_labels
        else ["LABELME_JSON", "YOLO_TXT_BUSH_AND_POLE"]
        if record_id == 7813238
        else [],
        "annotation_quality_status": "PUBLISHER_DESCRIBED_MANUAL_NOT_LOCAL_REVIEWED"
        if fruit_labels
        else "NOT_APPLICABLE_SINGLE_FRUIT",
        "independent_split": "PUBLISHED_SEQUENCE_SPLIT_TRAIN1490_VALIDATION200_TEST310"
        if record_id == 7813238
        else "UNVERIFIED",
        "test_exposure": "EXPOSED_PUBLIC_BENCHMARK",
        "download_status": "NOT_DOWNLOADED",
        "download_admission": "BLOCKED_IMAGE_LICENSE_SCOPE"
        if code_only
        else "BLOCKED_PENDING_PURPOSE_OR_PERMISSION"
        if cc_nc
        else "NOT_SELECTED_NOT_SINGLE_FRUIT_OR_ARCHIVE_EXCEEDS_PILOT_LIMIT"
        if cc_by
        else "BLOCKED_LICENSE_UNVERIFIED",
        "files": [
            {
                "name": item.get("key"),
                "size_bytes": item.get("size"),
                "checksum": item.get("checksum"),
                "download_url": item.get("links", {}).get("self"),
            }
            for item in payload.get("files", [])
        ],
        "license_evidence": {
            "metadata_license_id": license_id,
            "description_excerpt": description[:5000],
            "metadata_sha256": hashlib.sha256(
                json.dumps(meta, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
            ).hexdigest(),
        },
    }


def parse_roboflow_page(content: bytes) -> JSONDict:
    """Catalog the public landing page without inferring a license from 'open source'."""
    text = content.decode("utf-8", errors="replace")
    description = re.search(r'<meta name="description" content="([^"]+)"', text)
    excerpt = html.unescape(description.group(1)) if description else "UNKNOWN"
    count = re.match(r"([0-9]+) open source", excerpt)
    return {
        "source_id": "roboflow-blueberrydetection-v1",
        "name": "BlueBerryDetection v1",
        "official_url": "https://universe.roboflow.com/blueberrydetection/blueberrydetection/dataset/1",
        "publisher": "Roboflow Universe / BlueberryDetection project uploader",
        "purpose": "PUBLIC_EXTERNAL_BENCHMARK",
        "SYNTHETIC": False,
        "license_id": None,
        "license_url": None,
        "license_status": "LICENSE_UNVERIFIED",
        "research_use": None,
        "commercial_use": None,
        "model_training": "UNKNOWN",
        "redistribution": None,
        "attribution_required": None,
        "image_count": int(count.group(1)) if count else None,
        "image_types": ["UNKNOWN"],
        "contains_blueberry": "PROVIDER_DESCRIBED_BLUEBERRY",
        "has_per_fruit_annotations": "PROVIDER_DESCRIBED_OBJECT_DETECTION_NOT_LOCAL_REVIEWED",
        "independent_split": "PUBLIC_SPLIT_INDEPENDENCE_UNVERIFIED",
        "test_exposure": "EXPOSED_PUBLIC_BENCHMARK",
        "download_status": "NOT_DOWNLOADED",
        "download_admission": "BLOCKED_LICENSE_UNVERIFIED",
        "license_evidence": {
            "metadata_excerpt": excerpt,
            "page_sha256": hashlib.sha256(content).hexdigest(),
            "reason": "Landing-page open-source phrase is not an identified image license.",
        },
    }


def discover_sources(*, online: bool = True) -> JSONDict:
    """Refresh a curated official-source catalog; no images downloaded implicitly.

    Offline mode returns the historical versioned review with explicit provenance,
    so CI never depends on external data availability or refetches real images.
    """
    if not online:
        previous = read_json(REGISTRY_PATH)
        return seal(
            {
                **previous,
                "discovery_mode": "OFFLINE_PERSISTED_REVIEW",
                "fresh_network_verification": False,
            },
            "registry_hash",
        )
    now = datetime.now(UTC).isoformat()
    sources: list[JSONDict] = []
    checks: list[JSONDict] = []
    urls = [
        (
            "commons",
            "https://commons.wikimedia.org/w/api.php?action=query&titles="
            + quote("|".join(COMMONS_TITLES))
            + "&prop=imageinfo|revisions&iiprop=url|extmetadata|size&rvprop=ids&format=json",
        )
    ]
    urls += [
        (f"zenodo-{record_id}", f"https://zenodo.org/api/records/{record_id}")
        for record_id in ZENODO_IDS
    ]
    for kind, url in urls:
        try:
            content = fetch_public(url)
            payload = json.loads(content)
            rows = parse_commons(payload) if kind == "commons" else [parse_zenodo(payload)]
            sources.extend(rows)
            checks.append(
                {
                    "provider": kind,
                    "url": url,
                    "status": "FETCHED",
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "bytes": len(content),
                }
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            checks.append(
                {
                    "provider": kind,
                    "url": url,
                    "status": "UNAVAILABLE",
                    "reason": type(exc).__name__,
                    "detail": str(exc)[:200],
                }
            )
    roboflow_url = "https://universe.roboflow.com/blueberrydetection/blueberrydetection/dataset/1"
    try:
        content = fetch_public(roboflow_url)
        sources.append(parse_roboflow_page(content))
        checks.append(
            {
                "provider": "roboflow",
                "url": roboflow_url,
                "status": "FETCHED",
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
        )
    except (OSError, ValueError) as exc:
        checks.append(
            {
                "provider": "roboflow",
                "url": roboflow_url,
                "status": "UNAVAILABLE",
                "reason": type(exc).__name__,
                "detail": str(exc)[:200],
            }
        )
    for license_url in sorted({row["license_url"] for row in sources if row.get("license_url")}):
        try:
            terms = fetch_public(license_url)
            proof = {
                "url": license_url,
                "status": "FETCHED",
                "sha256": hashlib.sha256(terms).hexdigest(),
                "bytes": len(terms),
            }
        except (OSError, ValueError) as exc:
            proof = {
                "url": license_url,
                "status": "UNAVAILABLE",
                "reason": type(exc).__name__,
                "detail": str(exc)[:200],
            }
        checks.append({"provider": "official-license-terms", **proof})
        for row in sources:
            if row.get("license_url") == license_url:
                row["license_evidence"]["official_terms"] = proof
                if proof["status"] != "FETCHED":
                    row["license_status"] = "LICENSE_UNVERIFIED"
                    row["download_admission"] = "BLOCKED_LICENSE_TERMS_UNAVAILABLE"
    return seal(
        {
            "registry_version": "3.0.0",
            "checked_at": now,
            "discovery_mode": "ONLINE_OFFICIAL_METADATA",
            "fresh_network_verification": True,
            "sources": sources,
            "provider_checks": checks,
            "download_limits": {"image_count": MAX_PILOT_IMAGES, "bytes": MAX_PILOT_BYTES},
            "no_images_downloaded_by_discovery": True,
            "limitations": [
                (
                    "Provider declarations verified, not a legal opinion "
                    "or corporate image authorization."
                ),
                "Commercially affiliated task does not presume CC-BY-NC use is noncommercial.",
                (
                    "Source labels are not automatically business-approved, "
                    "or locally adjudicated human GT."
                ),
            ],
        },
        "registry_hash",
    )


def download_public_pilot(
    registry: JSONDict,
    output_dir: Path,
    source_ids: list[str],
    *,
    max_total_bytes: int = MAX_PILOT_BYTES,
) -> JSONDict:
    """Download only already license-admitted single-image sources; no archives or login."""
    if not 1 <= len(source_ids) <= MAX_PILOT_IMAGES:
        raise SourceError("PILOT_IMAGE_LIMIT")
    if len(set(source_ids)) != len(source_ids):
        raise SourceError("SOURCE_ID_DUPLICATED")
    if type(max_total_bytes) is not int or not 1 <= max_total_bytes <= MAX_PILOT_BYTES:
        raise SourceError("PILOT_BYTE_POLICY_INVALID")
    mapping = {row["source_id"]: row for row in registry.get("sources", [])}
    selected = []
    for source_id in source_ids:
        if source_id not in mapping:
            raise SourceError("SOURCE_ID_UNKNOWN")
        row = mapping[source_id]
        if (
            row.get("license_status") != "LICENSE_VERIFIED"
            or row.get("research_use") is not True
            or row.get("download_admission") != "ALLOWED_SMALL_PILOT"
        ):
            raise SourceError("LICENSE_NOT_ADMITTED")
        check_public_url(row["download_url"])
        if (
            type(row.get("asset_size_bytes")) is not int
            or not 1 <= row["asset_size_bytes"] <= MAX_IMAGE_BYTES
        ):
            raise SourceError("SOURCE_IMAGE_SIZE_UNVERIFIED")
        if not re.fullmatch(r"commons-[0-9]+", source_id):
            raise SourceError("SOURCE_ID_INVALID")
        selected.append(row)
    if sum(row["asset_size_bytes"] for row in selected) > max_total_bytes:
        raise SourceError("PILOT_TOTAL_BYTE_LIMIT")
    output_dir.mkdir(parents=True, exist_ok=False)
    images = []
    total = 0
    for row in selected:
        content = fetch_public(
            row["download_url"], max_bytes=min(MAX_IMAGE_BYTES, max_total_bytes - total)
        )
        if len(content) != row["asset_size_bytes"]:
            raise SourceError("SOURCE_SIZE_CHANGED")
        total += len(content)
        suffix = Path(urlparse(row["download_url"]).path).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png"}:
            raise SourceError("SOURCE_IMAGE_FORMAT_UNSUPPORTED")
        filename = row["source_id"] + suffix
        with (output_dir / filename).open("xb") as stream:
            stream.write(content)
        loaded = load_asset(output_dir, filename)
        if loaded.metadata["image_width"] != row.get("image_width") or loaded.metadata[
            "image_height"
        ] != row.get("image_height"):
            raise SourceError("SOURCE_DIMENSIONS_CHANGED")
        images.append(
            {
                "source_id": row["source_id"],
                "image_id": "public-" + row["source_id"],
                "asset_ref": filename,
                "asset_sha256": loaded.metadata["asset_sha256"],
                "image_width": loaded.metadata["image_width"],
                "image_height": loaded.metadata["image_height"],
                "bytes": len(content),
                "source_url": row["official_url"],
                "download_url": row["download_url"],
                "license_id": row["license_id"],
                "license_url": row["license_url"],
                "license_status": row["license_status"],
                "research_use": True,
                "commercial_use": row["commercial_use"],
                "model_training": row["model_training"],
                "redistribution": row["redistribution"],
                "attribution_required": row["attribution_required"],
                "creator": row["creator"],
                "share_alike_derivatives": row.get("share_alike_derivatives", False),
                "commons_revision_id": row.get("commons_revision_id"),
                "source_provided_capture_date": row.get("capture_date_source_text"),
                "observed_at": None,
                "capture_time_status": "UNKNOWN_NO_VERIFIED_TIMEZONE",
                "base_identity": {"status": "UNRESOLVED"},
                "variety": None,
                "annotations": None,
                "GT_status": "MISSING",
                "purpose": "PUBLIC_EXTERNAL_BENCHMARK",
                "SYNTHETIC": False,
            }
        )
    index = seal(
        {
            "dataset_id": "commons-blueberry-public-pilot-r3",
            "dataset_version": "3.0.0",
            "purpose": "PUBLIC_EXTERNAL_BENCHMARK",
            "SYNTHETIC": False,
            "source_registry_hash": registry.get("registry_hash"),
            "retrieved_at": datetime.now(UTC).isoformat(),
            "image_count": len(images),
            "total_bytes": total,
            "images": images,
            "reference_status": "NO_HUMAN_REFERENCE_LABELS",
        },
        "index_hash",
    )
    write_json_new(output_dir / "source_index.json", index)
    return index
