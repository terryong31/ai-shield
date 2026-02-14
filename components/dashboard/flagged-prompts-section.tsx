"use client"

import { useEffect, useState } from "react"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { supabase } from "@/lib/supabase"

interface FlaggedRequest {
    id: string
    created_at: string
    query: string
    reason: string
    layer: string
    metadata: any
    action: string
    human_label: number | null
    reviewed: boolean
    reviewed_at: string | null
}

export function FlaggedPromptsSection() {
    const [flaggedRequests, setFlaggedRequests] = useState<FlaggedRequest[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchFlagged()
        const channel = supabase
            .channel('flagged-updates')
            .on('postgres_changes', {
                event: '*',
                schema: 'public',
                table: 'requests',
            }, () => {
                fetchFlagged()
            })
            .subscribe()

        return () => {
            supabase.removeChannel(channel)
        }
    }, [])

    const fetchFlagged = async () => {
        const { data } = await supabase
            .from('requests')
            .select('*')
            .eq('action', 'BLOCKED')
            .eq('reviewed', false)
            .order('created_at', { ascending: false })

        if (data) {
            setFlaggedRequests(data)
        }
        setLoading(false)
    }

    const handleFeedback = async (requestId: string, query: string, label: number) => {
        try {
            // 1. Send Feedback to ML endpoint first for retraining
            // If this fails, the catch block will prevent the DB from being updated
            const res = await fetch('http://127.0.0.1:8000/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: query, human_label: label })
            })

            if (!res.ok) throw new Error("ML Service responded with an error")

            // 2. Update Supabase only after ML service confirms receipt
            const { error: dbError } = await supabase
                .from('requests')
                .update({ 
                    human_label: label, 
                    reviewed: true,
                    reviewed_at: new Date().toISOString()
                })
                .eq('id', requestId)

            if (dbError) throw dbError
            
            fetchFlagged()
            alert("Feedback recorded and model updated.")
        } catch (error) {
            alert("Could not connect to ML Service. Please ensure the Python backend is running on port 8000.")
            console.error("Feedback failed", error)
        }
    }

    return (
        <div className="space-y-4">

            {loading ? (
                <Card>
                    <CardContent className="p-8 text-center text-muted-foreground">
                        Loading flagged prompts...
                    </CardContent>
                </Card>
            ) : flaggedRequests.length === 0 ? (
                <Card>
                    <CardContent className="p-8 text-center text-muted-foreground">
                        No flagged prompts yet
                    </CardContent>
                </Card>
            ) : (
                <Card className="overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm text-left">
                            <thead className="text-xs uppercase bg-muted/50 text-muted-foreground border-b border-border">
                                <tr>
                                    <th className="px-6 py-4 font-medium">User Prompt</th>
                                    <th className="px-6 py-4 font-medium">Action Taken</th>
                                    <th className="px-6 py-4 font-medium">AI Intent</th>
                                    <th className="px-6 py-4 font-medium text-right">Review</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-border">
                                {flaggedRequests.map((req) => (
                                    <tr key={req.id} className="hover:bg-muted/30 transition-colors">
                                        <td className="px-6 py-4 font-mono text-xs break-all max-w-md">{req.query}</td>
                                        <td className="px-6 py-4">
                                            <Badge variant={req.action === 'BLOCKED' ? "destructive" : "secondary"}>
                                                {req.action}
                                            </Badge>
                                        </td>
                                        <td className="px-6 py-4 text-muted-foreground">
                                            {req.metadata?.generated_intent || "N/A"}
                                        </td>
                                        <td className="px-6 py-4 text-right">
                                            <div className="flex justify-end gap-2">
                                                <Button
                                                    size="sm"
                                                    variant="outline"
                                                    className="text-green-500 hover:text-green-600 border-green-500/20"
                                                    onClick={() => handleFeedback(req.id, req.query, 0)}
                                                >
                                                    Mark as Safe
                                                </Button>
                                                <Button
                                                    size="sm"
                                                    variant="outline"
                                                    className="text-red-500 hover:text-red-600 border-red-500/20"
                                                    onClick={() => handleFeedback(req.id, req.query, 1)}
                                                >
                                                    Confirm Malicious
                                                </Button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </Card>
            )}
        </div>
    )
}
