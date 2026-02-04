const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface AgentConfig {
    agent_name: string;
    provider: string | null;
    model: string | null;
    temperature: number | null;
    budget_limit: number | null;
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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
    });
    if (!res.ok) throw new Error("Failed to update config");
    return res.json();
}

export interface ModelInfo {
    id: string;
    label: string;
    input_cost_per_m: number;
    output_cost_per_m: number;
}

export async function getModels(provider: string): Promise<ModelInfo[]> {
    const res = await fetch(`${API_URL}/api/models?provider=${provider}`);
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
