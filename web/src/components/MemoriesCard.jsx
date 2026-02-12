const frameworkNames = {
  'none': '',
  'agent-framework': 'Agent Framework',
  'foundry': 'Foundry',
  'mem0': 'Mem0',
  'hindsight': 'Hindsight',
  'cognee': 'Cognee',
}

function Skeleton({ className = '' }) {
  return <div className={`animate-pulse rounded-md bg-gray-200/80 ${className}`} />
}

export function MemoriesCard({ memories, memoryFramework, isLoading = false, onRefresh }) {

  const frameworkLabel = frameworkNames[memoryFramework] || ''
  const title = frameworkLabel ? `${frameworkLabel} Memories` : 'Memories'

  const renderMessage = (message) => {
    if (message == null) return null
    if (typeof message === "string" || typeof message === "number") {
      return message
    }
    if (Array.isArray(message)) {
      return (
        <ul className="list-disc pl-5 space-y-1">
          {message.map((item, idx) => (
            <li key={idx}>{renderMessage(item)}</li>
          ))}
        </ul>
      )
    }
    if (typeof message === "object") {
      return (
        <ul className="space-y-1">
          {Object.entries(message).map(([key, value]) => (
            <li key={key}>
              <span className="font-semibold">{key}:</span> {renderMessage(value)}
            </li>
          ))}
        </ul>
      )
    }
    return String(message)
  }

  return (
    <div className="bg-white rounded-lg shadow-md p-6 md:col-span-2">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-bold text-lg">{title}</h3>
        <div className="flex items-center gap-2">
          {isLoading ? (
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-gray-600" />
              <span>Updating…</span>
            </div>
          ) : onRefresh ? (
            <button
              onClick={onRefresh}
              className="inline-flex items-center gap-1 rounded-md border border-gray-300 bg-white px-2.5 py-1 text-xs font-medium text-gray-700 shadow-sm hover:bg-gray-100 hover:border-gray-400 active:bg-gray-200 active:scale-95 transition-all cursor-pointer"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clipRule="evenodd" />
              </svg>
              Refresh
            </button>
          ) : null}
        </div>
      </div>
      <div className="space-y-2">
        {!memories ? (
          <div className="space-y-3">
            <div className="space-y-2">
              <Skeleton className="h-4 w-3/5" />
              <Skeleton className="h-4 w-11/12" />
              <Skeleton className="h-4 w-4/5" />
            </div>
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-4/5" />
            </div>
            <div className="text-xs text-gray-500">
              Memories will appear here after you chat.
            </div>
          </div>
        ) : memories.message ? (
          <div className="text-sm text-gray-700">
            {renderMessage(memories.message)}
          </div>
        ) : memories.memories && Array.isArray(memories.memories) ? (
          <div className="space-y-2">
            {memories.memories.map((memory, idx) => (
              <div key={idx} className="text-sm text-gray-700 p-2 bg-gray-50 rounded">
                {memory}
              </div>
            ))}
          </div>
        ) : (
          <pre className="text-xs overflow-auto max-h-64 bg-gray-50 p-3 rounded">
            {JSON.stringify(memories, null, 2)}
          </pre>
        )}
      </div>
    </div>
  )
}
