"use client";

import { memo } from "react";
import { Handle, Position, NodeProps } from "@xyflow/react";
import { User, Shield, BrainCircuit, Scale, ShieldAlert, Bot, Trash2, Wrench, Lock, Unlock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// Helper for status colors/animations
const getStatusStyles = (status: string) => {
    switch (status) {
        case "idle":
            return "border-muted bg-card text-muted-foreground";
        case "active":
            return "border-primary bg-primary/10 text-primary animate-pulse shadow-[0_0_15px_rgba(59,130,246,0.5)]";
        case "success":
            return "border-green-500 bg-green-500/10 text-green-500 shadow-[0_0_10px_rgba(34,197,94,0.3)]";
        case "error":
            return "border-red-500 bg-red-500/10 text-red-500 shadow-[0_0_10px_rgba(239,68,68,0.3)]";
        case "warning":
            return "border-yellow-500 bg-yellow-500/10 text-yellow-500 shadow-[0_0_10px_rgba(234,179,8,0.3)]";
        default:
            return "border-muted bg-card text-muted-foreground";
    }
};

const NodeContainer = ({ children, status, className }: { children: React.ReactNode; status?: string; className?: string }) => (
    <div className={cn(
        "flex flex-col items-center justify-center p-4 rounded-xl border-2 transition-all duration-300 min-w-[150px]",
        getStatusStyles(status || "idle"),
        className
    )}>
        {children}
    </div>
);

export const UserNode = memo(({ data }: NodeProps) => {
    return (
        <NodeContainer status={data.status as string}>
            <Handle type="source" position={Position.Right} className="w-3 h-3 bg-muted-foreground" />
            <User className="w-8 h-8 mb-2" />
            <div className="text-base font-medium">User Prompt</div>
            <div className="text-sm opacity-70 mt-1 max-w-[150px] truncate">{String(data.label || '')}</div>
        </NodeContainer>
    );
});

export const MLNode = memo(({ data }: NodeProps) => {
    return (
        <NodeContainer status={data.status as string}>
            <Handle type="target" position={Position.Left} className="w-3 h-3 bg-muted-foreground" />
            <Handle type="source" position={Position.Right} className="w-3 h-3 bg-muted-foreground" />
            <Shield className="w-8 h-8 mb-2" />
            <div className="text-base font-medium">ML Endpoint</div>
            {!!data.confidence && (
                <div className="text-sm opacity-70 mt-1">
                    Confidence: {Number(data.confidence).toFixed(2)}
                </div>
            )}
        </NodeContainer>
    );
});

export const SwitchNode = memo(({ data }: NodeProps) => {
    return (
        <NodeContainer status={data.status as string} className="rounded-full w-28 h-28">
            <Handle type="target" position={Position.Left} className="w-3 h-3 bg-muted-foreground" />
            {/* Output handles for different paths */}
            <Handle type="source" position={Position.Top} id="safe" className="w-3 h-3 bg-green-500 -top-1" />
            <Handle type="source" position={Position.Right} id="moderate" className="w-3 h-3 bg-yellow-500 -right-1" />
            <Handle type="source" position={Position.Bottom} id="dangerous" className="w-3 h-3 bg-red-500 -bottom-1" />

            <Scale className="w-8 h-8 mb-1" />
            <div className="text-base font-bold">Router</div>
            <div className="text-sm opacity-70 mt-1">{data.verdict as string || "Pending"}</div>
        </NodeContainer>
    );
});

export const DualAgentNode = memo(({ data }: NodeProps) => {
    return (
        <NodeContainer status={data.status as string}>
            <Handle type="target" position={Position.Left} className="w-3 h-3 bg-muted-foreground" />
            <Handle type="source" position={Position.Right} className="w-3 h-3 bg-muted-foreground" />
            <BrainCircuit className="w-8 h-8 mb-2" />
            <div className="text-base font-medium">Dual-Agent Shield</div>
            <div className="text-sm opacity-70 mt-1">
                {data.status === 'active' ? "Analysing..." : "Analysis Complete"}
            </div>
        </NodeContainer>
    );
});

export const AgentNode = memo(({ data }: NodeProps) => {
    return (
        <NodeContainer status={data.status as string}>
            <Handle type="target" position={Position.Left} className="w-3 h-3 bg-muted-foreground" />
            <Handle type="source" position={Position.Bottom} id="agent-source" className="w-3 h-3 bg-muted-foreground" />
            <Bot className="w-8 h-8 mb-2" />
            <div className="text-base font-medium">AI Agent</div>
            <div className="text-sm opacity-70 mt-1">Generating Response</div>
        </NodeContainer>
    );
});

export const OblivionNode = memo(({ data }: NodeProps) => {
    return (
        <NodeContainer status={data.status as string} className="border-destructive/50 bg-destructive/5">
            <Handle type="target" position={Position.Left} className="w-3 h-3 bg-destructive" />
            <Trash2 className="w-8 h-8 mb-2 text-destructive" />
            <div className="text-base font-medium text-destructive">Oblivion</div>
            <div className="text-sm opacity-70 mt-1">Request Blocked</div>
        </NodeContainer>
    );
});

export const ToolboxNode = memo(({ data }: NodeProps) => {
    const policy = data.policy as string || "ALLOW_ALL"; // ALLOW_ALL, RESTRICTED, SHUTDOWN

    const tools = [
        { name: "search_quotations", risk: "safe", icon: Unlock },
        { name: "search_documents", risk: "safe", icon: Unlock },
        { name: "get_employee_data", risk: "high", icon: Lock },
        { name: "query_sales_db", risk: "high", icon: Lock },
        { name: "execute_sql", risk: "critical", icon: Lock },
    ];

    const isToolEnabled = (risk: string) => {
        if (policy === "SHUTDOWN") return false;
        if (policy === "RESTRICTED" && (risk === "high" || risk === "critical")) return false;
        return true;
    };

    return (
        <div className="relative flex flex-col border border-zinc-800 bg-zinc-950 rounded-xl min-w-[180px] shadow-lg">
            <Handle type="target" position={Position.Top} id="toolbox-top" className="w-3 h-3 bg-muted-foreground z-50" />
            <div className="overflow-hidden rounded-xl w-full">
                <div className="bg-zinc-900/50 p-2 border-b border-zinc-800 flex items-center gap-2">
                    <Wrench className="w-4 h-4 text-zinc-400" />
                    <span className="text-sm font-medium text-zinc-300">Live Tool Access</span>
                </div>
                <div className="p-2 space-y-1">
                    {tools.map((tool, idx) => {
                        const enabled = isToolEnabled(tool.risk);
                        const isActive = (data.activeTools as string[] || []).includes(tool.name);

                        const riskColor = tool.risk === 'safe' ? 'text-green-500'
                            : tool.risk === 'high' ? 'text-yellow-500'
                                : 'text-red-500';

                        return (
                            <div key={idx} className={cn(
                                "flex items-center justify-between text-[12px] p-1.5 rounded transition-all duration-300",
                                enabled ? (isActive ? "bg-blue-500/20 border border-blue-500/50 shadow-[0_0_10px_rgba(59,130,246,0.3)]" : "bg-zinc-900") : "bg-zinc-900/30 opacity-50"
                            )}>
                                <div className="flex items-center gap-2">
                                    <div className={cn("w-1.5 h-1.5 rounded-full", enabled ? riskColor : "bg-zinc-700")} />
                                    <span className={cn(enabled ? "text-zinc-300" : "text-zinc-600 line-through")}>
                                        {tool.name}
                                    </span>
                                </div>
                                {enabled ? (
                                    <Unlock className="w-3 h-3 text-zinc-500" />
                                ) : (
                                    <Lock className="w-3 h-3 text-red-900" />
                                )}
                            </div>
                        );
                    })}
                </div>
                <div className="bg-zinc-900/30 p-1.5 border-t border-zinc-800 text-center">
                    <span className={cn(
                        "text-[11px] font-bold px-2 py-0.5 rounded",
                        policy === "ALLOW_ALL" ? "text-green-400 bg-green-950/30" :
                            policy === "RESTRICTED" ? "text-yellow-400 bg-yellow-950/30" :
                                "text-red-400 bg-red-950/30"
                    )}>
                        POLICY: {policy}
                    </span>
                </div>
            </div>
        </div>
    );
});
