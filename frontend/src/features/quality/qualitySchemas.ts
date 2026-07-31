import { z } from "zod";

export const qualityReportSchema = z
  .object({ report_id: z.string(), status: z.string() })
  .passthrough();
export const qualityComparisonSchema = z
  .object({ report_id: z.string(), status: z.string() })
  .passthrough();
export type QualityReport = z.infer<typeof qualityReportSchema>;
