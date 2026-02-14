import { NextResponse } from 'next/server';
import { supabase } from '@/lib/supabase';

export async function POST(request: Request) {
    try {
        const { requestId, prompt, human_label } = await request.json();

        // 1. Notify the ML Service (Optional: wrap in try/catch if ML service is unstable)
        try {
            // Use environment variable for ML API URL, default to localhost for development
            const mlApiUrl = process.env.ML_API_URL || 'http://127.0.0.1:8000';
            await fetch(`${mlApiUrl}/feedback`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt, human_label }),
            }).catch(err => console.error("Fetch to ML Service failed:", err));
        } catch (mlErr) {
            console.error("ML Service unreachable, proceeding with DB update:", mlErr);
        }

        // 2. Update Supabase so the Dashboard UI reflects the "Reviewed" state
        // We also update the 'action' field so it's no longer 'BLOCKED' if marked safe
        const newAction = human_label === 0 ? 'ALLOWED' : 'BLOCKED';

        console.log(`Updating Request ${requestId} to ${newAction}...`);

        const { data, error } = await supabase
            .from('requests')
            .update({
                human_label,
                reviewed: true,
                reviewed_at: new Date().toISOString(),
                action: newAction
            })
            .eq('id', requestId)
            .select(); // select() ensures we get the updated row back to verify success

        if (data) console.log("Supabase update successful:", data);
        if (error) throw error;

        return NextResponse.json({ success: true });
    } catch (error: any) {
        console.error("Feedback API Error:", error);
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}