"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"
import { Shield, ShieldAlert } from "lucide-react"

export function SettingsSection() {
    const [mode, setMode] = useState<"shield" | "guardrail">("shield")

    useEffect(() => {
        const savedMode = localStorage.getItem("securityMode") as "shield" | "guardrail"
        if (savedMode) setMode(savedMode)
    }, [])

    const toggleMode = (checked: boolean) => {
        const newMode = checked ? "shield" : "guardrail"
        setMode(newMode)
        localStorage.setItem("securityMode", newMode)
    }

    return (
        <div className="mx-auto">
            <div className="flex items-center justify-between space-x-4 rounded-lg p-4 bg-background">
                <div className="flex items-center gap-4">
                    <div className="space-y-1">
                        <Label htmlFor="security-mode" className="text-base font-bold">
                            AI S.H.I.E.L.D. Protection
                        </Label>
                    </div>
                </div>
                <Switch
                    id="security-mode"
                    checked={mode === "shield"}
                    onCheckedChange={toggleMode}
                />
            </div>
        </div>
    )
}
