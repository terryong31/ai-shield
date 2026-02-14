import { NextResponse } from "next/server"
import { supabase } from "@/lib/supabase"
import { DANGEROUS_TOOLS } from "@/lib/security/tools"
import { runDualAgents, getChatResponse, getGroqResponse } from "@/lib/security/agents"

// Use environment variable for local dev, fallback to relative path for Vercel
const ML_SERVICE_URL = process.env.ML_SERVICE_URL || "/api/predict"

// Helper for uniform logging to Supabase (fire and forget pattern for streaming)
async function logRequestToSupabase(data: any) {
    try {
        await supabase.from('requests').insert({
            query: data.query,
            action: data.action,
            reason: data.reason,
            layer: data.layer,
            metadata: data.metadata,
            reviewed: false
        });
    } catch (err) {
        console.error("Supabase Logging Error:", err);
    }
}

export const dynamic = 'force-dynamic';

export async function POST(req: Request) {
    const { message, mode = "shield", signer_name, passphrase } = await req.json()

    // Initialize log data structure
    let logData: any = {
        query: message,
        action: "ALLOWED",
        reason: "Processed",
        layer: "SYSTEM",
        metadata: {
            mlConfidence: 0,
            generated_intent: "None",
            analysis: "Standard processing",
            tool_calls: [],
            aiResponse: "",
            toolPolicy: "ALLOW_ALL",
            dualAgentTriggered: false,
            agentDialogue: [],
            mode: mode,
            authorized_signer: signer_name, // Log the signer (legacy or if passed)
            passphrase_provided: !!passphrase // Log if passphrase was provided (do not log the actual passphrase)
        }
    };

    const encoder = new TextEncoder();
    const stream = new ReadableStream({
        async start(controller) {
            const send = (data: any) => {
                controller.enqueue(encoder.encode(JSON.stringify(data) + "\n\n"));
                // Small delay to ensure UI has time to render animations
                // await new Promise(r => setTimeout(r, 100)); 
            };

            try {
                // 1. Start Event
                send({ type: 'START', query: message });

                // 2. ML Layer
                send({ type: 'STAGE_CHANGE', stage: 'ml_processing' });

                let mlVerdict = "UNCERTAIN"
                let mlConfidence = 0

                // BYPASS LOGIC: If mode is NOT 'shield', skip ML checks
                if (mode === 'shield') {
                    try {
                        const mlResponse = await fetch(ML_SERVICE_URL, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ message }),
                        })

                        if (mlResponse.ok) {
                            const mlData = await mlResponse.json()
                            mlConfidence = mlData.confidence_score

                            // Adjust ML thresholds
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
                } else {
                    console.log(`[API] Guardrails disabled (Mode: ${mode}). Skipping ML check.`);
                    mlVerdict = "SAFE"; // Force safe
                    mlConfidence = 0;
                }

                // SENSITIVE PROMOTION HEURISTIC: Force into Layer 2 for specific risky keywords
                const sensitiveKeywords = ["delete", "drop", "update", "execute", "select", "insert", "sql", "database", "table", "schema", "admin", "truncate", "email", "send"];
                const isSensitive = sensitiveKeywords.some(kw => message.toLowerCase().includes(kw));

                // If sensitive, downgrade "SAFE" to "UNCERTAIN" to force Agent Review, unless explicitly malicious
                if (isSensitive && mlVerdict === "SAFE" && mode === 'shield') {
                    console.log(`[API] Sensitive keyword detected. Escalating to Dual Agents.`);
                    mlVerdict = "UNCERTAIN";
                }

                // Add Passphrase check heuristic: If passphrase is provided, we should run agents to verify it,
                // BUT ONLY if the ML layer didn't already flag it as definitely MALICIOUS.
                if (passphrase && mode === 'shield' && mlVerdict !== "MALICIOUS") {
                    console.log(`[API] Passphrase provided. Escalating to Dual Agents for Authorization.`);
                    mlVerdict = "UNCERTAIN"; // Force agent review to validate passphrase
                }


                logData.metadata.mlConfidence = mlConfidence;
                logData.metadata.generated_intent = mlVerdict;

                send({ type: 'ML_RESULT', confidence: mlConfidence, verdict: mlVerdict });

                // CRITICAL SECURITY FIX: Immediately BLOCK high-confidence malicious requests
                if (mlVerdict === "MALICIOUS") {
                    console.log(`[API] Blocking High-Confidence Malicious Request (Confidence: ${mlConfidence})`);
                    send({ type: 'BLOCK', reason: "High confidence ML detection triggered immediate block." });

                    logData.action = "BLOCKED";
                    logData.reason = "High confidence ML detection";
                    logData.layer = "LAYER_1_ML";
                    logRequestToSupabase(logData); // Fire and forget

                    controller.close();
                    return;
                }

                // 3. Dual Agent Layer (Layer 2)
                // Trigger if ML is UNCERTAIN or if 'guardrail' mode is active (paranoid mode)
                // Note: MALICIOUS is handled above, so we only need to check for UNCERTAIN or forced check in SAFE
                let agentResult: any = { verdict: "SAFE", policy: "ALLOW_ALL", summary: "Skipped Layer 2", dialogue: [] };

                if (mlVerdict === "UNCERTAIN" || mode === 'guardrail') {
                    send({ type: 'STAGE_CHANGE', stage: 'debate' });
                    logData.metadata.dualAgentTriggered = true;

                    // Pass passphrase to agents
                    agentResult = await runDualAgents(message, passphrase, (step) => {
                        send(step);
                    });

                    logData.metadata.agentAnalysis = agentResult.analysis;
                    logData.metadata.agentDialogue = agentResult.dialogue;
                }

                // If Agents decide to BLOCK (MALICIOUS)
                if (agentResult.verdict === "MALICIOUS") {
                    send({ type: 'BLOCK', reason: agentResult.summary });

                    // Log Block
                    logData.action = "BLOCKED";
                    logData.reason = agentResult.summary;
                    logData.layer = "LAYER_2_DUAL_AGENT";
                    logRequestToSupabase(logData);

                    controller.close();
                    return;
                }

                // 4. Final Execution
                send({ type: 'STAGE_CHANGE', stage: 'final' });
                console.log(`[API] Final Policy Update: ${agentResult.policy}`);
                send({ type: 'POLICY_UPDATE', policy: agentResult.policy });

                let allowedTools = Object.keys(DANGEROUS_TOOLS);
                if (agentResult.policy === "RESTRICTED") {
                    allowedTools = allowedTools.filter(t => DANGEROUS_TOOLS[t as keyof typeof DANGEROUS_TOOLS].risk_level === "LOW");
                } else if (agentResult.policy === "SHUTDOWN") {
                    allowedTools = [];
                }

                logData.metadata.toolPolicy = agentResult.policy;
                logData.metadata.allowedTools = allowedTools;

                const realResponse = await getChatResponse(message, allowedTools, undefined, (event) => {
                    send(event);
                }, passphrase); // Pass passphrase (was signer_name)

                logData.metadata.aiResponse = realResponse;
                logRequestToSupabase(logData);

                send({ type: 'FINAL_RESPONSE', text: realResponse });

                controller.close();

            } catch (error: any) {
                console.error("Stream Error:", error);
                send({ type: 'ERROR', message: error.message });
                controller.close();
            }
        }
    });

    return new Response(stream, {
        headers: {
            'Content-Type': 'application/x-ndjson',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
        },
    });
}
