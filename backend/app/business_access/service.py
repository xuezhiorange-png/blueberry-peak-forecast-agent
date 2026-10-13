"""Authorized metadata discovery; canonical selection without forecast calculations."""

import json
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.business_access import repository
from backend.app.business_access.schemas import Filters, Selection, TokenClaims
from backend.app.business_access.tokens import Signer, digest
from backend.app.forecast_intelligence.read_schemas import ForecastReadQuery
from backend.app.forecast_intelligence.read_service import (
    FORECAST_FAMILY,
    PUBLIC_EVIDENCE_HASHES,
    ForecastIntelligenceReadService,
)
from backend.app.local_auth.authorization import authorize, binding_digest, grant_snapshot
from backend.app.local_auth.models import AuthResourceGrant
from backend.app.local_auth.schemas import ForecastBinding, QualityBinding
from backend.app.local_auth.service import AuthService
from backend.app.local_auth.sessions import AuthError, Principal, now

MAX_AUTHORIZED_GRANTS = 10000


@dataclass(frozen=True)
class Catalog:
    queries: list[ForecastReadQuery]
    grants: list[dict[str, Any]]
    metadata: list[dict[str, Any]]
    directory: str
    snapshot: str


def item(row: dict[str, Any], approved: Collection[tuple[str, int]]) -> dict[str, Any]:
    identity = {
        key: row[key]
        for key in ForecastReadQuery.model_fields
        if key != "expected_source_result_hash"
    }
    identity["origin_date"] = row["origin_date"].isoformat()
    count = row["daily_row_count"]
    completeness = (
        "INCOMPLETE_CHILD_COVERAGE"
        if row["source_status"] == "INCOMPLETE_CHILD_COVERAGE"
        else "EMPTY"
        if count == 0
        else "PARTIAL_DATE_WINDOW"
        if count < 15
        else "COMPLETE"
    )
    parent = row["rerun_of_run_id"]
    return {
        "forecast_identity": identity,
        "expected_source_result_hash": row["source_result_hash"],
        "entity_name": row["entity_name"],
        "forecast_family": row["forecast_family"],
        "origin_date": row["origin_date"].isoformat(),
        "completeness_status": completeness,
        "canonical_verification_required": True,
        "source_status": row["source_status"],
        "saved_at": row["created_at"].isoformat(),
        "rerun_of_run_id": parent if (row["source_kind"], parent) in approved else None,
    }


