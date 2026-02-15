"use client";

import { useEffect, useState, useCallback } from 'react';
import {
    ReactFlow,
    Controls,
    Background,
    useNodesState,
    useEdgesState,
    MarkerType,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { UserNode, MLNode, SwitchNode, DualAgentNode, AgentNode, OblivionNode, ToolboxNode } from './custom-nodes';

const nodeTypes = {
    user: UserNode,
    ml: MLNode,
    switch: SwitchNode,
    dualAgent: DualAgentNode,
    agent: AgentNode,
    oblivion: OblivionNode,
    toolbox: ToolboxNode,
};

// Initial layout structure
const initialNodes = [
    {
        id: 'user',
        type: 'user',
        position: { x: 50, y: 100 },
        data: { label: 'Waiting...', status: 'idle' }
    },
    {
        id: 'ml',
        type: 'ml',
        position: { x: 300, y: 100 },
        data: { status: 'idle', confidence: null }
    },
    {
        id: 'switch',
        type: 'switch',
        position: { x: 550, y: 100 },
        data: { status: 'idle', verdict: '' }
    },
    // Top Path (Safe) -> Agent
    {
        id: 'agent',
        type: 'agent',
        position: { x: 800, y: -50 },
        data: { status: 'idle' }
    },
    // Middle Path (Moderate) -> Dual Agent
    {
        id: 'dualAgent',
        type: 'dualAgent',
        position: { x: 800, y: 150 },
        data: { status: 'idle', currentMessage: '' }
    },
    // Bottom Path (Dangerous) -> Oblivion
    {
        id: 'oblivion',
        type: 'oblivion',
        position: { x: 800, y: 500 },
        data: { status: 'idle' }
    },

    // Toolbox (Attached to Agent)
    {
        id: 'toolbox',
        type: 'toolbox',
        position: { x: 1050, y: -50 },
        data: { policy: 'ALLOW_ALL' }
    }
];

const initialEdges = [
    {
        id: 'e1',
        source: 'user',
        target: 'ml',
        animated: true,
        style: { stroke: '#ffffff', strokeWidth: 5 }
    },
    {
        id: 'e2',
        source: 'ml',
        target: 'switch',
        animated: true,
        style: { stroke: '#ffffff', strokeWidth: 5 }
    },
    // Switch -> Agent (Safe)
    {
        id: 'e3',
        source: 'switch',
        sourceHandle: 'safe',
        target: 'agent',
        animated: false,
        label: 'Safe (<15%)',
        style: { stroke: '#ffffff', opacity: 0.2, strokeWidth: 5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#22c55e' },
    },
    // Switch -> Dual Agent (Moderate)
    {
        id: 'e4',
        source: 'switch',
        sourceHandle: 'moderate',
        target: 'dualAgent',
        animated: false,
        label: 'Uncertain',
        style: { stroke: '#ffffff', opacity: 0.2, strokeWidth: 5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#eab308' },
    },
    // Switch -> Oblivion (Dangerous)
    {
        id: 'e5',
        source: 'switch',
        sourceHandle: 'dangerous',
        target: 'oblivion',
        animated: false,
        label: 'Dangerous (>85%)',
        style: { stroke: '#ffffff', opacity: 0.2, strokeWidth: 5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#ef4444' },
    },
    // Dual Agent -> Agent (If Approved)
    {
        id: 'e6',
        source: 'dualAgent',
        target: 'agent',
        animated: false,
        label: 'Approved',
        style: { stroke: '#ffffff', opacity: 0.2, strokeWidth: 5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#22c55e' },
    },
    // Dual Agent -> Oblivion (If Blocked)
    {
        id: 'e7',
        source: 'dualAgent',
        target: 'oblivion',
        animated: false,
        label: 'Blocked',
        style: { stroke: '#ffffff', opacity: 0.2, strokeWidth: 5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#ef4444' },
    },
    {
        id: 'e8',
        source: 'agent',
        sourceHandle: 'agent-source',
        target: 'toolbox',
        targetHandle: 'toolbox-top',
        animated: true,
        style: { stroke: '#ffffff', strokeDasharray: '5,5', strokeWidth: 5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#3b82f6' },
    }
];

interface WorkflowVisualizerProps {
    workflowState: any; // Using any for now, refine later
    onNodeClick?: (event: React.MouseEvent, node: any) => void;
}


export function WorkflowVisualizer({ workflowState, onNodeClick }: WorkflowVisualizerProps) {
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
    const [rfInstance, setRfInstance] = useState<any>(null);

    const onNodeDragStop = useCallback((event: any, node: any) => {
        // Logic to save node position can be added here
        const mode = workflowState?.mode || 'shield';
        const isBypassMode = mode !== 'shield';
        const storageKey = isBypassMode ? 'workflow-node-positions-bypass' : 'workflow-node-positions-shield';

        // We would need to get current positions from nodes state or the event
        // For now, let's just log or no-op to fix the build
        console.log('Node drag stop', node.position);

        // Helper to save correct position
        const saved = localStorage.getItem(storageKey);
        const positions = saved ? JSON.parse(saved) : {};
        positions[node.id] = node.position;
        localStorage.setItem(storageKey, JSON.stringify(positions));
    }, [workflowState?.mode]);


    // Initial load and reload when mode changes (Layout & Viewport)
    useEffect(() => {
        if (!workflowState) return;

        const mode = workflowState.mode || 'shield';
        const isBypassMode = mode !== 'shield';

        // 1. Restore Viewport
        if (rfInstance) {
            const viewportKey = isBypassMode ? 'workflow-viewport-bypass' : 'workflow-viewport-shield';
            const savedViewport = localStorage.getItem(viewportKey);

            if (savedViewport) {
                const { x, y, zoom } = JSON.parse(savedViewport);
                rfInstance.setViewport({ x, y, zoom });
            } else {
                // If no saved viewport, fit view after a short delay to allow nodes to render
                setTimeout(() => rfInstance.fitView({ padding: 0.2, duration: 800 }), 100);
            }
        }

        const storageKey = isBypassMode ? 'workflow-node-positions-bypass' : 'workflow-node-positions-shield';

        // Load saved node positions (Logic merged from previous step)
        let savedPositions: Record<string, { x: number, y: number }> = {};
        try {
            const saved = localStorage.getItem(storageKey);
            if (saved) savedPositions = JSON.parse(saved);
        } catch (e) {
            console.error("Failed to load node positions", e);
        }

        const getPos = (id: string, defaultPos: { x: number, y: number }) => savedPositions[id] || defaultPos;

        // ... Node setting logic continues below (no changes needed to the node logic itself, just ensuring scope) ... 

        // ------------------------------------------------------------------
        // BYPASS MODE (No Guardrail / Standard Guardrail)
        // ------------------------------------------------------------------
        if (isBypassMode) {
            setNodes([
                {
                    id: 'user', type: 'user',
                    position: getPos('user', { x: 50, y: 100 }),
                    data: {
                        label: workflowState.query || 'Waiting...',
                        status: workflowState.stage === 'start' ? 'active' : 'success'
                    }
                },
                {
                    id: 'agent', type: 'agent',
                    position: getPos('agent', { x: 400, y: 100 }), // Moved closer
                    data: {
                        status: workflowState.stage === 'final' ? 'success' : 'idle'
                    }
                },
                {
                    id: 'toolbox', type: 'toolbox',
                    position: getPos('toolbox', { x: 650, y: 100 }), // Moved closer
                    data: {
                        policy: workflowState.blocked ? "SHUTDOWN" : (workflowState.toolPolicy || "ALLOW_ALL"),
                        activeTools: workflowState.activeTools || []
                    }
                }
            ] as any);

            setEdges([
                {
                    id: 'e-bypass',
                    source: 'user',
                    target: 'agent',
                    animated: true,
                    style: { stroke: '#ffffff', strokeWidth: 5 },
                    label: 'Direct Access',
                    labelStyle: { fill: '#ffffff', fontWeight: 700 }
                },
                {
                    id: 'e8',
                    source: 'agent',
                    sourceHandle: 'agent-source',
                    target: 'toolbox',
                    targetHandle: 'toolbox-top',
                    animated: true,
                    style: { stroke: '#ffffff', strokeDasharray: '5,5', strokeWidth: 5 },
                    markerEnd: { type: MarkerType.ArrowClosed, color: '#3b82f6' },
                }
            ] as any);
            return;
        }

        // ------------------------------------------------------------------
        // SHIELD MODE (Full Visualization)
        // ------------------------------------------------------------------
        setNodes(initialNodes.map((node) => {
            // Use saved position if available
            const position = getPos(node.id, node.position);

            // Update User Node
            if (node.id === 'user') {
                return {
                    ...node,
                    position,
                    data: {
                        ...node.data,
                        label: workflowState.query || 'Waiting...',
                        status: workflowState.stage === 'start' ? 'active' : 'success'
                    }
                };
            }

            // Update ML Node
            if (node.id === 'ml') {
                let status = 'idle';
                if (workflowState.stage === 'ml_processing') status = 'active';
                if (['ml_done', 'debate', 'final'].includes(workflowState.stage)) status = 'success';

                return {
                    ...node,
                    position,
                    data: {
                        ...node.data,
                        status,
                        confidence: workflowState.mlConfidence
                    }
                };
            }

            // Update Switch Node
            if (node.id === 'switch') {
                let status = 'idle';
                if (workflowState.stage === 'ml_done') status = 'active';
                if (['debate', 'final'].includes(workflowState.stage)) status = 'success';

                return {
                    ...node,
                    position,
                    data: {
                        ...node.data,
                        status,
                        verdict: workflowState.mlVerdict
                    }
                };
            }

            // Update Dual Agent Node
            if (node.id === 'dualAgent') {
                let status = 'idle';
                if (workflowState.stage === 'debate') status = 'active';
                // If we passed debate successfully or failed it
                if (workflowState.dualAgentTriggered && workflowState.stage === 'final') status = 'success';

                return {
                    ...node,
                    position,
                    data: {
                        ...node.data,
                        status,
                        currentMessage: workflowState.lastAgentMessage || '',
                        agentDialogue: workflowState.agentDialogue
                    }
                } as any;
            }

            // Update Oblivion Node
            if (node.id === 'oblivion') {
                let status = 'idle';
                if (workflowState.blocked) status = 'error';
                return {
                    ...node,
                    position,
                    data: { ...node.data, status }
                };
            }

            // Update Agent Node
            if (node.id === 'agent') {
                let status = 'idle';
                if (!workflowState.blocked && workflowState.stage === 'final') status = 'success';
                return {
                    ...node,
                    position,
                    data: { ...node.data, status }
                };
            }

            // Update Toolbox Node
            if (node.id === 'toolbox') {
                const policy = workflowState.blocked ? "SHUTDOWN" : (workflowState.toolPolicy || "ALLOW_ALL");
                const activeTools = workflowState.activeTools || [];

                return {
                    ...node,
                    position,
                    data: { ...node.data, policy, activeTools }
                };
            }

            return { ...node, position };
        }));

        // Update Edges based on path
        setEdges((eds) =>
            initialEdges.map((edge) => { // Use initialEdges as base to prevent state drift
                const stage = workflowState.stage;

                // Input -> ML
                if (edge.id === 'e1') {
                    const isActive = ['ml_processing', 'ml_done', 'debate', 'final'].includes(stage);
                    return {
                        ...edge,
                        style: { ...edge.style, stroke: isActive ? '#3b82f6' : '#ffffff', opacity: isActive ? 1 : 0.2 },
                        animated: stage === 'ml_processing'
                    };
                }

                // ML -> Router
                if (edge.id === 'e2') {
                    const isActive = ['ml_done', 'debate', 'final'].includes(stage) || (stage === 'ml_processing' && !!workflowState.mlVerdict);
                    return {
                        ...edge,
                        style: { ...edge.style, stroke: isActive ? '#ffffff' : '#ffffff', opacity: isActive ? 1 : 0.2 },
                        animated: stage === 'ml_processing' && !!workflowState.mlVerdict
                    };
                }

                // Activate edges based on state
                // Switch -> Safe
                if (edge.id === 'e3') {
                    const isActive = workflowState.mlVerdict === 'SAFE' && ['ml_done', 'debate', 'final'].includes(stage);
                    return {
                        ...edge,
                        style: {
                            ...edge.style,
                            stroke: isActive ? '#22c55e' : '#ffffff',
                            opacity: isActive ? 1 : 0.2,
                            strokeWidth: isActive ? 8 : 5
                        } as any,
                        animated: isActive && stage === 'ml_done'
                    };
                }
                // Switch -> Moderate (Router -> Dual Agent)
                if (edge.id === 'e4') {
                    // Activate ONLY if the stage is 'debate' or 'final'
                    const isActive = workflowState.mlVerdict === 'UNCERTAIN' && ['debate', 'final'].includes(stage);
                    return {
                        ...edge,
                        style: {
                            ...edge.style,
                            stroke: isActive ? '#eab308' : '#ffffff',
                            opacity: isActive ? 1 : 0.2,
                            strokeWidth: isActive ? 8 : 5
                        } as any,
                        animated: isActive && stage === 'debate'
                    };
                }
                // Switch -> Dangerous (Router -> Oblivion)
                if (edge.id === 'e5') {
                    // Activate if verdict is MALICIOUS.
                    // VISUAL FIX: If blocked, force it to light up even if stage lagging.
                    const isActive = workflowState.mlVerdict === 'MALICIOUS' &&
                        (['ml_done', 'debate', 'final'].includes(stage) || workflowState.blocked);
                    return {
                        ...edge,
                        style: {
                            ...edge.style,
                            stroke: isActive ? '#ef4444' : '#ffffff',
                            opacity: isActive ? 1 : 0.2,
                            strokeWidth: isActive ? 8 : 5
                        } as any,
                        // Animate if we are in the flow or if blocked
                        animated: isActive && (stage === 'ml_done' || workflowState.blocked)
                    };
                }
                // Dual Agent -> Approved
                if (edge.id === 'e6') {
                    // It's approved if dual agents ran, we are NOT blocked, and we reached final stage
                    // OR if we are in final stage after debate
                    const isActive = workflowState.dualAgentTriggered && !workflowState.blocked && ['final'].includes(stage);
                    return {
                        ...edge,
                        style: {
                            ...edge.style,
                            stroke: isActive ? '#22c55e' : '#ffffff',
                            opacity: isActive ? 1 : 0.2,
                            strokeWidth: isActive ? 8 : 5
                        } as any,
                        animated: isActive
                    };
                }
                // Dual Agent -> Blocked (Oblivion)
                if (edge.id === 'e7') {
                    // It's blocked if dual agents ran AND we are blocked. 
                    // Activate in 'final' stage OR if we are fully blocked (ignoring stage to be safe for live)
                    const isActive = workflowState.dualAgentTriggered && workflowState.blocked && (stage === 'final' || workflowState.blocked);
                    return {
                        ...edge,
                        style: {
                            ...edge.style,
                            stroke: isActive ? '#ef4444' : '#ffffff',
                            opacity: isActive ? 1 : 0.2,
                            strokeWidth: isActive ? 8 : 5
                        } as any,
                        animated: isActive
                    };
                }

                // Agent -> Toolbox
                if (edge.id === 'e8') {
                    const isActive = !workflowState.blocked && stage === 'final';
                    return {
                        ...edge,
                        style: {
                            ...edge.style,
                            stroke: isActive ? '#3b82f6' : '#ffffff',
                            opacity: isActive ? 1 : 0.2,
                            strokeWidth: 5
                        } as any,
                        animated: isActive
                    };
                }

                return edge;
            })
        );

    }, [workflowState, setNodes, setEdges, rfInstance]);

    // Save viewport on move end
    const onMoveEnd = (_: any, viewport: any) => {
        const mode = workflowState?.mode || 'shield';
        const isBypassMode = mode !== 'shield';
        const viewportKey = isBypassMode ? 'workflow-viewport-bypass' : 'workflow-viewport-shield';
        localStorage.setItem(viewportKey, JSON.stringify(viewport));
    };

    return (
        <div className="w-full h-full bg-zinc-950">
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={onNodeClick}
                onNodeDragStop={onNodeDragStop}
                onInit={setRfInstance}
                onMoveEnd={onMoveEnd}
                nodeTypes={nodeTypes}
                minZoom={0.1}
                maxZoom={4}
                attributionPosition="bottom-right"
                className="bg-zinc-950"
            >
                <Background color="#333" gap={20} />
                <Controls className="bg-zinc-900 border-zinc-800 text-zinc-400" />
            </ReactFlow>
        </div>
    );
}
