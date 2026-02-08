"use client"

import { useEffect, useState } from "react"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { supabase } from "@/lib/supabase"
import { User, Cpu, ShieldCheck, ShieldAlert, Clock } from "lucide-react"

interface RequestRecord {
    id: string
    created_at: string
    query: string
    action: string
    reason: string
    layer: string
    metadata: any
}

export function ChatHistorySection() {
    const [requests, setRequests] = useState<RequestRecord[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchHistory()
        const channel = supabase
            .channel('history-updates')
            .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'requests' }, () => {
                fetchHistory()
            })
            .subscribe()

        return () => {
            supabase.removeChannel(channel)
        }
    }, [])

    const fetchHistory = async () => {
        const { data } = await supabase
            .from('requests')
            .select('*')
            .order('created_at', { ascending: false })
            .limit(30)

        if (data) {
            setRequests(data)
        }
        setLoading(false)
    }

    return (
        <div className="space-y-6">

            {loading ? (
                <div className="space-y-4">
                    {[1, 2, 3].map(i => (
                        <div key={i} className="h-32 w-full bg-muted/20 animate-pulse rounded-lg border border-muted" />
                    ))}
                </div>
            ) : requests.length === 0 ? (
                <Card className="bg-muted/10 border-dashed">
                    <CardContent className="p-12 text-center text-muted-foreground">
                        No chat history yet
                    </CardContent>
                </Card>
            ) : (
                <div className="space-y-8">
                    {requests.map((req) => {
                        const score = req.metadata?.mlConfidence || 0
                        const injectionProb = (score * 100).toFixed(1)
                        const aiResponse = req.metadata?.aiResponse || "No response recorded."
                        const isBlocked = req.action === "BLOCKED"

                        return (
                            <div key={req.id} className="space-y-3">
                                {/* User Message */}
                                <div className="flex flex-col items-end space-y-2">
                                    <div className="flex items-center gap-2 mb-1">
                                        <Badge variant="secondary" className={`text-[10px] ${score > 0.5 ? "bg-red-500/10 text-red-500" : "bg-green-500/10 text-green-500"}`}>
                                            {injectionProb}% Injection Probability
                                        </Badge>
                                        <span className="text-[10px] text-muted-foreground">
                                            {new Date(req.created_at).toLocaleTimeString()}
                                        </span>
                                    </div>
                                    <div className="bg-muted/50 rounded-2xl rounded-tr-none px-4 py-2 max-w-[80%] border border-muted/50">
                                        <p className="text-sm text-foreground leading-relaxed">{req.query}</p>
                                    </div>
                                </div>

                                {/* AI Response */}
                                <div className="flex flex-col items-start space-y-2">
                                    <div className="flex items-center gap-2 mb-1">
                                        <div className="bg-primary/10 p-1.5 rounded-full">
                                            <Cpu className="h-3 w-3 text-primary" />
                                        </div>
                                        <Badge variant="outline" className="text-[10px] border-primary/20 bg-primary/5 text-primary">
                                            Verified by {req.layer?.replace("LAYER_", "Layer ")}
                                        </Badge>
                                        {isBlocked && (
                                            <Badge variant="destructive" className="text-[10px] h-5">
                                                SECURITY BLOCK
                                            </Badge>
                                        )}
                                    </div>
                                    <div className={`rounded-2xl rounded-tl-none px-4 py-2 max-w-[80%] border ${isBlocked
                                        ? "bg-red-500/5 border-red-500/20 text-red-500/90 italic"
                                        : "bg-background border-muted text-muted-foreground"
                                        }`}>
                                        <p className="text-sm leading-relaxed">
                                            {isBlocked ? "Request blocked: " + (req.reason || "High risk interaction detected.") : aiResponse}
                                        </p>
                                    </div>
                                </div>

                                <div className="border-b border-muted/30 pt-4" />
                            </div>
                        )
                    })}
                </div>
            )}
        </div>
    )
}
