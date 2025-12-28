import { useState, useEffect } from 'react'
import { HttpAgent } from '@ag-ui/client'
import { LoginCard } from './components/LoginCard'
import { WeatherCard } from './components/WeatherCard'
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

const STORAGE_KEY = 'amq:userName'
const AGENT_URL = 'http://localhost:5197/'

// This where we register components that can be rendered for activities.
// This isn't chat messages, but rather rich content the agent can show.
const componentRegistry = {
  WeatherCard: WeatherCard
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
    
    // Handle array of activities
    if (Array.isArray(parsed)) {
      return parsed.filter(item => item.role === 'activity' && item.activityType)
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
  const [agent] = useState(() => new HttpAgent({ url: AGENT_URL, components: componentRegistry }))
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')

  // Get the most recent activity message to display in main content
  const latestActivity = [...messages].reverse().find(msg => msg.role === 'activity')

  // This isn't important yet, but later we can use it for session management.
  const handleLogin = (userName) => {
    setName(userName)
    localStorage.setItem(STORAGE_KEY, userName)
  }

  // This is the function that sends user messages to the agent and processes responses.
  const sendMessage = async () => {
    if (!input.trim()) return

    // Add user message to state.
    const userMessage = { role: 'user', content: input }
    setMessages(prev => [...prev, userMessage])
    setInput('')

    // This creates a new agent instance with the updated message history
    // and runs it to get a response.
    try {
      const agentWithMessages = new HttpAgent({
        url: AGENT_URL,
        initialMessages: [...messages, userMessage],
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
    }
  }

  return (
    <div className="flex h-screen w-full">
      <MainContent 
        name={name} 
        onLogin={handleLogin}
        activity={latestActivity}
      />
      <ChatInterface 
        messages={messages} 
        input={input} 
        onInputChange={setInput}
        onSendMessage={sendMessage}
      />
    </div>
  )
}

// Main content area that shows login, welcome, or activity component
function MainContent({ name, onLogin, activity }) {
  return (
    <div className="flex-1 flex items-center justify-center p-4">
      {!name ? (
        <LoginCard onLogin={onLogin} />
      ) : activity ? (
        <div className="w-full max-w-2xl">
          <ActivityComponent message={activity} />
        </div>
      ) : (
        <Card className="mx-auto w-[350px]">
          <CardHeader className="text-center">
            <CardTitle>Welcome, {name}!</CardTitle>
            <CardDescription>Ask me about the weather!</CardDescription>
          </CardHeader>
        </Card>
      )}
    </div>
  )
}

function ChatInterface({ messages, input, onInputChange, onSendMessage }) {
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
      </div>

      <ChatInput 
        value={input} 
        onChange={onInputChange}
        onSend={onSendMessage}
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

function ChatInput({ value, onChange, onSend }) {
  return (
    <div className="p-4 border-t">
      <div className="flex gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && onSend()}
          placeholder="Message the agent..."
          className="flex-1 p-2 border rounded"
        />
        <button
          onClick={onSend}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Send
        </button>
      </div>
    </div>
  )
}

export default App