# Q2A-I3 Spreadsheet Parser Implementation

## Scope

Q2A-I3 implements only the transport boundary for user-supplied actual-harvest
observations:

```text
CSV/XLSX bytes
    -> strict transport checks
    -> ActualHarvestImportRecordInput
    -> deterministic diagnostics
```

It does not persist rows, resolve farm/season identity, select revision winners,
seal or validate a batch, commit labels, expose an API, or run a backtest. The
source remains an observed `FARM_PICK` weight in kilograms. Receipt, arrival,
capacity, model output, plan, and inventory values are not accepted as a
replacement source.

## Canonical field authority

The parser derives its importable header order and required-field set from
`ActualHarvestImportRecordInput.model_fields`. It excludes only the two
diagnostic provenance fields, `source_row_number` and `source_sheet_name`, from
file headers. The parser supplies those values from physical source location.
The server-generated `import_received_at` and `ingested_at` fields are not
accepted in a file and are absent from generated templates.

CSV and XLSX use `STRICT_CANONICAL_V1`: exact spelling is required, case folding
and fuzzy matching are forbidden, and unknown, missing, duplicate, or colliding
headers fail closed. Records are sorted by a stable canonical identity key, not
by a mapping or filesystem iteration order. `canonical_record_hash` excludes
transport-only row/sheet provenance.

## CSV policy

CSV is decoded as UTF-8 (with an optional UTF-8 BOM), requires one header row,
and rejects malformed row widths and malformed CSV syntax. A completely empty
data row is ignored only with a deterministic diagnostic. A non-empty invalid
row blocks the parse; no invalid row is silently skipped.

## XLSX policy

XLSX must contain exactly one sheet named `actual_harvest`. The parser rejects
case-insensitive duplicate canonical sheets, extra sheets, formulas, merged
cells, hidden rows, macros/active content, external links, unsafe ZIP paths,
and excessive workbook size or compression ratio. The workbook is loaded with
`data_only=False` and `keep_links=False`; formulas are never evaluated and
cached formula values are never treated as source facts.

The policy is versioned as `q2a-i3-spreadsheet-policy-v1` and centralizes file,
sheet, row, column, cell-text, uncompressed-size, and compression-ratio limits.
Date-only cells and explicitly formatted Excel serial dates are handled by the
versioned date policy. Ambiguous locale text and datetime cells with a time
component are rejected. `source_recorded_at` and other source timestamps must
be explicit timezone-aware ISO-8601 strings.

## Decimal and error contract

`actual_harvest_quantity_kg` is parsed as `Decimal` only. Native floats, bools,
scientific notation, non-finite values, negative values, more than six decimal
places, and more than twelve integer digits fail. Explicit zero is preserved;
missing quantity is not converted to zero. No rounding is performed at the
transport boundary. The existing I1 `NUMERIC(18,6)` validation remains the
schema authority.

Parser-specific error codes were added to the existing I1 validation enum only
where no equivalent existed. Existing codes are reused for required fields,
unknown fields, dates, datetimes, decimals, negative quantities, and record
status. Errors carry channel, row, sheet, and canonical-field identity plus a
bounded detail; they never include a raw row, credentials, or unrestricted user
content.

## Templates and dependency

CSV and XLSX templates are generated from the same schema-derived header
function. The XLSX sheet is exactly `actual_harvest`, contains no formula,
macro, external link, or sample value, and has no server-generated fields.
CSV bytes are stable. XLSX logical sheet/header content is stable; ZIP metadata
is treated as library-level output and is not claimed byte-identical.

`openpyxl` is used because the repository had no XLSX-capable maintained
workbook library. It is declared and pinned in the project dependency and CI
constraints. No Office automation, desktop Excel, macro execution, dataframe
framework, network parser, or external-link loading is used.

## Explicit exclusions

Q2A-I3 does not implement persistence, API, identity mapping, season resolution,
revision validation or winner selection, sealing, validation/commit lifecycle,
label snapshots, backtest execution, forecast/model behavior, Q2A-I4 through
I8, Q2B, or Q3.
