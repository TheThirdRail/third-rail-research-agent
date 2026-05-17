const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const ADMIN_API_KEY = process.env.NEXT_PUBLIC_ADMIN_API_KEY || "";

function adminHeaders(): Record<string, string> {
    const headers: Record<string, string> = {};
    if (ADMIN_API_KEY) {
        headers["X-Research-Agent-Key"] = ADMIN_API_KEY;
    }
    return headers;
}

export interface AgentConfig {
    agent_name: string;
    provider: string | null;
    model: string | null;
    temperature: number | null;
    budget_limit: number | null;
    free_tier: boolean | null;
    reasoning_effort: "none" | "low" | "medium" | "high" | null;
}

export interface AgentInfo {
    name: string;
    role: string;
    goal: string;
    config: AgentConfig;
}

export async function getAgents(): Promise<AgentInfo[]> {
    const res = await fetch(`${API_URL}/api/agents`);
    if (!res.ok) throw new Error("Failed to fetch agents");
    const data = await res.json();
    return data;
}

export async function updateAgentConfig(
    agentName: string,
    config: Partial<AgentConfig>
): Promise<AgentConfig> {
    const res = await fetch(`${API_URL}/api/agents/${agentName}/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...adminHeaders() },
        body: JSON.stringify(config),
    });
    if (!res.ok) {
        let detail = "Failed to update config";
        try {
            const error = await res.json();
            if (error?.detail) detail = error.detail;
        } catch {
            // ignore JSON parse errors
        }
        throw new Error(detail);
    }
    return res.json();
}

export interface ModelInfo {
    id: string;
    label: string;
    input_cost_per_m: number;
    output_cost_per_m: number;
}

export async function getModels(
    provider: string,
    refresh: boolean = false
): Promise<ModelInfo[]> {
    const params = new URLSearchParams({ provider });
    if (refresh) params.set("refresh", "true");
    const res = await fetch(`${API_URL}/api/models?${params.toString()}`, {
        headers: adminHeaders(),
    });
    if (!res.ok) {
        console.error("Failed to fetch models", res.statusText);
        return [];
    }
    return res.json();
}

export interface AnalyzeRequest {
    description: string;
    url?: string | null;
}

export interface AnalyzeResponse {
    story_id: string;
    report: string;
    status: string;
    source_count?: number;
    bias_spread_met?: boolean;
    left_source_count?: number;
    right_source_count?: number;
}

export async function analyzeStory(request: AnalyzeRequest): Promise<AnalyzeResponse> {
    const res = await fetch(`${API_URL}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
    });
    if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Analysis failed");
    }
    return res.json();
}

export async function exportReportPdf(report_markdown: string): Promise<Blob> {
    const res = await fetch(`${API_URL}/api/reports/pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report_markdown }),
    });
    if (!res.ok) {
        let detail = "Failed to export PDF";
        try {
            const error = await res.json();
            if (error?.detail) detail = error.detail;
        } catch {
            // ignore JSON parse errors
        }
        throw new Error(detail);
    }
    return res.blob();
}
