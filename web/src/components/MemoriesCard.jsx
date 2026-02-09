const frameworkNames = {
  'none': '',
  'agent-framework': 'Agent Framework',
  'mem0': 'Mem0',
  'hindsight': 'Hindsight',
  'cognee': 'Cognee',
}

function Skeleton({ className = '' }) {
  return <div className={`animate-pulse rounded-md bg-gray-200/80 ${className}`} />
}

export function MemoriesCard({ memories, memoryFramework, onDeleteMemories: _onDeleteMemories, deleteMemoriesDisabled: _deleteMemoriesDisabled, isLoading = false }) {

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
        {isLoading && (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-gray-300 border-t-gray-600" />
            <span>Updating…</span>
          </div>
        )}
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
      {/*<div className="mt-6 pt-4 border-t">
        <button
          onClick={onDeleteMemories}
          disabled={deleteMemoriesDisabled}
          className="px-3 py-2 text-sm bg-red-500 text-white rounded hover:bg-red-600 disabled:bg-gray-300 disabled:cursor-not-allowed"
        >
          Delete Memories
        </button>
      </div>*/}
    </div>
  )
}
