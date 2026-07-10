import React from 'react'
import { Loader, CheckCircle, XCircle, Clock } from 'lucide-react'

interface StatusBadgeProps {
  status: string
}

const statusConfig: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  pending: { color: 'bg-gray-100 text-gray-800', icon: <Clock className="w-4 h-4" />, label: 'Pending' },
  fetching: { color: 'bg-blue-100 text-blue-800', icon: <Loader className="w-4 h-4 animate-spin" />, label: 'Fetching' },
  analyzing: { color: 'bg-blue-100 text-blue-800', icon: <Loader className="w-4 h-4 animate-spin" />, label: 'Analyzing' },
  fixing: { color: 'bg-yellow-100 text-yellow-800', icon: <Loader className="w-4 h-4 animate-spin" />, label: 'Fixing' },
  testing: { color: 'bg-yellow-100 text-yellow-800', icon: <Loader className="w-4 h-4 animate-spin" />, label: 'Testing' },
  completed: { color: 'bg-green-100 text-green-800', icon: <CheckCircle className="w-4 h-4" />, label: 'Completed' },
  failed: { color: 'bg-red-100 text-red-800', icon: <XCircle className="w-4 h-4" />, label: 'Failed' },
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const config = statusConfig[status] || statusConfig.pending
  return (
    <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-semibold ${config.color}`}>
      {config.icon}
      {config.label}
    </span>
  )
}
