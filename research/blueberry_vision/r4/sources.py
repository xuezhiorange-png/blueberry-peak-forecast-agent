"""Company-associated research source gate; license permission is not GT quality."""

from ..r2_common import JSONDict


def source_admission(source: JSONDict) -> JSONDict:
    reasons = []
    if source.get("license_status") != "LICENSE_VERIFIED":
        reasons.append("LICENSE_UNVERIFIED")
    if source.get("research_use") is not True:
        reasons.append("RESEARCH_USE_NOT_AUTHORIZED")
    license_id = source.get("license_id")
    if license_id == "CC-BY-NC-4.0":
        reasons.append("COMPANY_NONCOMMERCIAL_SCOPE_UNRESOLVED")
    elif license_id not in {"CC0-1.0", "CC-BY-2.0", "CC-BY-4.0", "CC-BY-SA-4.0"}:
        reasons.append("LICENSE_SCOPE_NOT_SUPPORTED")
    return {
        "eligible": not reasons,
        "reason_codes": reasons,
        "qualified_gt": False,
        "scope": "COMPANY_ASSOCIATED_EXTERNAL_RESEARCH",
        "limitation": "No legal opinion, rights-holder waiver, or human GT authentication.",
    }
