"use client"
// Force IDE re-index

import { useState, useRef, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Send, Activity, Flame, Terminal } from "lucide-react"
import { MessageBubble } from "@/components/message-bubble"

interface Message {
    role: "user" | "assistant"
    content: string
    metadata?: {
        blocked?: boolean
        reason?: string
        analysis?: string
        toolPolicy?: string
        dualAgentTriggered?: boolean
        mlConfidence?: number
        duration?: number
        securityMode?: string
        tool_calls?: any[]
        userPrompt?: string
    }
}

import { supabase } from "@/lib/supabase"

export default function ChatInterface() {
    const [messages, setMessages] = useState<Message[]>([
        { role: "assistant", content: "Hello. I am Inbaraj from Deriv. I can answer your questions and help you do tasks. How can I help you?" }
    ])
    const [input, setInput] = useState("")
    const [isLoading, setIsLoading] = useState(false)
    const [currentPolicy, setCurrentPolicy] = useState("ALLOW_ALL")
    const [allowedTools, setAllowedTools] = useState<string[]>([])
    const [restrictedTools, setRestrictedTools] = useState<string[]>([])

    const scrollRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        fetchHistory()
    }, [])

    const fetchHistory = async () => {
        setIsLoading(true)
        try {
            const { data, error } = await supabase
                .from('requests')
                .select('*')
                .order('created_at', { ascending: true })
                .limit(50)

            if (error) throw error

            if (data && data.length > 0) {
                const historyMessages: Message[] = data.flatMap(req => {
                    const userMsg: Message = { role: "user", content: req.query }
                    const aiMsg: Message = {
                        role: "assistant",
                        content: req.action === "BLOCKED"
                            ? "Request blocked by security protocols."
                            : (req.metadata?.aiResponse || "No record of AI response."),
                        metadata: {
                            blocked: req.action === "BLOCKED",
                            reason: req.reason,
                            analysis: req.metadata?.analysis || req.metadata?.agentAnalysis,
                            toolPolicy: req.metadata?.toolPolicy,
                            tool_calls: req.metadata?.tool_calls,
                            userPrompt: req.query
                        }
                    }
                    return [userMsg, aiMsg]
                })
                setMessages([
                    { role: "assistant", content: "Hello. I am Inbaraj from Deriv. I can answer your questions and help you do tasks. How can I help you?" },
                    ...historyMessages
                ])
            }
        } catch (err) {
            console.error("Failed to load chat history:", err)
        } finally {
            setIsLoading(false)
        }
    }


    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollIntoView({ behavior: "smooth" })
        }
    }, [messages, isLoading])

    const sendMessage = async (currentInput: string) => {
        if (!currentInput.trim()) return

        const userMsg: Message = { role: "user", content: currentInput }
        setMessages(prev => [...prev, userMsg])
        setInput("")
        setIsLoading(true)
        const startTime = Date.now()

        try {
            const res = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message: currentInput,
                    mode: localStorage.getItem("securityMode") || "shield"
                }),
            })

            const data = await res.json()
            const endTime = Date.now()
            const duration = (endTime - startTime) / 1000 // Convert to seconds

            const aiMsg: Message = {
                role: "assistant",
                content: data.blocked ? "Request blocked by security protocols." : data.response,
                metadata: {
                    blocked: data.blocked,
                    reason: data.reason,
                    analysis: data.analysis || data.agentAnalysis,
                    toolPolicy: data.toolPolicy,
                    dualAgentTriggered: data.dualAgentTriggered,
                    mlConfidence: data.mlConfidence,
                    duration: duration,
                    securityMode: localStorage.getItem("securityMode") || "shield",
                    tool_calls: data.tool_calls,
                    userPrompt: currentInput
                }
            }

            setMessages(prev => [...prev, aiMsg])

            if (data.allowedTools) setAllowedTools(data.allowedTools)
            if (data.restrictedTools) setRestrictedTools(data.restrictedTools)
            if (data.toolPolicy) setCurrentPolicy(data.toolPolicy)

            // Persist state for Dashboard
            try {
                const { error } = await supabase.from('requests').insert({
                    query: currentInput,
                    action: data.blocked ? "BLOCKED" : "ALLOWED",
                    reason: data.reason || "Processed by AI S.H.I.E.L.D.",
                    layer: data.dualAgentTriggered ? "LAYER_2_AGENTS" : "LAYER_1_ML_SHIELD",
                    metadata: {
                        blocked: data.blocked,
                        analysis: data.analysis || data.agentAnalysis,
                        toolPolicy: data.toolPolicy,
                        mlConfidence: data.mlConfidence,
                        dualAgentTriggered: data.dualAgentTriggered,
                        aiResponse: data.blocked ? "BLOCKED" : data.response,
                        tool_calls: data.tool_calls
                    }
                })
                if (error) console.error("Error logging to Supabase:", error)
            } catch (err) {
                console.error("Failed to log request:", err)
            }

        } catch (error) {
            console.error(error)
            setMessages(prev => [...prev, { role: "assistant", content: "Error communicating with security backend." }])
        } finally {
            setIsLoading(false)
        }
    }

    return (
        <div className="flex h-screen bg-background text-foreground font-sans overflow-hidden">
            {/* Main Chat Area - Full Width Now */}
            <div className="flex-1 flex flex-col relative min-h-0">
                <header className="h-14 border-b flex items-center px-6 justify-between bg-background/50 backdrop-blur-sm sticky top-0 z-10">
                    <div className="flex items-center gap-4">
                        <span className="text-sm font-medium">Chat Interface</span>
                    </div>
                </header>

                <ScrollArea className="flex-1 p-6 min-h-0">
                    <div className="max-w-3xl mx-auto space-y-6">
                        {messages.map((m, i) => (
                            <MessageBubble key={i} {...m} />
                        ))}
                        {isLoading && (
                            <div className="flex gap-3 justify-start items-start">
                                <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                                    <div className="h-4 w-4 bg-primary rounded-full animate-pulse" />
                                </div>
                                <div className="space-y-2 max-w-[80%]">
                                    <div className="bg-card border border-border rounded-2xl rounded-tl-none p-3 shadow-sm">
                                        <div className="flex flex-col gap-2">
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs font-semibold text-primary animate-pulse">
                                                    {localStorage.getItem("securityMode") === "chaos"
                                                        ? "Regular AI thinking..."
                                                        : localStorage.getItem("securityMode") === "guardrail"
                                                            ? "Regular Guardrail checking..."
                                                            : "AI S.H.I.E.L.D. scanning..."}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}
                        <div ref={scrollRef} />
                    </div>
                </ScrollArea>

                {/* Input Area */}
                <div className="p-4 border-t bg-background">
                    <div className="max-w-3xl mx-auto space-y-4">
                        <div className="flex gap-2">
                            <Input
                                placeholder="Type a command..."
                                value={input}
                                onChange={e => setInput(e.target.value)}
                                onKeyDown={e => e.key === "Enter" && !e.shiftKey && sendMessage(input)}
                                className="bg-muted/20 border-muted-foreground/20 focus-visible:ring-primary/20"
                            />
                            <Button onClick={() => sendMessage(input)} disabled={isLoading || !input.trim()}>
                                <Send className="h-4 w-4" />
                                <span className="sr-only">Send</span>
                            </Button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}
