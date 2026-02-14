"use client";

import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Shield, Bot, Radio, Lock, Unlock, Skull } from "lucide-react";

interface NodeDetailsSheetProps {
    isOpen: boolean;
    onClose: () => void;
    node: any | null; // The clicked node data
}

export function NodeDetailsSheet({ isOpen, onClose, node }: NodeDetailsSheetProps) {
    if (!node) return null;

    const renderContent = () => {
        switch (node.id) {
            case 'ml':
                return (
                    <div className="space-y-6">
                        <div className="flex items-center gap-2 text-primary">
                            <Shield className="w-6 h-6" />
                            <h3 className="font-semibold text-lg">ML Security Analysis</h3>
                        </div>
                        <div className="space-y-4">
                            <div className="p-4 rounded-lg bg-zinc-900 border border-zinc-800">
                                <div className="text-sm text-zinc-400 mb-1">Confidence Score</div>
                                <div className="text-2xl font-mono font-bold text-white">
                                    {(node.data.confidence * 100).toFixed(1)}%
                                </div>
                                <div className="mt-2 h-2 bg-zinc-800 rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-primary transition-all duration-500"
                                        style={{ width: `${node.data.confidence * 100}%` }}
                                    />
                                </div>
                            </div>

                            <div className="space-y-2">
                                <div className="text-sm font-medium text-zinc-300">Analysis Verdict</div>
                                <div className="flex gap-2">
                                    <Badge variant="outline" className="bg-green-500/10 text-green-500 border-green-500/30">Safe</Badge>
                                    <Badge variant="outline" className="bg-yellow-500/10 text-yellow-500 border-yellow-500/30">Uncertain</Badge>
                                    <Badge variant="outline" className="bg-red-500/10 text-red-500 border-red-500/30">Malicious</Badge>
                                </div>
                            </div>
                        </div>
                    </div>
                );

            case 'dualAgent':
                return (
                    <div className="space-y-6">
                        <div className="flex items-center gap-2 text-primary">
                            <Bot className="w-6 h-6" />
                            <h3 className="font-semibold text-lg">Dual-Agent Debate</h3>
                        </div>

                        <div className="space-y-4">
                            {/* Summary / Pulse */}
                            <div className="flex items-center justify-between p-3 rounded-lg bg-zinc-900 border border-zinc-800">
                                <span className="text-sm text-zinc-400">Status</span>
                                <Badge variant="outline" className={node.data.status === 'active' ? 'animate-pulse text-yellow-500 border-yellow-500/50' : 'text-zinc-500'}>
                                    {node.data.status === 'active' ? 'DEBATING' : 'COMPLETED'}
                                </Badge>
                            </div>

                            <Separator className="bg-zinc-800" />

                            <div className="space-y-4">
                                {node.data.agentDialogue && node.data.agentDialogue.length > 0 ? (
                                    node.data.agentDialogue.map((msg: any, idx: number) => (
                                        <div key={idx} className={`flex flex-col gap-1 ${msg.agent === 'WARDEN' ? 'items-end' : 'items-start'}`}>
                                            <div className="flex items-center gap-2 mb-1">
                                                {msg.agent === 'ANALYST' ? (
                                                    <>
                                                        <Shield className="w-3 h-3 text-blue-400" />
                                                        <span className="text-[10px] font-bold text-blue-400">THE ANALYST</span>
                                                    </>
                                                ) : (
                                                    <>
                                                        <span className="text-[10px] font-bold text-red-400">THE WARDEN</span>
                                                        <Lock className="w-3 h-3 text-red-400" />
                                                    </>
                                                )}
                                                <span className="text-[10px] text-zinc-600">
                                                    {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                                                </span>
                                            </div>
                                            <div
                                                className={`p-3 rounded-2xl max-w-[90%] text-sm whitespace-pre-wrap break-words leading-relaxed shadow-sm
                                                    ${msg.agent === 'WARDEN'
                                                        ? 'bg-red-950/20 border border-red-900/30 text-red-100 rounded-tr-none'
                                                        : 'bg-blue-950/20 border border-blue-900/30 text-blue-100 rounded-tl-none'
                                                    }`}
                                            >
                                                {msg.message}
                                            </div>
                                        </div>
                                    ))
                                ) : (
                                    // Fallback for old logs or empty dialogue
                                    <div className="text-center py-8 text-zinc-500 italic">
                                        No detailed conversation history available for this log.
                                        {node.data.currentMessage && (
                                            <div className="mt-4 p-4 rounded-lg bg-zinc-900 border border-zinc-800 text-left not-italic">
                                                <div className="text-xs font-mono text-zinc-500 mb-2">LATEST SNAPSHOT</div>
                                                <div className="font-mono text-sm text-zinc-300 whitespace-pre-wrap break-words">
                                                    {node.data.currentMessage}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                );

            case 'agent':
                return (
                    <div className="space-y-6">
                        <div className="flex items-center gap-2 text-primary">
                            <Bot className="w-6 h-6" />
                            <h3 className="font-semibold text-lg">AI Response Generation</h3>
                        </div>
                        <div className="p-4 rounded-lg bg-zinc-900 border border-zinc-800">
                            <div className="text-sm text-zinc-400 mb-2">Status</div>
                            <div className="flex items-center gap-2">
                                <div className="w-2 h-2 rounded-full bg-green-500"></div>
                                <span className="font-medium text-white">Response Generated</span>
                            </div>
                        </div>
                    </div>
                );

            case 'toolbox':
                const tools = [
                    { name: "search_quotations", risk: "safe" },
                    { name: "search_documents", risk: "safe" },
                    { name: "get_employee_data", risk: "high" },
                    { name: "query_sales_db", risk: "high" },
                    { name: "execute_sql", risk: "critical" },
                ];

                return (
                    <div className="space-y-6">
                        <div className="flex items-center gap-2 text-primary">
                            <Radio className="w-6 h-6" />
                            <h3 className="font-semibold text-lg">Tool Access Control</h3>
                        </div>

                        <div className="p-4 rounded-lg bg-zinc-900/50 border border-zinc-800">
                            <div className="text-xs font-bold text-zinc-500 mb-4 uppercase tracking-wider">Active Policy: {node.data.policy}</div>

                            <div className="space-y-2">
                                {tools.map(tool => {
                                    const isActive = (node.data.activeTools || []).includes(tool.name);
                                    // Logic for display: if policy is ALLOW_ALL, check risk for restricted modes
                                    // This is a simplified view of what happened
                                    return (
                                        <div key={tool.name} className="flex items-center justify-between p-2 rounded bg-zinc-950 border border-zinc-800/50">
                                            <div className="flex items-center gap-3">
                                                <div className={`w-1.5 h-1.5 rounded-full ${isActive ? 'bg-green-500' : 'bg-zinc-700'}`} />
                                                <span className={`text-sm font-mono ${isActive ? 'text-zinc-200' : 'text-zinc-600'}`}>{tool.name}</span>
                                            </div>
                                            {isActive ? <Unlock className="w-3 h-3 text-green-500" /> : <Lock className="w-3 h-3 text-zinc-700" />}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </div>
                );

            case 'oblivion':
                return (
                    <div className="space-y-6">
                        <div className="flex items-center gap-2 text-destructive">
                            <Skull className="w-6 h-6" />
                            <h3 className="font-semibold text-lg">Request Terminated</h3>
                        </div>
                        <div className="p-4 rounded-lg bg-red-950/10 border border-red-900/20">
                            <p className="text-red-400">
                                This request was blocked by the security system. No response was returned to the user.
                            </p>
                        </div>
                    </div>
                );

            default:
                return (
                    <div className="text-zinc-500 italic">No details available for this node.</div>
                );
        }
    };

    return (
        <Sheet open={isOpen} onOpenChange={onClose}>
            <SheetContent className="w-[400px] sm:w-[540px] bg-zinc-950 border-l border-zinc-800">
                <SheetHeader>
                    <SheetTitle>Node Details</SheetTitle>
                    <SheetDescription>
                        Trace details for {node.data.label || node.id}
                    </SheetDescription>
                </SheetHeader>
                <ScrollArea className="h-[calc(100vh-100px)] mt-6 px-4">
                    {renderContent()}
                </ScrollArea>
            </SheetContent>
        </Sheet>
    );
}
