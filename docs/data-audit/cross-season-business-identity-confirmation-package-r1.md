# Cross-season Business Identity Confirmation Package R1

Task: `CROSS_SEASON_BUSINESS_IDENTITY_CONFIRMATION_PACKAGE_R1`
Base: `ed68512b5c8db1fd2f4b4097d187e129ab389997`

## Purpose and boundary

This package turns the frozen audit's 263 manual issues into exact, evidence-linked relation groups and a prioritized set of business questions. It does not decide any mapping.

The private question pack keeps source names, per-group quantities, issue IDs, mapping evidence, and decision fields. The repository contains only aggregate counts, hashes, policy, and sanitized examples.

## Grouping and selection

- Full relation groups: 294
- Selected business questions: 40
- Selected-band counts: A=16, B=12, C=12
- Four required high-risk composite groups are included; exact labels and answers remain in the private package.
- Grouping uses exact source labels and frozen canonical/candidate Base identity. No fuzzy matching, name-similarity acceptance, or subjective score is used.
- Quantities are rolled up by unique (season, source farm label). Reused-subfarm parent links are non-additive; selected totals use a set union.

## Coverage and impact

- Original issues accounted for: 263 / 263.
- Selected issues covered: 49 (0.1863117870722433460076045627 of the issue list).
- Current mapped quantity under review: 32841938.353 kg of 53777730.97 kg identified as reviewable.
- Unresolved quantity in selected questions: 20535320.157 kg (0.7171625173878772100389610702 of source-wide unresolved quantity 28634123.59 kg).
- Coverage quantities use full-source kg; each selected relation also shows the separately bounded business-window kg in the private pack.

The amount summaries are mechanical descriptions of the frozen audit. They do not imply a mapping is wrong or that unresolved quantity should be assigned.

## Frozen model-impact check

For accepted source identities, group-level impact flags are bound at Base-season grain to the published V0.7 S1 scopes and preserved S3 Model A/B training and comparison scopes. Unresolved labels are not represented as if they had entered the models. Relation names and Base IDs remain private.
S3 used a frozen V0.5 member-mapping hash that differs from the current R2 authority. Therefore S3 impact flags mean Base-season cohort overlap only; exact source-label membership in S3 rows is not proven.
- Replay verification: PASS.

## Example question shape (sanitized)

> Across two seasons, a source name is accepted in one season, unresolved in another, and a related member-set change is recorded. The business question asks whether names refer to the same operation in each season; it does not recommend an answer.

## Decision and authority status

All business decision cells are blank. A YES, NO, PARTIAL, OUT_OF_SCOPE, or UNKNOWN answer must be applied only by a separately authorized data-authority correction. This package changes no mapping authority, Base registry, model, V0.7 evidence, or release artifact.

Private package manifest SHA256: `bb38dbea3748948f0b72d7f5e192591805155eda79c46541c992b6a1d88cc0fd`
