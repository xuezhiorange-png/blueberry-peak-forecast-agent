from backend.app.actual_harvest_import.commit_models import (
    ActualHarvestCommitManifestModel,
)
from backend.app.actual_harvest_import.models import (
    ActualHarvestImportBatchModel,
    ActualHarvestImportRecordModel,
)
from backend.app.actual_harvest_import.validation_models import (
    ActualHarvestMappingPolicyRegistryModel,
    ActualHarvestMappingRegistryEntryModel,
    ActualHarvestMappingSnapshotModel,
    ActualHarvestValidationAttemptModel,
    ActualHarvestValidationErrorModel,
    ActualHarvestValidationLineageBasisMemberModel,
    ActualHarvestValidationLineageBasisModel,
    ActualHarvestValidationLineageEdgeModel,
    ActualHarvestValidationLineageNodeModel,
    ActualHarvestValidationMappingEvidenceModel,
    ActualHarvestValidationRecordModel,
    ActualHarvestValidationResultModel,
    ActualHarvestValidationRunModel,
)
from backend.app.models.analytics import (
    AnalyticsBuildRun,
    FactorySeasonPeakMetric,
    FactReceiptDaily,
)
from backend.app.models.baseline_backtest import BaselineBacktestResult, BaselineBacktestRun
from backend.app.models.core_forecast import (
    CoreForecastDailyRowModel,
    CoreForecastMetricModel,
    CoreForecastRunModel,
)
from backend.app.models.forecast_quality import (
    ModelBaselineComparisonModel,
    NaiveBaselineRunModel,
    QualityBreakdownResultModel,
    QualityEvaluationManifestModel,
    QualityEvaluationRunModel,
    QualityMetricResultModel,
)
from backend.app.models.harvest_state import (
    HarvestStateCohortTransitionRowModel,
    HarvestStateDailyMemberRowModel,
    HarvestStateDailyPoolRowModel,
    HarvestStateFutureArrivalRowModel,
    HarvestStateRun,
)
from backend.app.models.historical_import import FactReceiptRaw, IngestFile
from backend.app.models.master_data import Factory, Farm, Grade, Holiday, Season, Subfarm, Variety
from backend.app.models.maturity import (
    MaturityDailyPredictionModel,
    MaturityForecastRun,
    MaturityModelArtifact,
    MaturityModelRun,
)
from backend.app.models.planning import (
    AgroClimateZone,
    ClimateZoneImportRun,
    LocationReference,
    MinimalForecastTask,
    ParameterInferenceResult,
    ParameterInferenceRun,
    ParameterLibraryVersion,
    ParameterObservation,
)
from backend.app.models.production_plan import FarmSeasonVarietyPlan, ProductionPlanImportRun
from backend.app.models.residual_model import (
    ResidualModelArtifact,
    ResidualModelExecutionAttempt,
    ResidualModelManifestRow,
    ResidualModelPredictionRow,
    ResidualModelPredictionRun,
    ResidualModelTrainingRun,
)
from backend.app.models.rolling_backtest import (
    RollingBacktestAttempt,
    RollingBacktestAvailabilityAudit,
    RollingBacktestDagSnapshot,
    RollingBacktestNode,
    RollingBacktestOrchestrationSnapshot,
    RollingBacktestResolvedInput,
    RollingBacktestRun,
    RollingBacktestStageEvent,
)
from backend.app.models.task9_authority import (
    Task9AuthorityLifecycleEvent,
    Task9CapacityPoolDefinition,
    Task9CapacityPoolMember,
    Task9DailyCapacityAuthority,
    Task9HolidayCalendarDate,
    Task9HolidayCalendarVersion,
    Task9InitialInventoryCohort,
    Task9InitialInventorySnapshot,
    Task9MatureInventoryLossAuthority,
    Task9RunParameterPackage,
    Task9WeatherRuleConfigVersion,
)
from backend.app.models.trial import (
    CoreForecastMarketablePolicyEntryModel,
    CoreForecastMarketablePolicyModel,
    TrialForecastEvidenceModel,
    TrialResourceBindingModel,
)
from backend.app.models.weather import (
    BaseTemperatureSearchRun,
    LocationWeatherMapping,
    WeatherDailyObservation,
    WeatherFeatureRun,
    WeatherImportRun,
    WeatherSourceLocation,
)

