# R2 execution workpaper

Base main: 68ed5691b5ee1163cc18e1ad1208146e3ebf82f3.
Previous PR607 head: 3be879c432a4393737bb0d2aaee5f9e7d4b02696.
Same branch, no force push, clean initial checkout.

1. Verified source 1:1 using only 2024–2025 farm/subfarm/factory columns.
2. Created Farm and Factory through canonical service; reused Dx; no coordinates.
3. Added regression tests before implementation. Four new cases initially failed
   at the old schema/resolver/ranker boundaries.
4. Implemented explicit farm identity mode, candidate loading and ranking without
   fabricated geo. Tested exact identity, unknown identity, conflicts, PIT cutoff,
   literature provenance, positive same-farm inference and geographic rejection.
5. Started PR code on loopback 8007 with the existing acceptance DB binding.
   Actual HTTP request: POST /planning/tasks; response 422, detail:
   parameter library version not found. This is not a completed inference run.
6. Independently verified resolved farm identity and read-only zero counts for
   parameter versions/observations, plans and maturity artifacts.
7. Checked current and retained V0.2 sources: header-only parameter templates,
   no recoverable authorized observations found. No default/demo database used.
8. No parameter creation, library activation, Task8/9, forecast, budget or TEST access.

Local verification uses synthetic unit fixtures only; business acceptance uses
normal API/database dependencies. PostgreSQL regression results are reported by
the final exact-head CI separately from locally skipped integration tests.
The final response/PR checks identify that CI run; no self-referential commit hash
is asserted inside this document.

INTERNAL_DATA_PRODUCT_BLOCKER=AUTHORIZED_PARAMETER_OBSERVATION_MATERIALIZATION_NOT_AVAILABLE

MISSING_EXTERNAL_BUSINESS_FACTS=NONE

FINAL_STOP_GATE=COORDINATOR_BANNA_PARAMETER_AUTHORITY_R2_REVIEW
