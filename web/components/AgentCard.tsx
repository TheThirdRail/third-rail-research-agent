"use client";

import { motion } from "framer-motion";
import { Cpu, Settings, Activity } from "lucide-react";
import { AgentInfo } from "@/lib/api";
import { cn } from "@/lib/utils";

interface AgentCardProps {
    agent: AgentInfo;
    onConfigure: (agent: AgentInfo) => void;
}

export function AgentCard({ agent, onConfigure }: AgentCardProps) {
    // Format budget currency
    const budgetLimit = agent.config.budget_limit;
    const limit = budgetLimit === null || budgetLimit === undefined
        ? "∞"
        : `$${budgetLimit.toFixed(2)}`;

    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            whileHover={{ scale: 1.02, boxShadow: "0 0 25px rgba(0, 243, 255, 0.3)" }}
            className="relative group bg-midnight-purple/80 border border-neon-cyan/50 rounded-lg p-5 backdrop-blur-sm overflow-hidden"
        >
            {/* Scanline overlay for card */}
            <div className="absolute inset-0 bg-gradient-to-b from-transparent via-neon-cyan/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />

            {/* Header */}
            <div className="flex justify-between items-start mb-4">
                <div>
                    <h3 className="text-xl font-bold text-neon-cyan font-orbitron tracking-wider flex items-center gap-2">
                        <Cpu className="w-5 h-5" />
                        {agent.name.toUpperCase()}
                    </h3>
                    <p className="text-xs text-gray-400 mt-1 font-mono uppercase tracking-widest">
                        {agent.role}
                    </p>
                </div>
                <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-terminal-green/10 border border-terminal-green/30">
                    <div className="w-2 h-2 rounded-full bg-terminal-green animate-pulse" />
                    <span className="text-[10px] text-terminal-green font-bold">ONLINE</span>
                </div>
            </div>

            {/* Content */}
            <div className="space-y-3 font-mono text-sm relative z-10">
                <div className="flex justify-between border-b border-white/10 pb-2">
                    <span className="text-gray-400">PROVIDER</span>
                    <span className="text-white font-bold">{agent.config.provider || "DEFAULT"}</span>
                </div>
                <div className="flex justify-between border-b border-white/10 pb-2">
                    <span className="text-gray-400">MODEL</span>
                    <span className="text-neon-purple font-bold truncate max-w-[150px]" title={agent.config.model || "Default"}>
                        {agent.config.model || "AUTO"}
                    </span>
                </div>
                <div className="flex justify-between">
                    <span className="text-gray-400">BUDGET</span>
                    <span className="text-hot-pink font-bold">{limit}</span>
                </div>
            </div>

            {/* Action */}
            <button
                onClick={() => onConfigure(agent)}
                className="mt-5 w-full py-2 bg-neon-cyan/10 hover:bg-neon-cyan/20 border border-neon-cyan text-neon-cyan font-bold uppercase tracking-wider text-xs transition-all hover:text-white hover:shadow-[0_0_15px_rgba(0,243,255,0.4)] flex items-center justify-center gap-2"
            >
                <Settings className="w-4 h-4" />
                Configure
            </button>

            {/* Decorative corner accents */}
            <div className="absolute top-0 left-0 w-2 h-2 border-t border-l border-neon-cyan" />
            <div className="absolute top-0 right-0 w-2 h-2 border-t border-r border-neon-cyan" />
            <div className="absolute bottom-0 left-0 w-2 h-2 border-b border-l border-neon-cyan" />
            <div className="absolute bottom-0 right-0 w-2 h-2 border-b border-r border-neon-cyan" />
        </motion.div>
    );
}
