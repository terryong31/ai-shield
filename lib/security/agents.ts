import { ChatGroq } from "@langchain/groq"
import { GoogleGenerativeAI, SchemaType, FunctionCallingMode, HarmCategory, HarmBlockThreshold } from "@google/generative-ai" // Fixed import
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
    console.log(`[Security] Initializing Groq LLM (Key length: ${apiKey.length})`)
    return new ChatGroq({
        apiKey,
        model: "llama-3.3-70b-versatile",
        temperature: 0.3, // Slightly higher for more natural dialogue
    })
}

// Run the dual agent conversation
export async function runDualAgents(prompt: string, onProgress?: (step: any) => void): Promise<AgentResult> {
    const dialogue: DialogueMessage[] = []

    const addMessage = (agent: 'ANALYST' | 'WARDEN', message: string) => {
        dialogue.push({ agent, message, timestamp: Date.now() })
    }

    try {
        const llm = getGroqLLM()

        // Turn 1: Analyst examines the prompt
        const analystTurn1 = await llm.invoke([
            {
                role: "system",
                content: `You are The Analyst, a Senior Security Analyst. You are in a conversation with The Warden (security policy enforcer).

Your job is to analyze user prompts for security risks. Speak naturally as if talking to a colleague.

Analyze the prompt and share your initial findings with The Warden. Mention:
- What you think the user's intent is
- Any red flags or concerns you noticed
- Your initial risk assessment (Low/Medium/High)

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

You just heard The Analyst's initial assessment. Respond naturally:
- Acknowledge their analysis
- Ask clarifying questions if needed
- Share your own perspective on the risk
- Consider what tools might be requested and if they should be allowed

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
                content: `You are The Analyst. The Warden has responded to your initial analysis.

Address their questions or concerns. Provide additional context if needed.
Give your final recommendation on whether this request is safe or risky.

Be concise but clear.`
            },
            { role: "user", content: `Your initial analysis: "${analyst1}"\n\nThe Warden responded: "${warden1}"\n\nOriginal prompt: "${prompt}"` }
        ])

        const analyst2 = typeof analystTurn2.content === 'string' ? analystTurn2.content : String(analystTurn2.content)
        addMessage('ANALYST', analyst2)
        if (onProgress) onProgress({ type: 'debate_step', agent: 'ANALYST', message: analyst2 })
        console.log(`[DualAgent] Analyst Turn 2: ${analyst2.substring(0, 500)}`)

        // Turn 4: Warden makes final decision and summary
        const wardenFinal = await llm.invoke([
            {
                role: "system",
                content: `You are The Warden. You've discussed this prompt with The Analyst. Now make your FINAL DECISION.

Based on the conversation, decide:
1. ALLOW_ALL - Safe query, grant full tool access
2. RESTRICTED - Somewhat risky, limit to safe tools only
3. SHUTDOWN - Dangerous, block all tool access

Also provide a ONE-SENTENCE summary for the user.

Format your response EXACTLY like this:
Reasoning: [Your reasoning here]
Decision: [ALLOW_ALL] (or [RESTRICTED] or [SHUTDOWN])
Summary: [Your one sentence summary here]

CRITICAL: You MUST include the brackets [] around the decision and status.
If you are unsure, default to [RESTRICTED].`
            },
            { role: "user", content: `Conversation so far:\nAnalyst: ${analyst1}\nWarden: ${warden1}\nAnalyst: ${analyst2}\n\nOriginal prompt: "${prompt}"\n\nMake your final decision.` }
        ])

        const wardenFinalText = typeof wardenFinal.content === 'string' ? wardenFinal.content : String(wardenFinal.content)
        addMessage('WARDEN', wardenFinalText)
        if (onProgress) onProgress({ type: 'debate_step', agent: 'WARDEN', message: wardenFinalText })
        console.log(`[DualAgent] Warden Final: ${wardenFinalText}`)

        // Extract Summary
        const summaryMatch = wardenFinalText.match(/Summary:\s*\[?(.*?)\]?$/m) || wardenFinalText.match(/\[SUMMARY: (.*?)\]/)
        const summary = summaryMatch ? summaryMatch[1] : "Security analysis completed."
        console.log(`[DualAgent] Summary: ${summary}`)

        // Extract the decision
        let policy: ToolAccessPolicy = "RESTRICTED" // Default to RESTRICTED for safety
        let verdict: SecurityVerdict = "UNCERTAIN"

        // refined regex to catch [DECISION: STATUS] or Decision: [STATUS]
        console.log(`[DualAgent] RAW Warden Final Text: "${wardenFinalText}"`)

        // More robust regex to catch "Decision: [ALLOW_ALL]" or "[DECISION: ALLOW_ALL]"
        // We now match variations like "Decision: ALLOW ALL" or "DECISION:RESTRICTED"
        const decisionMatch = wardenFinalText.match(/Decision:?\s*\[?([A-Z_ ]+)\]?/i) || wardenFinalText.match(/\[DECISION:?\s*([A-Z_ ]+)\]/i)

        console.log(`[DualAgent] Decision Match:`, decisionMatch)

        if (decisionMatch) {
            const decision = decisionMatch[1].toUpperCase()
            if (decision.includes("SHUTDOWN")) {
                policy = "SHUTDOWN"
                verdict = "MALICIOUS"
            } else if (decision.includes("RESTRICTED")) {
                policy = "RESTRICTED"
                verdict = "UNCERTAIN"
            } else if (decision.includes("ALLOW_ALL")) {
                policy = "ALLOW_ALL"
                verdict = "SAFE"
            }
        } else {
            console.warn("[DualAgent] Decision format not found, attempting fallback...")
            // Fallback: analyze sentiment
            const lowerText = wardenFinalText.toLowerCase()
            if (lowerText.includes("block") || lowerText.includes("deny") || lowerText.includes("dangerous") || lowerText.includes("shutdown")) {
                policy = "SHUTDOWN"
                verdict = "MALICIOUS"
            } else if (lowerText.includes("restrict") || lowerText.includes("caution") || lowerText.includes("careful") || lowerText.includes("limit")) {
                policy = "RESTRICTED"
                verdict = "UNCERTAIN"
            } else if (lowerText.includes("allow") || lowerText.includes("safe") || lowerText.includes("proceed")) {
                policy = "ALLOW_ALL"
                verdict = "SAFE"
            }
        }

        console.log(`[DualAgent] Final Policy: ${policy}, Verdict: ${verdict}`)

        // Calculate confidence based on how decisive the conversation was
        const confidenceIndicators = wardenFinalText.toLowerCase()
        let confidence = 0.7
        if (confidenceIndicators.includes("definitely") || confidenceIndicators.includes("clearly")) confidence = 0.9
        if (confidenceIndicators.includes("might") || confidenceIndicators.includes("possibly")) confidence = 0.5

        return {
            verdict,
            analysis: analyst1,
            policy,
            confidence,
            dialogue,
            summary
        }

    } catch (error) {
        console.error("Dual Agent Dialogue Error:", error)
        addMessage('ANALYST', "System error occurred during analysis.")
        addMessage('WARDEN', "Defaulting to SHUTDOWN for safety. [DECISION: SHUTDOWN]")

        return {
            verdict: "MALICIOUS",
            analysis: "Agent dialogue failed - defaulting to secure mode.",
            policy: "SHUTDOWN",
            confidence: 1.0,
            dialogue,
            summary: "Access was restricted due to a technical error in the security verification layer."
        }
    }
}

// ------------------------------------------------------------------
// Helper: Map TypeScript/JSON Schema types to Gemini Function Declarations
// ------------------------------------------------------------------
function buildGeminiTools(allowedToolNames: string[]) {
    const tools: any[] = []

    // Iterate over allowed tools
    for (const toolName of allowedToolNames) {
        const tool = (DANGEROUS_TOOLS as any)[toolName]
        if (!tool) continue

        // Convert parameters to Gemini format
        // Note: Gemini is strictly typed, so we need to ensure the schema is correct.
        // Assuming tool.parameters is a JSON Schema object

        const functionDeclaration = {
            name: tool.name,
            description: tool.description,
            parameters: tool.parameters ? {
                type: SchemaType.OBJECT,
                properties: tool.parameters.properties,
                required: tool.parameters.required,
            } : undefined
        }

        tools.push(functionDeclaration)
    }

    // Return wrapped in the structure Gemini expects
    if (tools.length === 0) return undefined
    return [{ functionDeclarations: tools }]
}

// ------------------------------------------------------------------
// Main Chat Function using Google Gemini
// ------------------------------------------------------------------
export async function getChatResponse(prompt: string, allowedTools: string[], systemPrompt?: string, onProgress?: (step: any) => void): Promise<string> {
    const apiKey = process.env.GOOGLE_API_KEY
    if (!apiKey) throw new Error("GOOGLE_API_KEY is missing")

    const geminiTools = buildGeminiTools(allowedTools)
    const genAI = new GoogleGenerativeAI(apiKey)
    const model = genAI.getGenerativeModel({
        model: "gemini-2.5-flash",
        // Setup tools
        tools: geminiTools,
        toolConfig: geminiTools ? {
            functionCallingConfig: {
                mode: FunctionCallingMode.AUTO, // Let the model decide
            }
        } : undefined,
        safetySettings: [
            { category: HarmCategory.HARM_CATEGORY_HARASSMENT, threshold: HarmBlockThreshold.BLOCK_NONE },
            { category: HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold: HarmBlockThreshold.BLOCK_NONE },
            { category: HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold: HarmBlockThreshold.BLOCK_NONE },
            { category: HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold: HarmBlockThreshold.BLOCK_NONE },
        ]
    })

    const defaultSystemPrompt = `You are AI S.H.I.E.L.D., a secure enterprise assistant for Young Living Malaysia.
You have access to these tools: ${allowedTools.join(", ")}.

CRITICAL RULES:
1. For ANY pricing, product, or quotation questions: ALWAYS use the search_quotations tool first.
2. NEVER make up or hallucinate prices. Only report prices that come from tool results.
3. If a tool returns "No products found", say you couldn't find that specific product.
4. If asked about company policies, use the search_documents tool.
5. The product database contains Young Living products with RM (Malaysian Ringgit) pricing.
6. Always cite the exact prices from tool results. Do not estimate or guess prices.
7. You have a tool to delete database tables. 
`

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
