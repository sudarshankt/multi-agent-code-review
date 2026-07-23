import { useEffect, useState } from 'react'

export interface SSEEvent {
  type: string
  [key: string]: any
}

export interface ReviewStage {
  name: string
  status: 'pending' | 'in_progress' | 'completed'
  timestamp?: Date
  details?: any
}

export const STAGES: ReviewStage[] = [
  { name: 'Initialized', status: 'pending' },
  { name: 'PR Fetched', status: 'pending' },
  { name: 'Analyzing', status: 'pending' },
  { name: 'Aggregating', status: 'pending' },
  { name: 'Fixing', status: 'pending' },
  { name: 'Completed', status: 'pending' },
]

const STAGE_MAP: Record<string, number> = {
  'INITIALIZED': 0,
  'PR_FETCHED': 1,
  'ANALYSIS_COMPLETE': 2,
  'FIXING_START': 3,
  'FIXING_COMPLETE': 4,
  'COMPLETED': 5,
}

export const useSSE = (reviewId: string | null, enabled = true, reviewStatus?: string) => {
  const [events, setEvents] = useState<SSEEvent[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [stages, setStages] = useState<ReviewStage[]>(STAGES)
  const [currentStage, setCurrentStage] = useState<string>('pending')

  // Initialize stages based on current review status
  useEffect(() => {
    if (!reviewId || !enabled) return

    const now = new Date()
    const newStages: ReviewStage[] = STAGES.map(stage => ({
      ...stage,
      status: 'pending' as const,
    }))

    // Initialize stages based on review status to handle page refresh mid-review
    if (reviewStatus === 'completed' || reviewStatus === 'failed') {
      // All stages complete
      newStages.forEach((stage: ReviewStage) => {
        stage.status = 'completed'
        stage.timestamp = now
      })
      setCurrentStage('COMPLETED')
    } else if (reviewStatus === 'fixing') {
      // Analysis done, fixing in progress: stages 0-3 complete, 4 in progress
      for (let i = 0; i <= 3; i++) {
        newStages[i].status = 'completed'
        newStages[i].timestamp = now
      }
      if (newStages[4]) {
        newStages[4].status = 'in_progress'
      }
      setCurrentStage('FIXING_START')
    } else if (reviewStatus === 'analyzing') {
      // PR fetched, analyzing in progress: stages 0-1 complete, 2 in progress
      for (let i = 0; i <= 1; i++) {
        newStages[i].status = 'completed'
        newStages[i].timestamp = now
      }
      if (newStages[2]) {
        newStages[2].status = 'in_progress'
      }
      setCurrentStage('PR_FETCHED')
    } else if (reviewStatus === 'fetching') {
      // Just started: stage 0 complete, 1 in progress
      newStages[0].status = 'completed'
      newStages[0].timestamp = now
      if (newStages[1]) {
        newStages[1].status = 'in_progress'
      }
      setCurrentStage('INITIALIZED')
    }

    setStages(newStages)
  }, [reviewId, reviewStatus, enabled])

  // SSE connection - keep it open and don't reset when status changes
  useEffect(() => {
    if (!reviewId || !enabled) return

    // Skip SSE if already completed (stages already pre-populated)
    if (reviewStatus === 'completed' || reviewStatus === 'failed') {
      return
    }

    setIsConnected(true)
    setError(null)
    setEvents([])
    const initialStages: ReviewStage[] = STAGES.map(stage => ({
      ...stage,
      status: 'pending' as const,
    }))
    setStages(initialStages)

    const eventSource = new EventSource(`/api/v1/sse/reviews/${reviewId}`)

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setEvents((prev) => [...prev, data])

        // Update stages based on event type
        if (data.type === 'stage_update' && data.stage) {
          const stageIndex = STAGE_MAP[data.stage]
          if (stageIndex !== undefined) {
            setStages((prev) => {
              const updated = prev.map(stage => ({ ...stage }))
              const now = new Date()
              // Mark all stages up to this one as completed
              for (let i = 0; i <= stageIndex; i++) {
                if (updated[i]) {
                  updated[i].status = 'completed'
                  if (!updated[i].timestamp) {
                    updated[i].timestamp = now
                  }
                }
              }
              // Mark next stage as in_progress if exists
              if (updated[stageIndex + 1]) {
                updated[stageIndex + 1].status = 'in_progress'
              }
              return updated
            })
            setCurrentStage(data.stage)
          }
        } else if (data.type === 'agent_completed') {
          setStages((prev) => {
            const updated = prev.map(stage => ({ ...stage }))
            if (updated[2]) updated[2].status = 'in_progress'
            return updated
          })
        }
        // Fix-review and test-gate events (proposed_fix, fix_status_changed,
        // fixes_committed, test_run_update) are intentionally NOT handled here.
        // They're consumed directly from `events` by ReviewDetail, which is
        // the single source of truth for fix state — avoiding a second copy
        // of the list that would need merging (and could go stale/out of sync).
      } catch (e) {
        console.error('Failed to parse SSE event:', e)
      }
    }

    eventSource.onerror = () => {
      setIsConnected(false)
      setError('Connection lost')
      eventSource.close()
    }

    return () => {
      eventSource.close()
    }
  }, [reviewId, enabled])

  return { events, isConnected, error, stages, currentStage }
}
