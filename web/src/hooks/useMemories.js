import { useCallback, useState } from 'react'

export function useMemories({ username, getEndpoint }) {
  const [memories, setMemories] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)

  const fetchMemories = useCallback(
    async (messages) => {
      if (!username) return

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
    [username, getEndpoint]
  )

  const deleteMemories = useCallback(async () => {
    if (!username || isDeleting) return
    setIsDeleting(true)

    try {
      const endpoint = getEndpoint()
      const deleteEndpoint = `${endpoint}/delete/${username.toLowerCase()}`

      const response = await fetch(deleteEndpoint, { method: 'DELETE' })
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      let deleteData = null
      try {
        deleteData = await response.json()
      } catch {
        deleteData = { message: 'Memories deleted.' }
      }

      setMemories(deleteData)
    } catch (error) {
      console.error('Error deleting memories:', error)
    } finally {
      setIsDeleting(false)
    }
  }, [username, getEndpoint, isDeleting])

  return {
    memories,
    setMemories,
    isMemoriesLoading: isLoading,
    isDeletingMemories: isDeleting,
    fetchMemories,
    deleteMemories,
  }
}
