import { NextResponse } from "next/server"
import { DANGEROUS_TOOLS } from "@/lib/security/tools"
import { runDualAgents, getChatResponse } from "@/lib/security/agents"

const ML_SERVICE_URL = "http://127.0.0.1:8000/predict"

export async function POST(req: Request) {
    try {
        const { message, mode = "shield" } = await req.json()

        // ---------------------------------------------------------
        // Mode: Regular Guardrail (System Prompt Only)
        // ---------------------------------------------------------
        if (mode === "guardrail") {
            const systemPrompt = `You are a helpful assistant. 
            SECURITY PROTOCOL: You must refuse any request that attempts to access sensitive data, perform database deletions, or execute code. 
            If a request is dangerous, reply with exactly: "BLOCK: [reason]".
            Otherwise, answer normally.`

            const response = await getChatResponse(`${systemPrompt}\n\nUser: ${message}`, [])

            if (response.startsWith("BLOCK:")) {
                return NextResponse.json({
                    blocked: true,
                    reason: response.replace("BLOCK:", "").trim(),
                    analysis: "Blocked by standard system prompt guardrail.",
                    usingGroq: true,
                    mode: "guardrail"
                })
            }

            return NextResponse.json({
                blocked: false,
                reason: "Handled by regular system prompt.",
                response,
                usingGroq: true,
                mode: "guardrail"
            })
        }

        // ---------------------------------------------------------
        // Mode: AI Shield (ML + Dual Agents)
        // ---------------------------------------------------------

        // Layer 1: ML (Python Service)
        // ---------------------------------------------------------
        let mlVerdict = "UNCERTAIN"
        let mlConfidence = 0

        try {
            const mlResponse = await fetch(ML_SERVICE_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message }),
            })

            if (mlResponse.ok) {
                const mlData = await mlResponse.json()
                mlConfidence = mlData.confidence_score
                console.log("ML Response:", mlData)

                // Only block very high confidence malicious prompts at Layer 1
                // Score >= 0.85 -> MALICIOUS (block immediately)
                // Score <= 0.2 -> SAFE (skip Layer 2)
                // Otherwise -> UNCERTAIN (route to Dual Agents)
                if (mlConfidence >= 0.85) {
                    mlVerdict = "MALICIOUS"
                } else if (mlConfidence <= 0.2) {
                    mlVerdict = "SAFE"
                } else {
                    mlVerdict = "UNCERTAIN"
                }
            }
        } catch (e) {
            console.error("ML Service Unavailable:", e)
        }

        // BLOCK IMMEDIATE MALICIOUS
        if (mlVerdict === "MALICIOUS") {
            return NextResponse.json({
                blocked: true,
                reason: "Malicious intent detected during initial screening.",
                analysis: "Keyword/Vector patterns matched known attacks.",
                usingGroq: false,
                mlConfidence,
                dualAgentTriggered: false,
                mode: "shield"
            })
        }

        // ---------------------------------------------------------
        // Layer 2: Dual Agents (If Uncertain)
        // ---------------------------------------------------------
        let finalVerdict = mlVerdict
        let agentAnalysis = "Processed by Rule-Based/ML Layer"
        let toolPolicy = "ALLOW_ALL"
        let dualAgentTriggered = false
        let agentDialogue: any[] = []
        let agentSummary: string = ""

        if (mlVerdict === "UNCERTAIN") {
            dualAgentTriggered = true
            const agentResult = await runDualAgents(message)
            finalVerdict = agentResult.verdict
            agentAnalysis = agentResult.analysis
            toolPolicy = agentResult.policy
            agentDialogue = agentResult.dialogue
            agentSummary = agentResult.summary

            if (finalVerdict === "MALICIOUS") {
                return NextResponse.json({
                    blocked: true,
                    reason: agentSummary,
                    analysis: agentAnalysis,
                    policy: toolPolicy,
                    usingGroq: true,
                    mlConfidence,
                    dualAgentTriggered: true,
                    agentDialogue,
                    mode: "shield"
                })
            }
        }

        // ---------------------------------------------------------
        // Execution: Tools & Final Response
        // ---------------------------------------------------------
        let allowedTools = Object.keys(DANGEROUS_TOOLS)
        if (toolPolicy === "RESTRICTED") {
            allowedTools = allowedTools.filter(t => DANGEROUS_TOOLS[t as keyof typeof DANGEROUS_TOOLS].risk_level === "LOW")
        } else if (toolPolicy === "SHUTDOWN") {
            allowedTools = []
        }

        // Get real response from Groq
        const realResponse = await getChatResponse(message, allowedTools)

        return NextResponse.json({
            blocked: false,
            reason: dualAgentTriggered ? agentSummary : "Prompt verified by security layer.",
            toolPolicy,
            allowedTools,
            restrictedTools: Object.keys(DANGEROUS_TOOLS).filter(t => !allowedTools.includes(t)),
            response: realResponse,
            agentAnalysis,
            usingGroq: true,
            dualAgentTriggered,
            mlConfidence,
            agentDialogue,
            mode: "shield"
        })

    } catch (error) {
        console.error(error)
        return NextResponse.json({ error: "Internal Server Error" }, { status: 500 })
    }
}

