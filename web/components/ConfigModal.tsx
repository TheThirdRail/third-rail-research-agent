"use client";

import { useState, useEffect, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Save, Terminal, Loader2 } from "lucide-react";
import { AgentConfig, AgentInfo, updateAgentConfig, getModels, ModelInfo } from "@/lib/api";

interface ConfigModalProps {
    agent: AgentInfo | null;
    isOpen: boolean;
    onClose: () => void;
    onSaved: () => void;
}

export function ConfigModal({ agent, isOpen, onClose, onSaved }: ConfigModalProps) {
    const [formData, setFormData] = useState<Partial<AgentConfig>>({});
    const [loading, setLoading] = useState(false);
    const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
    const [loadingModels, setLoadingModels] = useState(false);
    const [modelSearch, setModelSearch] = useState("");
    const selectedProvider = formData.provider || "";
    const selectedModel = formData.model || "";
    const showReasoningEffort =
        selectedProvider === "openai" && /^(gpt-|o\d|o-|codex)/i.test(selectedModel);

    useEffect(() => {
        if (agent) {
            setFormData(agent.config);
        }
    }, [agent]);

    const loadModels = async (refresh = false) => {
        if (!formData.provider) {
            setAvailableModels([]);
            return;
        }

        setLoadingModels(true);
        try {
            const models = await getModels(formData.provider, refresh);
            setAvailableModels(models);
        } catch (error) {
            console.error("Failed to load models", error);
            setAvailableModels([]);
        } finally {
            setLoadingModels(false);
        }
    };

    useEffect(() => {
        loadModels(false);
    }, [formData.provider]);

    const filteredModels = useMemo(() => {
        let models = availableModels;
        const term = modelSearch.trim().toLowerCase();
        if (term) {
            models = models.filter((m) => {
                const label = (m.label || m.id || "").toLowerCase();
                return label.includes(term) || m.id.toLowerCase().includes(term);
            });
        }
        return models;
    }, [availableModels, modelSearch]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!agent) return;

        setLoading(true);
        try {
            await updateAgentConfig(agent.name, formData);
            onSaved();
            onClose();
        } catch (err) {
            console.error(err);
            alert(err instanceof Error ? err.message : "Failed to save configuration");
        } finally {
            setLoading(false);
        }
    };

    return (
        <AnimatePresence>
            {isOpen && agent && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
                    <motion.div
                        initial={{ opacity: 0, scale: 0.9, y: 20 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.9, y: 20 }}
                        className="w-full max-w-lg bg-midnight-purple border-2 border-neon-purple shadow-[0_0_50px_rgba(189,0,255,0.3)] relative overflow-hidden"
                    >
                        {/* Header */}
                        <div className="bg-neon-purple/20 p-3 border-b border-neon-purple flex justify-between items-center">
                            <div className="flex items-center gap-2 text-neon-purple font-bold font-mono">
                                <Terminal className="w-5 h-5" />
                                <span>ROOT@{agent.name.toUpperCase()}:~ CONFIG.EXE</span>
                            </div>
                            <button onClick={onClose} className="text-white/70 hover:text-white transition-colors">
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        {/* Form */}
                        <form onSubmit={handleSubmit} className="p-6 space-y-6 font-mono text-sm">
                            <div className="space-y-4">

                                {/* Provider */}
                                <div className="space-y-1.5">
                                    <label className="text-neon-cyan text-xs uppercase tracking-wider block">LLM Provider</label>
                                    <select
                                        value={formData.provider || ""}
                                        onChange={(e) =>
                                            setFormData({
                                                ...formData,
                                                provider: e.target.value || null,
                                                model: null,
                                                reasoning_effort:
                                                    e.target.value === "openai"
                                                        ? formData.reasoning_effort ?? null
                                                        : null,
                                            })
                                        }
                                        className="w-full bg-void border border-white/20 text-white p-2 focus:border-neon-cyan focus:outline-none focus:shadow-[0_0_10px_rgba(0,243,255,0.2)]"
                                    >
                                        <option value="">(Default)</option>
                                        <option value="openrouter">OpenRouter</option>
                                        <option value="lmstudio">LM Studio (Local)</option>
                                        <option value="ollama">Ollama (Local)</option>
                                        <option value="openai">OpenAI</option>
                                        <option value="anthropic">Anthropic</option>
                                        <option value="gemini">Google Gemini</option>
                                        <option value="groq">Groq</option>
                                        <option value="cerebras">Cerebras</option>
                                        <option value="sambanova">SambaNova</option>
                                        <option value="mistral">Mistral AI</option>
                                        <option value="xai">xAI (Grok)</option>
                                    </select>
                                </div>

                                <label className="flex items-center gap-2 text-xs text-white/70">
                                    <input
                                        type="checkbox"
                                        checked={Boolean(formData.free_tier)}
                                        onChange={(e) =>
                                            setFormData({ ...formData, free_tier: e.target.checked })
                                        }
                                        className="accent-neon-cyan"
                                    />
                                    Free Tier API (enable backoff)
                                </label>

                                {/* Model */}
                                <div className="space-y-1.5">
                                    <div className="flex justify-between items-center">
                                        <label className="text-neon-cyan text-xs uppercase tracking-wider block">Model Name</label>
                                        <div className="flex items-center gap-3">
                                            {loadingModels && (
                                                <span className="text-neon-purple text-xs flex items-center gap-1 animate-pulse">
                                                    <Loader2 className="w-3 h-3 animate-spin" />
                                                    Fetching models...
                                                </span>
                                            )}
                                            <button
                                                type="button"
                                                onClick={() => loadModels(true)}
                                                className="text-xs text-white/70 hover:text-white uppercase tracking-wider"
                                            >
                                                Refresh
                                            </button>
                                        </div>
                                    </div>

                                    <input
                                        type="text"
                                        value={modelSearch}
                                        onChange={(e) => setModelSearch(e.target.value)}
                                        placeholder="Search models..."
                                        className="w-full bg-void border border-white/20 text-white p-2 text-xs focus:border-neon-cyan focus:outline-none focus:shadow-[0_0_10px_rgba(0,243,255,0.2)]"
                                    />

                                    {filteredModels.length > 0 ? (
                                        <select
                                            value={formData.model || ""}
                                            onChange={(e) => setFormData({ ...formData, model: e.target.value || null })}
                                            className="w-full bg-void border border-white/20 text-white p-2 focus:border-neon-cyan focus:outline-none focus:shadow-[0_0_10px_rgba(0,243,255,0.2)]"
                                        >
                                            <option value="">Select a model...</option>
                                            {filteredModels.map((m) => (
                                                <option key={m.id} value={m.id}>
                                                    {m.label}
                                                </option>
                                            ))}
                                            <option value="custom">Custom...</option>
                                        </select>
                                    ) : (
                                        <input
                                            type="text"
                                            value={formData.model || ""}
                                            onChange={(e) => setFormData({ ...formData, model: e.target.value || null })}
                                            placeholder={loadingModels ? "Loading models..." : "e.g. gpt-4o, llama3:8b"}
                                            disabled={loadingModels}
                                            className="w-full bg-void border border-white/20 text-white p-2 focus:border-neon-cyan focus:outline-none focus:shadow-[0_0_10px_rgba(0,243,255,0.2)] disabled:opacity-50"
                                        />
                                    )}

                                    {/* Fallback for when "custom" is selected in dropdown, typically would need extra logic but keeping simple for now */}
                                    {formData.model === "custom" && (
                                        <input
                                            type="text"
                                            placeholder="Enter custom model ID..."
                                            onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                                            className="w-full mt-2 bg-void border border-white/20 text-white p-2 focus:border-neon-cyan"
                                            autoFocus
                                        />
                                    )}
                                </div>

                                {showReasoningEffort && (
                                    <div className="space-y-1.5">
                                        <label className="text-neon-cyan text-xs uppercase tracking-wider block">
                                            Reasoning Effort
                                        </label>
                                        <select
                                            value={formData.reasoning_effort || ""}
                                            onChange={(e) =>
                                                setFormData({
                                                    ...formData,
                                                    reasoning_effort:
                                                        (e.target.value as AgentConfig["reasoning_effort"]) || null,
                                                })
                                            }
                                            className="w-full bg-void border border-white/20 text-white p-2 focus:border-neon-cyan focus:outline-none focus:shadow-[0_0_10px_rgba(0,243,255,0.2)]"
                                        >
                                            <option value="">Provider default</option>
                                            <option value="none">None</option>
                                            <option value="low">Low</option>
                                            <option value="medium">Medium</option>
                                            <option value="high">High</option>
                                        </select>
                                    </div>
                                )}

                                {/* Temperature */}
                                <div className="space-y-1.5">
                                    <label className="text-neon-cyan text-xs uppercase tracking-wider block">
                                        Temperature ({formData.temperature ?? 0.7})
                                    </label>
                                    <input
                                        type="range"
                                        min="0"
                                        max="1"
                                        step="0.1"
                                        value={formData.temperature ?? 0.7}
                                        onChange={(e) => setFormData({ ...formData, temperature: parseFloat(e.target.value) })}
                                        className="w-full accent-neon-cyan"
                                    />
                                </div>

                                {/* Budget */}
                                <div className="space-y-1.5">
                                    <label className="text-neon-cyan text-xs uppercase tracking-wider block">Budget Limit ($)</label>
                                    <input
                                        type="number"
                                        step="0.01"
                                        value={formData.budget_limit || ""}
                                        onChange={(e) => setFormData({ ...formData, budget_limit: parseFloat(e.target.value) || null })}
                                        placeholder="Unlimited"
                                        className="w-full bg-void border border-white/20 text-white p-2 focus:border-neon-cyan focus:outline-none focus:shadow-[0_0_10px_rgba(0,243,255,0.2)]"
                                    />
                                </div>

                            </div>

                            {/* Footer Actions */}
                            <div className="pt-4 flex justify-end gap-3 border-t border-white/10">
                                <button
                                    type="button"
                                    onClick={onClose}
                                    className="px-4 py-2 text-white/60 hover:text-white uppercase text-xs tracking-wider"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={loading}
                                    className="px-6 py-2 bg-neon-purple hover:bg-hot-pink text-white font-bold uppercase text-xs tracking-wider border border-white/20 shadow-[0_0_15px_rgba(189,0,255,0.4)] transition-all flex items-center gap-2 group"
                                >
                                    {loading ? (
                                        <span className="animate-pulse">Saving...</span>
                                    ) : (
                                        <>
                                            <Save className="w-4 h-4 group-hover:scale-110 transition-transform" />
                                            Execute Save
                                        </>
                                    )}
                                </button>
                            </div>
                        </form>
                    </motion.div>
                </div>
            )}
        </AnimatePresence>
    );
}
