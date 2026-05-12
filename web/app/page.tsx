"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import {
  getAgents,
  AgentInfo,
  analyzeStory,
  getAdminSession,
  loginAdmin,
  logoutAdmin,
} from "@/lib/api";
import { AgentCard } from "@/components/AgentCard";
import { ConfigModal } from "@/components/ConfigModal";
import { ResearchInput } from "@/components/ResearchInput";
import { ReportModal } from "@/components/ReportModal";
import { KeyRound, Loader2, LogOut, ShieldCheck, Zap } from "lucide-react";

export default function Dashboard() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedAgent, setSelectedAgent] = useState<AgentInfo | null>(null);

  const [analyzing, setAnalyzing] = useState(false);
  const [report, setReport] = useState<string | null>(null);
  const [isReportOpen, setIsReportOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sourceHint, setSourceHint] = useState<string | null>(null);
  const [adminAuthenticated, setAdminAuthenticated] = useState(false);
  const [checkingAdminSession, setCheckingAdminSession] = useState(true);
  const [adminKey, setAdminKey] = useState("");
  const [adminAuthBusy, setAdminAuthBusy] = useState(false);

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
    getAdminSession()
      .then((session) => setAdminAuthenticated(session.authenticated))
      .catch(() => setAdminAuthenticated(false))
      .finally(() => setCheckingAdminSession(false));
  }, []);

  const handleAnalyze = async (description: string, url: string | null) => {
    if (!adminAuthenticated) {
      setError("Admin login required.");
      return;
    }
    setAnalyzing(true);
    setError(null);
    setSourceHint(null);
    try {
      const response = await analyzeStory({ description, url });
      setReport(response.report);
      setIsReportOpen(true);
      if (response.source_count !== undefined && response.bias_spread_met !== undefined) {
        const left = response.left_source_count ?? 0;
        const right = response.right_source_count ?? 0;
        setSourceHint(
          `Sources: ${response.source_count} | Bias spread: ${
            response.bias_spread_met ? "met" : "not met"
          } (left ${left}, right ${right})`
        );
      }
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : "Failed to initiate research");
    } finally {
      setAnalyzing(false);
    }
  };

  const handleAdminLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!adminKey.trim()) return;
    setAdminAuthBusy(true);
    setError(null);
    try {
      const session = await loginAdmin(adminKey);
      setAdminAuthenticated(session.authenticated);
      setAdminKey("");
    } catch (err) {
      setAdminAuthenticated(false);
      setError(err instanceof Error ? err.message : "Admin login failed");
    } finally {
      setAdminAuthBusy(false);
    }
  };

  const handleAdminLogout = async () => {
    setAdminAuthBusy(true);
    setError(null);
    try {
      await logoutAdmin();
      setAdminAuthenticated(false);
      setSelectedAgent(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Admin logout failed");
    } finally {
      setAdminAuthBusy(false);
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

          <div className="mt-6 md:mt-0 w-full md:w-auto font-mono text-xs">
            {adminAuthenticated ? (
              <div className="flex flex-col items-start md:items-end gap-2">
                <div className="flex items-center gap-2 text-terminal-green">
                  <ShieldCheck className="w-4 h-4" />
                  ADMIN SESSION ACTIVE
                </div>
                <button
                  onClick={handleAdminLogout}
                  disabled={adminAuthBusy}
                  className="flex items-center gap-2 text-neon-purple hover:text-white uppercase tracking-widest disabled:opacity-50"
                >
                  <LogOut className="w-4 h-4" />
                  Logout
                </button>
              </div>
            ) : (
              <form
                onSubmit={handleAdminLogin}
                className="flex flex-col sm:flex-row gap-2 items-stretch sm:items-center"
              >
                <div className="relative">
                  <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neon-cyan" />
                  <input
                    type="password"
                    value={adminKey}
                    onChange={(event) => setAdminKey(event.target.value)}
                    placeholder={
                      checkingAdminSession ? "Checking session..." : "Admin key"
                    }
                    disabled={checkingAdminSession || adminAuthBusy}
                    className="w-full sm:w-56 bg-void/80 border border-neon-cyan/30 text-white pl-10 pr-3 py-2 focus:border-neon-cyan focus:outline-none"
                  />
                </div>
                <button
                  type="submit"
                  disabled={
                    checkingAdminSession || adminAuthBusy || !adminKey.trim()
                  }
                  className="px-4 py-2 bg-neon-cyan/10 border border-neon-cyan text-neon-cyan hover:bg-neon-cyan/20 hover:text-white uppercase tracking-widest disabled:opacity-50"
                >
                  Login
                </button>
              </form>
            )}
          </div>
        </header>

        {/* Header content... */}

        {error && (
          <div className="border border-red-400/40 bg-red-950/40 text-red-200 font-mono text-xs p-3 tracking-wide">
            {error}
          </div>
        )}
        {sourceHint && (
          <div className="border border-neon-cyan/40 bg-midnight-purple/40 text-neon-cyan font-mono text-xs p-3 tracking-wide">
            {sourceHint}
          </div>
        )}

        <ResearchInput
          onAnalyze={handleAnalyze}
          isLoading={analyzing}
          disabled={!adminAuthenticated}
        />

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
                disabled={!adminAuthenticated}
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
        canExportPdf={adminAuthenticated}
      />
    </main>
  );
}
