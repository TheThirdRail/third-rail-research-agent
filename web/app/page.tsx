"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { getAgents, AgentInfo, analyzeStory } from "@/lib/api";
import { AgentCard } from "@/components/AgentCard";
import { ConfigModal } from "@/components/ConfigModal";
import { ResearchInput } from "@/components/ResearchInput";
import { ReportModal } from "@/components/ReportModal";
import { Loader2, Zap } from "lucide-react";

export default function Dashboard() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAgent, setSelectedAgent] = useState<AgentInfo | null>(null);

  const [analyzing, setAnalyzing] = useState(false);
  const [report, setReport] = useState<string | null>(null);
  const [isReportOpen, setIsReportOpen] = useState(false);

  const fetchAgents = async () => {
    try {
      const data = await getAgents();
      setAgents(data);
    } catch (err) {
      console.error(err);
      // Fallback for demo/development if backend not reachable
      // setAgents(MOCK_AGENTS); 
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAgents();
  }, []);

  const handleAnalyze = async (description: string, url: string | null) => {
    setAnalyzing(true);
    try {
      const response = await analyzeStory({ description, url });
      setReport(response.report);
      setIsReportOpen(true);
    } catch (err) {
      console.error(err);
      alert(err instanceof Error ? err.message : "Failed to initiate research");
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <main className="min-h-screen relative p-6 md:p-12 overflow-x-hidden scanlines bg-void text-foreground selection:bg-neon-cyan selection:text-black">

      {/* Background Layer */}
      <div className="fixed inset-0 z-0">
        <Image
          src="/synthwave_background.png"
          alt="Synthwave Landscape"
          fill
          className="object-cover opacity-30"
          priority
        />
        {/* Gradient Overlay to fade bottom into void */}
        <div className="absolute inset-0 bg-gradient-to-t from-midnight-purple via-midnight-purple/60 to-transparent" />
      </div>

      {/* Grid Overlay Effect (CSS based in globals, but structure helps) */}
      <div className="fixed inset-0 z-0 bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.1)_50%),linear-gradient(90deg,rgba(255,0,255,0.03),rgba(255,0,0,0.03))] bg-[length:100%_4px,60px_100%] pointer-events-none" />

      {/* Content Layer */}
      <div className="relative z-10 max-w-7xl mx-auto space-y-12">

        {/* Header */}
        <header className="flex flex-col md:flex-row justify-between items-end border-b border-white/10 pb-8 backdrop-blur-sm">
          <div className="space-y-2">
            <h1 className="text-4xl md:text-6xl font-black font-orbitron text-transparent bg-clip-text bg-gradient-to-r from-neon-cyan via-white to-neon-purple drop-shadow-[0_0_10px_rgba(0,243,255,0.5)]">
              RESEARCH AGENT
            </h1>
            <div className="flex items-center gap-3">
              <span className="px-2 py-0.5 bg-neon-cyan/10 border border-neon-cyan/40 text-neon-cyan font-mono text-[10px] tracking-widest uppercase rounded">
                System v2.4
              </span>
              <span className="text-gray-400 font-mono text-xs tracking-[0.2em] uppercase">
                // Multi-Agent Orchestration
              </span>
            </div>
          </div>

          <div className="mt-6 md:mt-0 text-right font-mono text-xs space-y-1">
            <div className="flex items-center gap-2 justify-end text-terminal-green">
              <div className="w-2 h-2 bg-terminal-green rounded-full animate-pulse" />
              SYSTEM ONLINE
            </div>
            <div className="text-neon-purple tracking-widest">
              GRID STATUS: STABLE
            </div>
          </div>
        </header>

        {/* Header content... */}

        <ResearchInput onAnalyze={handleAnalyze} isLoading={analyzing} />

        {/* Grid */}
        {loading ? (
          <div className="h-64 flex flex-col items-center justify-center text-neon-cyan gap-4">
            <Loader2 className="w-12 h-12 animate-spin" />
            <span className="font-mono tracking-[0.2em] animate-pulse">ESTABLISHING UPLINK...</span>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 pb-20">
            {agents.map((agent) => (
              <AgentCard
                key={agent.name}
                agent={agent}
                onConfigure={setSelectedAgent}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer / Copyright */}
      <footer className="fixed bottom-0 left-0 right-0 p-4 border-t border-white/5 bg-black/40 backdrop-blur-md z-20 text-center text-[10px] text-gray-500 font-mono tracking-widest uppercase">
        <div className="flex items-center justify-center gap-2">
          <Zap className="w-3 h-3 text-neon-cyan" />
          <span>Powered by Antigravity Engine</span>
        </div>
      </footer>

      {/* Configuration Modal */}
      <ConfigModal
        agent={selectedAgent}
        isOpen={!!selectedAgent}
        onClose={() => setSelectedAgent(null)}
        onSaved={fetchAgents}
      />

      {/* Report Modal */}
      <ReportModal
        report={report}
        isOpen={isReportOpen}
        onClose={() => setIsReportOpen(false)}
      />
    </main>
  );
}
