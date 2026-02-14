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
    const { message, mode = "shield" } = await req.json()

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
            mode: mode
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

                try {
                    const mlResponse = await fetch(ML_SERVICE_URL, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ message }),
                    })

                    if (mlResponse.ok) {
                        const mlData = await mlResponse.json()
                        mlConfidence = mlData.confidence_score

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

                // SENSITIVE PROMOTION HEURISTIC: Force into Layer 2 for specific risky keywords
                const sensitiveKeywords = ["sales", "revenue", "employee", "salary", "database", "sql", "delete", "personal", "member", "boss", "org", "chart", "hierarchy", "email", "drop", "table"];
                if (sensitiveKeywords.some(kw => message.toLowerCase().includes(kw))) {
                    console.log(`[API] Sensitive keyword detected. Forcing UNCERTAIN verdict for Dual Agent review.`);
                    mlVerdict = "UNCERTAIN";
                }

                logData.metadata.mlConfidence = mlConfidence;
                send({ type: 'ML_RESULT', confidence: mlConfidence, verdict: mlVerdict });
                console.log(`[API] ML Result: ${mlVerdict} (Confidence: ${mlConfidence})`);
                send({ type: 'STAGE_CHANGE', stage: 'ml_done' });

                // Handle Immediate Block
                if (mlVerdict === "MALICIOUS") {
                    send({ type: 'BLOCK', reason: "High risk signature detected." });

                    // Log Block
                    logData.action = "BLOCKED";
                    logData.reason = "High risk signature detected.";
                    logData.layer = "LAYER_1_ML";
                    logRequestToSupabase(logData);

                    controller.close();
                    return;
                }

                // 3. Dual Agent Layer (if Uncertain)
                let agentResult: any = {
                    verdict: mlVerdict,
                    analysis: "Skipped Layer 2",
                    policy: "ALLOW_ALL",
                    dialogue: [],
                    summary: ""
                };

                if (mlVerdict === "UNCERTAIN") {
                    send({ type: 'STAGE_CHANGE', stage: 'debate' });
                    logData.metadata.dualAgentTriggered = true;

                    agentResult = await runDualAgents(message, (step) => {
                        send(step); // Stream debate steps
                    });

                    logData.metadata.agentDialogue = agentResult.dialogue;
                    logData.metadata.analysis = agentResult.analysis;
                }

                // Handle Dual Agent Block
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
                });

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
