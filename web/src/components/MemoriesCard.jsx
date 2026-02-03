const frameworkNames = {
  'none': '',
  'agent-framework': 'Agent Framework',
  'mem0': 'Mem0',
  'hindsight': 'Hindsight',
  'cognee': 'Cognee',
}

export function MemoriesCard({ memories, memoryFramework, onDeleteMemories, deleteMemoriesDisabled }) {
  if (!memories) return null

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
      <h3 className="font-bold text-lg mb-4">{title}</h3>
      <div className="space-y-2">
        {memories.message ? (
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
      <div className="mt-6 pt-4 border-t">
        <button
          onClick={onDeleteMemories}
          disabled={deleteMemoriesDisabled}
          className="px-3 py-2 text-sm bg-red-500 text-white rounded hover:bg-red-600 disabled:bg-gray-300 disabled:cursor-not-allowed"
        >
          Delete Memories
        </button>
      </div>
    </div>
  )
}
