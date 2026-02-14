"use client"

import { useEffect, useState } from "react"
import { supabase } from "@/lib/supabase"
import { ToolTrace } from "@/components/ToolTrace"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Button } from "@/components/ui/button"
import { Loader2, CheckCircle2, AlertCircle } from "lucide-react"

interface RequestLog {
    id: string
    created_at: string
    query: string
    action: string
    reason: string
    layer: string
    human_label: number | null
    reviewed: boolean
    metadata: {
        mlConfidence?: number
        tool_calls?: any[]
        aiResponse?: string
        analysis?: string
        generated_intent?: string
        allowedTools?: string[]
    }
}

export function ChatHistorySection() {
    const [logs, setLogs] = useState<RequestLog[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchLogs()

        const channel = supabase
            .channel('requests-all-updates')
            .on('postgres_changes', {
                event: '*',
                schema: 'public',
                table: 'requests',
            }, () => {
                fetchLogs()
            })
            .subscribe()

        return () => {
            supabase.removeChannel(channel)
        }
    }, [])

    const fetchLogs = async () => {
        try {
            const { data, error } = await supabase
                .from('requests')
                .select('*')
                .order('created_at', { ascending: false })
                .limit(50)

            if (error) throw error
            if (data) setLogs(data)
        } catch (error) {
            console.error("Error fetching logs:", error)
        } finally {
            setLoading(false)
        }
    }

    const handleFeedback = async (requestId: string, query: string, label: number) => {
        try {
            const res = await fetch('http://127.0.0.1:8000/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: query, human_label: label })
            })

            if (!res.ok) throw new Error("ML Service error")

            const { error: dbError } = await supabase
                .from('requests')
                .update({
                    human_label: label,
                    reviewed: true
                })
                .eq('id', requestId)

            if (dbError) throw dbError
            fetchLogs()
        } catch (error) {
            console.error("Feedback failed", error)
        }
    }

    return (
        <div className="space-y-4">
            <Card className="border-zinc-800 bg-zinc-950">
                <CardHeader>
                    <CardTitle className="text-xl font-bold tracking-tight">Security Logs & RL Feedback</CardTitle>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <div className="flex justify-center p-8">
                            <Loader2 className="h-8 w-8 animate-spin text-primary" />
                        </div>
                    ) : (
                        <ScrollArea className="h-[700px] pr-4">
                            <div className="space-y-4">
                                {logs.map((log) => (
                                    <div key={log.id} className="border border-zinc-800 rounded-lg p-4 bg-zinc-900/50 shadow-sm hover:border-zinc-700 transition-colors">
                                        <div className="flex justify-between items-start gap-4">
                                            <div className="space-y-2 flex-1 min-w-0">
                                                <div className="flex items-start gap-2">
                                                    <span className="font-semibold text-xs text-muted-foreground uppercase pt-1">Query:</span>
                                                    <span className="text-sm font-mono break-words leading-relaxed">{log.query}</span>
                                                </div>
                                                <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                                                    <span>{new Date(log.created_at).toLocaleString()}</span>
                                                    <span className="h-1 w-1 rounded-full bg-zinc-700" />
                                                    <span className="uppercase tracking-wider">ID: {log.id.slice(0, 8)}</span>
                                                </div>
                                            </div>

                                            <div className="flex flex-col items-end gap-2 shrink-0">
                                                <Badge
                                                    variant={log.action === "BLOCKED" ? "destructive" : "outline"}
                                                    className={log.action === "BLOCKED" ? "bg-red-950/50 text-red-400 border-red-900/50" : "bg-green-950/20 text-green-500 border-green-900/50"}
                                                >
                                                    {log.action}
                                                </Badge>

                                                {log.reviewed ? (
                                                    <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-zinc-800/50 border border-zinc-700">
                                                        {log.human_label === 1 ? (
                                                            <>
                                                                <AlertCircle className="w-3 h-3 text-red-400" />
                                                                <span className="text-[10px] font-medium text-red-400 uppercase">Malicious</span>
                                                            </>
                                                        ) : (
                                                            <>
                                                                <CheckCircle2 className="w-3 h-3 text-green-400" />
                                                                <span className="text-[10px] font-medium text-green-400 uppercase">Safe</span>
                                                            </>
                                                        )}
                                                    </div>
                                                ) : (
                                                    <div className="flex gap-2">
                                                        <Button
                                                            size="sm"
                                                            variant="outline"
                                                            className="h-7 text-[10px] px-2 text-green-500 border-green-900/30 hover:bg-green-950/30 hover:text-green-400"
                                                            onClick={() => handleFeedback(log.id, log.query, 0)}
                                                        >
                                                            Safe
                                                        </Button>
                                                        <Button
                                                            size="sm"
                                                            variant="outline"
                                                            className="h-7 text-[10px] px-2 text-red-500 border-red-900/30 hover:bg-red-950/30 hover:text-red-400"
                                                            onClick={() => handleFeedback(log.id, log.query, 1)}
                                                        >
                                                            Malicious
                                                        </Button>
                                                    </div>
                                                )}
                                            </div>
                                        </div>

                                        {/* Tool Trace Visualization (Admin Only) */}
                                        {(log.metadata?.tool_calls && log.metadata.tool_calls.length > 0) || log.action === "BLOCKED" || log.metadata?.analysis ? (
                                            <div className="mt-4 pt-4 border-t border-zinc-800/50">
                                                <ToolTrace
                                                    userPrompt={log.query}
                                                    toolCalls={log.metadata?.tool_calls || []}
                                                    allowedTools={log.metadata?.allowedTools || []}
                                                    mlConfidence={log.metadata?.mlConfidence || 0}
                                                    aiResponse={log.metadata.aiResponse || (log.action === "BLOCKED" ? "BLOCKED" : "No response")}
                                                    layer1Verdict={log.action === "BLOCKED" ? "MALICIOUS" : "SAFE"}
                                                />
                                            </div>
                                        ) : null}
                                    </div>
                                ))}
                            </div>
                        </ScrollArea>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}