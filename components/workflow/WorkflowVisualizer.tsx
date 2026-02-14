"use client";

import { useEffect } from 'react';
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
        label: 'Safe (<20%)',
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

    // Initial load from localStorage
    useEffect(() => {
        const saved = localStorage.getItem('workflow-node-positions');
        if (saved) {
            try {
                const positions = JSON.parse(saved);
                setNodes(nds => nds.map(node => ({
                    ...node,
                    position: positions[node.id] || node.position
                })));
            } catch (e) {
                console.error("Failed to load node positions", e);
            }
        }
    }, [setNodes]);

    const onNodeDragStop = (_: any, node: any) => {
        const saved = localStorage.getItem('workflow-node-positions');
        const positions = saved ? JSON.parse(saved) : {};
        positions[node.id] = node.position;
        localStorage.setItem('workflow-node-positions', JSON.stringify(positions));
    };

    // Sync workflowState with nodes/edges
    useEffect(() => {
        if (!workflowState) return;

        setNodes((nds) =>
            nds.map((node) => {
                // Update User Node
                if (node.id === 'user') {
                    return {
                        ...node,
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
                        data: { ...node.data, status }
                    };
                }

                // Update Agent Node
                if (node.id === 'agent') {
                    let status = 'idle';
                    if (!workflowState.blocked && workflowState.stage === 'final') status = 'success';
                    return {
                        ...node,
                        data: { ...node.data, status }
                    };
                }

                // Update Toolbox Node
                // Update ToolboxNode
                if (node.id === 'toolbox') {
                    // Default to ALLOW_ALL if not specified, 
                    // or inherit from workflow state if available
                    // We need to pass policy from ChatInterface -> WorkflowState -> Here
                    const policy = workflowState.blocked ? "SHUTDOWN" : (workflowState.toolPolicy || "ALLOW_ALL");
                    const activeTools = workflowState.activeTools || [];

                    return {
                        ...node,
                        data: { ...node.data, policy, activeTools }
                    };
                }

                return node;
            })
        );

        // Update Edges based on path
        setEdges((eds) =>
            eds.map((edge) => {
                // Activate edges based on state
                // Switch -> Safe
                if (edge.id === 'e3') {
                    const isActive = workflowState.mlVerdict === 'SAFE';
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
                // Switch -> Moderate
                if (edge.id === 'e4') {
                    const isActive = workflowState.mlVerdict === 'UNCERTAIN';
                    return {
                        ...edge,
                        style: {
                            ...edge.style,
                            stroke: isActive ? '#eab308' : '#ffffff',
                            opacity: isActive ? 1 : 0.2,
                            strokeWidth: isActive ? 8 : 5
                        } as any,
                        animated: isActive
                    };
                }
                // Switch -> Dangerous
                if (edge.id === 'e5') {
                    const isActive = workflowState.mlVerdict === 'MALICIOUS';
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
                // Dual Agent -> Approved
                if (edge.id === 'e6') {
                    const isActive = workflowState.dualAgentTriggered && !workflowState.blocked && workflowState.stage === 'final';
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
                // Dual Agent -> Blocked
                if (edge.id === 'e7') {
                    const isActive = workflowState.dualAgentTriggered && workflowState.blocked;
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

                // Default thickness for static edges
                if (['e1', 'e2', 'e8'].includes(edge.id)) {
                    return {
                        ...edge,
                        style: { ...edge.style, strokeWidth: 5 }
                    };
                }

                return edge;
            })
        );

    }, [workflowState, setNodes, setEdges]);

    return (
        <div className="w-full h-full bg-zinc-950">
            <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={onNodeClick}
                onNodeDragStop={onNodeDragStop}
                nodeTypes={nodeTypes}
                fitView
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
