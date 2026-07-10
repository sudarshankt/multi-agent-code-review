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