__all__ = [
    "ActualHarvestCommitManifestModel",
    "ActualHarvestImportBatchModel",
    "ActualHarvestImportRecordModel",
    "ActualHarvestMappingPolicyRegistryModel",
    "ActualHarvestMappingRegistryEntryModel",
    "ActualHarvestMappingSnapshotModel",
    "ActualHarvestValidationAttemptModel",
    "ActualHarvestValidationErrorModel",
    "ActualHarvestValidationLineageBasisMemberModel",
    "ActualHarvestValidationLineageBasisModel",
    "ActualHarvestValidationLineageEdgeModel",
    "ActualHarvestValidationLineageNodeModel",
    "ActualHarvestValidationMappingEvidenceModel",
    "ActualHarvestValidationRecordModel",
    "ActualHarvestValidationResultModel",
    "ActualHarvestValidationRunModel",
    "AnalyticsBuildRun",
    "AgroClimateZone",
    "BaselineBacktestResult",
    "ClimateZoneImportRun",
    "BaselineBacktestRun",
    "CoreForecastDailyRowModel",
    "CoreForecastMarketablePolicyEntryModel",
    "CoreForecastMarketablePolicyModel",
    "CoreForecastMetricModel",
    "CoreForecastRunModel",
    "FactReceiptRaw",
    "FactReceiptDaily",
    "Factory",
    "FactorySeasonPeakMetric",
    "Farm",
    "FarmSeasonVarietyPlan",
    "Grade",
    "HarvestStateCohortTransitionRowModel",
    "HarvestStateDailyMemberRowModel",
    "HarvestStateDailyPoolRowModel",
    "HarvestStateFutureArrivalRowModel",
    "HarvestStateRun",
    "Holiday",
    "IngestFile",
    "LocationReference",
    "MaturityDailyPredictionModel",
    "MaturityForecastRun",
    "MaturityModelArtifact",
    "MaturityModelRun",
    "ModelBaselineComparisonModel",
    "MinimalForecastTask",
    "NaiveBaselineRunModel",
    "LocationWeatherMapping",
    "ParameterInferenceResult",
    "ParameterInferenceRun",
    "ParameterLibraryVersion",
    "ParameterObservation",
    "ProductionPlanImportRun",
    "QualityBreakdownResultModel",
    "QualityEvaluationManifestModel",
    "QualityEvaluationRunModel",
    "QualityMetricResultModel",
    "ResidualModelArtifact",
    "ResidualModelExecutionAttempt",
    "ResidualModelManifestRow",
    "ResidualModelPredictionRow",
    "ResidualModelPredictionRun",
    "ResidualModelTrainingRun",
    "RollingBacktestAttempt",
    "RollingBacktestAvailabilityAudit",
    "RollingBacktestDagSnapshot",
    "RollingBacktestNode",
    "RollingBacktestOrchestrationSnapshot",
    "RollingBacktestResolvedInput",
    "RollingBacktestRun",
    "RollingBacktestStageEvent",
    "S2MaterializedDatasetModel",
    "S2MaterializedMaterializableRowModel",
    "S2MaterializedPartitionModel",
    "Task9AuthorityLifecycleEvent",
    "Task9CapacityPoolDefinition",
    "Task9CapacityPoolMember",
    "Task9DailyCapacityAuthority",
    "Task9HolidayCalendarDate",
    "Task9HolidayCalendarVersion",
    "Task9InitialInventoryCohort",
    "Task9InitialInventorySnapshot",
    "Task9MatureInventoryLossAuthority",
    "Task9RunParameterPackage",
    "Task9WeatherRuleConfigVersion",
    "TrialForecastEvidenceModel",
    "TrialResourceBindingModel",
    "Season",
    "Subfarm",
    "Variety",
    "BaseTemperatureSearchRun",
    "WeatherDailyObservation",
    "WeatherFeatureRun",
    "WeatherImportRun",
    "WeatherSourceLocation",
]

_S2_MODEL_EXPORTS = {
    "S2MaterializedDatasetModel",
    "S2MaterializedMaterializableRowModel",
    "S2MaterializedPartitionModel",
}


def __getattr__(name: str):
    if name in _S2_MODEL_EXPORTS:
        from backend.app.s2_materialized_dataset.lane_d import service as lane_d_service

        return getattr(lane_d_service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
