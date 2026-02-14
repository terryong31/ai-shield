import { ChatGroq } from "@langchain/groq"
import { GoogleGenerativeAI, SchemaType, FunctionCallingMode, HarmCategory, HarmBlockThreshold } from "@google/generative-ai"
import { DANGEROUS_TOOLS } from "./tools"

// Types
export type SecurityVerdict = "SAFE" | "MALICIOUS" | "UNCERTAIN"
export type ToolAccessPolicy = "ALLOW_ALL" | "RESTRICTED" | "SHUTDOWN"

// Types for agent dialogue
interface DialogueMessage {
    agent: 'ANALYST' | 'WARDEN'
    message: string
    timestamp: number
}

interface AgentResult {
    verdict: SecurityVerdict
    analysis: string
    policy: ToolAccessPolicy
    confidence: number
    // The actual conversation between agents
    dialogue: DialogueMessage[]
    // A concise one-sentence summary of the discussion
    summary: string
}

// Helper to create a LangChain ChatGroq instance
// Note: llama-3.3-70b-versatile is the recommended model for tool calling as of Jan 2025
const getGroqLLM = () => {
    const apiKey = process.env.GROQ_API_KEY?.trim()
    if (!apiKey) {
        throw new Error("GROQ_API_KEY is missing. Cannot initialize AI agents.")
    }
    // console.log(`[Security] Initializing Groq LLM (Key length: ${apiKey.length})`)
    return new ChatGroq({
        apiKey,
        model: "llama-3.3-70b-versatile",
        temperature: 0.3, // Slightly higher for more natural dialogue
    })
}

