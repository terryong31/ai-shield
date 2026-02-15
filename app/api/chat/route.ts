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
                            } else if (mlConfidence <= 0.15) {
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
                // BUT: Context is king. We need to avoid false positives like Base64 strings.
                const sensitiveKeywords = ["delete", "drop", "update", "execute", "select", "insert", "sql", "database", "table", "schema", "admin", "truncate", "email", "send"];

                // Helper to check for Base64-like patterns (long strings with no spaces, mixed case numbers/letters)
                const isBase64Like = (str: string) => {
                    const base64Pattern = /^[A-Za-z0-9+/=]{20,}$/; // Simplistic check for long continuous alphanumeric blocks
                    const words = str.split(/\s+/);
                    return words.some(word => base64Pattern.test(word));
                };

                const containsSensitiveKeyword = sensitiveKeywords.some(kw => message.toLowerCase().includes(kw));
                const appearsEncoded = isBase64Like(message);

                // If sensitive AND NOT encoded AND ML is not extremely confident it's safe (>0.05)
                // If confidence is < 0.05, we TRUST the model that it's safe (e.g. 0.00 confidence = 100% safe)
                if (containsSensitiveKeyword && !appearsEncoded && mlConfidence > 0.05 && mlVerdict === "SAFE" && mode === 'shield') {
                    console.log(`[API] Sensitive keyword detected (Confidence: ${mlConfidence}). Escalating to Dual Agents.`);
                    mlVerdict = "UNCERTAIN";
                } else if (appearsEncoded) {
                    console.log(`[API] Message appears to contain encoded/hash data. Skipping sensitive keyword sensitive check.`);
                }

                // Add Passphrase check heuristic: If passphrase is provided, we should run agents to verify it,
                // BUT ONLY if the ML layer didn't already flag it as definitely MALICIOUS.
                // AND: Don't trigger if it's extremely safe (Confidence < 0.1) and NOT sensitive.
                // This prevents "Hello" or "Base64(Safe)" from being forced into Dual Agents just because a key exists.
                if (passphrase && mode === 'shield' && mlVerdict !== "MALICIOUS") {
                    if (containsSensitiveKeyword || mlVerdict === "UNCERTAIN" || mlConfidence > 0.1) {
                        console.log(`[API] Passphrase provided AND request warrants review. Escalating to Dual Agents.`);
                        mlVerdict = "UNCERTAIN";
                    } else {
                        console.log(`[API] Passphrase provided but request is high-confidence SAFE (${mlConfidence}). Skipping Dual Agents.`);
                    }
                }


                logData.metadata.mlConfidence = mlConfidence;
                logData.metadata.generated_intent = mlVerdict;

                send({ type: 'ML_RESULT', confidence: mlConfidence, verdict: mlVerdict });

                // CRITICAL SECURITY FIX: Immediately BLOCK high-confidence malicious requests
                if (mlVerdict === "MALICIOUS") {
                    console.log(`[API] Blocking High-Confidence Malicious Request (Confidence: ${mlConfidence})`);
                    send({ type: 'BLOCK', reason: "High confidence ML detection triggered immediate block." });

                    // Ensure frontend knows we are done
                    send({ type: 'STAGE_CHANGE', stage: 'final' });

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

                    // Ensure frontend knows we are done
                    send({ type: 'STAGE_CHANGE', stage: 'final' });

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
