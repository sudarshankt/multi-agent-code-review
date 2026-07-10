import React from 'react'
import { CheckCircle2, Circle, Clock } from 'lucide-react'
import { ReviewStage } from '../hooks/useSSE'

interface ProgressStagesProps {
  stages: ReviewStage[]
}

export const ProgressStages: React.FC<ProgressStagesProps> = ({ stages }) => {
  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-6">Review Progress</h3>
      <div className="space-y-4">
        {stages.map((stage, idx) => (
          <div key={idx} className="flex items-center gap-4">
            <div className="relative">
              {stage.status === 'completed' && (
                <CheckCircle2 className="w-6 h-6 text-green-600 flex-shrink-0" />
              )}
              {stage.status === 'in_progress' && (
                <Clock className="w-6 h-6 text-blue-600 flex-shrink-0 animate-pulse" />
              )}
              {stage.status === 'pending' && (
                <Circle className="w-6 h-6 text-gray-300 flex-shrink-0" />
              )}

              {/* Connecting line */}
              {idx < stages.length - 1 && (
                <div
                  className={`absolute top-6 left-2.5 w-0.5 h-4 ${
                    stage.status === 'completed' ? 'bg-green-600' : 'bg-gray-300'
                  }`}
                />
              )}
            </div>

            <div className="flex-1">
              <p
                className={`font-medium ${
                  stage.status === 'completed'
                    ? 'text-green-900'
                    : stage.status === 'in_progress'
                      ? 'text-blue-900'
                      : 'text-gray-500'
                }`}
              >
                {stage.name}
              </p>
              {stage.timestamp && (
                <p className="text-xs text-gray-500">
                  {stage.timestamp.toLocaleTimeString()}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
