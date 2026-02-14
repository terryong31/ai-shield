'use client';

import { useEffect, useState } from 'react';
import { createClient } from '@supabase/supabase-js';

// Initialize Supabase client
// Note: Ensure NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are set in your .env.local
const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || '';
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '';
const supabase = createClient(supabaseUrl, supabaseAnonKey);

interface RequestLog {
  id: number;
  query: string;
  action: 'BLOCK' | 'ALLOW';
  reason: string;
  metadata: {
    generated_intent?: string;
  };
}

export default function AdminDashboard() {
  const [requests, setRequests] = useState<RequestLog[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchPendingRequests = async () => {
    setLoading(true);
    const { data, error } = await supabase
      .from('requests')
      .select('id, query, action, reason, metadata')
      .eq('reviewed', false)
      .order('id', { ascending: false });

    if (error) {
      console.error('Error fetching requests:', error);
    } else {
      setRequests((data as RequestLog[]) || []);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchPendingRequests();
  }, []);

  const handleReview = async (id: number, query: string, label: number) => {
    try {
      // 1. Send Feedback to ML endpoint for retraining
      const res = await fetch('http://127.0.0.1:8000/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: query, human_label: label })
      });

      if (!res.ok) throw new Error("ML Service responded with an error");

      // 2. Update Supabase
      const { error } = await supabase
        .from('requests')
        .update({
          human_label: label,
          reviewed: true,
          reviewed_at: new Date().toISOString(),
        })
        .eq('id', id);

      if (error) {
        alert('Error updating record: ' + error.message);
      } else {
        // Optimistically update UI by removing the reviewed item from the list
        setRequests((prev) => prev.filter((r) => r.id !== id));
      }
    } catch (error) {
      console.error("Feedback failed", error);
      alert("Could not connect to ML Service. Ensure backend is running on port 8000.");
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 p-8">
      <div className="max-w-6xl mx-auto">
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-gray-800">Security Review Queue</h1>
          <p className="text-gray-600">Reinforcement Learning from Human Feedback (RLHF) Interface</p>
        </header>
        
        <div className="bg-white shadow-sm rounded-xl border border-gray-200 overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-500 uppercase">User Query</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-500 uppercase">AI Action</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-500 uppercase">Security Reason</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-500 uppercase">AI's Interpretation</th>
                <th className="px-6 py-4 text-right text-xs font-semibold text-gray-500 uppercase">Feedback</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {loading ? (
                <tr><td colSpan={5} className="px-6 py-10 text-center text-gray-400 animate-pulse">Fetching pending requests...</td></tr>
              ) : requests.length === 0 ? (
                <tr><td colSpan={5} className="px-6 py-10 text-center text-gray-400">All caught up! No pending reviews.</td></tr>
              ) : (
                requests.map((req) => (
                  <tr key={req.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-4 text-sm text-gray-900 font-medium">{req.query}</td>
                    <td className="px-6 py-4 text-sm">
                      <span className={`px-2 py-1 rounded text-xs font-bold ${req.action === 'BLOCK' ? 'bg-red-100 text-red-700' : 'bg-blue-100 text-blue-700'}`}>
                        {req.action}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">{req.reason}</td>
                    <td className="px-6 py-4 text-sm text-indigo-600 italic">{req.metadata?.generated_intent || 'Unknown'}</td>
                    <td className="px-6 py-4 text-right text-sm font-medium space-x-3 whitespace-nowrap">
                      <button onClick={() => handleReview(req.id, req.query, 1)} className="text-red-600 hover:bg-red-50 px-3 py-1.5 rounded-lg border border-red-200 transition-all">Confirm Malicious</button>
                      <button onClick={() => handleReview(req.id, req.query, 0)} className="text-green-600 hover:bg-green-50 px-3 py-1.5 rounded-lg border border-green-200 transition-all">Mark as Safe</button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}