import React, { useState } from 'react'
import { useNavigate } from '../hooks/useNavigate'
import { reviewAPI } from '../api/client'
import { Loader } from 'lucide-react'

export const TriggerReview: React.FC = () => {
  const navigate = useNavigate()
  const [prUrl, setPrUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      if (!prUrl.trim()) {
        throw new Error('Please enter a PR URL')
      }

      const response = await reviewAPI.createReview(prUrl)
      const reviewId = response.data.id
      navigate(`/review/${reviewId}`)
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Failed to create review')
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl p-8 w-full max-w-md">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Cap PR Review</h1>
        <p className="text-gray-600 mb-8">AI-powered PR analysis</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="prUrl" className="block text-sm font-medium text-gray-700 mb-2">
              GitHub PR URL
            </label>
            <input
              id="prUrl"
              type="text"
              value={prUrl}
              onChange={(e) => setPrUrl(e.target.value)}
              placeholder="https://github.com/owner/repo/pull/123"
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              disabled={loading}
            />
            <p className="text-xs text-gray-500 mt-1">
              Example: https://github.com/facebook/react/pull/1234
            </p>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-semibold py-2 px-4 rounded-lg transition flex items-center justify-center gap-2"
          >
            {loading && <Loader className="w-4 h-4 animate-spin" />}
            {loading ? 'Submitting...' : 'Analyze PR'}
          </button>
        </form>

        <div className="mt-8 pt-8 border-t border-gray-200">
          <p className="text-xs text-gray-500">
            This will analyze the PR using AI agents to detect security issues, bugs, style problems, and performance concerns.
          </p>
        </div>
      </div>
    </div>
  )
}
