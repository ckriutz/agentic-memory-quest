import { useState, useEffect, useRef, useCallback } from 'react'
import { UserCard } from './components/UserCard'
import { Banner } from './components/Banner'
import { UsageStats } from './components/UsageStats'
import { ClearChatCard } from './components/ClearChatCard'
import { GitHubRepoCard } from './components/GitHubRepoCard'
import { MemoriesCard } from './components/MemoriesCard'
import { useMemories } from './hooks/useMemories'

const STORAGE_KEY = 'amq:userName'
// In production this is proxied by nginx (see web/nginx/default.conf.template).
// In development, we call the FastAPI server directly.
const AGENT_URL = import.meta.env.DEV ? 'http://localhost:8000/' : '/api/'

function App() {
  const [name, setName] = useState(() => localStorage.getItem(STORAGE_KEY) || '')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [memoryFramework, setMemoryFramework] = useState('none')
  const [memoryMode, setMemoryMode] = useState('standard') // 'none' | 'standard' | 'hot-cold'
  const [usage, setUsage] = useState(null)
  const [timing, setTiming] = useState(null)
  const [comparison, setComparison] = useState(null) // { none, standard, hot_cold }
  const [isComparing, setIsComparing] = useState(false)
  const inFlightControllerRef = useRef(null)
  const getEndpoint = useCallback(
    () => (memoryFramework === 'none' ? AGENT_URL : `${AGENT_URL}${memoryFramework}`),
    [memoryFramework]
  )

  const {
    memories,
    setMemories,
    isMemoriesLoading,
    fetchMemories,
  } = useMemories({ username: name, getEndpoint, memoryFramework })

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
    setTiming(null)
    setMemories(null)
  }

  const handleClearChat = () => {
    setMessages([])
    setUsage(null)
    setTiming(null)
    setComparison(null)
    setMemories(null)
  }

  const handleMemoryFrameworkChange = (nextFramework) => {
    // If a request is in-flight, abort it so a late response can't re-populate chat.
    if (inFlightControllerRef.current) {
      inFlightControllerRef.current.abort()
      inFlightControllerRef.current = null
    }

    setMemoryFramework(nextFramework)
    // 'none' framework has no memory; others default to 'standard'
    if (nextFramework === 'none') {
      setMemoryMode('none')
    } else {
      setMemoryMode('standard')
    }
    handleClearChat()
    setInput('')
    setIsLoading(false)
  }

  // This is the function that sends user messages to the agent and processes responses.
  const sendMessage = async () => {
    if (!input.trim() || isLoading) return

    // Ensure only one in-flight request at a time.
    if (inFlightControllerRef.current) {
      inFlightControllerRef.current.abort()
    }
    const controller = new AbortController()
    inFlightControllerRef.current = controller
    let didAbort = false

    // Add user message to state.
    const userMessage = { role: 'user', content: input }
    const updatedMessages = [...messages, userMessage]
    setMessages(updatedMessages)
    setInput('')
    setIsLoading(true)

    // This creates a new agent instance with the updated message history
    // and runs it to get a response.
    try {
      const endpoint = getEndpoint()

      console.log(`Using agent URL: ${endpoint}`)

      // Send the message to the agent using a standard HTTP Post.
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        signal: controller.signal,
        body: JSON.stringify({
          username: name.toLowerCase(),
          messages: updatedMessages.filter(m => m.role !== 'activity' && m.role !== 'error'),  // Only send chat messages
          memory_mode: memoryFramework === 'none' ? 'none' : memoryMode,
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

      // Capture timing info if available.
      if (data.timing_ms) {
        setTiming(data.timing_ms)
      }

    } catch (error) {
      if (error?.name === 'AbortError') {
        didAbort = true
        return
      }
      console.error('Agent error:', error)
      setMessages(prev => [...prev, { role: 'error', content: `Something went wrong: ${error.message}` }])
    } finally {
      setIsLoading(false)
      if (inFlightControllerRef.current === controller) {
        inFlightControllerRef.current = null
      }
      // Fetch memories after successful response (separate from chat)
      if (!didAbort) {
        await fetchMemories(updatedMessages)
      }
    }
  }

  // Run the same last user message through all 3 memory modes in parallel.
  const runComparison = async () => {
    if (memoryFramework === 'none' || messages.length === 0 || isComparing) return
    setIsComparing(true)
    setComparison(null)
    // Find the last user message
    const lastUserMsg = [...messages].reverse().find(m => m.role === 'user')
    if (!lastUserMsg) { setIsComparing(false); return }
    const payload = {
      username: name.toLowerCase(),
      messages: [lastUserMsg],
      query: memoryFramework, // tells server which agent to use
      memory_mode: 'hot-cold', // ignored by /compare, but keeps schema valid
    }
    try {
      const response = await fetch(`${AGENT_URL}compare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      setComparison(data)
    } catch (err) {
      console.error('Compare error:', err)
    } finally {
      setIsComparing(false)
    }
  }

  return (
    <div className="flex h-screen w-full">
      <MainContent
        name={name}
        onLogin={handleLogin}
        onLogout={handleLogout}
        usage={usage}
        timing={timing}
        comparison={comparison}
        isComparing={isComparing}
        onCompare={runComparison}
        onClearChat={handleClearChat}
        memories={memories}
        memoryFramework={memoryFramework}
        memoryMode={memoryMode}
        isMemoriesLoading={isMemoriesLoading}
        onRefreshMemories={() => fetchMemories(messages)}
        hasMessages={messages.length > 0}
      />
      <ChatInterface
        messages={messages}
        input={input}
        onInputChange={setInput}
        onSendMessage={sendMessage}
        isLoading={isLoading}
        name={name}
        memoryFramework={memoryFramework}
        memoryMode={memoryMode}
        onMemoryFrameworkChange={handleMemoryFrameworkChange}
        onMemoryModeChange={setMemoryMode}
      />
    </div>
  )
}

// Main content area that shows login, welcome, or activity component
function MainContent({ name, onLogin, onLogout, usage, timing, comparison, isComparing, onCompare, onClearChat, memories, memoryFramework, memoryMode, isMemoriesLoading, onRefreshMemories, hasMessages }) {
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
            <TimingCard timing={timing} memoryMode={memoryMode} memoryFramework={memoryFramework} />
            <ClearChatCard onClearChat={onClearChat} />
            <GitHubRepoCard />
            <MemoriesCard
              memories={memories}
              memoryFramework={memoryFramework}
              isLoading={isMemoriesLoading}
              onRefresh={onRefreshMemories}
            />
          </div>

          {/* Side-by-side comparison section */}
          {memoryFramework !== 'none' && (
            <ComparisonPanel
              comparison={comparison}
              isComparing={isComparing}
              onCompare={onCompare}
              hasMessages={hasMessages}
              memoryFramework={memoryFramework}
            />
          )}

          <div className="mt-6"></div>
        </div>
      )}
    </div>
  )
}

function ChatInterface({ messages, input, onInputChange, onSendMessage, isLoading, name, memoryFramework, memoryMode, onMemoryFrameworkChange, onMemoryModeChange }) {
  // Only show text messages in chat (not activities)
  const chatMessages = messages.filter(msg => msg.role !== 'activity' && msg.role !== 'error')
  const errorMessages = messages.filter(msg => msg.role === 'error')
  const messagesEndRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages, isLoading])

  const showMemoryToggle = memoryFramework !== 'none'

  return (
    <div className="w-[400px] border-l flex flex-col">
      <div className="p-4 border-b">
        <h2 className="font-bold text-lg">Agent Interface</h2>
        <select
          className="mt-2 w-full p-2 border rounded text-sm"
          value={memoryFramework}
          onChange={(e) => onMemoryFrameworkChange(e.target.value)}
        >
          <option value="none">None (No Memory)</option>
          <option value="agent-framework">Agent Framework</option>
          <option value="foundry">Foundry</option>
          <option value="mem0">Mem0</option>
          <option value="hindsight">Hindsight</option>
          <option value="cognee">Cognee</option>
        </select>

        {showMemoryToggle && (
          <div className="mt-3 flex items-center gap-3">
            <span className="text-xs font-medium text-gray-600">Memory Mode:</span>
            <div className="flex bg-gray-100 rounded-lg p-0.5">
              <button
                onClick={() => onMemoryModeChange('standard')}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-all ${
                  memoryMode === 'standard'
                    ? 'bg-white text-blue-700 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                Standard
              </button>
              <button
                onClick={() => onMemoryModeChange('hot-cold')}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-all ${
                  memoryMode === 'hot-cold'
                    ? 'bg-white text-orange-700 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                Hot/Cold
              </button>
            </div>
          </div>
        )}

        {memoryFramework === 'none' && (
          <p className="mt-2 text-xs text-gray-400">No memory — the agent forgets everything between messages.</p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.filter(msg => msg.role !== 'activity').map((msg, i) => (
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
        <div ref={messagesEndRef} />
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
  const isError = message.role === 'error'

  if (isError) {
    return (
      <div className="p-3 rounded bg-red-50 border border-red-200 mr-8">
        <div className="font-semibold text-sm mb-1 text-red-600">Error</div>
        <div className="text-red-700 text-sm">{message.content}</div>
      </div>
    )
  }

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
          onKeyDown={(e) => e.key === 'Enter' && !disabled && onSend()}
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

function ComparisonPanel({ comparison, isComparing, onCompare, hasMessages, memoryFramework }) {
  const modes = [
    { key: 'none', label: 'No Memory', color: 'gray', bg: 'bg-gray-50', border: 'border-gray-200', badge: 'bg-gray-200 text-gray-700', desc: 'Raw LLM, no memory' },
    { key: 'standard', label: 'Standard', color: 'blue', bg: 'bg-blue-50', border: 'border-blue-200', badge: 'bg-blue-100 text-blue-700', desc: 'Memory built into agent (2+ LLM calls)' },
    { key: 'hot_cold', label: 'Hot/Cold', color: 'orange', bg: 'bg-orange-50', border: 'border-orange-200', badge: 'bg-orange-100 text-orange-700', desc: '1 LLM call + external memory I/O' },
  ]

  // Rank by agent response time (llm), not total — memory I/O is a separate concern
  let fastest = null, slowest = null
  const agentTimes = {}
  if (comparison) {
    modes.forEach(m => {
      agentTimes[m.key] = comparison[m.key]?.timing_ms?.llm ?? Infinity
    })
    const entries = Object.entries(agentTimes)
    fastest = entries.reduce((a, b) => a[1] < b[1] ? a : b)[0]
    slowest = entries.reduce((a, b) => a[1] > b[1] ? a : b)[0]
  }

  // Find the max agent time for the relative bar widths
  const maxAgent = comparison ? Math.max(...Object.values(agentTimes).filter(v => v < Infinity), 1) : 1

  return (
    <div className="mt-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-white font-bold text-lg drop-shadow-lg">Side-by-Side Comparison</h3>
        <button
          onClick={onCompare}
          disabled={isComparing || !hasMessages}
          className="px-4 py-2 bg-purple-600 text-white text-sm font-medium rounded-lg hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors shadow-md"
        >
          {isComparing ? (
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Comparing…
            </span>
          ) : 'Compare All Modes'}
        </button>
      </div>

      {!comparison && !isComparing && (
        <div className="bg-white/90 backdrop-blur rounded-lg p-6 text-center text-gray-500 text-sm">
          Send a message in chat, then click <strong>Compare All Modes</strong> to see how No Memory, Standard, and Hot/Cold perform side by side.
        </div>
      )}

      {isComparing && !comparison && (
        <div className="grid grid-cols-3 gap-3">
          {modes.map(m => (
            <div key={m.key} className="bg-white/90 backdrop-blur rounded-lg p-4 animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-1/2 mb-3" />
              <div className="h-3 bg-gray-200 rounded w-full mb-2" />
              <div className="h-3 bg-gray-200 rounded w-3/4" />
            </div>
          ))}
        </div>
      )}

      {comparison && (
        <div className="grid grid-cols-3 gap-3">
          {modes.map(m => {
            const data = comparison[m.key]
            if (!data) return (
              <div key={m.key} className="bg-white/90 backdrop-blur rounded-lg border p-4">
                <span className={`text-xs font-semibold px-2 py-0.5 rounded ${m.badge}`}>{m.label}</span>
                <p className="mt-2 text-sm text-gray-400">Not available</p>
              </div>
            )
            const t = data.timing_ms || {}
            const agentTime = t.llm ?? 0
            const hasMemoryIO = (t.memory_retrieve > 0) || (t.memory_enqueue > 0)
            const memoryIO = (t.memory_retrieve ?? 0) + (t.memory_enqueue ?? 0)
            const isFastest = m.key === fastest
            const isSlowest = m.key === slowest && fastest !== slowest
            return (
              <div key={m.key} className={`bg-white/95 backdrop-blur rounded-lg border ${isFastest ? 'border-green-400 ring-2 ring-green-200' : isSlowest ? 'border-red-300' : 'border-gray-200'} p-4 transition-all`}>
                <div className="flex items-center justify-between mb-1">
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded ${m.badge}`}>{m.label}</span>
                  {isFastest && <span className="text-[10px] font-bold text-green-600 bg-green-50 px-1.5 py-0.5 rounded">FASTEST</span>}
                  {isSlowest && <span className="text-[10px] font-bold text-red-500 bg-red-50 px-1.5 py-0.5 rounded">SLOWEST</span>}
                </div>
                <p className="text-[10px] text-gray-400 mb-3">{m.desc}</p>

                {/* Agent response time — the primary comparable metric */}
                <div className="flex items-baseline justify-between mb-1">
                  <span className="text-xs font-medium text-gray-700">Agent Response</span>
                  <span className="font-mono font-bold text-lg text-gray-900">{agentTime}<span className="text-xs font-normal text-gray-500">ms</span></span>
                </div>

                {/* Relative bar — width proportional to max agent time across modes */}
                <div className="h-3 rounded-full overflow-hidden bg-gray-100 mb-3">
                  <div
                    className={`h-full rounded-full transition-all ${isFastest ? 'bg-green-500' : isSlowest ? 'bg-red-400' : 'bg-blue-500'}`}
                    style={{ width: `${Math.max((agentTime / maxAgent) * 100, 2)}%` }}
                  />
                </div>

                {/* Memory I/O — only shown for hot/cold where it's an actual separate operation */}
                {hasMemoryIO ? (
                  <div className="border-t border-gray-100 pt-2 space-y-1">
                    <div className="text-[10px] font-medium text-gray-400 uppercase tracking-wide">Memory I/O (separate)</div>
                    {t.memory_retrieve > 0 && (
                      <div className="flex justify-between text-xs">
                        <span className="text-gray-500">Retrieve</span>
                        <span className="font-mono text-green-600">{t.memory_retrieve}ms</span>
                      </div>
                    )}
                    {t.memory_enqueue > 0 && (
                      <div className="flex justify-between text-xs">
                        <span className="text-gray-500">Enqueue</span>
                        <span className="font-mono text-orange-600">{t.memory_enqueue}ms</span>
                      </div>
                    )}
                    <div className="flex justify-between text-xs border-t border-dashed border-gray-200 pt-1">
                      <span className="text-gray-500">Wall Clock Total</span>
                      <span className="font-mono text-gray-500">{t.total}ms</span>
                    </div>
                  </div>
                ) : (
                  m.key === 'standard' && (
                    <div className="border-t border-gray-100 pt-2">
                      <p className="text-[10px] text-gray-400 italic">Memory is handled inline by the agent — retrieval + storage happen inside the LLM call chain.</p>
                    </div>
                  )
                )}

                {/* Truncated response preview */}
                <p className="mt-3 text-xs text-gray-600 line-clamp-3 leading-relaxed">
                  {data.message || '—'}
                </p>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function TimingCard({ timing, memoryMode, memoryFramework }) {
  const modeLabels = {
    'none': 'No Memory',
    'standard': 'Standard Memory',
    'hot-cold': 'Hot/Cold Memory',
  }
  const modeDescs = {
    'none': 'Raw LLM, no memory',
    'standard': 'Memory built into agent (2+ LLM calls)',
    'hot-cold': '1 LLM call + external memory I/O',
  }

  const hasMemoryIO = timing && ((timing.memory_retrieve > 0) || (timing.memory_enqueue > 0))

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h3 className="font-bold text-lg mb-1">Response Timing</h3>
      <div className="text-xs font-medium text-gray-500 mb-1">
        Mode: <span className={`font-semibold ${memoryMode === 'hot-cold' ? 'text-orange-600' : memoryMode === 'standard' ? 'text-blue-600' : 'text-gray-600'}`}>
          {modeLabels[memoryMode] || memoryMode}
        </span>
      </div>
      <p className="text-[10px] text-gray-400 mb-3">{modeDescs[memoryMode] || ''}</p>
      {!timing ? (
        <p className="text-sm text-gray-400">Send a message to see timing data.</p>
      ) : (
        <div className="space-y-2">
          <div className="flex justify-between items-baseline">
            <span className="text-sm font-semibold">Agent Response</span>
            <span className="font-mono font-bold text-lg text-gray-900">{timing.llm ?? '—'}<span className="text-xs font-normal text-gray-500">ms</span></span>
          </div>
          {timing.llm > 0 && (
            <div className="h-3 rounded-full overflow-hidden bg-gray-100">
              <div
                className={`h-full rounded-full ${memoryMode === 'hot-cold' ? 'bg-orange-500' : memoryMode === 'standard' ? 'bg-blue-500' : 'bg-gray-500'}`}
                style={{ width: '100%' }}
                title={`Agent Response: ${timing.llm}ms`}
              />
            </div>
          )}

          {hasMemoryIO && (
            <div className="pt-2 border-t border-gray-100 space-y-1">
              <div className="text-[10px] font-medium text-gray-400 uppercase tracking-wide">Memory I/O (separate)</div>
              {timing.memory_retrieve > 0 && (
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Retrieve</span>
                  <span className="font-mono text-green-600">{timing.memory_retrieve}ms</span>
                </div>
              )}
              {timing.memory_enqueue > 0 && (
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Enqueue</span>
                  <span className="font-mono text-orange-600">{timing.memory_enqueue}ms</span>
                </div>
              )}
              <div className="flex justify-between text-xs border-t border-dashed border-gray-200 pt-1">
                <span className="text-gray-500">Wall Clock Total</span>
                <span className="font-mono text-gray-500">{timing.total}ms</span>
              </div>
            </div>
          )}

          {!hasMemoryIO && memoryMode === 'standard' && (
            <div className="pt-2 border-t border-gray-100">
              <p className="text-[10px] text-gray-400 italic">Memory is handled inline by the agent — retrieval + storage happen inside the LLM call chain.</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function TimingRow({ label, value, color = 'text-gray-700', bold = false }) {
  return (
    <div className="flex justify-between items-center">
      <span className={`text-sm ${bold ? 'font-semibold' : ''}`}>{label}</span>
      <span className={`text-sm font-mono ${color} ${bold ? 'font-bold' : ''}`}>
        {value != null ? `${value}ms` : '—'}
      </span>
    </div>
  )
}

export default App