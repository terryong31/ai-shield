import { useEffect, useState, useMemo } from "react"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { supabase } from "@/lib/supabase"
import { Line, LineChart, CartesianGrid, XAxis, Label, PolarGrid, PolarRadiusAxis, RadialBar, RadialBarChart } from "recharts"

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

export function OverviewSection() {
    const [metrics, setMetrics] = useState({
        total: 0,
        blocked: 0,
        safe: 0,
        threatLevel: 0
    })
    const [chartData, setChartData] = useState<any[]>([])
    const [activeChart, setActiveChart] = useState<keyof typeof chartConfig>("blocked")

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

        requests.forEach(r => {
            const date = new Date(r.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            if (!timeFrames[date]) {
                timeFrames[date] = { date, blocked: 0, safe: 0 }
            }
            if (r.action === "BLOCKED") {
                timeFrames[date].blocked++
            } else {
                timeFrames[date].safe++
            }
        })

        const formattedData = Object.values(timeFrames).slice(-15)
        setChartData(formattedData)
    }

    const totals = useMemo(
        () => ({
            blocked: chartData.reduce((acc, curr) => acc + curr.blocked, 0),
            safe: chartData.reduce((acc, curr) => acc + curr.safe, 0),
        }),
        [chartData]
    )

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
        </div>
    )
}