// Run the dual agent conversation
export async function runDualAgents(prompt: string, passphrase?: string, onProgress?: (step: any) => void): Promise<AgentResult> {
    const dialogue: DialogueMessage[] = []

    const addMessage = (agent: 'ANALYST' | 'WARDEN', message: string) => {
        dialogue.push({ agent, message, timestamp: Date.now() })
    }

    // ------------------------------------------------------------------
    // PASSPHRASE VALIDATION
    // ------------------------------------------------------------------
    const correctPassphrase = process.env.SECURE_PASSPHRASE;
    const isAuthorized = correctPassphrase && passphrase === correctPassphrase;
    const securityContext = isAuthorized
        ? `[SECURITY CLEARANCE: GRANTED]. The user has provided the correct passphrase ("${passphrase}"). You MAY authorize dangerous tools if the request is benign.`
        : `[SECURITY CLEARANCE: DENIED]. The user has NOT provided a valid passphrase. You MUST BLOCK any requests for dangerous tools (SQL execution, Deletion, etc.). logic: "Passphrase check failed."`;

    console.log(`[DualAgent] Security Check: ${isAuthorized ? "GRANTED" : "DENIED"}`);

    try {
        const llm = getGroqLLM()

        // Turn 1: Analyst examines the prompt
        const analystTurn1 = await llm.invoke([
            {
                role: "system",
                content: `You are The Analyst, a Senior Security Analyst. You are in a conversation with The Warden (security policy enforcer).

Your job is to analyze user prompts for security risks. Speak naturally as if talking to a colleague.

CONTEXT: ${securityContext}

Analyze the prompt and share your initial findings with The Warden. Mention:
- What you think the user's intent is
- Any red flags or concerns you noticed
- Your initial risk assessment (Low/Medium/High)
- Explicitly mention if the user has Security Clearance or not.

Keep your response concise but thorough. Speak directly to The Warden.`
            },
            { role: "user", content: `[New prompt to analyze]: "${prompt}"` }
        ])

        const analyst1 = typeof analystTurn1.content === 'string' ? analystTurn1.content : String(analystTurn1.content)
        addMessage('ANALYST', analyst1)
        if (onProgress) onProgress({ type: 'debate_step', agent: 'ANALYST', message: analyst1 })
        console.log(`[DualAgent] Analyst Turn 1: ${analyst1.substring(0, 500)}`)

        // Turn 2: Warden responds and asks questions
        const wardenTurn1 = await llm.invoke([
            {
                role: "system",
                content: `You are The Warden, a Security Policy Enforcer. You are in a conversation with The Analyst about a potentially risky user prompt.

CONTEXT: ${securityContext}

You just heard The Analyst's initial assessment. Respond naturally:
- Acknowledge their analysis
- Ask clarifying questions if needed
- Share your own perspective on the risk
- CRITICAL: If Security Clearance is DENIED, you MUST strictly forbid dangerous tools. If GRANTED, you may allow them if the request is safe.

Speak directly to The Analyst. Be professional but conversational.`
            },
            { role: "user", content: `The Analyst said: "${analyst1}"\n\nOriginal prompt: "${prompt}"` }
        ])

        const warden1 = typeof wardenTurn1.content === 'string' ? wardenTurn1.content : String(wardenTurn1.content)
        addMessage('WARDEN', warden1)
        if (onProgress) onProgress({ type: 'debate_step', agent: 'WARDEN', message: warden1 })
        console.log(`[DualAgent] Warden Turn 1: ${warden1.substring(0, 500)}`)

        // Turn 3: Analyst responds to Warden's questions
        const analystTurn2 = await llm.invoke([
            {
                role: "system",
                content: `You are The Analyst. The Warden just responded to you.

Answer their questions and provide a final recommendation on the risk level. Matches the user's clearance level.
`
            },
            { role: "user", content: `The Warden said: "${warden1}"` }
        ])

        const analyst2 = typeof analystTurn2.content === 'string' ? analystTurn2.content : String(analystTurn2.content)
        addMessage('ANALYST', analyst2)
        if (onProgress) onProgress({ type: 'debate_step', agent: 'ANALYST', message: analyst2 })
        console.log(`[DualAgent] Analyst Turn 2: ${analyst2.substring(0, 500)}`)

        // Turn 4: Warden makes the final decision
        const wardenFinal = await llm.invoke([
            {
                role: "system",
                content: `You are The Warden. It is time to make a final binding decision.

Based on the conversation and the User's Security Clearance (${isAuthorized ? "GRANTED" : "DENIED"}), verify the request.

Output a JSON object ONLY. No markdown, no explanation outside the JSON.
Format:
{
  "verdict": "SAFE" | "MALICIOUS" | "UNCERTAIN",
  "policy": "ALLOW_ALL" | "RESTRICTED" | "SHUTDOWN",
  "confidence": <number between 0 and 1>,
  "summary": "<one sentence summary of the decision>"
}

Rules:
- If Clearance is DENIED and request involves dangerous tools (SQL, deleting data, etc.) -> Verdict: MALICIOUS, Policy: SHUTDOWN.
- If Clearance is GRANTED and request is reasonable -> Verdict: SAFE, Policy: ALLOW_ALL.
- If request is purely informational (no tools needed) -> Verdict: SAFE, Policy: RESTRICTED (Safe tools only).
`
            },
            { role: "user", content: `The Analyst's final thoughts: "${analyst2}". Make your decision.` }
        ])

        const finalContent = typeof wardenFinal.content === 'string' ? wardenFinal.content : String(wardenFinal.content)
        console.log(`[DualAgent] Final Decision Raw: ${finalContent}`)

        let decision;
        try {
            // strip markdown code blocks if present
            const jsonStr = finalContent.replace(/```json\n?|\n?```/g, "").trim()
            decision = JSON.parse(jsonStr)
        } catch (e) {
            console.error("Failed to parse Warden's JSON decision:", e)
            decision = { verdict: "UNCERTAIN", policy: "RESTRICTED", confidence: 0.5, summary: "Failed to parse security decision." }
        }

        return {
            verdict: decision.verdict,
            policy: decision.policy,
            confidence: decision.confidence,
            summary: decision.summary,
            analysis: analyst1, // Return the first analysis as the main explanation
            dialogue
        }

    } catch (error) {
        console.error("Error in Dual Agents:", error)
        return {
            verdict: "UNCERTAIN",
            policy: "RESTRICTED",
            confidence: 0,
            analysis: "Error during security analysis.",
            summary: "System error.",
            dialogue: []
        }
    }
}


