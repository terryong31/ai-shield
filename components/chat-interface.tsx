"use client"

import { useState, useRef, useEffect, useCallback } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Send, Terminal, Loader2, Lock, Unlock } from "lucide-react"
import { MessageBubble } from "@/components/message-bubble"
import { WorkflowVisualizer } from "@/components/workflow/WorkflowVisualizer"
import { supabase } from "@/lib/supabase"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"


interface Message {
    role: "user" | "assistant"
    content: string
    timestamp?: string
    metadata?: any
}

interface WorkflowState {
    query: string
    stage: 'idle' | 'start' | 'ml_processing' | 'ml_done' | 'debate' | 'final'
    mlConfidence: number | null
    mlVerdict: string
    lastAgentMessage: string
    dualAgentTriggered: boolean
    blocked: boolean
    toolPolicy?: string
    activeTools: string[]
    mode?: 'shield' | 'guardrail' | 'chaos'
}

const initialWorkflowState: WorkflowState = {
    query: "",
    stage: 'idle',
    mlConfidence: null,
    mlVerdict: "",
    lastAgentMessage: "",
    dualAgentTriggered: false,
    blocked: false,
    activeTools: [],
    mode: 'shield'
}

export default function ChatInterface() {
    const [messages, setMessages] = useState<Message[]>([
        { role: "assistant", content: "System online. AI S.H.I.E.L.D. active. Ready for analysis." }
    ])
    const [input, setInput] = useState("")
    const [isLoading, setIsLoading] = useState(false)

    // Passphrase State
    const [passphrase, setPassphrase] = useState("")
    const [isPassphraseDialogOpen, setIsPassphraseDialogOpen] = useState(false)
    const [tempPassphrase, setTempPassphrase] = useState("")

    // Resizable Panel State
    const [sidebarWidth, setSidebarWidth] = useState(50) // Percentage
    const [isDragging, setIsDragging] = useState(false)

    // Workflow Visualization State
    const [workflowState, setWorkflowState] = useState<WorkflowState>(initialWorkflowState)
    const [displayLimit, setDisplayLimit] = useState(10)
    const [hasMore, setHasMore] = useState(false)

    const scrollRef = useRef<HTMLDivElement>(null)
    const isSendingRef = useRef(false)

    useEffect(() => {
        fetchHistory()
        // Load passphrase from local storage if exists
        const savedPassphrase = localStorage.getItem("shield_passphrase")
        if (savedPassphrase) {
            setPassphrase(savedPassphrase)
            setTempPassphrase(savedPassphrase)
        }
    }, [])

    const fetchHistory = async () => {
        setIsLoading(true)
        try {
            const { data, count, error } = await supabase
                .from('requests')
                .select('*', { count: 'exact' })
                .order('created_at', { ascending: false })
                .limit(displayLimit)

            if (error) throw error

            if (data) {
                // Reverse to show chronological order
                const sortedData = [...data].reverse()
                const historyMessages: Message[] = sortedData.flatMap(req => {
                    const timestamp = new Date(req.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                    const userMsg: Message = {
                        role: "user",
                        content: req.query,
                        timestamp
                    }
                    const aiMsg: Message = {
                        role: "assistant",
                        content: req.action === "BLOCKED"
                            ? `Request blocked: ${req.reason}`
                            : (req.metadata?.aiResponse || "No record of AI response."),
                        timestamp,
                        metadata: {
                            blocked: req.action === "BLOCKED",
                            reason: req.reason,
                            analysis: req.metadata?.analysis || req.metadata?.agentAnalysis,
                            toolPolicy: req.metadata?.toolPolicy,
                            tool_calls: req.metadata?.tool_calls,
                            userPrompt: req.query,
                            duration: req.metadata?.duration,
                            dualAgentTriggered: req.metadata?.dualAgentTriggered || req.layer === "LAYER_2_DUAL_AGENT",
                            mlConfidence: req.metadata?.mlConfidence,
                            stage: req.metadata?.stage
                        }
                    }
                    return [userMsg, aiMsg]
                })
                setMessages([
                    { role: "assistant", content: "System online. AI S.H.I.E.L.D. active. Ready for analysis." },
                    ...historyMessages
                ])
                setHasMore(count ? count > displayLimit : false)
            }
        } catch (err) {
            console.error("Failed to load chat history:", err)
        } finally {
            setIsLoading(false)
        }
    }

    useEffect(() => {
        fetchHistory()
    }, [displayLimit])

    // Initial scroll to bottom on load
    useEffect(() => {
        if (!isLoading && displayLimit === 10 && messages.length > 1 && scrollRef.current) {
            scrollRef.current.scrollIntoView({ behavior: "instant" })
        }
    }, [messages, isLoading, displayLimit])

    // Listen for security mode changes
    useEffect(() => {
        const updateMode = () => {
            const mode = (localStorage.getItem("securityMode") as any) || "shield";
            setWorkflowState(prev => ({ ...prev, mode }));
        };

        // Initial check
        updateMode();

        window.addEventListener("security-mode-change", updateMode);
        return () => window.removeEventListener("security-mode-change", updateMode);
    }, []);

    // Dragging Logic
    const startResizing = useCallback(() => setIsDragging(true), [])
    // Load saved width
    useEffect(() => {
        const savedWidth = localStorage.getItem("sidebarWidth");
        if (savedWidth) {
            setSidebarWidth(parseFloat(savedWidth));
        }
    }, []);

    // Save width when dragging stops
    const stopResizing = useCallback(() => {
        setIsDragging(false);
        localStorage.setItem("sidebarWidth", sidebarWidth.toString());
    }, [sidebarWidth]);

    const resize = useCallback((mouseEvent: MouseEvent) => {
        if (isDragging) {
            const newWidth = (mouseEvent.clientX / window.innerWidth) * 100
            if (newWidth > 20 && newWidth < 80) setSidebarWidth(newWidth)
        }
    }, [isDragging])

    useEffect(() => {
        window.addEventListener("mousemove", resize)
        window.addEventListener("mouseup", stopResizing)
        return () => {
            window.removeEventListener("mousemove", resize)
            window.removeEventListener("mouseup", stopResizing)
        }
    }, [resize, stopResizing])

    useEffect(() => {
        if (!isLoading && scrollRef.current && isSendingRef.current) {
            scrollRef.current.scrollIntoView({ behavior: "smooth" })
            isSendingRef.current = false
        }
    }, [messages, isLoading])

    const handleSavePassphrase = () => {
        setPassphrase(tempPassphrase)
        localStorage.setItem("shield_passphrase", tempPassphrase)
        setIsPassphraseDialogOpen(false)
    }

    const sendMessage = async () => {
        if (!input.trim() || isLoading || isSendingRef.current) return

        const currentInput = input
        setInput("")

        setIsLoading(true)
        isSendingRef.current = true

        // Reset workflow state for new request
        setWorkflowState({
            ...initialWorkflowState,
            query: currentInput,
            stage: 'start',
            mode: (localStorage.getItem("securityMode") as any) || "shield"
        })

        // Add user message immediately
        const userMessage: Message = {
            role: "user",
            content: currentInput,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
        setMessages(prev => [...prev, userMessage])

        // Proceed directly - NO frontend interception anymore.
        // The passphrase is sent with the request, and the AGENT decides.
        executeChatRequest(currentInput)
    }

    const executeChatRequest = async (messageText: string) => {
        setIsLoading(true)
        isSendingRef.current = true
        const startTime = Date.now()

        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message: messageText,
                    mode: localStorage.getItem("securityMode") || "shield",
                    passphrase: passphrase // Pass the stored passphrase
                }),
            })

            if (!response.ok) throw new Error("Network response was not ok")
            if (!response.body) throw new Error("No response body")

            const reader = response.body.getReader()
            const decoder = new TextDecoder()
            let buffer = ""
            let aiResponseText = ""
            let fullMetadata: any = {}

            while (true) {
                const { done, value } = await reader.read()
                if (done) break

                buffer += decoder.decode(value, { stream: true })
                const lines = buffer.replace(/}\s*{/g, '}\n{').split("\n")

                // Keep the last line in buffer as it might be incomplete
                buffer = lines.pop() || ""

                for (const line of lines) {
                    if (line.trim() === "") continue
                    try {
                        const data = JSON.parse(line)

                        // Update Workflow State based on event type
                        switch (data.type) {
                            case 'START':
                                setWorkflowState(prev => ({ ...prev, stage: 'start' }))
                                break

                            case 'STAGE_CHANGE':
                                setWorkflowState(prev => ({
                                    ...prev,
                                    stage: data.stage,
                                    // If we hit 'debate' stage, dual agents are triggered
                                    dualAgentTriggered: prev.dualAgentTriggered || data.stage === 'debate'
                                }))
                                if (data.stage === 'debate') fullMetadata.dualAgentTriggered = true
                                break

                            case 'ML_RESULT':
                                setWorkflowState(prev => ({
                                    ...prev,
                                    mlConfidence: data.confidence,
                                    mlVerdict: data.verdict
                                }))
                                fullMetadata.mlConfidence = data.confidence
                                fullMetadata.mlVerdict = data.verdict
                                break

                            case 'debate_step':
                                setWorkflowState(prev => ({
                                    ...prev,
                                    stage: 'debate',
                                    dualAgentTriggered: true,
                                    lastAgentMessage: data.message
                                }))
                                fullMetadata.dualAgentTriggered = true
                                break

                            case 'TOOL_START':
                                setWorkflowState(prev => ({
                                    ...prev,
                                    activeTools: [...prev.activeTools, data.tool]
                                }))
                                break

                            case 'TOOL_END':
                                setWorkflowState(prev => ({
                                    ...prev,
                                    activeTools: prev.activeTools.filter(t => t !== data.tool)
                                }))
                                break

                            case 'BLOCK':
                                const blockDuration = (Date.now() - startTime) / 1000
                                setWorkflowState(prev => ({ ...prev, blocked: true }))
                                setMessages(prev => [...prev, {
                                    role: "assistant",
                                    content: `Request blocked: ${data.reason}`,
                                    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                                    metadata: {
                                        blocked: true,
                                        reason: data.reason,
                                        duration: blockDuration,
                                        dualAgentTriggered: fullMetadata.dualAgentTriggered
                                    }
                                }])
                                break

                            case 'POLICY_UPDATE':
                                console.log(`[Frontend] Received POLICY_UPDATE: ${data.policy}`);
                                setWorkflowState(prev => ({ ...prev, toolPolicy: data.policy }))
                                fullMetadata.toolPolicy = data.policy
                                break

                            case 'FINAL_RESPONSE':
                                setWorkflowState(prev => ({ ...prev, stage: 'final' }))
                                aiResponseText = data.text
                                break

                            case 'ERROR':
                                console.error("Stream error:", data.message)
                                break
                        }

                    } catch (e) {
                        console.error("Error parsing JSON chunk", e)
                    }
                }
            }

            // If we got a final response, add it to chat
            if (aiResponseText) {
                const duration = (Date.now() - startTime) / 1000
                setMessages(prev => [...prev, {
                    role: "assistant",
                    content: aiResponseText,
                    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    metadata: {
                        ...fullMetadata,
                        duration: duration,
                        dualAgentTriggered: fullMetadata.dualAgentTriggered
                    }
                }])
            }

        } catch (error) {
            console.error(error)
            setMessages(prev => [...prev, { role: "assistant", content: "Error communicating with security backend." }])
        } finally {
            setIsLoading(false)
        }
    }

    return (
        <div className="h-screen bg-zinc-950 text-foreground font-sans flex overflow-hidden">
            {/* Left Panel: Chat Interface */}
            <div
                className="flex flex-col relative h-full min-h-0 overflow-hidden bg-zinc-950"
                style={{ width: `${sidebarWidth}%` }}
            >
                <header className="h-14 border-b border-zinc-800 flex items-center px-6 justify-between bg-background/50 backdrop-blur-sm shrink-0">
                    <div className="flex items-center gap-2">
                        <Terminal className="h-4 w-4 text-primary" />
                        <span className="text-sm font-medium">Chat Interface</span>
                    </div>

                    {/* Security Locker */}
                    <Dialog open={isPassphraseDialogOpen} onOpenChange={setIsPassphraseDialogOpen}>
                        <DialogTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-primary">
                                {passphrase ? <Lock className="h-4 w-4" /> : <Unlock className="h-4 w-4 text-red-500" />}
                            </Button>
                        </DialogTrigger>
                        <DialogContent className="sm:max-w-[425px] bg-zinc-900 border-zinc-800">
                            <DialogHeader>
                                <DialogTitle>Security Locker</DialogTitle>
                                <DialogDescription>
                                    Enter the security passphrase to authorize dangerous actions.
                                </DialogDescription>
                            </DialogHeader>
                            <div className="grid gap-4 py-4">
                                <div className="grid grid-cols-4 items-center gap-4">
                                    <Label htmlFor="passphrase" className="text-right">
                                        Passphrase
                                    </Label>
                                    <Input
                                        id="passphrase"
                                        type="password"
                                        value={tempPassphrase}
                                        onChange={(e) => setTempPassphrase(e.target.value)}
                                        className="col-span-3 bg-zinc-950 border-zinc-800"
                                        placeholder="Enter passphrase..."
                                    />
                                </div>
                            </div>
                            <DialogFooter>
                                <Button onClick={handleSavePassphrase}>Save Configuration</Button>
                            </DialogFooter>
                        </DialogContent>
                    </Dialog>
                </header>

                <div className="flex-1 overflow-y-auto overflow-x-hidden min-h-0 p-6 scroll-smooth">
                    <div className="max-w-2xl mx-auto space-y-6">
                        {hasMore && (
                            <div className="flex justify-center mb-4">
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="text-xs text-muted-foreground hover:text-primary transition-colors"
                                    onClick={() => setDisplayLimit(prev => prev + 10)}
                                >
                                    Show 10 more
                                </Button>
                            </div>
                        )}
                        {messages.map((m, i) => (
                            <MessageBubble key={i} {...m} />
                        ))}
                        {isLoading && !workflowState.blocked && !messages[messages.length - 1]?.role.includes("assistant") && (
                            <div className="flex gap-3 justify-start items-start opacity-70">
                                <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                                    <Loader2 className="h-4 w-4 animate-spin text-primary" />
                                </div>
                                <div className="text-sm pt-1.5 flex flex-col gap-1">
                                    <span>AI S.H.I.E.L.D. Processing...</span>
                                    <span className="text-xs text-muted-foreground">
                                        {workflowState.stage === 'ml_processing' && "Analyzing intent & vectors..."}
                                        {workflowState.stage === 'debate' && (
                                            <div className="flex flex-col gap-1 mt-1">
                                                <span>Dual Agents debating security clearance...</span>
                                            </div>
                                        )}
                                        {workflowState.stage === 'final' && "(AI Agent Running...)"}
                                    </span>
                                </div>
                            </div>
                        )}
                        <div ref={scrollRef} />
                    </div>

                    <div className="p-4 border-t border-zinc-800 bg-background/50 backdrop-blur-sm shrink-0">
                        {/* Resizer Handle */}
                        <div
                            className="absolute right-0 top-0 bottom-0 w-1 bg-zinc-800 hover:bg-primary/50 cursor-col-resize transition-colors z-50"
                            onMouseDown={startResizing}
                        />

                        <div className="max-w-2xl mx-auto relative">
                            <Input
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
                                placeholder="Type a message..."
                                className="pr-12 bg-zinc-900 border-zinc-800"
                                disabled={isLoading}
                            />
                            <Button
                                size="icon"
                                className="absolute right-1 top-1 h-8 w-8"
                                onClick={sendMessage}
                                disabled={!input.trim() || isLoading}
                            >
                                <Send className="h-4 w-4" />
                            </Button>
                        </div>
                    </div>
                </div>
            </div>

            {/* Right Panel: Workflow Visualization */}
            <div className="flex-1 h-full min-h-0 overflow-hidden bg-background border-l border-zinc-800">
                <WorkflowVisualizer workflowState={workflowState} />
            </div>
        </div>
    )
}
