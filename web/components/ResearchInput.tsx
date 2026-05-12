"use client";

import { useState } from "react";
import { Search, Globe, Loader2, Sparkles } from "lucide-react";
import { motion } from "framer-motion";

interface ResearchInputProps {
    onAnalyze: (description: string, url: string | null) => Promise<void>;
    isLoading: boolean;
    disabled?: boolean;
}

export function ResearchInput({ onAnalyze, isLoading, disabled = false }: ResearchInputProps) {
    const [description, setDescription] = useState("");
    const [url, setUrl] = useState("");
    const controlsDisabled = isLoading || disabled;

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (disabled || !description.trim()) return;
        onAnalyze(description, url.trim() || null);
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className="w-full bg-midnight-purple/40 border border-neon-cyan/30 backdrop-blur-md p-6 shadow-[0_0_30px_rgba(0,243,255,0.1)]"
        >
            <form onSubmit={handleSubmit} className="space-y-4">
                <div className="flex items-center gap-2 mb-2">
                    <Sparkles className="w-5 h-5 text-neon-cyan animate-pulse" />
                    <h2 className="text-neon-cyan font-orbitron font-bold tracking-widest text-sm uppercase">Execute Research Directive</h2>
                </div>

                <div className="relative">
                    <textarea
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        placeholder="Enter story description or news topic to research..."
                        className="w-full h-32 bg-void/80 border border-white/10 text-white p-4 focus:border-neon-cyan focus:outline-none focus:shadow-[0_0_15px_rgba(0,243,255,0.15)] font-mono text-sm placeholder:text-gray-600 resize-none transition-all"
                        disabled={controlsDisabled}
                    />
                </div>

                <div className="flex flex-col md:flex-row gap-4 items-end">
                    <div className="flex-1 w-full space-y-1.5">
                        <label className="text-[10px] text-gray-500 uppercase tracking-[0.2em] ml-1">Reference URL (Optional)</label>
                        <div className="relative">
                            <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                            <input
                                type="url"
                                value={url}
                                onChange={(e) => setUrl(e.target.value)}
                                placeholder="https://news-source.com/article"
                                className="w-full bg-void/80 border border-white/10 text-white pl-10 pr-4 py-2 focus:border-neon-cyan focus:outline-none font-mono text-xs transition-all"
                                disabled={controlsDisabled}
                            />
                        </div>
                    </div>

                    <button
                        type="submit"
                        disabled={controlsDisabled || !description.trim()}
                        className="w-full md:w-auto px-8 py-3 bg-neon-cyan text-void font-black uppercase text-xs tracking-[0.2em] shadow-[0_0_20px_rgba(0,243,255,0.4)] hover:shadow-[0_0_30px_rgba(0,243,255,0.6)] hover:bg-white transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:shadow-none"
                    >
                        {isLoading ? (
                            <>
                                <Loader2 className="w-4 h-4 animate-spin" />
                                Analyzing...
                            </>
                        ) : disabled ? (
                            "Login Required"
                        ) : (
                            <>
                                <Search className="w-4 h-4" />
                                Initiate Scan
                            </>
                        )}
                    </button>
                </div>
            </form>
        </motion.div>
    );
}
