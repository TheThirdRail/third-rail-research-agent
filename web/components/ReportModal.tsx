"use client";

import { useMemo, useRef, useState } from "react";
import { motion, AnimatePresence, useDragControls } from "framer-motion";
import { X, FileText, Download, Terminal } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { exportReportPdf } from "@/lib/api";

interface ReportModalProps {
    report: string | null;
    isOpen: boolean;
    onClose: () => void;
    canExportPdf?: boolean;
}

export function ReportModal({
    report,
    isOpen,
    onClose,
    canExportPdf = true,
}: ReportModalProps) {
    const contentRef = useRef<HTMLDivElement | null>(null);
    const overlayRef = useRef<HTMLDivElement | null>(null);
    const dragControls = useDragControls();
    const [isExportingPdf, setIsExportingPdf] = useState(false);

    const reportSessionId = useMemo(
        () => Math.random().toString(36).substring(7).toUpperCase(),
        [report],
    );

    const extractSourceMatrixTable = (markdown: string) => {
        const lines = markdown.split(/\r?\n/);
        const headingRegex = /^(#{1,6})\s+source matrix\s*:?\s*$/i;
        let startIndex = -1;
        let headingLevel = 0;

        for (let i = 0; i < lines.length; i += 1) {
            const match = lines[i].match(headingRegex);
            if (match) {
                startIndex = i + 1;
                headingLevel = match[1].length;
                break;
            }
        }

        if (startIndex === -1) {
            return null;
        }

        const sectionLines: string[] = [];
        for (let i = startIndex; i < lines.length; i += 1) {
            const line = lines[i];
            const headingMatch = line.match(/^(#{1,6})\s+/);
            if (headingMatch && headingMatch[1].length <= headingLevel) {
                break;
            }
            sectionLines.push(line);
        }

        const isSeparator = (line: string) =>
            /^\s*\|?\s*:?-{3,}/.test(line);

        for (let i = 0; i < sectionLines.length - 1; i += 1) {
            const headerLine = sectionLines[i];
            const separatorLine = sectionLines[i + 1];
            if (!headerLine.includes("|") || !isSeparator(separatorLine)) {
                continue;
            }

            const parseRow = (row: string) =>
                row
                    .trim()
                    .replace(/^\|/, "")
                    .replace(/\|$/, "")
                    .split("|")
                    .map((cell) => cell.trim());

            const headers = parseRow(headerLine);
            const rows: string[][] = [];
            for (let j = i + 2; j < sectionLines.length; j += 1) {
                const rowLine = sectionLines[j];
                if (!rowLine.includes("|")) {
                    break;
                }
                rows.push(parseRow(rowLine));
            }

            if (headers.length > 0 && rows.length > 0) {
                return { headers, rows };
            }
        }

        return null;
    };

    const handleDownloadCsv = () => {
        if (!report) return;
        const table = extractSourceMatrixTable(report);
        if (!table) {
            alert("Could not find a Source Matrix table to export.");
            return;
        }

        const escapeCell = (value: string) => {
            const text = String(value ?? "");
            if (/[",\r\n]/.test(text)) {
                return `"${text.replace(/"/g, '""')}"`;
            }
            return text;
        };

        const csvLines = [
            table.headers,
            ...table.rows,
        ].map((row) => row.map(escapeCell).join(","));

        const blob = new Blob([csvLines.join("\r\n")], {
            type: "text/csv;charset=utf-8;",
        });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "source-matrix.csv";
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    };

    const handleExportPdf = async () => {
        if (!report || isExportingPdf || !canExportPdf) return;
        setIsExportingPdf(true);
        try {
            const blob = await exportReportPdf(report);
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = "research-report.pdf";
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
        } catch (error) {
            const message =
                error instanceof Error
                    ? error.message
                    : "Failed to export PDF.";
            alert(message);
        } finally {
            setIsExportingPdf(false);
        }
    };

    return (
        <AnimatePresence>
            {isOpen && report && (
                <div
                    ref={overlayRef}
                    className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/90 backdrop-blur-md"
                >
                    <motion.div
                        initial={{ opacity: 0, scale: 0.9, rotateX: 10 }}
                        animate={{ opacity: 1, scale: 1, rotateX: 0 }}
                        exit={{ opacity: 0, scale: 0.9, rotateX: 10 }}
                        drag
                        dragControls={dragControls}
                        dragListener={false}
                        dragConstraints={overlayRef}
                        dragMomentum={false}
                        style={{ resize: "both" }}
                        className="w-[95vw] max-w-[1200px] max-h-[92vh] min-h-[60vh] bg-midnight-purple border-2 border-neon-cyan shadow-[0_0_60px_rgba(0,243,255,0.2)] flex flex-col overflow-hidden"
                    >
                        {/* Header */}
                        <div
                            onPointerDown={(event) => dragControls.start(event)}
                            className="bg-neon-cyan/20 p-4 border-b border-neon-cyan flex justify-between items-center cursor-move select-none"
                        >
                            <div className="flex items-center gap-3 text-neon-cyan font-bold font-orbitron tracking-widest text-[clamp(11px,1.3vw,13px)]">
                                <Terminal className="w-5 h-5" />
                                <span>RESEARCH_REPORT_LOG.MD</span>
                            </div>
                            <button
                                onClick={onClose}
                                onPointerDown={(event) => event.stopPropagation()}
                                className="text-white/70 hover:text-neon-cyan transition-colors bg-void/50 p-1 rounded"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        {/* Content */}
                        <div className="flex-1 overflow-y-auto overflow-x-auto p-6 md:p-8 font-mono text-[clamp(12px,1.2vw,15px)] leading-relaxed custom-scrollbar bg-void/30">
                            <div
                                ref={contentRef}
                                className="prose prose-invert max-w-none break-words prose-headings:text-neon-cyan prose-h1:text-2xl prose-h1:font-orbitron prose-h2:text-xl prose-h2:text-neon-purple prose-a:text-neon-cyan hover:prose-a:text-white prose-strong:text-hot-pink"
                            >
                                <ReactMarkdown
                                    remarkPlugins={[remarkGfm]}
                                    components={{
                                        table: ({ node, ...props }) => (
                                            <div className="w-full overflow-x-auto">
                                                <table
                                                    {...props}
                                                    className="w-full table-auto border-collapse border border-neon-cyan/40 bg-void/60 text-white/90"
                                                />
                                            </div>
                                        ),
                                        tr: ({ node, ...props }) => (
                                            <tr
                                                {...props}
                                                className="odd:bg-void/60 even:bg-void/40"
                                            />
                                        ),
                                        thead: ({ node, ...props }) => (
                                            <thead
                                                {...props}
                                                className="bg-neon-cyan/10 text-neon-cyan"
                                            />
                                        ),
                                        tbody: ({ node, ...props }) => (
                                            <tbody {...props} className="divide-y divide-white/10" />
                                        ),
                                        th: ({ node, ...props }) => (
                                            <th
                                                {...props}
                                                className="border border-neon-cyan/30 px-3 py-2 text-[11px] uppercase tracking-wider align-top whitespace-normal"
                                            />
                                        ),
                                        td: ({ node, ...props }) => (
                                            <td
                                                {...props}
                                                className="border border-white/15 px-3 py-2 text-[11px] align-top whitespace-normal break-words"
                                            />
                                        ),
                                        sup: ({ node, ...props }) => (
                                            <sup
                                                {...props}
                                                className="text-neon-cyan text-[10px] ml-0.5"
                                            />
                                        ),
                                    }}
                                >
                                    {report}
                                </ReactMarkdown>
                            </div>
                        </div>

                        {/* Footer */}
                        <div className="p-4 border-t border-white/10 bg-void/50 flex flex-wrap gap-2 justify-between items-center">
                            <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono">
                                End of transmission // ID: {reportSessionId}
                            </div>
                            <div className="flex gap-4">
                                <button
                                    onClick={handleDownloadCsv}
                                    className="flex items-center gap-2 text-[10px] text-neon-cyan hover:text-white transition-colors uppercase tracking-widest font-bold"
                                >
                                    <Download className="w-3 h-3" />
                                    Download CSV
                                </button>
                                <button
                                    onClick={handleExportPdf}
                                    disabled={isExportingPdf || !canExportPdf}
                                    className="flex items-center gap-2 text-[10px] text-neon-purple hover:text-white transition-colors uppercase tracking-widest font-bold disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    <FileText className="w-3 h-3" />
                                    {isExportingPdf
                                        ? "Exporting..."
                                        : canExportPdf
                                          ? "Export PDF"
                                          : "Login Required"}
                                </button>
                            </div>
                        </div>
                    </motion.div>
                </div>
            )}
        </AnimatePresence>
    );
}
