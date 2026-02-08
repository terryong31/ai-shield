"use client"

import {
    Sidebar,
    SidebarContent,
    SidebarGroup,
    SidebarGroupContent,
    SidebarGroupLabel,
    SidebarMenu,
    SidebarMenuButton,
    SidebarMenuItem,
    SidebarHeader,
} from "@/components/ui/sidebar"

interface AppSidebarProps {
    currentSection: string
    onSectionChange: (section: string) => void
}

export function AppSidebar({ currentSection, onSectionChange }: AppSidebarProps) {
    return (
        <Sidebar variant="sidebar" collapsible="icon">
            <SidebarHeader>
                <div className="px-4 py-2">
                    <h2 className="text-lg font-bold">AI S.H.I.E.L.D.</h2>
                </div>
            </SidebarHeader>
            <SidebarContent>
                <SidebarGroup>
                    <SidebarGroupLabel>Navigation</SidebarGroupLabel>
                    <SidebarGroupContent>
                        <SidebarMenu>
                            <SidebarMenuItem>
                                <SidebarMenuButton
                                    onClick={() => onSectionChange("overview")}
                                    isActive={currentSection === "overview"}
                                >
                                    Overview
                                </SidebarMenuButton>
                            </SidebarMenuItem>
                            <SidebarMenuItem>
                                <SidebarMenuButton
                                    onClick={() => onSectionChange("history")}
                                    isActive={currentSection === "history"}
                                >
                                    Chat History
                                </SidebarMenuButton>
                            </SidebarMenuItem>
                            <SidebarMenuItem>
                                <SidebarMenuButton
                                    onClick={() => onSectionChange("flagged")}
                                    isActive={currentSection === "flagged"}
                                >
                                    Flagged Prompts
                                </SidebarMenuButton>
                            </SidebarMenuItem>
                            <SidebarMenuItem>
                                <SidebarMenuButton
                                    onClick={() => onSectionChange("agent-monitor")}
                                    isActive={currentSection === "agent-monitor"}
                                >
                                    Agent Test
                                </SidebarMenuButton>
                            </SidebarMenuItem>
                        </SidebarMenu>

                    </SidebarGroupContent>
                </SidebarGroup>
            </SidebarContent>
        </Sidebar>
    )
}
