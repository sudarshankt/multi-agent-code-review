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

export const evalAPI = {
  getLatest: () => api.get<EvalReport>('/eval/latest'),
  getLatestFix: () => api.get<FixEvalReport>('/eval/latest-fix'),
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

export default api
