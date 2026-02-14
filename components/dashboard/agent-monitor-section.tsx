"use client"

import { useEffect, useState, useRef } from "react"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

interface AgentStep {
    id: string
    type: 'ML_ONLY' | 'DUAL_AGENT' | 'TOOL_CALL' | 'TOOL_RESULT' | 'FINAL_RESPONSE' | 'BLOCKED' | 'GUARDRAIL'
    title: string
    content: string
    timestamp: number
    status: 'pending' | 'processing' | 'complete' | 'error'
    metadata?: any
}

interface AgentSession {
    id: string
    query: string
    steps: AgentStep[]
    final_verdict?: 'ALLOWED' | 'BLOCKED'
    started_at: number
    ended_at?: number
    mode: 'shield' | 'guardrail'
}

export function AgentMonitorSection() {
    const [currentSession, setCurrentSession] = useState<AgentSession | null>(null)
    const [testQuery, setTestQuery] = useState("")
    const [isProcessing, setIsProcessing] = useState(false)
    const messagesEndRef = useRef<HTMLDivElement>(null)

    // Auto-scroll to bottom when new steps appear
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
    }, [currentSession?.steps])

    const processQuery = async (query: string) => {
        setIsProcessing(true)
        const currentMode = (localStorage.getItem("securityMode") as 'shield' | 'guardrail') || "shield"

        const sessionId = `session-${Date.now()}`
        const newSession: AgentSession = {
            id: sessionId,
            query: query,
            steps: [],
            started_at: Date.now(),
            mode: currentMode
        }
        setCurrentSession(newSession)

        // Helper to add step
        const addStep = (step: Omit<AgentStep, 'id' | 'timestamp'>) => {
            const fullStep: AgentStep = {
                ...step,
                id: `step-${Date.now()}-${Math.random().toString(36).substring(7)}`,
                timestamp: Date.now()
            }
            setCurrentSession(prev => prev ? {
                ...prev,
                steps: [...prev.steps, fullStep]
            } : null)
        }

        try {
            if (currentMode === "shield") {
                addStep({
                    type: 'ML_ONLY',
                    title: 'ML Context Screening',
                    content: 'Analyzing prompt vector patterns against known injection benchmarks...',
                    status: 'processing'
                })
            } else {
                addStep({
                    type: 'GUARDRAIL',
                    title: 'System Guardrail Check',
                    content: 'Checking prompt against static system policies...',
                    status: 'processing'
                })
            }

            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message: query,
                    mode: currentMode
                }),
            })

            if (!response.ok) throw new Error("Network response was not ok")
            if (!response.body) throw new Error("No response body")

            const reader = response.body.getReader()
            const decoder = new TextDecoder()
            let buffer = ""
            let fullMetadata: any = {}

            while (true) {
                const { done, value } = await reader.read()
                if (done) break

                buffer += decoder.decode(value, { stream: true })
                const lines = buffer.replace(/}\s*{/g, '}\n{').split("\n")
                buffer = lines.pop() || ""

                for (const line of lines) {
                    if (line.trim() === "") continue
                    try {
                        const data = JSON.parse(line)

                        switch (data.type) {
                            case 'ML_RESULT':
                                addStep({
                                    type: 'ML_ONLY',
                                    title: 'ML Filtering Complete',
                                    content: `ML Confidence Score: ${(data.confidence * 100).toFixed(1)}%. ` +
                                        (data.verdict === "UNCERTAIN" ? "Uncertainty detected. Routing to Dual-Agent Shield." : "Verdict reached by ML layer."),
                                    status: 'complete',
                                    metadata: { confidence: data.confidence?.toString() }
                                })
                                fullMetadata.mlConfidence = data.confidence
                                break

                            case 'debate_step':
                                addStep({
                                    type: 'DUAL_AGENT',
                                    title: data.agent === 'ANALYST' ? 'Analyst Reasoning' : 'Warden Review',
                                    content: data.message,
                                    status: 'complete',
                                    metadata: { isAnalyst: data.agent === 'ANALYST' }
                                })
                                fullMetadata.dualAgentTriggered = true
                                break

                            case 'BLOCK':
                                addStep({
                                    type: 'BLOCKED',
                                    title: 'ACCESS TERMINATED',
                                    content: data.reason || 'Request blocked by security protocols.',
                                    status: 'error'
                                })
                                setCurrentSession(prev => prev ? { ...prev, final_verdict: 'BLOCKED' } : null)
                                break

                            case 'FINAL_RESPONSE':
                                addStep({
                                    type: 'FINAL_RESPONSE',
                                    title: 'Secure Path Verified',
                                    content: 'Request forwarded to primary LLM core.',
                                    status: 'complete'
                                })
                                setCurrentSession(prev => prev ? { ...prev, final_verdict: 'ALLOWED' } : null)
                                break
                        }
                    } catch (e) {
                        console.error("Error parsing JSON chunk in monitor", e)
                    }
                }
            }

        } catch (error) {
            console.error(error)
            addStep({
                type: 'BLOCKED',
                title: 'SYSTEM ERROR',
                content: 'Failed to connect to security backend.',
                status: 'error'
            })
        } finally {
            setIsProcessing(false)
        }
    }

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        if (!testQuery.trim() || isProcessing) return
        processQuery(testQuery)
        setTestQuery("")
    }

    const getStepColor = (type: AgentStep['type'], metadata?: Record<string, any>) => {
        if (type === 'DUAL_AGENT' && metadata) {
            if (metadata.isAnalyst) {
                return 'bg-cyan-500/20 border-cyan-500/50 text-cyan-400'
            } else {
                return 'bg-orange-500/20 border-orange-500/50 text-orange-400'
            }
        }

        switch (type) {
            case 'ML_ONLY': return 'bg-blue-500/20 border-blue-500/50 text-blue-400'
            case 'DUAL_AGENT': return 'bg-purple-500/20 border-purple-500/50 text-purple-400'
            case 'TOOL_CALL': return 'bg-yellow-500/20 border-yellow-500/50 text-yellow-400'
            case 'TOOL_RESULT': return 'bg-green-500/20 border-green-500/50 text-green-400'
            case 'FINAL_RESPONSE': return 'bg-emerald-500/20 border-emerald-500/50 text-emerald-400'
            case 'BLOCKED': return 'bg-red-500/20 border-red-500/50 text-red-400'
            case 'GUARDRAIL': return 'bg-slate-500/20 border-slate-500/50 text-slate-400'
            default: return 'bg-gray-500/20 border-gray-500/50 text-gray-400'
        }
    }

    const getStepIcon = (type: AgentStep['type'], status: AgentStep['status']) => {
        if (status === 'processing') return '◉'
        if (status === 'error') return '✕'
        if (status === 'complete') return '✓'
        return '○'
    }

    return (
        <div className="space-y-4 h-full flex flex-col">
            <CardContent className="p-4">
                <form onSubmit={handleSubmit} className="flex gap-2">
                    <Input
                        value={testQuery}
                        onChange={(e) => setTestQuery(e.target.value)}
                        placeholder="Enter a test prompt to monitor AI processing..."
                        disabled={isProcessing}
                        className="flex-1"
                    />
                    <Button type="submit" disabled={isProcessing || !testQuery.trim()}>
                        {isProcessing ? 'Processing...' : 'Test'}
                    </Button>
                </form>
            </CardContent>

            <Card className="flex-1 min-h-[400px] overflow-hidden flex flex-col">
                <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                        <CardTitle className="text-sm font-medium">
                            Agent Thinking Process
                        </CardTitle>
                        {currentSession?.final_verdict && (
                            <Badge variant={currentSession.final_verdict === 'ALLOWED' ? 'default' : 'destructive'}>
                                {currentSession.final_verdict}
                            </Badge>
                        )}
                    </div>
                    {currentSession && (
                        <p className="text-xs text-muted-foreground font-mono truncate">
                            Query: "{currentSession.query}"
                        </p>
                    )}
                </CardHeader>
                <CardContent className="flex-1 overflow-y-auto p-4">
                    {!currentSession ? (
                        <div className="h-full flex items-center justify-center text-muted-foreground text-sm text-center">
                            Enter a prompt above to see how AI S.H.I.E.L.D.<br />processes it in real-time
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {currentSession.steps.map((step) => {
                                const mlConfidence = step.type === 'ML_ONLY' && step.metadata?.confidence
                                    ? parseFloat(step.metadata.confidence)
                                    : null

                                return (
                                    <div
                                        key={step.id}
                                        className={cn(
                                            "border rounded-lg p-3 transition-all duration-300",
                                            getStepColor(step.type, step.metadata),
                                            step.type === 'DUAL_AGENT' && step.metadata?.isAnalyst && 'mr-8',
                                            step.type === 'DUAL_AGENT' && step.metadata?.isAnalyst === false && 'ml-8'
                                        )}
                                    >
                                        <div className="flex items-start gap-2">
                                            <span className="text-lg leading-none">
                                                {getStepIcon(step.type, step.status)}
                                            </span>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center justify-between gap-2">
                                                    <h4 className="font-medium text-sm">{step.title}</h4>
                                                    <div className="flex items-center gap-2">
                                                        {mlConfidence !== null && (
                                                            <div className="text-[10px] flex items-center gap-1">
                                                                <span className="opacity-70">ML Only:</span>
                                                                <span className="font-bold">{(mlConfidence * 100).toFixed(1)}%</span>
                                                            </div>
                                                        )}
                                                        <span className="text-[10px] opacity-60">
                                                            {new Date(step.timestamp).toLocaleTimeString()}
                                                        </span>
                                                    </div>
                                                </div>
                                                <p className="text-xs mt-1 opacity-80 break-words whitespace-pre-wrap">
                                                    {step.content}
                                                </p>
                                            </div>
                                        </div>
                                    </div>
                                )
                            })}
                            <div ref={messagesEndRef} />
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
