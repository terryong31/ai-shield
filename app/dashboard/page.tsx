"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { PanelLeft } from "lucide-react"
import { OverviewSection } from "@/components/dashboard/overview-section"
import { ChatHistorySection } from "@/components/dashboard/chat-history-section"
import { SettingsSection } from "@/components/dashboard/settings-section"

const navItems = [
    { id: "overview", label: "Overview" },
    { id: "history", label: "Chat Logs" },
    { id: "settings", label: "Settings" },
]

export default function Dashboard() {
    const [currentSection, setCurrentSection] = useState("overview")
    const [sidebarOpen, setSidebarOpen] = useState(true)

    return (
        <div className="flex h-screen bg-background">
            {/* Sidebar */}
            <aside className={cn(
                "h-full border-r bg-card transition-all duration-300",
                sidebarOpen ? "w-64" : "w-0 overflow-hidden"
            )}>
                <div className="flex flex-col h-full">
                    <div className="flex h-14 items-center gap-2 px-4 border-b">
                        <div className="flex flex-col">
                            <span className="font-semibold">AI S.H.I.E.L.D.</span>
                        </div>
                    </div>
                    <nav className="flex-1 p-2 space-y-1">
                        {navItems.map((item) => (
                            <button
                                key={item.id}
                                onClick={() => setCurrentSection(item.id)}
                                className={cn(
                                    "w-full text-left px-3 py-2 rounded-md text-sm transition-colors",
                                    currentSection === item.id
                                        ? "bg-accent text-accent-foreground font-medium"
                                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                                )}
                            >
                                {item.label}
                            </button>
                        ))}
                    </nav>
                </div>
            </aside>

            {/* Main Content */}
            <div className="flex-1 flex flex-col overflow-hidden">
                <header className="h-14 border-b flex items-center justify-between px-4 shrink-0 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
                    <div className="flex items-center gap-4">
                        <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setSidebarOpen(!sidebarOpen)}
                            className="h-7 w-7"
                        >
                            <PanelLeft className="h-4 w-4" />
                            <span className="sr-only">Toggle Sidebar</span>
                        </Button>
                        <span className="font-semibold">
                            {navItems.find(item => item.id === currentSection)?.label}
                        </span>
                    </div>
                </header>
                <main className="flex-1 overflow-y-auto p-6">
                    {currentSection === "overview" && <OverviewSection />}
                    {currentSection === "history" && <ChatHistorySection />}
                    {currentSection === "settings" && <SettingsSection />}
                </main>
            </div>
        </div>
    )
}
