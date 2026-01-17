---
trigger: model_decision
description: Rules for Front End
---

# Project Rules: Frontend (Next.js)

---

## File Naming

| Element | Convention | Example |
|---------|------------|---------|
| **Pages** | kebab-case folders | `app/discover/page.tsx` |
| **Components** | PascalCase | `BiasIndicator.tsx` |
| **Utilities** | camelCase | `formatBiasLabel.ts` |
| **Hooks** | use prefix | `useAnalysis.ts` |

---

## Component Pattern

```tsx
// components/custom/BiasIndicator.tsx
import { cn } from "@/lib/utils"

interface BiasIndicatorProps {
  value: number  // -4 to +4
  showLabel?: boolean
  className?: string
}

export function BiasIndicator({ 
  value, 
  showLabel = true,
  className 
}: BiasIndicatorProps) {
  const label = getBiasLabel(value)
  const color = getBiasColor(value)
  
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div 
        className="h-3 w-3 rounded-full" 
        style={{ backgroundColor: color }}
      />
      {showLabel && <span className="text-sm">{label}</span>}
    </div>
  )
}
```

---

## API Client Pattern

```typescript
// lib/api.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export async function analyzeStory(request: AnalyzeRequest): Promise<AnalysisResponse> {
  const response = await fetch(`${API_BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  })
  
  if (!response.ok) {
    throw new Error(`API error: ${response.status}`)
  }
  
  return response.json()
}
```

---

## UI Libraries

- **shadcn/ui** - Component library (Tailwind-based)
- **Tailwind CSS** - Styling
- **React Query** - Data fetching and caching
- **Zustand** - State management (if needed)
