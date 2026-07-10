import React, { useEffect, useState } from 'react'
import { TriggerReview } from './pages/TriggerReview'
import { ReviewDetailPage } from './pages/ReviewDetail'

type Page = 'trigger' | 'detail'

export const App: React.FC = () => {
  const [page, setPage] = useState<Page>('trigger')
  const [reviewId, setReviewId] = useState<string | null>(null)

  useEffect(() => {
    const handlePopState = () => {
      const path = window.location.pathname
      if (path.startsWith('/review/')) {
        const id = path.split('/')[2]
        setReviewId(id)
        setPage('detail')
      } else {
        setPage('trigger')
        setReviewId(null)
      }
    }

    // Initial route
    handlePopState()

    // Listen for route changes
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navigation */}
      <nav className="bg-white shadow">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <a href="/" className="text-2xl font-bold text-blue-600">
            Cap PR Review
          </a>
          {page === 'detail' && (
            <button
              onClick={() => {
                window.history.pushState({}, '', '/')
                window.dispatchEvent(new PopStateEvent('popstate'))
              }}
              className="text-blue-600 hover:text-blue-700 font-medium"
            >
              ← Back
            </button>
          )}
        </div>
      </nav>

      {/* Content */}
      <div className="py-8">
        {page === 'trigger' && <TriggerReview />}
        {page === 'detail' && reviewId && <ReviewDetailPage reviewId={reviewId} />}
      </div>
    </div>
  )
}

export default App
