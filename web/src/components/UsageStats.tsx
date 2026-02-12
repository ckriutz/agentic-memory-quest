import { Card, CardContent, CardHeader, CardTitle } from './ui/card'

interface UsageStats {
  inputTokenCount?: number
  outputTokenCount?: number
  totalTokenCount?: number
}

export function UsageStats({ usage }: { usage?: UsageStats }) {
  if (!usage) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle>Non-Memory Token Usage</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-sm text-gray-600">Input:</span>
            <span className="font-mono text-sm font-semibold">{usage.inputTokenCount?.toLocaleString() || 0}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-sm text-gray-600">Output:</span>
            <span className="font-mono text-sm font-semibold">{usage.outputTokenCount?.toLocaleString() || 0}</span>
          </div>
          <div className="pt-2 border-t border-gray-200">
            <div className="flex justify-between items-center">
              <span className="text-sm font-semibold text-gray-700">Total:</span>
              <span className="font-mono text-base font-bold text-blue-600">{usage.totalTokenCount?.toLocaleString() || 0}</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}