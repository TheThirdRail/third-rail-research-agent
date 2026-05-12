"use client";

import { useEffect } from "react";
import { Terminal } from "lucide-react";

export default function Error({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    const isDevelopment = process.env.NODE_ENV === "development";

    useEffect(() => {
        // Log the error to an analytics service
        console.error("Dashboard Error:", error);
    }, [error]);

    return (
        <div className="h-screen w-full flex items-center justify-center bg-void text-neon-cyan font-mono p-4">
            <div className="max-w-2xl w-full border border-neon-purple/50 bg-midnight-purple/80 p-8 rounded-lg shadow-[0_0_50px_rgba(189,0,255,0.2)] backdrop-blur-md">
                <div className="flex items-center gap-3 mb-6 border-b border-white/20 pb-4">
                    <Terminal className="w-8 h-8 text-hot-pink" />
                    <h2 className="text-2xl font-bold font-orbitron text-white">SYSTEM CRITICAL FAILURE</h2>
                </div>

                <div className="space-y-4">
                    <p className="text-white/80">An unrecoverable handling error occurred within the dashboard matrix.</p>

                    <div className="bg-black/80 border border-white/10 p-4 rounded overflow-auto max-h-64">
                        {error.digest ? (
                            <p className="text-hot-pink font-bold mb-2">Error Digest: {error.digest}</p>
                        ) : null}
                        {isDevelopment ? (
                            <>
                                <p className="text-terminal-green mb-2">Message: {error.message}</p>
                                <pre className="text-xs text-gray-500 whitespace-pre-wrap">{error.stack}</pre>
                            </>
                        ) : (
                            <p className="text-terminal-green mb-2">Message: An unexpected dashboard error occurred.</p>
                        )}
                    </div>

                    <button
                        onClick={() => reset()}
                        className="mt-4 px-6 py-2 bg-neon-cyan/20 border border-neon-cyan hover:bg-neon-cyan/40 text-white uppercase tracking-wider transition-all"
                    >
                        Attempt System Reset
                    </button>
                </div>
            </div>
        </div>
    );
}