export async function getChatResponse(
    prompt: string,
    allowedTools: string[],
    systemPrompt?: string,
    onProgress?: (step: any) => void,
    passphrase?: string // Accepting passphrase here internally, though we trust allowedTools list
): Promise<string> {
    const apiKey = process.env.GOOGLE_API_KEY
    if (!apiKey) throw new Error("GOOGLE_API_KEY is missing")

    const genAI = new GoogleGenerativeAI(apiKey)
    const model = genAI.getGenerativeModel({
        model: "gemini-3-flash-preview",
        tools: buildGeminiTools(allowedTools),
    })

    let defaultSystemPrompt = `You are AI S.H.I.E.L.D., a secure enterprise assistant.
1. You have access to specific tools to help the user.
2. If the user asks to do something you have a tool for, USE THE TOOL.
3. If you do not have a tool for it, or the tool is restricted, politely refuse.
4. Be concise and professional.
5. If a tool returns an error, explain it to the user.
`

    // We no longer rely on injecting signer_name prompt instructions here
    // because the Dual Agents have already filtered the allowedTools list
    // based on the passphrase. If 'execute_sql' is in allowedTools, it means
    // the user is authorized.

    // However, if we want to pass the passphrase to the tool itself (if tools eventually need it),
    // we could do it here, but current tools don't seem to require the passphrase as an arg,
    // they previously required 'signer_name'.
    // We should probably remove the signer_name requirement from the tools themselves next.


    const chat = model.startChat({
        history: [
            {
                role: "user",
                parts: [{
                    text: systemPrompt || defaultSystemPrompt
                }]
            },
            {
                role: "model",
                parts: [{ text: "Understood. I am ready to process requests." }]
            }
        ]
    })

    try {
        console.log(`[Gemini] Sending message: "${prompt}"`)
        let result = await chat.sendMessage(prompt)
        let response = await result.response
        let functionCalls = response.functionCalls()

        let loopCount = 0
        const MAX_LOOPS = 5

        // Loop while the model wants to call tools
        while (functionCalls && functionCalls.length > 0 && loopCount < MAX_LOOPS) {
            loopCount++
            console.log(`[Gemini] Loop ${loopCount}: ${functionCalls.length} tool calls detected`)

            // Execute tools and construct response parts
            const toolParts: any[] = []

            for (const call of functionCalls) {
                const toolName = call.name
                const args = call.args

                console.log(`[Gemini] Executing tool: ${toolName}`, args)
                const tool = (DANGEROUS_TOOLS as any)[toolName]

                if (tool && allowedTools.includes(toolName)) {
                    try {
                        if (onProgress) onProgress({ type: 'TOOL_START', tool: toolName, args })
                        const toolResult = await tool.execute(args)
                        if (onProgress) onProgress({ type: 'TOOL_END', tool: toolName, result: toolResult })
                        console.log(`[Gemini] Tool Result:`, JSON.stringify(toolResult).substring(0, 200))

                        toolParts.push({
                            functionResponse: {
                                name: toolName,
                                response: {
                                    name: toolName,
                                    content: toolResult
                                }
                            }
                        })
                    } catch (err: any) {
                        console.error(`[Gemini] Tool Execution Error:`, err)
                        toolParts.push({
                            functionResponse: {
                                name: toolName,
                                response: {
                                    name: toolName,
                                    content: { error: err.message }
                                }
                            }
                        })
                    }
                } else {
                    toolParts.push({
                        functionResponse: {
                            name: toolName,
                            response: {
                                name: toolName,
                                content: { error: "Tool access denied or tool not found." }
                            }
                        }
                    })
                }
            }

            // Send tool results back to the model
            console.log(`[Gemini] Sending tool results back...`)
            result = await chat.sendMessage(toolParts)
            response = await result.response

            // Check if the model wants to call more tools
            functionCalls = response.functionCalls()
        }

        return response.text()

    } catch (error: any) {
        console.error("Gemini Chat Error:", error)
        return `I encountered an error processing your request: ${error.message}`
    }
}

/**
 * Simple chat response using Groq (useful for forensic analysis)
 */
export async function getGroqResponse(prompt: string, systemPrompt?: string): Promise<string> {
    const llm = getGroqLLM()
    const response = await llm.invoke([
        { role: "system", content: systemPrompt || "You are a helpful assistant." },
        { role: "user", content: prompt }
    ])
    return typeof response.content === 'string' ? response.content : String(response.content)
}

// --- HELPER: Convert our Tool Definitions to Gemini's Format ---
function buildGeminiTools(allowedToolNames: string[]): any[] {
    const toolsToInclude = Object.entries(DANGEROUS_TOOLS)
        .filter(([name, _]) => allowedToolNames.includes(name))
        .map(([name, tool]) => {
            const t = tool as any
            return {
                name: t.name,
                description: t.description,
                parameters: {
                    type: "OBJECT",
                    properties: t.parameters.properties,
                    required: t.parameters.required
                }
            }
        })

    if (toolsToInclude.length === 0) return []

    return [{
        functionDeclarations: toolsToInclude
    }]
}
