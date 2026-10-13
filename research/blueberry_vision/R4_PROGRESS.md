# R4 recovery checkpoint

TASK_ID=BLUEBERRY_VISION_R4_QUALIFIED_REAL_GT_AND_BASELINE_EVALUATION
BRANCH=research/blueberry-vision-r4-qualified-real-gt
SOURCE_R3_HEAD=b0b6f8c9e368317af8cd927db701315b6c961317
BASE_MAIN_SHA=c35524174865785164fe4529f35067037ccddc2a
PARENT_PR=720; GRANDPARENT_PR=719 (both unchanged OPEN_DRAFT)

M0 complete in this checkpoint: fresh fetch; clean isolated worktree; repository push
permission confirmed; 634 inherited tests freshly passed (0 skipped); R3 artifact
index/frozen source/model and original A/B prediction file + canonical hashes verified.
3697 inherited tracked files inventoried; none changed. 100 semi-auto candidate boxes,
675 semi-auto polygons and 500 manual **damage-region** boxes do not qualify as
single-fruit human GT. See evidence/r4/m0_preflight.json and m0_regression.json.

Next M1: current official source/license review; BlueberryDCM company-associated
noncommercial applicability unresolved; no restricted dataset download.
Current data: 8 authorized public real images, zero qualified GT, no real metrics.
No human reviewers assigned. No production/actual/Harvest State/parent PR changes.
Each stage ordinary commit/push/remote verification; own commit hash is supplied by
next checkpoint and final receipt, never self-embedded. Resume from fetched R4 HEAD.
