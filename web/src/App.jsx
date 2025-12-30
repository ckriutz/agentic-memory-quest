import { useState, useEffect } from 'react'
import { HttpAgent } from '@ag-ui/client'
import { LoginCard } from './components/LoginCard'
import { WeatherCard } from './components/WeatherCard'
import { AppointmentCard } from './components/AppointmentCard'
import { UserCard } from './components/UserCard'
import { Banner } from './components/Banner'
import { Footer } from './components/Footer'
import { PrescriptionCard } from './components/PrescriptionCard'

const STORAGE_KEY = 'amq:userName'
const AGENT_URL = 'http://localhost:5197/'

// This where we register components that can be rendered for activities.
// This isn't chat messages, but rather rich content the agent can show.
const componentRegistry = {
  WeatherCard: WeatherCard,
  PrescriptionCard: PrescriptionCard
}

// Parse activity messages from assistant message content.
// Messages are jusst standard chat mesages, but if it's an activity,
// we parse out the JSON and connect it to the component that will render.
function parseActivityMessage(msg) {
  if (msg.role !== 'assistant' || !msg.content || typeof msg.content !== 'string') {
    return msg
  }

  const text = msg.content.trim()
  if (!text.startsWith('{') && !text.startsWith('[')) {
    return msg
  }

  try {
    const parsed = JSON.parse(text)

    // Handle array of messages (activities and text messages)
    if (Array.isArray(parsed)) {
      return parsed
    }

    // Handle single activity
    if (parsed.role === 'activity' && parsed.activityType) {
      return parsed
    }
  } catch {
    // Invalid JSON, return original
  }

  return msg
}

// Filter out intermediate tool call messages
function isDisplayableMessage(msg) {
  return (msg.role === 'assistant' && !msg.toolCalls) || msg.role === 'activity'
}

function App() {
  const [name, setName] = useState(() => localStorage.getItem(STORAGE_KEY) || '')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  // Get all activities, keyed by activityType. Later ones overwrite earlier ones.
  const activities = messages
    .filter(msg => msg.role === 'activity')
    .reduce((map, activity) => {
      map[activity.activityType] = activity
      return map
    }, {})

  // This isn't important yet, but later we can use it for session management.
  const handleLogin = (userName) => {
    setName(userName.toLowerCase())
    localStorage.setItem(STORAGE_KEY, userName.toLowerCase())
  }

  const handleLogout = () => {
    setName('')
    localStorage.removeItem(STORAGE_KEY)
    setMessages([])
  }

  // This is the function that sends user messages to the agent and processes responses.
  const sendMessage = async () => {
    if (!input.trim() || isLoading) return

    // Add user message to state.
    const userMessage = { role: 'user', content: input }
    setMessages(prev => [...prev, userMessage])
    setInput('')
    setIsLoading(true)

    // This creates a new agent instance with the updated message history
    // and runs it to get a response.
    try {
      const agentWithMessages = new HttpAgent({
        url: AGENT_URL,
        initialMessages: [
          {
            role: 'system',
            content: `You are assisting user: ${name.toLowerCase()}`
          },
          ...messages,
          userMessage
        ],
        components: componentRegistry
      })

      // Run the agent to get a response
      const result = await agentWithMessages.runAgent()

      // Transform and filter messages - flatten array results
      const newMessages = (result.newMessages || [])
        .flatMap(msg => {
          const parsed = parseActivityMessage(msg)
          // If parsed result is an array, return it directly; otherwise wrap in array
          return Array.isArray(parsed) ? parsed : [parsed]
        })
        .filter(isDisplayableMessage)

      if (newMessages.length > 0) {
        setMessages(prev => [...prev, ...newMessages])
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
        activities={activities}
      />
      <ChatInterface
        messages={messages}
        input={input}
        onInputChange={setInput}
        onSendMessage={sendMessage}
        isLoading={isLoading}
        name={name}
      />
    </div>
  )
}

// Main content area that shows login, welcome, or activity component
function MainContent({ name, onLogin, onLogout, activities }) {
  return (
    <div className="flex-1 flex flex-col overflow-y-auto">
      {!name ? (
        <div className="flex-1 flex items-center justify-center p-4">
          <LoginCard onLogin={onLogin} />
        </div>
      ) : (
        <div className="w-full max-w-6xl mx-auto px-4 pt-6">
          <Banner />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {/* Appointment Card - Takes 2 columns on larger screens */}
            <AppointmentCard className="lg:col-span-2" />

            {/* User Card and Activity Cards flow naturally in the grid */}
            <UserCard name={name} onLogout={onLogout} />

            {Object.values(activities).map(activity => (
              <ActivityComponent key={activity.activityType} message={activity} />
            ))}
          </div>
          <div className="mt-6"></div>
        </div>
      )}
    </div>
  )
}

function ChatInterface({ messages, input, onInputChange, onSendMessage, isLoading, name }) {
  // Only show text messages in chat (not activities)
  const chatMessages = messages.filter(msg => msg.role !== 'activity')

  return (
    <div className="w-[400px] border-l flex flex-col">
      <div className="p-4 border-b">
        <h2 className="font-bold text-lg">Agent Interface</h2>
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

function ActivityComponent({ message }) {
  const Component = componentRegistry[message.activityType]

  if (!Component) {
    return <div className="text-red-500">Unknown component: {message.activityType}</div>
  }

  return <Component {...message.content} />
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