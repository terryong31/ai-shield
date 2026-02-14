import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { ShieldAlert, ShieldCheck, Cpu, Clock } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

interface MessageBubbleProps {
    role: "user" | "assistant"
    content: string
    timestamp?: string
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

export function MessageBubble({ role, content, metadata, timestamp }: MessageBubbleProps) {
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
                <Card className={`p-3 text-sm break-all [overflow-wrap:anywhere] ${isUser
                    ? "bg-primary text-primary-foreground border-primary"
                    : isBlocked
                        ? "bg-destructive/10 border-destructive"
                        : "bg-muted/50"
                    }`}>
                    <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                            p: ({ node, ...props }) => <p className="mb-2 last:mb-0 leading-relaxed" {...props} />,
                            ul: ({ node, ...props }) => <ul className="list-disc pl-4 mb-2 last:mb-0 space-y-1" {...props} />,
                            ol: ({ node, ...props }) => <ol className="list-decimal pl-4 mb-2 last:mb-0 space-y-1" {...props} />,
                            li: ({ node, ...props }) => <li className="pl-1" {...props} />,
                            a: ({ node, ...props }) => <a className="text-blue-500 hover:underline underline-offset-2 font-medium" target="_blank" rel="noopener noreferrer" {...props} />,
                            blockquote: ({ node, ...props }) => <blockquote className="border-l-2 border-primary/50 pl-4 italic my-2" {...props} />,
                            code: ({ node, inline, className, children, ...props }: any) => {
                                return inline ? (
                                    <code className={`px-1 py-0.5 rounded font-mono text-xs ${isUser ? "bg-primary-foreground/20" : "bg-black/10 dark:bg-white/10"}`} {...props}>
                                        {children}
                                    </code>
                                ) : (
                                    <pre className={`p-2 rounded mb-2 overflow-x-auto font-mono text-xs ${isUser ? "bg-primary-foreground/10" : "bg-black/10 dark:bg-white/10"}`} {...props}>
                                        <code>{children}</code>
                                    </pre>
                                )
                            }
                        }}
                    >
                        {content}
                    </ReactMarkdown>
                </Card>

                {timestamp && (
                    <span className="text-[10px] text-zinc-500 mt-0.5 px-1">
                        {timestamp}
                    </span>
                )}

                {!isUser && metadata && (
                    <div className="flex flex-col gap-1 mt-1 w-full">
                        {/* Security Metadata Badge */}
                        <div className="flex flex-wrap items-center gap-2">
                            {isBlocked ? (
                                <Badge variant="destructive" className="flex gap-1 items-center w-fit text-[10px] px-1 h-5 bg-red-950 text-red-400 border-red-900">
                                    BLOCKED BY {metadata?.dualAgentTriggered ? "AGENTS" : "ML"}
                                </Badge>
                            ) : (
                                <Badge variant="outline" className="flex gap-1 items-center w-fit text-[10px] px-1 h-5 text-green-500 border-green-950 bg-green-950/20">
                                    SECURE
                                </Badge>
                            )}

                            {metadata.duration !== undefined && (
                                <Badge variant="secondary" className="flex gap-1 items-center w-fit text-[10px] px-1 h-5 bg-zinc-900 text-zinc-400 border-zinc-800">
                                    <Clock className="h-3 w-3" />
                                    {metadata.duration.toFixed(2)}s
                                </Badge>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}
