import { useState, useEffect } from 'react'
import { UserCard } from './components/UserCard'
import { Banner } from './components/Banner'
import { UsageStats } from './components/UsageStats'
import { ClearChatCard } from './components/ClearChatCard'

const STORAGE_KEY = 'amq:userName'
const AGENT_URL = 'http://localhost:8000/'

function App() {
  const [name, setName] = useState(() => localStorage.getItem(STORAGE_KEY) || '')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [memoryFramework, setMemoryFramework] = useState('none')
  const [usage, setUsage] = useState(null)

  // This isn't important yet, but later we can use it for session management.
  const handleLogin = (userName) => {
    setName(userName.toLowerCase())
    localStorage.setItem(STORAGE_KEY, userName.toLowerCase())
  }

  const handleLogout = () => {
    setName('')
    localStorage.removeItem(STORAGE_KEY)
    setMessages([])
    setUsage(null)
  }

  const handleClearChat = () => {
    setMessages([])
    setUsage(null)
  }

  // This is the function that sends user messages to the agent and processes responses.
  const sendMessage = async () => {
    if (!input.trim() || isLoading) return

    // Add user message to state.
    const userMessage = { role: 'user', content: input }
    const updatedMessages = [...messages, userMessage]
    setMessages(updatedMessages)
    setInput('')
    setIsLoading(true)

    // This creates a new agent instance with the updated message history
    // and runs it to get a response.
    try {
      // Select endpoint based on memory framework
      const endpoint = memoryFramework === 'none' ? AGENT_URL : `${AGENT_URL}${memoryFramework}`

      console.log(`Using agent URL: ${endpoint}`)

      // Send the message to the agent using a standard HTTP Post.
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username: name.toLowerCase(),
          messages: updatedMessages.filter(m => m.role !== 'activity')  // Only send chat messages
        })
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data = await response.json()
      console.log('Agent response data:', data)

      // Add assistant response(s) to state.
      if (data.message) {
        const assistantMessage = { role: 'assistant', content: data.message }
        setMessages(prev => [...prev, assistantMessage])
      }

      // Capture usage info if available.
      if (data.usage) {
        setUsage(data.usage)
      }

    } catch (error) {
      console.error('Agent error:', error)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex h-screen w-full">
      <MainContent
        name={name}
        onLogin={handleLogin}
        onLogout={handleLogout}
        usage={usage}
        onClearChat={handleClearChat}
      />
      <ChatInterface
        messages={messages}
        input={input}
        onInputChange={setInput}
        onSendMessage={sendMessage}
        isLoading={isLoading}
        name={name}
        memoryFramework={memoryFramework}
        onMemoryFrameworkChange={setMemoryFramework}
      />
    </div>
  )
}

// Main content area that shows login, welcome, or activity component
function MainContent({ name, onLogin, onLogout, usage, onClearChat }) {
  return (
    <div className="flex-1 flex flex-col overflow-y-auto" style={{ backgroundImage: 'url(/images/resort_image.png)', backgroundSize: 'cover', backgroundPosition: 'center', backgroundAttachment: 'fixed' }}>
      {!name ? (
        <div className="flex-1 flex items-center justify-center p-4">
          <UserCard onLogin={onLogin} onLogout={onLogout} />
        </div>
      ) : (
        <div className="w-full max-w-6xl mx-auto px-4 pt-6">
          <Banner />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">

            {/* User Card and Activity Cards flow naturally in the grid */}
            <UserCard name={name} onLogin={onLogin} onLogout={onLogout} />
            <UsageStats usage={usage} />
            <ClearChatCard onClearChat={onClearChat} />
          </div>
          <div className="mt-6"></div>
        </div>
      )}
    </div>
  )
}

function ChatInterface({ messages, input, onInputChange, onSendMessage, isLoading, name, memoryFramework, onMemoryFrameworkChange }) {
  // Only show text messages in chat (not activities)
  const chatMessages = messages.filter(msg => msg.role !== 'activity')

  return (
    <div className="w-[400px] border-l flex flex-col">
      <div className="p-4 border-b">
        <h2 className="font-bold text-lg">Agent Interface</h2>
        <select
          className="mt-2 w-full p-2 border rounded text-sm"
          value={memoryFramework}
          onChange={(e) => onMemoryFrameworkChange(e.target.value)}
        >
          <option value="none">None</option>
          <option value="agent-framework">Agent Framework</option>
          <option value="mem0">Mem0</option>
          <option value="hindsight">Hindsight</option>
          <option value="cognee">Cognee</option>
        </select>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {chatMessages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}
        {isLoading && (
          <div className="p-3 rounded bg-gray-100 mr-8">
            <div className="font-semibold text-sm mb-1">Agent</div>
            <div className="flex items-center gap-2">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
              </div>
            </div>
          </div>
        )}
      </div>

      <ChatInput
        value={input}
        onChange={onInputChange}
        onSend={onSendMessage}
        disabled={isLoading || !name}
      />
    </div>
  )
}

function MessageBubble({ message }) {
  const isUser = message.role === 'user'

  return (
    <div className={`p-3 rounded ${isUser ? 'bg-blue-100 ml-8' : 'bg-gray-100 mr-8'}`}>
      <div className="font-semibold text-sm mb-1">
        {isUser ? 'You' : 'Agent'}
      </div>
      <div>{message.content}</div>
    </div>
  )
}

function ChatInput({ value, onChange, onSend, disabled }) {
  return (
    <div className="p-4 border-t">
      <div className="flex gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && !disabled && onSend()}
          placeholder="Message the agent..."
          className="flex-1 p-2 border rounded disabled:bg-gray-100 disabled:cursor-not-allowed"
          disabled={disabled}
        />
        <button
          onClick={onSend}
          disabled={disabled}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed"
        >
          Send
        </button>
      </div>
    </div>
  )
}

export default App