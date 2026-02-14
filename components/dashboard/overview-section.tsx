import { useEffect, useState, useMemo, useCallback } from "react"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { supabase } from "@/lib/supabase"
import { Line, LineChart, CartesianGrid, XAxis, Label, PolarGrid, PolarRadiusAxis, RadialBar, RadialBarChart, Sankey, Tooltip as RechartsTooltip, Rectangle, Layer, ResponsiveContainer } from "recharts"
import WordCloud from "react-d3-cloud"

const chartConfig = {
    views: {
        label: "Requests",
    },
    blocked: {
        label: "Blocked Attempts",
        color: "#ffffff",
    },
    safe: {
        label: "Safe Queries",
        color: "#ffffff",
    },
} satisfies ChartConfig

const totalRequestsConfig = {
    value: { label: "Requests" },
    total: { label: "Total", color: "#ffffff" },
} satisfies ChartConfig

const blockedConfig = {
    value: { label: "Blocked" },
    blocked: { label: "Blocked", color: "#ef4444" },
} satisfies ChartConfig

const safeConfig = {
    value: { label: "Safe" },
    safe: { label: "Safe", color: "#22c55e" },
} satisfies ChartConfig

const threatConfig = {
    value: { label: "Threat" },
    threat: { label: "Threat", color: "#ef4444" },
} satisfies ChartConfig

// Custom Sankey Node
// Custom Sankey Node
const DemoSankeyNode = ({ x, y, width, height, index, payload, containerWidth }: any) => {
    if (isNaN(y) || isNaN(height)) return null;
    // For responsive, we can't easily know containerWidth inside the node without passing it down.
    // But we know the node is "out" if x is close to the right edge.
    // A simple heuristic: if x > 50% of 900 (or whatever base width), align text to end.
    // Or better: check if it's the last layer (index based? no, payload doesn't have layer index).
    // Let's assume nodes on the right side (x > 100) are "out" or should be left-aligned?
    // Actually, standard Sankey nodes: left nodes -> text start, right nodes -> text end.
    // Let's use a heuristic based on x position relative to a presumed width, or just align based on "source" vs "target" nature?
    // The previous logic `isOut` checked against `containerWidth`.
    // Let's safe-guard containerWidth or default to a large number.
    const safeWidth = containerWidth || 1000;
    const isOut = x + width + 100 > safeWidth;
    return (
        <Layer key={`CustomNode${index}`}>
            <Rectangle
                x={x} y={y} width={width} height={height}
                fill={payload.color || "#8884d8"}
                fillOpacity="1"
            />
            <text
                textAnchor={isOut ? 'end' : 'start'}
                x={isOut ? x - 6 : x + width + 6}
                y={y + height / 2}
                fontSize="14"
                stroke="none"
                fill="#fff"
                dy={4} // vertical align middle
            >
                {payload.name}
                {payload.value ? ` (${payload.value})` : ''}
            </text>
        </Layer>
    );
};

