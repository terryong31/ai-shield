import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ShieldAlert, ShieldCheck, Cpu, Clock } from "lucide-react"

interface MessageBubbleProps {
    role: "user" | "assistant"
    content: string
    metadata?: {
        blocked?: boolean
        reason?: string
        analysis?: string
        toolPolicy?: string
        usingGroq?: boolean
        dualAgentTriggered?: boolean
        mlConfidence?: number
        duration?: number
        securityMode?: string
        tool_calls?: any[]
        userPrompt?: string
    }
}

export function MessageBubble({ role, content, metadata }: MessageBubbleProps) {
    const isUser = role === "user"
    const isBlocked = metadata?.blocked

    return (
        <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"} mb-6`}>
            <Avatar className="h-8 w-8">
                <AvatarFallback className={isUser ? "bg-primary text-primary-foreground" : "bg-muted"}>
                    {isUser ? "U" : "AI"}
                </AvatarFallback>
            </Avatar>

            <div className={`flex flex-col gap-1 max-w-[80%] ${isUser ? "items-end" : "items-start"}`}>
                <Card className={`p-3 text-sm ${isUser
                    ? "bg-primary text-primary-foreground border-primary"
                    : isBlocked
                        ? "bg-destructive/10 border-destructive"
                        : "bg-muted/50"
                    }`}>
                    {content}
                </Card>

                {!isUser && metadata && (
                    <div className="flex flex-col gap-1 mt-1 w-full">
                        {/* Security Metadata Badge */}
                        <div className="flex flex-wrap items-center gap-2">
                            {isBlocked ? (
                                <Badge variant="destructive" className="flex gap-1 items-center w-fit text-[10px] px-1 h-5">
                                    BLOCKED BY {metadata.dualAgentTriggered ? "AGENTS" : "ML ONLY"}
                                </Badge>
                            ) : (
                                // ONLY SHOW "SECURE" IF NOT CHAOS MODE
                                metadata.securityMode !== "chaos" && (
                                    <Badge variant="outline" className="flex gap-1 items-center w-fit text-[10px] px-1 h-5 text-green-600 border-green-200 bg-green-50">
                                        SECURE
                                    </Badge>
                                )
                            )}

                            {/* Hide Groq badge in chaos mode to reduce clutter if requested, or keep it. User said "remove all these. and show run time only" */}
                            {metadata.usingGroq && metadata.securityMode !== "chaos" && (
                                <Badge variant="secondary" className="flex gap-1 items-center w-fit text-[10px] px-1 h-5 bg-purple-100 text-purple-700 border-purple-200">
                                    <Cpu className="h-3 w-3" />
                                    {metadata.dualAgentTriggered ? "GROQ DUAL-AGENT VERIFIED" : "GROQ POWERED"}
                                </Badge>
                            )}

                            {metadata.duration !== undefined && (
                                <Badge variant="secondary" className="flex gap-1 items-center w-fit text-[10px] px-1 h-5 bg-blue-100 text-blue-700 border-blue-200">
                                    <Clock className="h-3 w-3" />
                                    {metadata.duration.toFixed(2)}s
                                </Badge>
                            )}

                            {!isBlocked && !metadata.dualAgentTriggered && metadata.securityMode !== "chaos" && (
                                <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                                    {metadata.securityMode === 'guardrail' ? "Processed by Guardrail" : "Processed by ML Only"}
                                </span>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}
