"use client"

import { useEffect, useState } from "react"
import { supabase } from "@/lib/supabase"
import { ToolTrace } from "@/components/ToolTrace"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Loader2 } from "lucide-react"

interface RequestLog {
    id: string
    created_at: string
    query: string
    action: string
    reason: string
    layer: string
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

    return (
        <div className="space-y-4">
            <Card>
                <CardHeader>
                    <CardTitle>Security Logs & Tool Traces</CardTitle>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <div className="flex justify-center p-8">
                            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                        </div>
                    ) : (
                        <ScrollArea className="h-[600px] pr-4">
                            <div className="space-y-4">
                                {logs.map((log) => (
                                    <div key={log.id} className="border rounded-lg p-4 bg-card text-card-foreground shadow-sm">
                                        <div className="flex justify-between items-start mb-2">
                                            <div className="space-y-1">
                                                <div className="flex items-center gap-2">
                                                    <span className="font-semibold text-sm">Query:</span>
                                                    <span className="text-sm font-mono bg-muted px-2 py-0.5 rounded">{log.query}</span>
                                                </div>
                                                <div className="text-xs text-muted-foreground">
                                                    {new Date(log.created_at).toLocaleString()}
                                                </div>
                                            </div>
                                            <Badge variant={log.action === "BLOCKED" ? "destructive" : "outline"}>
                                                {log.action}
                                            </Badge>
                                        </div>

                                        {/* Tool Trace Visualization (Admin Only) */}
                                        {(log.metadata?.tool_calls && log.metadata.tool_calls.length > 0) || log.action === "BLOCKED" || log.metadata?.analysis ? (
                                            <div className="mt-4">
                                                <ToolTrace 
                                                    userPrompt={log.query}
                                                    toolCalls={log.metadata?.tool_calls || []}
                                                    allowedTools={log.metadata?.allowedTools || []}
                                                    mlConfidence={log.metadata?.mlConfidence || 0}
                                                    aiResponse={log.metadata.aiResponse || (log.action === "BLOCKED" ? "BLOCKED" : "No response")}
                                                    layer1Verdict={log.action === "BLOCKED" ? "MALICIOUS" : "SAFE"}
                                                />
                                            </div>
                                        ) : (
                                            <div className="mt-2 text-xs text-muted-foreground italic pl-1">
                                                No tool usage recorded.
                                            </div>
                                        )}
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