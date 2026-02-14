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
        style: { stroke: '#e4e4e7' }
    },
    {
        id: 'e2',
        source: 'ml',
        target: 'switch',
        animated: true,
        style: { stroke: '#e4e4e7' }
    },
    // Switch -> Agent (Safe)
    {
        id: 'e3',
        source: 'switch',
        sourceHandle: 'safe',
        target: 'agent',
        animated: false,
        label: 'Safe (<20%)',
        style: { stroke: '#22c55e', opacity: 0.2 },
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
        style: { stroke: '#eab308', opacity: 0.2 },
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
        style: { stroke: '#ef4444', opacity: 0.2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#ef4444' },
    },
    // Dual Agent -> Agent (If Approved)
    {
        id: 'e6',
        source: 'dualAgent',
        target: 'agent',
        animated: false,
        label: 'Approved',
        style: { stroke: '#22c55e', opacity: 0.2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#22c55e' },
    },
    // Dual Agent -> Oblivion (If Blocked)
    {
        id: 'e7',
        source: 'dualAgent',
        target: 'oblivion',
        animated: false,
        label: 'Blocked',
        style: { stroke: '#ef4444', opacity: 0.2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#ef4444' },
    },
    {
        id: 'e8',
        source: 'agent',
        target: 'toolbox',
        animated: true,
        style: { stroke: '#3b82f6', strokeDasharray: '5,5' },
    }
];

interface WorkflowVisualizerProps {
    workflowState: any; // Using any for now, refine later
}

export function WorkflowVisualizer({ workflowState }: WorkflowVisualizerProps) {
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

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
                            currentMessage: workflowState.lastAgentMessage || ''
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
                if (node.id === 'toolbox') {
                    // Default to ALLOW_ALL if not specified, 
                    // or inherit from workflow state if available
                    // We need to pass policy from ChatInterface -> WorkflowState -> Here
                    const policy = workflowState.blocked ? "SHUTDOWN" : (workflowState.toolPolicy || "ALLOW_ALL");

                    return {
                        ...node,
                        data: { ...node.data, policy }
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
                    return {
                        ...edge,
                        style: { ...edge.style, opacity: workflowState.mlVerdict === 'SAFE' ? 1 : 0.2, strokeWidth: workflowState.mlVerdict === 'SAFE' ? 2 : 1 } as any,
                        animated: workflowState.mlVerdict === 'SAFE'
                    };
                }
                // Switch -> Moderate
                if (edge.id === 'e4') {
                    return {
                        ...edge,
                        style: { ...edge.style, opacity: workflowState.mlVerdict === 'UNCERTAIN' ? 1 : 0.2, strokeWidth: workflowState.mlVerdict === 'UNCERTAIN' ? 2 : 1 } as any,
                        animated: workflowState.mlVerdict === 'UNCERTAIN'
                    };
                }
                // Switch -> Dangerous
                if (edge.id === 'e5') {
                    return {
                        ...edge,
                        style: { ...edge.style, opacity: workflowState.mlVerdict === 'MALICIOUS' ? 1 : 0.2, strokeWidth: workflowState.mlVerdict === 'MALICIOUS' ? 2 : 1 } as any,
                        animated: workflowState.mlVerdict === 'MALICIOUS'
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
