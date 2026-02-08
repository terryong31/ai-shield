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
}

export function FlaggedPromptsSection() {
    const [flaggedRequests, setFlaggedRequests] = useState<FlaggedRequest[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        fetchFlagged()
        const channel = supabase
            .channel('flagged-updates')
            .on('postgres_changes', {
                event: 'INSERT',
                schema: 'public',
                table: 'requests',
                filter: 'action=eq.BLOCKED'
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
            .eq('action', 'BLOCKED')
            .order('created_at', { ascending: false })

        if (data) {
            setFlaggedRequests(data)
        }
        setLoading(false)
    }

    const handleWhitelist = async (id: string) => {
        // TODO: Implement whitelist logic
        console.log("Whitelist request:", id)
        // For now, just show a message
        alert("Whitelist functionality coming soon!")
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
                <div className="space-y-3">
                    {flaggedRequests.map((req) => (
                        <Card key={req.id} className="border-red-500/20">
                            <CardHeader>
                                <div className="flex items-start justify-between gap-4">
                                    <div className="flex-1">
                                        <div className="flex items-center gap-2 mb-2">
                                            <Badge variant="destructive">BLOCKED</Badge>
                                            <span className="text-xs text-muted-foreground">
                                                {new Date(req.created_at).toLocaleString()}
                                            </span>
                                        </div>
                                        <p className="font-mono text-sm break-all mb-3">{req.query}</p>
                                        <div className="text-xs text-muted-foreground space-y-1">
                                            <div><strong>Reason:</strong> {req.reason}</div>
                                        </div>
                                    </div>
                                    <div className="flex flex-col gap-2">
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            onClick={() => handleWhitelist(req.id)}
                                        >
                                            Whitelist
                                        </Button>
                                    </div>
                                </div>
                            </CardHeader>
                        </Card>
                    ))}
                </div>
            )}
        </div>
    )
}
