const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const BACKEND_PROXY_URL = "/api/backend";

async function errorDetail(res: Response, fallback: string): Promise<string> {
    try {
        const error = await res.json();
        if (error?.detail) {
            return String(error.detail);
        }
    } catch {
        // ignore JSON parse errors
    }
    return fallback;
}

function backendPath(path: string): string {
    return `${BACKEND_PROXY_URL}${path}`;
}

export interface AdminSession {
    authenticated: boolean;
}

export async function getAdminSession(): Promise<AdminSession> {
    const res = await fetch("/api/admin/session", { cache: "no-store" });
    if (!res.ok) {
        return { authenticated: false };
    }
    return res.json();
}

export async function loginAdmin(adminKey: string): Promise<AdminSession> {
    const res = await fetch("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ adminKey }),
    });
    if (!res.ok) {
        throw new Error(await errorDetail(res, "Admin login failed"));
    }
    return res.json();
}

export async function logoutAdmin(): Promise<void> {
    const res = await fetch("/api/admin/logout", { method: "POST" });
    if (!res.ok) {
        throw new Error(await errorDetail(res, "Admin logout failed"));
    }
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
    const res = await fetch(backendPath(`/api/agents/${agentName}/config`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
    });
    if (!res.ok) {
        throw new Error(await errorDetail(res, "Failed to update config"));
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
    const res = await fetch(backendPath(`/api/models?${params.toString()}`));
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
    const res = await fetch(backendPath("/api/analyze"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
    });
    if (!res.ok) {
        throw new Error(await errorDetail(res, "Analysis failed"));
    }
    return res.json();
}

export async function exportReportPdf(report_markdown: string): Promise<Blob> {
    const res = await fetch(backendPath("/api/reports/pdf"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report_markdown }),
    });
    if (!res.ok) {
        throw new Error(await errorDetail(res, "Failed to export PDF"));
    }
    return res.blob();
}
