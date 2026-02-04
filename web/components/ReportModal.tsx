"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X, FileText, Download, Terminal } from "lucide-react";
import ReactMarkdown from "react-markdown";

interface ReportModalProps {
    report: string | null;
    isOpen: boolean;
    onClose: () => void;
}

export function ReportModal({ report, isOpen, onClose }: ReportModalProps) {
    return (
        <AnimatePresence>
            {isOpen && report && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/90 backdrop-blur-md">
                    <motion.div
                        initial={{ opacity: 0, scale: 0.9, rotateX: 10 }}
                        animate={{ opacity: 1, scale: 1, rotateX: 0 }}
                        exit={{ opacity: 0, scale: 0.9, rotateX: 10 }}
                        className="w-full max-w-4xl max-h-[90vh] bg-midnight-purple border-2 border-neon-cyan shadow-[0_0_60px_rgba(0,243,255,0.2)] flex flex-col overflow-hidden"
                    >
                        {/* Header */}
                        <div className="bg-neon-cyan/20 p-4 border-b border-neon-cyan flex justify-between items-center">
                            <div className="flex items-center gap-3 text-neon-cyan font-bold font-orbitron tracking-widest text-sm">
                                <Terminal className="w-5 h-5" />
                                <span>RESEARCH_REPORT_LOG.MD</span>
                            </div>
                            <button
                                onClick={onClose}
                                className="text-white/70 hover:text-neon-cyan transition-colors bg-void/50 p-1 rounded"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        {/* Content */}
                        <div className="flex-1 overflow-y-auto p-8 font-mono text-sm custom-scrollbar bg-void/30">
                            <div className="prose prose-invert max-w-none prose-headings:text-neon-cyan prose-h1:text-2xl prose-h1:font-orbitron prose-h2:text-xl prose-h2:text-neon-purple prose-a:text-neon-cyan hover:prose-a:text-white prose-strong:text-hot-pink">
                                <ReactMarkdown>{report}</ReactMarkdown>
                            </div>
                        </div>

                        {/* Footer */}
                        <div className="p-4 border-t border-white/10 bg-void/50 flex justify-between items-center">
                            <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono">
                                End of transmission // ID: {Math.random().toString(36).substring(7).toUpperCase()}
                            </div>
                            <div className="flex gap-4">
                                <button className="flex items-center gap-2 text-[10px] text-neon-cyan hover:text-white transition-colors uppercase tracking-widest font-bold">
                                    <Download className="w-3 h-3" />
                                    Download CSV
                                </button>
                                <button className="flex items-center gap-2 text-[10px] text-neon-purple hover:text-white transition-colors uppercase tracking-widest font-bold">
                                    <FileText className="w-3 h-3" />
                                    Export PDF
                                </button>
                            </div>
                        </div>
                    </motion.div>
                </div>
            )}
        </AnimatePresence>
    );
}
