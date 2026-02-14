"use client"

import React, { useState } from 'react';

interface ToolCall {
    tool_name: string;
    input_parameters: any;
    timestamp: string;
}

interface ToolTraceProps {
    userPrompt: string;
    layer1Verdict?: string;
    toolCalls?: ToolCall[];
    aiResponse?: string;
    mlConfidence?: number;
    allowedTools?: string[];
}

export function ToolTrace({ userPrompt, layer1Verdict = "SAFE", toolCalls = [], aiResponse, mlConfidence = 0, allowedTools = [] }: ToolTraceProps) {
    const [isOpen, setIsOpen] = useState(false);

    return (
        <div className="border rounded-lg p-2 bg-white dark:bg-gray-900 shadow-sm my-2">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="flex items-center justify-between w-full text-left font-semibold text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 p-2 rounded transition-colors focus:outline-none focus:ring-0 active:bg-white dark:active:bg-gray-900"
            >
                <span className="flex items-center gap-2">
                    Tool Trace Analysis
                    {toolCalls.length > 0 && <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full">{toolCalls.length} Tools</span>}
                </span>
                <span className="font-mono" style={{ fontVariantNumeric: 'tabular-nums', textRendering: 'geometricPrecision', WebkitFontSmoothing: 'antialiased' }}>{isOpen ? '▼' : '▶'}</span>
            </button>

            {isOpen && (
                <div className="mt-4 space-y-6 relative pl-4 border-l-2 border-gray-200 dark:border-gray-700 ml-2">
                    {/* User Prompt */}
                    <div className="relative">
                        <div className="absolute -left-[21px] bg-blue-500 h-3 w-3 rounded-full mt-1.5 ring-4 ring-white dark:ring-gray-900"></div>
                        <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider">User Input</h4>
                        <p className="mt-1 text-sm text-gray-800 dark:text-gray-100 bg-gray-50 dark:bg-gray-800 p-3 rounded border border-gray-100 dark:border-gray-700">
                            {userPrompt}
                        </p>
                    </div>

                    {/* Layer 1 Analysis */}
                    <div className="relative">
                        <div className={`absolute -left-[21px] h-3 w-3 rounded-full mt-1.5 ring-4 ring-white dark:ring-gray-900 ${mlConfidence > 0.8 ? 'bg-red-500' : 'bg-green-500'}`}></div>
                        <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider">Layer 1: ML Analysis</h4>
                        <div className="mt-1 text-sm flex items-center gap-2">
                            <span className="font-mono text-xs bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded border border-gray-200 dark:border-gray-700">Confidence: {(mlConfidence * 100).toFixed(1)}%</span>
                            <span className="text-gray-600 dark:text-gray-400">{layer1Verdict}</span>
                        </div>
                    </div>

                    {/* Tool Execution */}
                    <div className="relative">
                        <div className={`absolute -left-[21px] h-3 w-3 rounded-full mt-1.5 ring-4 ring-white dark:ring-gray-900 ${toolCalls && toolCalls.length > 0 ? 'bg-purple-500' : 'bg-gray-300 dark:bg-gray-700'}`}></div>
                        <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider">Tool Execution</h4>

                        {toolCalls && toolCalls.length > 0 ? (
                            <div className="mt-2 space-y-3">
                                {toolCalls.map((tool, idx) => (
                                    <div key={idx} className="bg-gray-50 dark:bg-gray-800 p-3 rounded border border-gray-200 dark:border-gray-700">
                                        <div className="flex justify-between items-center mb-2">
                                            <span className="text-sm font-semibold text-purple-700 dark:text-purple-400 flex items-center gap-2">
                                                <span className="w-2 h-2 rounded-full bg-purple-500 animate-pulse"></span>
                                                {tool.tool_name}
                                            </span>
                                            <span className="text-xs text-gray-500 font-mono">{new Date(tool.timestamp).toLocaleTimeString()}</span>
                                        </div>
                                        <div className="text-xs font-mono bg-gray-900 text-green-400 p-2 rounded overflow-x-auto">
                                            <span className="text-gray-500 select-none">$ </span>
                                            {JSON.stringify(tool.input_parameters)}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="mt-1 text-sm text-gray-500 dark:text-gray-400 italic bg-gray-50 dark:bg-gray-800/50 p-2 rounded border border-dashed border-gray-200 dark:border-gray-700">
                                No tools triggered.
                                {allowedTools && allowedTools.length > 0 && (
                                    <div className="mt-1 text-xs text-gray-400 not-italic">
                                        <span className="font-semibold">Available Scope:</span> {allowedTools.join(", ")}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Final Response */}
                    <div className="relative">
                        <div className="absolute -left-[21px] bg-green-600 h-3 w-3 rounded-full mt-1.5 ring-4 ring-white dark:ring-gray-900"></div>
                        <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider">Final AI Response</h4>
                        <p className="mt-1 text-sm text-gray-800 dark:text-gray-100 bg-green-50 dark:bg-green-900/20 p-3 rounded border border-green-100 dark:border-green-900/30">
                            {aiResponse || "No response generated."}
                        </p>
                    </div>
                </div>
            )}
        </div>
    );
}