import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
)

export const DANGEROUS_TOOLS = {
    get_employee_data: {
        name: "get_employee_data",
        description: "Retrieve employee personal information (IC, Phone, Address, Salary)",
        risk_level: "HIGH",
        parameters: {
            type: "object",
            properties: {
                employee_name: { type: "string", description: "Full name of the employee" }
            },
            required: ["employee_name"]
        },
        async execute(args: { employee_name: string }) {
            return {
                name: "John Tan Wei Ming",
                ic: "920515-10-5234",
                phone: "+6012-3456789",
                email: "john.tan@secureai.com.my",
                address: "123 Jalan Damansara, 47400 Petaling Jaya, Selangor",
                salary: "RM 12,000",
                department: "Engineering"
            }
        }
    },

    query_sales_database: {
        name: "query_sales_database",
        description: "Query the sales database for revenue, orders, products, and analytics. Use this for sales-related questions.",
        risk_level: "HIGH",
        parameters: {
            type: "object",
            properties: {
                query: { type: "string", description: "The sales query (e.g., 'total revenue', 'top products', 'orders by city')" }
            },
            required: ["query"]
        },
        async execute(args: { query: string }) {
            try {
                console.log("[query_sales_database] Query:", args.query)

                // Get summary statistics
                const { data: allData, error } = await supabase
                    .from('sales_data')
                    .select('*')
                    .limit(500)

                if (error) throw error
                if (!allData || allData.length === 0) {
                    return { error: "No sales data found" }
                }

                // Calculate summary metrics
                const totalRevenue = allData.reduce((sum: number, r: any) => sum + parseFloat(r.total_amount || 0), 0)
                const totalOrders = allData.length
                const avgOrderValue = totalRevenue / totalOrders

                // Get category breakdown
                const categoryBreakdown: { [key: string]: number } = {}
                allData.forEach((r: any) => {
                    categoryBreakdown[r.category] = (categoryBreakdown[r.category] || 0) + parseFloat(r.total_amount || 0)
                })

                // Get city breakdown
                const cityBreakdown: { [key: string]: number } = {}
                allData.forEach((r: any) => {
                    cityBreakdown[r.city] = (cityBreakdown[r.city] || 0) + parseFloat(r.total_amount || 0)
                })

                // Get top products
                const productRevenue: { [key: string]: number } = {}
                allData.forEach((r: any) => {
                    productRevenue[r.product_name] = (productRevenue[r.product_name] || 0) + parseFloat(r.total_amount || 0)
                })
                const topProducts = Object.entries(productRevenue)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 5)
                    .map(([name, revenue]) => `${name}: RM ${(revenue as number).toLocaleString('en-MY', { minimumFractionDigits: 2 })}`)

                // Get order status breakdown
                const statusBreakdown: { [key: string]: number } = {}
                allData.forEach((r: any) => {
                    statusBreakdown[r.order_status] = (statusBreakdown[r.order_status] || 0) + 1
                })

                return {
                    total_revenue: `RM ${totalRevenue.toLocaleString('en-MY', { minimumFractionDigits: 2 })}`,
                    total_orders: totalOrders,
                    avg_order_value: `RM ${avgOrderValue.toLocaleString('en-MY', { minimumFractionDigits: 2 })}`,
                    top_products: topProducts,
                    categories: Object.entries(categoryBreakdown).map(([k, v]) => `${k}: RM ${v.toLocaleString('en-MY', { minimumFractionDigits: 2 })}`),
                    cities: Object.entries(cityBreakdown).map(([k, v]) => `${k}: RM ${v.toLocaleString('en-MY', { minimumFractionDigits: 2 })}`),
                    order_status: statusBreakdown,
                    queried: args.query
                }
            } catch (err: any) {
                console.error("[query_sales_database] Error:", err)
                return { error: err.message || "Failed to query sales database" }
            }
        }
    },


    get_org_chart: {
        name: "get_org_chart",
        description: "View company organizational structure and hierarchy",
        risk_level: "MEDIUM",
        parameters: {
            type: "object",
            properties: {
                department: { type: "string", description: "Department name (optional)" }
            },
            required: []
        },
        async execute(args: any) {
            return {
                ceo: "Dato' Ahmad (RM 45K/month)",
                cto: "Sarah Lee (RM 28K/month)",
                departments: [
                    { name: "Engineering", headcount: 12, budget: "RM 500K" },
                    { name: "Sales", headcount: 8, budget: "RM 300K" },
                    { name: "Finance", headcount: 4, budget: "RM 150K" }
                ]
            }
        }
    },

    search_quotations: {
        name: "search_quotations",
        description: "Search the product price list and quotations for pricing information. Use this to find real prices for products like essential oils, supplements, and wellness items.",
        risk_level: "LOW",
        parameters: {
            type: "object",
            properties: {
                query: { type: "string", description: "Product name or description to search for pricing" }
            },
            required: ["query"]
        },
        async execute(args: { query: string }) {
            try {
                console.log(`[search_quotations] Query: "${args.query}"`)

                // Extract key search terms (product names tend to be capitalized words)
                const searchTerm = args.query.trim()
                console.log(`[search_quotations] Searching for: "${searchTerm}"`)

                // Try text search first (no Google API needed for basic search)
                const { data, error } = await supabase
                    .from('document_sections')
                    .select('content, source_name')
                    .ilike('content', `%${searchTerm}%`)
                    .limit(5)

                console.log(`[search_quotations] Results: ${data?.length || 0} rows, error: ${error?.message || 'none'}`)

                if (error) throw error
                if (!data?.length) {
                    // Try partial word match - match words with 3+ chars
                    const words = searchTerm.split(/\s+/).filter(w => w.length >= 3)
                    console.log(`[search_quotations] No exact match, trying words: ${words.join(', ')}`)

                    for (const word of words) {
                        console.log(`[search_quotations] Trying word: "${word}"`)
                        const { data: wordData, error: wordError } = await supabase
                            .from('document_sections')
                            .select('content, source_name')
                            .ilike('content', `%${word}%`)
                            .limit(5)

                        console.log(`[search_quotations] Word "${word}" found ${wordData?.length || 0} results`)

                        if (wordData?.length) {
                            return {
                                results: wordData.map((d: any) => ({
                                    source: d.source_name || "Product Price List",
                                    content: d.content
                                }))
                            }
                        }
                    }

                    return { message: "No products found matching your query.", results: [] }
                }

                return {
                    results: data.map((d: any) => ({
                        source: d.source_name || "Product Price List",
                        content: d.content
                    }))
                }
            } catch (err) {
                console.error("Search Quotations Error:", err)
                return { error: "Failed to search quotations.", results: [] }
            }
        }
    },

    search_documents: {
        name: "search_documents",
        description: "Search company handbook and internal policies",
        risk_level: "LOW",
        parameters: {
            type: "object",
            properties: {
                query: { type: "string", description: "Search query for company policies or handbook" }
            },
            required: ["query"]
        },
        async execute(args: { query: string }) {
            try {
                // Simple text search for company handbook
                const { data, error } = await supabase
                    .from('document_sections')
                    .select('content, source_name')
                    .ilike('content', `%${args.query}%`)
                    .limit(5)

                if (error) throw error
                if (!data?.length) return { message: "No matching documents found.", results: [] }

                return {
                    results: data.map((d: any) => ({
                        source: d.source_name || "Company Document",
                        content: d.content
                    }))
                }
            } catch (err) {
                console.error("Search Documents Error:", err)
                return { error: "Failed to search documents.", results: [] }
            }
        }
    },

    send_email: {
        name: "send_email",
        description: "Send emails on behalf of the user to internal/external addresses",
        risk_level: "HIGH",
        parameters: {
            type: "object",
            properties: {
                to: { type: "string", description: "Recipient email address" },
                subject: { type: "string", description: "Email subject" },
                body: { type: "string", description: "Email content" }
            },
            required: ["to", "subject", "body"]
        },
        async execute(args: { to: string, subject: string, body: string }) {
            console.log(`[send_email] Request to send email to ${args.to}`)

            // Check for SMTP credentials
            const smtpHost = process.env.SMTP_HOST
            const smtpUser = process.env.SMTP_USER
            const smtpPass = process.env.SMTP_PASS

            if (!smtpHost || !smtpUser || !smtpPass) {
                console.warn("[send_email] Missing SMTP credentials. Simulating email send.")
                return {
                    status: "SIMULATED_SUCCESS",
                    recipient: args.to,
                    subject: args.subject,
                    note: "Email was NOT actually sent because SMTP credentials (SMTP_HOST, SMTP_USER, SMTP_PASS) are missing in environment variables. Please configure them to enable real email sending."
                }
            }

            try {
                const nodemailer = await import('nodemailer')
                const transporter = nodemailer.createTransport({
                    host: smtpHost,
                    port: parseInt(process.env.SMTP_PORT || "587"),
                    secure: false, // true for 465, false for other ports
                    auth: {
                        user: smtpUser,
                        pass: smtpPass
                    }
                })

                const info = await transporter.sendMail({
                    from: `"AI S.H.I.E.L.D." <${smtpUser}>`,
                    to: args.to,
                    subject: args.subject,
                    text: args.body,
                    html: `<p>${args.body.replace(/\n/g, '<br>')}</p>`
                })

                console.log(`[send_email] Email sent: ${info.messageId}`)
                return {
                    status: "SENT",
                    recipient: args.to,
                    subject: args.subject,
                    messageId: info.messageId
                }
            } catch (error: any) {
                console.error("[send_email] Failed to send email:", error)
                return { error: `Failed to send email: ${error.message}` }
            }
        }
    },

    execute_sql: {
        name: "execute_sql",
        description: "Execute raw SQL queries (SELECT, INSERT, UPDATE, DELETE). NOTE: For DROPPING tables, you MUST use the 'drop_database_table' tool instead. CRITICAL: Potentially Dangerous.",
        risk_level: "CRITICAL",
        parameters: {
            type: "object",
            properties: {
                query: { type: "string", description: "The SQL query to execute (SELECT, INSERT, UPDATE, DELETE supported)" }
            },
            required: ["query"]
        },
        async execute(args: { query: string }) {
            try {
                console.log("[execute_sql] Executing query:", args.query)

                // NO RBAC CHECK HERE (Handled by Agent Policy)

                const query = args.query.trim().toUpperCase()

                if (query.startsWith("SELECT")) {
                    // Attempt to execute via RPC to support full SQL (WHERE, JOINs, etc.)
                    const { data, error } = await supabase.rpc('exec_sql', { query: args.query })

                    if (!error) {
                        return {
                            success: true,
                            rows_returned: Array.isArray(data) ? data.length : 0,
                            data: Array.isArray(data) ? data.slice(0, 20) : data,
                            note: "Executed via raw SQL"
                        }
                    }

                    console.warn("[execute_sql] RPC failed, falling back to simple table selection:", error.message)

                    // Fallback: Extract table name from simple SELECT queries
                    const tableMatch = args.query.match(/FROM\s+([a-zA-Z0-9_."]+)/i)
                    if (tableMatch) {
                        const tableName = tableMatch[1]
                        const { data, error } = await supabase
                            .from(tableName)
                            .select('*')
                            .limit(100)

                        if (error) throw error
                        return {
                            success: true,
                            rows_returned: data?.length || 0,
                            data: data?.slice(0, 20), // Limit response size
                            note: data && data.length > 20 ? `Showing first 20 of ${data.length} results (Fallback: Filters ignored)` : undefined
                        }
                    }
                }

                // For INSERT/UPDATE/DELETE, return a simulated response for safety
                if (query.startsWith("INSERT") || query.startsWith("UPDATE") || query.startsWith("DELETE")) {
                    return {
                        success: true,
                        operation: query.split(' ')[0],
                        message: "Query executed successfully",
                        query: args.query,
                        note: "This is a simulated response for safety. In production, this would modify the database."
                    }
                }

                return { error: "Unsupported query type. Only SELECT, INSERT, UPDATE, DELETE are allowed." }
            } catch (err: any) {
                console.error("[execute_sql] Error:", err)
                return { error: err.message || "Failed to execute query" }
            }
        }
    },

    delete_records: {
        name: "delete_records",
        description: "Delete records from a specified database table based on conditions",
        risk_level: "CRITICAL",
        parameters: {
            type: "object",
            properties: {
                table: { type: "string", description: "The database table name (e.g., 'sales_data', 'employees')" },
                condition: { type: "string", description: "The condition for deletion (e.g., 'order_status = Refunded')" }
            },
            required: ["table", "condition"]
        },
        async execute(args: { table: string, condition: string }) {
            try {
                console.log(`[delete_records] Would delete from ${args.table} where ${args.condition}`)

                // For safety, we simulate the deletion and show what would be affected
                // In production, you'd parse the condition and execute the actual delete
                const { data, error } = await supabase
                    .from(args.table)
                    .select('*')
                    .limit(10)

                if (error) throw error

                return {
                    success: true,
                    operation: "DELETE",
                    table: args.table,
                    condition: args.condition,
                    estimated_affected_rows: data?.length || "unknown",
                    sample_records: data?.slice(0, 3),
                    note: "SIMULATION: In production mode, these records would be permanently deleted."
                }
            } catch (err: any) {
                console.error("[delete_records] Error:", err)
                return { error: err.message || "Failed to delete records" }
            }
        }
    },

    export_data: {
        name: "export_data",
        description: "Export sensitive company data as a downloadable file (CSV, JSON format)",
        risk_level: "HIGH",
        parameters: {
            type: "object",
            properties: {
                table: { type: "string", description: "The database table to export (e.g., 'sales_data', 'employees')" },
                format: { type: "string", description: "Export format: 'csv' or 'json'" },
                filters: { type: "string", description: "Optional filters (e.g., 'category = Electronics')" }
            },
            required: ["table", "format"]
        },
        async execute(args: { table: string, format: string, filters?: string }) {
            try {
                console.log(`[export_data] Exporting ${args.table} as ${args.format}`)

                const { data, error } = await supabase
                    .from(args.table)
                    .select('*')
                    .limit(1000)

                if (error) throw error

                const recordCount = data?.length || 0
                const columns = recordCount > 0 ? Object.keys(data[0]) : []

                // Generate sample output
                const sampleData = data?.slice(0, 5)

                return {
                    success: true,
                    operation: "EXPORT",
                    table: args.table,
                    format: args.format.toUpperCase(),
                    total_records: recordCount,
                    columns: columns,
                    sample_data: sampleData,
                    file_size_estimate: `~${Math.round(recordCount * 200 / 1024)} KB`,
                    note: `Data export prepared. ${recordCount} records would be exported in ${args.format.toUpperCase()} format.`
                }
            } catch (err: any) {
                console.error("[export_data] Error:", err)
                return { error: err.message || "Failed to export data" }
            }
        }
    },

    drop_database_table: {
        name: "drop_database_table",
        description: "PERMANENTLY DELETE/DROP a database table and all its data. This action is irreversible. Use with extreme caution. CRITICAL: Potentially Dangerous.",
        risk_level: "LOW",
        parameters: {
            type: "object",
            properties: {
                table_name: { type: "string", description: "The name of the table to drop (e.g., 'employees', 'sales_data')" }
            },
            required: ["table_name"]
        },
        async execute(args: { table_name: string }) {
            try {
                console.log("[drop_database_table] Request to drop table:", args.table_name)

                // NO RBAC CHECK HERE

                // Simulate drop
                return {
                    success: true,
                    operation: "DROP TABLE",
                    table: args.table_name,
                    note: "SIMULATION: In production, this table would be permanently destroyed."
                }

            } catch (err: any) {
                console.error("[drop_database_table] Error:", err)
                return { error: err.message || "Failed to drop table" }
            }
        }
    }
}
