import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
})

export interface Review {
  id: string
  status: string
  pr_number: number
  pr_title?: string
  pr_author?: string
  total_findings: number
  total_fixes: number
  created_at: string
  updated_at: string
  completed_at?: string
}

export interface Finding {
  id: string
  category: string
  severity: string
  confidence: string
  title: string
  description: string
  location: {
    file_path: string
    start_line?: number
    end_line?: number
    snippet?: string
  }
  suggestion?: string
  references: string[]
  cwe_id?: string
  agent_name?: string
  created_at: string
}

export interface ReviewDetail extends Review {
  findings_by_category: Record<string, Finding[]>
  fix_pr_url?: string
  proposed_fixes?: ProposedFix[]
  test_run?: TestRunSummary
}

export interface ProposedFix {
  id: string
  review_id: string
  category: string
  file_path: string
  finding_ids: string[]
  original_code: string
  fixed_code: string
  diff: string
  explanation: string
  status: 'pending' | 'approved' | 'rejected' | 'committed' | 'failed'
  commit_sha?: string
  error?: string
  created_at: string
}

export interface TestRunSummary {
  status: 'running' | 'passed' | 'failed' | 'skipped'
  tests_passed: number
  tests_failed: number
  skipped: boolean
  skip_reason: string
  output: string
  duration_seconds: number
  ran_at: string
}

export interface EvalMatchedPair {
  expected: { description: string; start_line: number; end_line: number; severity?: string }
  actual_title: string
  actual_description: string
  actual_start_line?: number
  similarity: number
}

export interface EvalCaseResult {
  file: string
  matched: EvalMatchedPair[]
  missed: { description: string; start_line: number; end_line: number; severity?: string }[]
  unexpected: string[]
}

export interface EvalAgentMetrics {
  agent_name: string
  true_positives: number
  false_positives: number
  false_negatives: number
  precision: number
  recall: number
  f1: number
  avg_similarity: number
  cases: EvalCaseResult[]
}

export interface EvalReport {
  generated_at: string
  agents: EvalAgentMetrics[]
}

export interface FixJudgeScore {
  resolved: boolean
  correctness: number
  safety: number
  minimality: number
  explanation_quality: number
  regression_risk: string
  notes: string
}

export interface FixCaseResult {
  model_label: string
  file: string
  category: string
  success: boolean
  syntax_valid?: boolean | null
  error?: string | null
  judge?: FixJudgeScore | null
}

export interface FixModelMetrics {
  model_label: string
  cases: number
  success_rate: number
  syntax_valid_rate: number
  resolved_rate: number
  avg_correctness: number
  avg_safety: number
  avg_minimality: number
  avg_explanation_quality: number
  case_results: FixCaseResult[]
}

export interface FixEvalReport {
  generated_at: string
  models: FixModelMetrics[]
}

export interface PipelineCaseResult {
  finding: EvalCaseResult
  fix_attempted: boolean
  fix_success: boolean
  syntax_valid?: boolean | null
  fix_error?: string | null
  judge?: FixJudgeScore | null
}

export interface PipelineMetrics {
  agent_name: string
  cases: number
  true_positives: number
  false_positives: number
  false_negatives: number
  precision: number
  recall: number
  f1: number
  avg_similarity: number
  fix_attempted: number
  fix_success_rate: number
  syntax_valid_rate: number
  resolved_rate: number
  avg_correctness: number
  avg_safety: number
  avg_minimality: number
  avg_explanation_quality: number
  case_results: PipelineCaseResult[]
}

export interface E2EReport {
  generated_at: string
  agents: PipelineMetrics[]
}

export const evalAPI = {
  getLatest: () => api.get<EvalReport>('/eval/latest'),
  getLatestFix: () => api.get<FixEvalReport>('/eval/latest-fix'),
  getLatestE2E: () => api.get<E2EReport>('/eval/latest-e2e'),
}

export const reviewAPI = {
  createReview: (prUrl: string) =>
    api.post<Review>('/reviews', { pr_url: prUrl }),

  getReview: (id: string) =>
    api.get<ReviewDetail>(`/reviews/${id}`),

  listReviews: (page = 1, pageSize = 10) =>
    api.get<{ items: Review[]; total: number; page: number; page_size: number }>(
      '/reviews',
      { params: { page, page_size } }
    ),
}

export const fixesAPI = {
  listFixes: (reviewId: string) =>
    api.get<{ review_id: string; proposed_fixes: ProposedFix[]; total: number }>(`/reviews/${reviewId}/fixes`),

  reviewFix: (reviewId: string, fixId: string, action: 'approve' | 'reject') =>
    api.patch<{ fix_id: string; status: string }>(`/reviews/${reviewId}/fixes/${fixId}`, { action }),

  applyApprovedFixes: (reviewId: string) =>
    api.post<{ committed: number; failed: number; commit_shas: Record<string, string> }>(
      `/reviews/${reviewId}/fixes/apply`
    ),

  runTests: (reviewId: string, fixIds?: string[]) =>
    api.post<{ status: string; message: string }>(
      `/reviews/${reviewId}/fixes/run-tests`,
      { fix_ids: fixIds ?? [] }
    ),

  getTestResults: (reviewId: string) =>
    api.get<TestRunSummary>(`/reviews/${reviewId}/fixes/test-results`),

  fixTests: (reviewId: string) =>
    api.post<{ status: string; message: string }>(`/reviews/${reviewId}/fixes/fix-tests`),
}

export interface TestFixProgress {
  type: 'test_fix_iteration' | 'test_fix_file' | 'test_fix_committed' | 'test_fix_complete'
  iteration?: number
  max?: number
  status?: string
  files?: string[]
  file_path?: string
  explanation?: string
  commit_sha?: string
  tests_passed?: number
  tests_failed?: number
  message?: string
}

export default api
