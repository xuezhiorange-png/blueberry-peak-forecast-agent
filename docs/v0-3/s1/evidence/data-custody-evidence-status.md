# Data Custody Evidence Status

## Current evidence state

    EVIDENCE_RECORD_ID=V0_3_S1_DATA_CUSTODY_EVIDENCE
    EVIDENCE_RECORD_STATUS=BLOCKED
    CURRENT_DATA_CUSTODY_STATUS=BLOCKED
    CUSTODY_RECORD_STATUS=NOT_ISSUED
    CUSTODY_POLICY_VERSION=NOT_PROVIDED
    STORAGE_TYPE=NOT_PROVIDED
    ACCESS_OWNER_ROLE=NOT_PROVIDED
    SOURCE_OWNER_ROLE=NOT_PROVIDED
    APPROVED_USAGE_PURPOSE=NOT_PROVIDED
    LEAST_PRIVILEGE_SCOPE=NOT_PROVIDED
    AUTHORIZED_ROLE_SET=NOT_PROVIDED
    CREDENTIAL_REFERENCE_POLICY=NOT_PROVIDED
    RETENTION_POLICY_VERSION=NOT_PROVIDED
    RETENTION_PERIOD_OR_RULE=NOT_PROVIDED
    WITHDRAWAL_POLICY_VERSION=NOT_PROVIDED
    VOID_PROPAGATION_POLICY_VERSION=NOT_PROVIDED
    DOWNSTREAM_PROPAGATION_TARGETS=NOT_PROVIDED
    EXTERNAL_OBJECT_BINDING_HASH=NOT_ISSUED
    CUSTODY_RECORD_HASH=NOT_ISSUED
    INDEPENDENT_REVIEW_STATUS=NOT_STARTED

No source-specific custody proof was supplied. This record therefore contains
policy-field absence states only; it does not name storage, credentials,
private locators, people, or source objects.

## Required lifecycle evidence

The future custody record must prove least-privilege access, retention,
withdrawal and void propagation, downstream propagation to the source cohort,
future split and snapshot manifests, and acceptance records. Withdrawal must
not delete existing evidence, and a replacement source must receive a new
identity and new hashes.

No custody record is accepted by this package, and no data access is
authorized.

## Authority

    AUTHORITY_CONTRACT=docs/v0-3/s1/split-holdout-and-custody-contract.md
    CUSTODY_SCHEMA=docs/v0-3/s1/schemas/source-cohort-manifest.schema.json
