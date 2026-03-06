import { useCallback, useState } from 'react'

export function useMemories({ username, getEndpoint, memoryFramework }) {
  const [memories, setMemories] = useState(null)
  const [isLoading, setIsLoading] = useState(false)

  const fetchMemories = useCallback(
    async (messages) => {
      if (!username) return
      // Skip fetching for the generic (no-memory) agent
      if (memoryFramework === 'none') {
        setMemories({ message: 'No memory — the generic agent does not use memory. Select a memory framework to see memories.' })
        return
      }

      setIsLoading(true)
      try {
        const endpoint = getEndpoint()
        const memoriesEndpoint = `${endpoint}/memories`

        const response = await fetch(memoriesEndpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            username: username.toLowerCase(),
            messages: (messages || []).filter(m => m.role !== 'activity'),
          }),
        })

        if (response.ok) {
          const data = await response.json()
          setMemories(data)
        }
      } catch (error) {
        console.error('Error fetching memories:', error)
      } finally {
        setIsLoading(false)
      }
    },
    [username, getEndpoint, memoryFramework]
  )

  return {
    memories,
    setMemories,
    isMemoriesLoading: isLoading,
    fetchMemories,
  }
}
