"use client"

import { useEffect, useState } from "react"
import { supabase } from "@/lib/supabase"
import { WorkflowVisualizer } from "@/components/workflow/WorkflowVisualizer"
import { NodeDetailsSheet } from "@/components/workflow/NodeDetailsSheet"
import { CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Loader2, CheckCircle2, AlertCircle, Share2, ChevronDown, ChevronUp, Play } from "lucide-react"

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
        // Add other metadata fields as needed for reconstruction
        stage?: string
        mlVerdict?: string
        dualAgentTriggered?: boolean
        blocked?: boolean
        toolPolicy?: string
        activeTools?: string[]
        agentDialogue?: any[]
    }
}

export function ChatHistorySection() {
    const [logs, setLogs] = useState<RequestLog[]>([])
    const [loading, setLoading] = useState(true)
    const [expandedLogId, setExpandedLogId] = useState<string | null>(null)
    const [selectedNode, setSelectedNode] = useState<any>(null)
    const [isSheetOpen, setIsSheetOpen] = useState(false)
    const [playbackState, setPlaybackState] = useState<{ logId: string, stage: string } | null>(null)

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

    const toggleExpand = (id: string) => {
        setExpandedLogId(expandedLogId === id ? null : id)
    }

    const handleNodeClick = (_: React.MouseEvent, node: any) => {
        setSelectedNode(node)
        setIsSheetOpen(true)
    }

    // Helper to reconstruct workflow state from log metadata
    const mapLogToWorkflowState = (log: RequestLog, overrideStage?: string) => {
        // Default values if metadata is missing (backward compatibility)
        const mlConfidence = log.metadata.mlConfidence || 0;

        let mlVerdict = log.metadata.mlVerdict;
        if (!mlVerdict) {
            // Infer if missing
            if (mlConfidence > 0.85) mlVerdict = "MALICIOUS";
            else if (mlConfidence > 0.2) mlVerdict = "UNCERTAIN";
            else mlVerdict = "SAFE";
        }

        // Determine final stage
        let stage = overrideStage || "final";
        const blocked = log.action === "BLOCKED";

        // Reconstruct dual agent state
        // If action was blocked but ML wasn't high confidence, likely dual agent blocked it
        const dualAgentTriggered = mlVerdict === "UNCERTAIN" || log.metadata.dualAgentTriggered;

        return {
            query: log.query,
            stage: stage,
            mlConfidence: mlConfidence,
            mlVerdict: mlVerdict,
            dualAgentTriggered: dualAgentTriggered,
            blocked: blocked,
            toolPolicy: log.metadata.toolPolicy || (blocked ? "SHUTDOWN" : "ALLOW_ALL"),
            activeTools: log.metadata.activeTools || log.metadata.allowedTools || [],
            lastAgentMessage: log.metadata.analysis || "Historical analysis log",
            agentDialogue: log.metadata.agentDialogue || [],
        };
    };

    const handleReplay = (e: React.MouseEvent, logId: string) => {
        e.stopPropagation();
        setExpandedLogId(logId); // Ensure it's open

        // Start animation sequence
        setPlaybackState({ logId, stage: 'start' });

        setTimeout(() => setPlaybackState({ logId, stage: 'ml_processing' }), 800);
        setTimeout(() => setPlaybackState({ logId, stage: 'ml_done' }), 2500);

        // If dual agent is involved, show debate stage
        const log = logs.find(l => l.id === logId);
        const dualAgentTriggered = log && (log.metadata.mlVerdict === "UNCERTAIN" || log.metadata.dualAgentTriggered);

        if (dualAgentTriggered) {
            setTimeout(() => setPlaybackState({ logId, stage: 'debate' }), 3500);
            setTimeout(() => setPlaybackState({ logId, stage: 'final' }), 6500); // Longer debate
            setTimeout(() => setPlaybackState(null), 7000); // Reset to static final state
        } else {
            setTimeout(() => setPlaybackState({ logId, stage: 'final' }), 3500);
            setTimeout(() => setPlaybackState(null), 4000);
        }
    };

    return (
        <div className="space-y-4">
            <CardContent>
                {loading ? (
                    <div className="flex justify-center p-8">
                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                    </div>
                ) : (
                    <div className="space-y-4">
                        {logs.map((log) => (
                            <div key={log.id} className="border border-zinc-800 rounded-lg bg-zinc-900/50 shadow-sm hover:border-zinc-700 transition-colors overflow-hidden">
                                <div className="p-4 flex justify-between items-start gap-4 cursor-pointer" onClick={() => toggleExpand(log.id)}>
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
                                        <div className="flex items-center gap-2">
                                            <Badge
                                                variant={log.action === "BLOCKED" ? "destructive" : "outline"}
                                                className={log.action === "BLOCKED" ? "bg-red-950/50 text-red-400 border-red-900/50" : "bg-green-950/20 text-green-500 border-green-900/50"}
                                            >
                                                {log.action}
                                            </Badge>
                                            {expandedLogId === log.id ? <ChevronUp className="w-4 h-4 text-zinc-500" /> : <ChevronDown className="w-4 h-4 text-zinc-500" />}
                                        </div>

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
                                            <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
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

                                {/* Visual Workflow Trace */}
                                {expandedLogId === log.id && (
                                    <div className="border-t border-zinc-800/50 bg-black/40 h-[400px] relative">
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={(e) => handleReplay(e, log.id)}
                                            className="absolute top-2 left-2 z-10 bg-zinc-950/80 hover:bg-zinc-900 border-zinc-800 backdrop-blur text-[10px] text-zinc-400 uppercase tracking-widest flex items-center gap-2 h-auto py-1 px-2"
                                        >
                                            <Play className="w-3 h-3 text-primary" />
                                            Replay Workflow
                                        </Button>
                                        <WorkflowVisualizer
                                            workflowState={mapLogToWorkflowState(
                                                log,
                                                playbackState?.logId === log.id ? playbackState.stage : undefined
                                            )}
                                            onNodeClick={handleNodeClick}
                                        />
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </CardContent>

            <NodeDetailsSheet
                isOpen={isSheetOpen}
                onClose={() => setIsSheetOpen(false)}
                node={selectedNode}
            />
        </div>
    )
}