export function OverviewSection() {
    const [metrics, setMetrics] = useState({
        total: 0,
        blocked: 0,
        safe: 0,
        threatLevel: 0
    })
    const [chartData, setChartData] = useState<any[]>([])
    const [activeChart, setActiveChart] = useState<keyof typeof chartConfig>("blocked")
    const [sankeyData, setSankeyData] = useState<{ nodes: any[], links: any[] }>({ nodes: [], links: [] })
    const [wordCloudData, setWordCloudData] = useState<{ text: string, value: number }[]>([])

    useEffect(() => {
        fetchData()
        const channel = supabase
            .channel('dashboard-updates')
            .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'requests' }, () => {
                fetchData()
            })
            .subscribe()

        return () => {
            supabase.removeChannel(channel)
        }
    }, [])

    const fetchData = async () => {
        const { data: requests } = await supabase
            .from('requests')
            .select('*')
            .order('created_at', { ascending: true })

        if (!requests) return

        const total = requests.length
        const blocked = requests.filter(r => r.action === "BLOCKED").length
        const safe = total - blocked
        const threatLevel = total > 0 ? Math.round((blocked / total) * 100) : 0

        setMetrics({ total, blocked, safe, threatLevel })

        // Process data for interactive chart
        const timeFrames: { [key: string]: { date: string, blocked: number, safe: number } } = {}

        // Sankey Data Processing
        let mlSafe = 0
        let mlBlocked = 0
        let mlUncertain = 0
        let daSafe = 0
        let daBlocked = 0

        // Word Cloud Processing
        const wordCounts: { [key: string]: number } = {}
        const stopWords = new Set(['the', 'is', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'up', 'about', 'into', 'over', 'after', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his', 'her', 'its', 'our', 'their', 'what', 'where', 'when', 'who', 'how', 'why', 'can', 'could', 'would', 'should', 'will', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'not', 'no', 'yes', 'please', 'hi', 'hello', 'hey', 'thanks', 'thank'])

        requests.forEach(r => {
            // Line Chart Data
            const date = new Date(r.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            if (!timeFrames[date]) {
                timeFrames[date] = { date, blocked: 0, safe: 0 }
            }
            if (r.action === "BLOCKED") {
                timeFrames[date].blocked++
            } else {
                timeFrames[date].safe++
            }

            // Sankey Data
            const layer = r.layer || "LAYER_1_ML" // Default to ML if missing
            const action = r.action
            // Heuristic for uncertain: came from Layer 2 (Dual Agent) or was flagged as uncertain in metadata
            const isDualAgent = r.layer === "LAYER_2_DUAL_AGENT" || r.metadata?.dualAgentTriggered

            if (!isDualAgent) {
                // Resolved at ML Layer
                if (action === "BLOCKED") mlBlocked++
                else mlSafe++
            } else {
                // Sent to Dual Agent (Uncertain at ML Layer)
                mlUncertain++
                if (action === "BLOCKED") daBlocked++
                else daSafe++
            }

            // Word Cloud
            const words = (r.query || "").toLowerCase().replace(/[^\w\s]/g, '').split(/\s+/)
            words.forEach((word: string) => {
                if (word && !stopWords.has(word) && isNaN(Number(word))) {
                    wordCounts[word] = (wordCounts[word] || 0) + 1
                }
            })
        })

        const formattedData = Object.values(timeFrames).slice(-15)
        setChartData(formattedData)

        // Set Sankey Data
        const nodes = [
            { name: "Total Requests", color: "#60a5fa" },      // 0
            { name: "ML: Safe", color: "#4ade80" },            // 1
            { name: "ML: Blocked", color: "#f87171" },         // 2
            { name: "ML: Uncertain", color: "#fbbf24" },       // 3
            { name: "Agent: Approved", color: "#4ade80" },     // 4
            { name: "Agent: Blocked", color: "#f87171" }       // 5
        ]

        const links = []
        if (mlSafe > 0) links.push({ source: 0, target: 1, value: mlSafe })
        if (mlBlocked > 0) links.push({ source: 0, target: 2, value: mlBlocked })
        if (mlUncertain > 0) links.push({ source: 0, target: 3, value: mlUncertain })
        if (daSafe > 0) links.push({ source: 3, target: 4, value: daSafe })
        if (daBlocked > 0) links.push({ source: 3, target: 5, value: daBlocked })

        setSankeyData({ nodes, links })

        // Set Word Cloud Data
        const cloudData = Object.entries(wordCounts)
            .map(([text, value]) => ({ text, value: value * 100 })) // Scale up for visibility
            .sort((a, b) => b.value - a.value)
            .slice(0, 50) // Top 50 words

        setWordCloudData(cloudData)
    }

    const totals = useMemo(
        () => ({
            blocked: chartData.reduce((acc, curr) => acc + curr.blocked, 0),
            safe: chartData.reduce((acc, curr) => acc + curr.safe, 0),
        }),
        [chartData]
    )

    const onWordClick = useCallback((word: any) => {
        console.log(`Word clicked: ${word.text}`)
    }, [])

    return (
        <div className="space-y-6">
            {/* Radial Charts Row */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {/* Total Requests */}
                <Card className="flex flex-col">
                    <CardHeader className="items-center pb-0">
                        <CardTitle className="text-sm">Total Requests</CardTitle>
                    </CardHeader>
                    <CardContent className="flex-1 pb-0">
                        <ChartContainer
                            config={totalRequestsConfig}
                            className="mx-auto aspect-square max-h-[180px]"
                        >
                            <RadialBarChart
                                data={[{ name: "total", value: metrics.total, fill: "var(--color-total)" }]}
                                startAngle={0}
                                endAngle={Math.min(360, (metrics.total / Math.max(1, metrics.total)) * 360)}
                                innerRadius={60}
                                outerRadius={85}
                            >
                                <PolarGrid
                                    gridType="circle"
                                    radialLines={false}
                                    stroke="none"
                                    className="first:fill-muted last:fill-background"
                                    polarRadius={[66, 54]}
                                />
                                <RadialBar dataKey="value" background cornerRadius={10} />
                                <PolarRadiusAxis tick={false} tickLine={false} axisLine={false}>
                                    <Label
                                        content={({ viewBox }) => {
                                            if (viewBox && "cx" in viewBox && "cy" in viewBox) {
                                                return (
                                                    <text x={viewBox.cx} y={viewBox.cy} textAnchor="middle" dominantBaseline="middle">
                                                        <tspan x={viewBox.cx} y={viewBox.cy} className="fill-foreground text-3xl font-bold">
                                                            {metrics.total}
                                                        </tspan>
                                                        <tspan x={viewBox.cx} y={(viewBox.cy || 0) + 20} className="fill-muted-foreground text-xs">
                                                            Total
                                                        </tspan>
                                                    </text>
                                                )
                                            }
                                        }}
                                    />
                                </PolarRadiusAxis>
                            </RadialBarChart>
                        </ChartContainer>
                    </CardContent>
                </Card>

                {/* Injection Attempts */}
                <Card className="flex flex-col">
                    <CardHeader className="items-center pb-0">
                        <CardTitle className="text-sm">Injection Attempts</CardTitle>
                    </CardHeader>
                    <CardContent className="flex-1 pb-0">
                        <ChartContainer
                            config={blockedConfig}
                            className="mx-auto aspect-square max-h-[180px]"
                        >
                            <RadialBarChart
                                data={[{ name: "blocked", value: metrics.blocked, fill: "var(--color-blocked)" }]}
                                startAngle={0}
                                endAngle={metrics.total > 0 ? (metrics.blocked / metrics.total) * 360 : 0}
                                innerRadius={60}
                                outerRadius={85}
                            >
                                <PolarGrid
                                    gridType="circle"
                                    radialLines={false}
                                    stroke="none"
                                    className="first:fill-muted last:fill-background"
                                    polarRadius={[66, 54]}
                                />
                                <RadialBar dataKey="value" background cornerRadius={10} />
                                <PolarRadiusAxis tick={false} tickLine={false} axisLine={false}>
                                    <Label
                                        content={({ viewBox }) => {
                                            if (viewBox && "cx" in viewBox && "cy" in viewBox) {
                                                return (
                                                    <text x={viewBox.cx} y={viewBox.cy} textAnchor="middle" dominantBaseline="middle">
                                                        <tspan x={viewBox.cx} y={viewBox.cy} className="fill-red-500 text-3xl font-bold">
                                                            {metrics.blocked}
                                                        </tspan>
                                                        <tspan x={viewBox.cx} y={(viewBox.cy || 0) + 20} className="fill-muted-foreground text-xs">
                                                            Blocked
                                                        </tspan>
                                                    </text>
                                                )
                                            }
                                        }}
                                    />
                                </PolarRadiusAxis>
                            </RadialBarChart>
                        </ChartContainer>
                    </CardContent>
                </Card>

                {/* Safe Queries */}
                <Card className="flex flex-col">
                    <CardHeader className="items-center pb-0">
                        <CardTitle className="text-sm">Safe Queries</CardTitle>
                    </CardHeader>
                    <CardContent className="flex-1 pb-0">
                        <ChartContainer
                            config={safeConfig}
                            className="mx-auto aspect-square max-h-[180px]"
                        >
                            <RadialBarChart
                                data={[{ name: "safe", value: metrics.safe, fill: "var(--color-safe)" }]}
                                startAngle={0}
                                endAngle={metrics.total > 0 ? (metrics.safe / metrics.total) * 360 : 0}
                                innerRadius={60}
                                outerRadius={85}
                            >
                                <PolarGrid
                                    gridType="circle"
                                    radialLines={false}
                                    stroke="none"
                                    className="first:fill-muted last:fill-background"
                                    polarRadius={[66, 54]}
                                />
                                <RadialBar dataKey="value" background cornerRadius={10} />
                                <PolarRadiusAxis tick={false} tickLine={false} axisLine={false}>
                                    <Label
                                        content={({ viewBox }) => {
                                            if (viewBox && "cx" in viewBox && "cy" in viewBox) {
                                                return (
                                                    <text x={viewBox.cx} y={viewBox.cy} textAnchor="middle" dominantBaseline="middle">
                                                        <tspan x={viewBox.cx} y={viewBox.cy} className="fill-green-500 text-3xl font-bold">
                                                            {metrics.safe}
                                                        </tspan>
                                                        <tspan x={viewBox.cx} y={(viewBox.cy || 0) + 20} className="fill-muted-foreground text-xs">
                                                            Safe
                                                        </tspan>
                                                    </text>
                                                )
                                            }
                                        }}
                                    />
                                </PolarRadiusAxis>
                            </RadialBarChart>
                        </ChartContainer>
                    </CardContent>
                </Card>

                {/* Threat Level */}
                <Card className="flex flex-col">
                    <CardHeader className="items-center pb-0">
                        <CardTitle className="text-sm">Threat Level</CardTitle>
                    </CardHeader>
                    <CardContent className="flex-1 pb-0">
                        <ChartContainer
                            config={threatConfig}
                            className="mx-auto aspect-square max-h-[180px]"
                        >
                            <RadialBarChart
                                data={[{ name: "threat", value: metrics.threatLevel, fill: "var(--color-threat)" }]}
                                startAngle={0}
                                endAngle={(metrics.threatLevel / 100) * 360}
                                innerRadius={60}
                                outerRadius={85}
                            >
                                <PolarGrid
                                    gridType="circle"
                                    radialLines={false}
                                    stroke="none"
                                    className="first:fill-muted last:fill-background"
                                    polarRadius={[66, 54]}
                                />
                                <RadialBar dataKey="value" background cornerRadius={10} />
                                <PolarRadiusAxis tick={false} tickLine={false} axisLine={false}>
                                    <Label
                                        content={({ viewBox }) => {
                                            if (viewBox && "cx" in viewBox && "cy" in viewBox) {
                                                return (
                                                    <text x={viewBox.cx} y={viewBox.cy} textAnchor="middle" dominantBaseline="middle">
                                                        <tspan x={viewBox.cx} y={viewBox.cy} className={`text-3xl font-bold ${metrics.threatLevel > 20 ? "fill-red-500" :
                                                            metrics.threatLevel > 10 ? "fill-yellow-500" : "fill-green-500"
                                                            }`}>
                                                            {metrics.threatLevel}%
                                                        </tspan>
                                                        <tspan x={viewBox.cx} y={(viewBox.cy || 0) + 20} className="fill-muted-foreground text-xs">
                                                            Threat
                                                        </tspan>
                                                    </text>
                                                )
                                            }
                                        }}
                                    />
                                </PolarRadiusAxis>
                            </RadialBarChart>
                        </ChartContainer>
                    </CardContent>
                </Card>
            </div>

            {/* Interactive Line Chart */}
            <Card className="py-4 sm:py-0">
                <CardHeader className="flex flex-col items-stretch border-b !p-0 sm:flex-row">
                    <div className="flex flex-1 flex-col justify-center gap-1 px-6 pb-3 sm:pb-0">
                        <CardTitle>AI S.H.I.E.L.D. Activity</CardTitle>
                        <CardDescription>
                            Real-time monitoring of safe vs malicious interactions
                        </CardDescription>
                    </div>
                    <div className="flex">
                        {["blocked", "safe"].map((key) => {
                            const chart = key as keyof typeof chartConfig
                            return (
                                <button
                                    key={chart}
                                    data-active={activeChart === chart}
                                    className="data-[active=true]:bg-muted/50 flex flex-1 flex-col justify-center gap-1 border-t px-6 py-4 text-left even:border-l sm:border-t-0 sm:border-l sm:px-8 sm:py-6"
                                    onClick={() => setActiveChart(chart)}
                                >
                                    <span className="text-muted-foreground text-xs">
                                        {chartConfig[chart].label}
                                    </span>
                                    <span className="text-lg leading-none font-bold sm:text-3xl">
                                        {totals[key as keyof typeof totals].toLocaleString()}
                                    </span>
                                </button>
                            )
                        })}
                    </div>
                </CardHeader>
                <CardContent className="px-2 sm:p-6">
                    <ChartContainer
                        config={chartConfig}
                        className="aspect-auto h-[250px] w-full"
                    >
                        <LineChart
                            accessibilityLayer
                            data={chartData}
                            margin={{
                                left: 12,
                                right: 12,
                            }}
                        >
                            <CartesianGrid vertical={false} />
                            <XAxis
                                dataKey="date"
                                tickLine={false}
                                axisLine={false}
                                tickMargin={8}
                                minTickGap={32}
                            />
                            <ChartTooltip
                                content={
                                    <ChartTooltipContent
                                        className="w-[150px]"
                                        nameKey="views"
                                    />
                                }
                            />
                            <Line
                                dataKey={activeChart}
                                type="monotone"
                                stroke={`var(--color-${activeChart})`}
                                strokeWidth={2}
                                dot={false}
                            />
                        </LineChart>
                    </ChartContainer>
                </CardContent>
            </Card>

            {/* Row for Sankey and Cloud */}
            <div className="flex flex-col gap-6">
                {/* Sankey Chart */}
                <Card className="flex flex-col">
                    <CardHeader>
                        <CardTitle>Request Flow Map</CardTitle>
                        <CardDescription>Authorization flow from ML to Dual Agents</CardDescription>
                    </CardHeader>
                    <CardContent className="flex-1 min-h-0">
                        {sankeyData.links.length > 0 ? (
                            <div className="w-full h-[600px]">
                                <ResponsiveContainer width="100%" height="100%">
                                    <Sankey
                                        data={sankeyData}
                                        node={<DemoSankeyNode containerWidth={1200} />}
                                        nodePadding={50}
                                        margin={{
                                            left: 20,
                                            right: 200,
                                            top: 20,
                                            bottom: 20,
                                        }}
                                        link={{ stroke: '#374151' }}
                                    >
                                        <RechartsTooltip />
                                    </Sankey>
                                </ResponsiveContainer>
                            </div>
                        ) : (
                            <div className="flex items-center justify-center h-full text-muted-foreground">Not enough data</div>
                        )}
                    </CardContent>
                </Card>

                {/* Word Cloud */}
                <Card className="flex flex-col">
                    <CardHeader>
                        <CardTitle>Common Keywords</CardTitle>
                        <CardDescription>Most frequent terms in user prompts</CardDescription>
                    </CardHeader>
                    <CardContent className="flex-1 flex items-center justify-center overflow-hidden">
                        {wordCloudData.length > 0 ? (
                            <div className="w-full h-full">
                                <WordCloud
                                    data={wordCloudData}
                                    width={800}
                                    height={300}
                                    font="Inter"
                                    fontStyle="normal"
                                    fontWeight="bold"
                                    fontSize={(word: any) => Math.log2(word.value) * 5 + 15}
                                    spiral="rectangular"
                                    rotate={0}
                                    padding={2}
                                    random={() => 0.5}
                                    onWordClick={onWordClick}
                                    fill={(d: any, i: number) => {
                                        const colors = ["#22c55e", "#ef4444", "#3b82f6", "#eab308", "#8b5cf6"]
                                        return colors[i % colors.length]
                                    }}
                                />
                            </div>
                        ) : (
                            <div className="flex items-center justify-center h-full text-muted-foreground">No keywords found</div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    )
}