class DiscoveryService:
    def __init__(self, auth: AuthService):
        self.auth = auth
        self.signer = Signer(auth.settings.business_access_signing_key.get_secret_value())

    async def directory(
        self, db: AsyncSession, principal: Principal
    ) -> tuple[list[ForecastReadQuery], list[dict[str, Any]], str]:
        if principal.must_change_password:
            raise AuthError("PASSWORD_CHANGE_REQUIRED")
        try:
            organizations = json.loads(self.auth.settings.local_auth_organization_ids_json)
            if (
                not isinstance(organizations, list)
                or not organizations
                or any(not isinstance(v, str) or not v or "*" in v for v in organizations)
            ):
                raise ValueError("Invalid authority")
        except (ValueError, TypeError):
            raise AuthError("AUTHORIZATION_UNAVAILABLE", 503) from None
        instant = now()
        grants = (
            await db.scalars(
                select(AuthResourceGrant)
                .where(
                    AuthResourceGrant.principal_id == principal.principal_id,
                    AuthResourceGrant.organization_id.in_(organizations),
                    AuthResourceGrant.revoked_at.is_(None),
                    AuthResourceGrant.valid_from <= instant,
                    AuthResourceGrant.valid_until > instant,
                )
                .order_by(AuthResourceGrant.grant_id)
                .limit(MAX_AUTHORIZED_GRANTS + 1)
            )
        ).all()
        if not grants:
            raise AuthError("FORBIDDEN")
        if len(grants) > MAX_AUTHORIZED_GRANTS:
            raise AuthError("DIRECTORY_LIMIT", 503)
        snapshots = [
            {
                **grant_snapshot(g),
                "valid_from": g.valid_from.isoformat(),
                "valid_until": g.valid_until.isoformat(),
            }
            for g in grants
        ]
        queries: dict[tuple[str, int], ForecastReadQuery] = {}
        for grant in grants:
            if grant.resource_kind == "QUALITY":
                try:
                    quality = QualityBinding.model_validate(grant.quality_binding)
                except ValueError:
                    raise AuthError("AUTHORIZATION_UNAVAILABLE", 503) from None
                if (
                    quality.evidence_hashes != PUBLIC_EVIDENCE_HASHES
                    or quality.evidence_set_digest != binding_digest(PUBLIC_EVIDENCE_HASHES)
                ):
                    raise AuthError("AUTHORITY_MISMATCH", 409)
            if grant.resource_kind != "FORECAST" or grant.capability != "may_read_forecast":
                continue
            try:
                binding = ForecastBinding.model_validate(grant.forecast_binding)
            except ValueError:
                raise AuthError("AUTHORIZATION_UNAVAILABLE", 503) from None
            query = ForecastReadQuery.model_validate(
                {
                    **binding.identity.model_dump(mode="json"),
                    "expected_source_result_hash": binding.expected_source_result_hash,
                }
            )
            if query.forecast_family != FORECAST_FAMILY or (
                query.source_kind == "OPERATIONAL_PEAK"
            ) != (query.hierarchy_level == "BASE"):
                raise AuthError("AUTHORITY_MISMATCH", 409)
            physical = (query.source_kind, query.run_id)
            if physical in queries and queries[physical] != query:
                raise AuthError("AUTHORITY_MISMATCH", 409)
            queries[physical] = query
        configuration = {
            "organizations": organizations,
            "publisher": self.auth.settings.local_auth_publisher_boundaries_json.get_secret_value(),
            "catalog": self.auth.settings.local_auth_simple_admin_catalog_json.get_secret_value(),
        }
        return (
            list(queries.values()),
            snapshots,
            digest({"grants": snapshots, "configuration": configuration}),
        )

    async def catalog(
        self, db: AsyncSession, principal: Principal, expected_directory: str | None = None
    ) -> Catalog:
        queries, grants, directory = await self.directory(db, principal)
        if expected_directory is not None and directory != expected_directory:
            raise AuthError("AUTHORITY_MISMATCH", 409)
        metadata = await repository.rows(db, queries) if queries else []
        if len(metadata) != len(queries):
            raise AuthError("SAVED_RUN_NOT_FOUND", 404)
        by_id = {(q.source_kind, q.run_id): q for q in queries}
        for row in metadata:
            query = by_id[(row["source_kind"], row["run_id"])]
            if (
                any(
                    row[k] != getattr(query, k)
                    for k in ForecastReadQuery.model_fields
                    if k != "expected_source_result_hash"
                )
                or row["source_result_hash"] != query.expected_source_result_hash
            ):
                raise AuthError("AUTHORITY_MISMATCH", 409)
            if row["daily_row_count"] < 0 or row["daily_row_count"] > 15:
                raise AuthError("AUTHORITY_MISMATCH", 409)
            if row["source_status"] not in {"completed", "COMPLETE", "INCOMPLETE_CHILD_COVERAGE"}:
                raise AuthError("AUTHORITY_MISMATCH", 409)
        approved = set(by_id)
        snapshot = digest(
            {"directory": directory, "metadata": [item(r, approved) for r in metadata]}
        )
        return Catalog(queries, grants, metadata, directory, snapshot)

    def claims(
        self,
        principal: Principal,
        catalog: Catalog,
        purpose: Literal["cursor", "selection"],
        **kwargs: Any,
    ) -> TokenClaims:
        instant = int(now().timestamp())
        return TokenClaims(
            version=1,
            purpose=purpose,
            principal=principal.principal_id,
            session=principal.session_id,
            auth_revision=principal.auth_revision,
            grant_revision=principal.grant_revision,
            grant_directory=catalog.directory,
            catalog_snapshot=catalog.snapshot,
            issued_at=instant,
            expires_at=instant + (900 if purpose == "cursor" else 300),
            **kwargs,
        )

    async def scope(self, db: AsyncSession, principal: Principal) -> tuple[dict[str, Any], Catalog]:
        catalog = await self.catalog(db, principal)
        entities = {
            (r["hierarchy_level"], r["entity_id"], r["entity_name"]) for r in catalog.metadata
        }
        return {
            "entities": [
                {"hierarchy_level": level, "entity_id": entity, "entity_name": name}
                for level, entity, name in sorted(entities)
            ],
            "data_types": sorted({g["resource_kind"] for g in catalog.grants}),
            "capabilities": sorted({g["capability"] for g in catalog.grants}),
            "organization_ids": sorted({g["organization_id"] for g in catalog.grants}),
            "grant_revision": principal.grant_revision,
            "catalog_snapshot": catalog.snapshot,
        }, catalog

    async def saved_runs(
        self, db: AsyncSession, principal: Principal, filters: Filters
    ) -> tuple[dict[str, Any], Catalog]:
        claims = self.signer.verify(filters.cursor, "cursor", principal) if filters.cursor else None
        filter_hash = digest(filters.signature_input())
        if claims is not None and (claims.filter_hash != filter_hash or claims.last_key is None):
            raise AuthError("INVALID_CONTEXT", 422)
        catalog = await self.catalog(db, principal, claims.grant_directory if claims else None)
        if not catalog.queries:
            raise AuthError("FORBIDDEN")
        if claims is not None and catalog.snapshot != claims.catalog_snapshot:
            raise AuthError("AUTHORITY_MISMATCH", 409)
        rows = await repository.rows(
            db, catalog.queries, filters=filters, last_key=claims.last_key if claims else None
        )
        page = rows[: filters.page_size]
        token = None
        if len(rows) > filters.page_size:
            token = self.signer.sign(
                self.claims(
                    principal,
                    catalog,
                    "cursor",
                    filter_hash=filter_hash,
                    last_key=repository.key(page[-1]),
                )
            )
        approved = {(q.source_kind, q.run_id) for q in catalog.queries}
        return {
            "items": [item(r, approved) for r in page],
            "next_cursor": token,
            "grant_revision": principal.grant_revision,
            "catalog_snapshot": catalog.snapshot,
        }, catalog

    async def selection(
        self, db: AsyncSession, principal: Principal, selection: Selection
    ) -> tuple[dict[str, Any], Catalog, ForecastReadQuery]:
        query = ForecastReadQuery.model_validate(
            {
                **selection.forecast_identity.model_dump(mode="json"),
                "expected_source_result_hash": selection.expected_source_result_hash,
            }
        )
        await authorize(
            self.auth, principal, query
        )  # Before any canonical or metadata business read.
        if selection.grant_revision != principal.grant_revision:
            raise AuthError("AUTHORITY_MISMATCH", 409)
        claims = (
            self.signer.verify(selection.handoff_token, "selection", principal)
            if selection.handoff_token
            else None
        )
        if claims and (
            claims.forecast_identity != selection.forecast_identity
            or claims.expected_source_result_hash != selection.expected_source_result_hash
        ):
            raise AuthError("FORBIDDEN")
        catalog = await self.catalog(db, principal, claims.grant_directory if claims else None)
        if catalog.snapshot != selection.catalog_snapshot or (
            claims and claims.catalog_snapshot != catalog.snapshot
        ):
            raise AuthError("AUTHORITY_MISMATCH", 409)
        source = await ForecastIntelligenceReadService(db).curve(query)
        token = self.signer.sign(
            self.claims(
                principal,
                catalog,
                "selection",
                forecast_identity=selection.forecast_identity,
                expected_source_result_hash=selection.expected_source_result_hash,
            )
        )
        return (
            {
                "forecast_identity": selection.forecast_identity.model_dump(mode="json"),
                "expected_source_result_hash": source.source_result_hash,
                "projection_hash": source.projection_hash,
                "handoff_token": token,
                "expires_in": 300,
                "authorization_required_on_consumption": True,
            },
            catalog,
            query,
        )
