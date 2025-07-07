'use client'

import React from 'react'

interface QualityMetricsProps {
  metrics: {
    quality_trend?: Array<{ chapter: number; score: number; date: string }>
    average_quality?: number
    total_chapters?: number
    quality_distribution?: { excellent: number; good: number; fair: number; poor: number }
  } | null
}

export function QualityMetrics({ metrics }: QualityMetricsProps) {
  if (!metrics) {
    return (
      <div className="card">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Quality Metrics</h2>
        <div className="text-center py-8">
          <div className="animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-3/4 mx-auto mb-2"></div>
            <div className="h-4 bg-gray-200 rounded w-1/2 mx-auto"></div>
          </div>
        </div>
      </div>
    )
  }

  const getQualityColor = (score: number) => {
    if (score >= 80) return 'text-green-600'
    if (score >= 70) return 'text-blue-600'
    if (score >= 60) return 'text-yellow-600'
    return 'text-red-600'
  }

  return (
    <div className="card">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">Quality Metrics</h2>
      
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="text-center">
          <div className={`text-2xl font-bold ${getQualityColor(metrics.average_quality || 0)}`}>
            {metrics.average_quality?.toFixed(1) || '0.0'}
          </div>
          <div className="text-sm text-gray-500">Average Quality</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-gray-900">
            {metrics.total_chapters || 0}
          </div>
          <div className="text-sm text-gray-500">Total Chapters</div>
        </div>
      </div>

      {/* Quality Distribution */}
      {metrics.quality_distribution && (
        <div className="mb-6">
          <h3 className="text-sm font-medium text-gray-700 mb-3">Quality Distribution</h3>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">Excellent (80+)</span>
              <span className="px-2 py-1 text-xs bg-green-100 text-green-800 rounded">
                {metrics.quality_distribution.excellent}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">Good (70-79)</span>
              <span className="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded">
                {metrics.quality_distribution.good}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">Fair (60-69)</span>
              <span className="px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded">
                {metrics.quality_distribution.fair}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">Poor (&lt; 60)</span>
              <span className="px-2 py-1 text-xs bg-red-100 text-red-800 rounded">
                {metrics.quality_distribution.poor}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Quality Trend List */}
      {metrics.quality_trend && metrics.quality_trend.length > 0 ? (
        <div>
          <h3 className="text-sm font-medium text-gray-700 mb-3">Recent Quality Scores</h3>
          <div className="space-y-2 max-h-32 overflow-y-auto">
            {metrics.quality_trend.slice(-5).map((item) => (
              <div key={item.chapter} className="flex justify-between items-center text-sm">
                <span className="text-gray-600">Chapter {item.chapter}</span>
                <span className={`font-medium ${getQualityColor(item.score)}`}>
                  {item.score.toFixed(1)}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="text-center py-8 text-gray-500">
          <p>No quality data available yet</p>
          <p className="text-sm mt-1">Generate chapters to see quality scores</p>
        </div>
      )}
    </div>
  )
} 