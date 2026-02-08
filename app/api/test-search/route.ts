import { NextResponse } from 'next/server'
import { DANGEROUS_TOOLS } from '@/lib/security/tools'

export async function GET() {
    try {
        const results = await DANGEROUS_TOOLS.search_documents.execute({ query: "What is the policy for medical leave?" })
        return NextResponse.json(results)
    } catch (error: any) {
        return NextResponse.json({ error: error.message }, { status: 500 })
    }
}
