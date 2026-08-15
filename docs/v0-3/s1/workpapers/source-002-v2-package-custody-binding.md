# Source 002 v2 package durable custody binding

## Result

```text
TASK=SOURCE_002_V2_PACKAGE_APPROVED_DURABLE_STORAGE_BINDING
RESULT=CUSTODY_BINDING_COMPLETED_REVIEW_REQUIRED
BASE_MAIN_SHA=dcb1456489e753b6a03f58941bd635b97d61de58
BINDING_REFERENCE=source-002-v2-package-custody-binding-v1
STORAGE_PROVIDER=GOOGLE_DRIVE
APPROVED_DURABLE_STORAGE_SELECTED=true
DURABLE_EXTERNAL_COPY_CREATED=true
OPAQUE_REFERENCE_BOUND=true
HANDOFF_COMPLETE=true
CUSTODY_BINDING_ACCEPTED=false
```

The exact Source 002 v2 derived-value package was stored as a non-Git raw JSON file in separately approved durable storage. The provider-side object remained unshared at the time of binding. No provider file ID, Drive URL, folder ID, plaintext locator, credential, or token is recorded in Git.

## Exact file identity

```text
PACKAGE_ID=source-002-attestation-derived-values-v2-rederived
PACKAGE_CANONICAL_SHA256=9220ec20bd9d2fb3e466ad8936382327e045a4ba09df99a0f06d42b0aa5da19f
FILE_BYTE_COUNT=9944
FILE_BYTES_SHA256=0ce08cf071816e80d6144337200d8fa1f1be0c7a76f025b78b79cf01829fcf59
RAW_FILE_READBACK_PERFORMED=true
READBACK_BYTE_COUNT=9944
READBACK_SHA256=0ce08cf071816e80d6144337200d8fa1f1be0c7a76f025b78b79cf01829fcf59
READBACK_EXACT_BYTES_MATCH=true
```

The readback hash was recomputed from the raw stored file bytes after upload. The package was not converted into a Google Docs object.

## Opaque locator binding

```text
OPAQUE_REFERENCE_ID=source-002-v2-package-custody-binding-v1
REFERENCE_STATUS=BOUND_TO_APPROVED_EXTERNAL_STORAGE
STORAGE_LOCATOR_HASH=b8808e32eec032060894b9839dae7969bccad50ba4bf0c399fe19c5b16958eb9
STORAGE_LOCATOR_HASH_ALGORITHM=SHA256
STORAGE_LOCATOR_HASH_CANONICALIZATION=UTF8("GOOGLE_DRIVE_FILE_ID:" + PRIVATE_PROVIDER_FILE_ID)
PLAINTEXT_PRIVATE_LOCATOR_IN_GIT=false
PROVIDER_FILE_ID_IN_GIT=false
PROVIDER_URL_IN_GIT=false
```

The locator preimage remains out of Git. A reviewer can verify the recorded hash format and binding payload, while full locator replay requires separately authorized access to the private provider identifier.

## Binding hash attestation

The binding hash is SHA-256 over recursively sorted compact UTF-8 JSON containing exactly:

```json
{
  "binding_reference": "source-002-v2-package-custody-binding-v1",
  "file_byte_count": 9944,
  "file_bytes_sha256": "0ce08cf071816e80d6144337200d8fa1f1be0c7a76f025b78b79cf01829fcf59",
  "package_canonical_sha256": "9220ec20bd9d2fb3e466ad8936382327e045a4ba09df99a0f06d42b0aa5da19f",
  "storage_locator_hash": "b8808e32eec032060894b9839dae7969bccad50ba4bf0c399fe19c5b16958eb9",
  "storage_provider": "GOOGLE_DRIVE"
}
```

```text
BINDING_HASH=d11d2cae5e0e47e7b32c4dd9c625cfa5f00961e4c613ff7a08a9681a4407a6d2
BINDING_HASH_ALGORITHM=SHA256
```

## Governance boundary

This record closes only the external-storage custody-binding execution. It does **not** issue or accept Source Authority.

```text
CUSTODY_BINDING_COMPLETE=true
CUSTODY_BINDING_ACCEPTED=false
INDEPENDENT_REVIEW_REQUIRED=true

FINAL_FIELD_BINDING_AUTHORIZED=false
FINAL_SOURCE_ATTESTATION_AUTHORIZED=false
SOURCE_AUTHORITY_ACCEPTANCE_AUTHORIZED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
CANONICAL_GATE_STATUS_CHANGED=false

S1_REMAINING_05_COMPLETE=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

Next action after this branch reaches successful exact-head CI is an independent review of the custody-binding evidence only.
