# VulnGraph: Multi-Agent Vulnerability Analysis Framework

## Project Overview

VulnGraph is a sophisticated **multi-agent autonomous system** designed to analyze software vulnerabilities and assets through a coordinated workflow. It leverages LLMs with tool integration to discover, analyze, and report on CVE impacts across software ecosystems.

**Key Innovation:** Dynamic planning with parallel execution and intelligent routing between specialized agent nodes.

---

## System Architecture

### High-Level Multi-Agent Flow

```mermaid
graph TB
    subgraph Orchestration["🎯 Orchestration Layer"]
        CoordNode["<b>Coordinator</b><br/>Input Processing<br/>& Validation"]
        PlannerNode["<b>Planner</b><br/>Dynamic Plan<br/>Generation"]
        UserFeedback["<b>User Feedback</b><br/>Human-in-the-loop<br/>Intervention"]
    end
    
    subgraph Workers["🤖 Worker Agents"]
        AssetAnalyzer["<b>Asset Analyzer</b><br/>Dependency Graph<br/>Analysis"]
        VulnDetail["<b>Vuln Detail</b><br/>CVE Deep Dive<br/>Analysis"]
        VulnDiscovery["<b>Vuln Discovery</b><br/>Find Related<br/>CVEs"]
    end
    
    subgraph Output["📋 Output Generation"]
        Reporter["<b>Reporter</b><br/>Generate Report<br/>& Jira Ticket"]
    end
    
    CoordNode --> PlannerNode
    PlannerNode --> UserFeedback
    UserFeedback --> Workers
    Workers --> PlannerNode
    PlannerNode --> Reporter
    Reporter --> END["Final Report"]
    
    style CoordNode fill:#4A90E2,stroke:#333,stroke-width:2px,color:#fff
    style PlannerNode fill:#7B68EE,stroke:#333,stroke-width:2px,color:#fff
    style UserFeedback fill:#FF9500,stroke:#333,stroke-width:2px,color:#fff
    style AssetAnalyzer fill:#50C878,stroke:#333,stroke-width:2px,color:#fff
    style VulnDetail fill:#50C878,stroke:#333,stroke-width:2px,color:#fff
    style VulnDiscovery fill:#50C878,stroke:#333,stroke-width:2px,color:#fff
    style Reporter fill:#E94B3C,stroke:#333,stroke-width:2px,color:#fff
    style END fill:#999,stroke:#333,stroke-width:2px,color:#fff
```

---

## Core Components

### 1. **Orchestration Layer**

| Component | Role | Key Feature |
|-----------|------|-------------|
| **Coordinator** | Entry point & initial routing | Validates input, invokes planner |
| **Planner** | Intelligent task decomposition | Creates multi-step execution plans |
| **User Feedback** | Human-in-the-loop control | Plan refinement & approval |

### 2. **Worker Agents** (Specialized & Parallelizable)

```mermaid
graph LR
    subgraph AssetSub["Asset Analysis Subgraph"]
        A1["Analyze Asset<br/>Dependencies"]
        A2["Tool Node<br/>Execute Tools"]
        A3["Process Results"]
    end
    
    subgraph VulnDetailSub["Vuln Detail Subgraph"]
        V1["Deep Dive<br/>CVE Analysis"]
        V2["Tool Node<br/>Fetch Details"]
        V3["Parse Vulnerabilities"]
    end
    
    subgraph VulnDiscoverySub["Vuln Discovery Subgraph"]
        D1["Discover Related<br/>CVEs"]
        D2["Tool Node<br/>Search Tools"]
        D3["Extract CVE IDs"]
    end
    
    A1 --> A2 --> A3
    V1 --> V2 --> V3
    D1 --> D2 --> D3
    
    A3 -.->|Results| Results["Step Results<br/>Dictionary"]
    V3 -.->|Results| Results
    D3 -.->|Results| Results
    
    style A1 fill:#90EE90,stroke:#333
    style A2 fill:#90EE90,stroke:#333
    style A3 fill:#90EE90,stroke:#333
    style V1 fill:#87CEEB,stroke:#333
    style V2 fill:#87CEEB,stroke:#333
    style V3 fill:#87CEEB,stroke:#333
    style D1 fill:#DDA0DD,stroke:#333
    style D2 fill:#DDA0DD,stroke:#333
    style D3 fill:#DDA0DD,stroke:#333
    style Results fill:#FFE4B5,stroke:#333,stroke-width:2px
```

**Parallel Execution Strategy:**
- **Asset Analysis** & **Vuln Detail**: Can run in parallel (configured via `STEP_CONFIG`)
- **Vuln Discovery**: Serial execution for stability
- Results aggregated in `step_results` dictionary before refinement

### 3. **State Management**

```mermaid
graph LR
    subgraph StateModel["NodeState Schema"]
        Input["<b>Input</b><br/>user_input<br/>run_id"]
        Planning["<b>Planning</b><br/>plan<br/>plan_iterations"]
        Execution["<b>Execution</b><br/>step_results<br/>step_id"]
        Output["<b>Output</b><br/>final_report<br/>status"]
    end
    
    Input -->|Initialize| Planning
    Planning -->|Execute| Execution
    Execution -->|Aggregate| Output
    
    style Input fill:#E1F5FE,stroke:#333
    style Planning fill:#F3E5F5,stroke:#333
    style Execution fill:#E8F5E9,stroke:#333
    style Output fill:#FFF3E0,stroke:#333
```

**Key Fields:**
- `messages`: LangChain message history
- `vulns`: Discovered & analyzed vulnerabilities
- `step_results`: Parallel execution results (keyed by step_id)
- `final_report`: Generated markdown report

---

## Execution Flow & Intelligent Routing

```mermaid
sequenceDiagram
    participant User
    participant Coord as Coordinator
    participant Planner
    participant Router as Worker Router
    participant Workers as Workers
    participant Reporter
    
    User->>Coord: Input Query
    Coord->>Planner: Route to Planner
    
    loop Plan Iterations
        Planner->>Planner: Generate/Refine Plan
        Planner->>Router: Send execution steps
        
        par Parallel Workers
            Router->>Workers: Dispatch Step 1
            Router->>Workers: Dispatch Step 2
        end
        
        Workers->>Workers: Execute + Aggregate Results
        Workers->>Planner: Return step_results
        
        alt User Feedback Requested
            Planner->>User: Ask for approval/clarification
            User->>Planner: Provide feedback
        end
    end
    
    Planner->>Reporter: Final analysis
    Reporter->>User: Generate & return report
```

---

## Key Technical Features

### 1. **Async/Concurrent Execution**
- Built on **LangGraph** with async-first design
- SQLite checkpointer for state persistence
- Support for long-running analyses without blocking

### 2. **Dynamic Planning System**
```python
# Plan structure:
class Plan:
    reasoning: str           # Why this approach
    steps: List[Step]        # Executable tasks
    expected_outcome: str    # Success criteria

# Steps can be:
# - asset_analysis: Analyze software dependencies
# - vuln_discovery: Find related CVEs
# - vuln_detail: Deep dive into specific CVEs
# - reporting: Generate final output
```

### 3. **Tool Integration**
Each worker agent has access to specialized tools:
- **Asset Tools**: Dependency analysis, software scanning
- **Vuln Tools**: CVE database queries, vulnerability scoring
- **Search Tools**: DuckDuckGo integration for discovery

### 4. **Multi-Model Support**
```python
Model Types:
├── "agentic" (Kimi K2): Complex reasoning & tool calls
├── "normal" (DeepSeek V3.2): General analysis
└── "free" (Ollama): Local fallback option
```

### 5. **State Persistence & Resumability**
- SQLite checkpoint database tracks all execution states
- Can resume interrupted analyses using `run_id`
- Enables long-term analysis tracking and audit logs

---

## Configuration & Customization

```yaml
Key Settings:
├── max_plan_iterations: 3          # Planning refinement rounds
├── max_step_num: 3                 # Max steps per plan
├── enable_parallel_execution: true # Run compatible steps in parallel
├── enable_clarification: true      # Ask user for clarification
├── enable_background_investigation: true  # Async discovery
└── max_clarification_rounds: 2     # Human-in-the-loop limit
```

---

## Project Structure

```
src/
├── main.py                 # Entry point & CLI handler
├── workflow.py             # Async workflow orchestration
├── models.py               # LLM initialization
├── settings.py             # Configuration management
├── logger.py               # Structured logging
│
├── graph/
│   ├── builder.py          # Graph compilation & checkpointer setup
│   ├── nodes.py            # All agent node implementations
│   ├── state.py            # State schema definition
│   └── subgraphs/
│       ├── asset_analysis.py       # Asset analyzer subgraph
│       ├── vuln_detail.py          # Vuln detail analyzer subgraph
│       └── vuln_discovery.py       # Vuln discovery subgraph
│
├── schemas/
│   ├── plans.py            # Plan & Step data models
│   ├── vulns.py            # Vulnerability data models
│   └── assets.py           # Asset data models
│
├── tools/
│   ├── asset_tools.py      # Asset analysis tools
│   ├── vuln_tools.py       # Vulnerability tools
│   ├── vuln_analyzer.py    # CVE analysis utilities
│   └── search.py           # Search integrations
│
└── prompts/
    ├── coordinator.md      # Coordinator system prompt
    ├── planner.md          # Planner system prompt
    ├── asset_analyzer.md   # Asset analyzer prompt
    ├── vuln_analyzer.md    # Vuln analyzer prompt
    ├── vuln_discovery.md   # Discovery prompt
    ├── reporter.md         # Reporter prompt
    └── template.py         # Prompt template engine
```

---

## Unique Value Propositions

| Feature | Benefit | Implementation |
|---------|---------|-----------------|
| **Dynamic Planning** | Adapts analysis depth based on findings | Planner + PlanRefine nodes |
| **Parallel Execution** | Reduces total analysis time 40-60% | LangGraph Send/Command routing |
| **Human-in-the-Loop** | Expert oversight on critical decisions | UserFeedback interrupts |
| **Checkpointing** | Resume analysis after interruptions | AsyncSqliteSaver persistence |
| **Multi-LLM Support** | Leverage best model for each task | Model selector by capability |
| **Structured Output** | Machine-readable vulnerability graphs | Pydantic schema enforcement |

---

## Technology Stack

```
Core Framework:
├── LangGraph 0.2+ (multi-agent orchestration)
├── LangChain (LLM abstraction & tools)
└── Pydantic (data validation)

LLM Providers:
├── Kimi K2 (agentic reasoning)
├── DeepSeek V3.2 (general analysis)
└── Ollama (local alternative)

Infrastructure:
├── SQLite (state checkpointing)
├── aiohttp (async HTTP)
└── Rich (terminal UI)
```

---

## Example Usage

```python
# Single shot analysis
await run_agent_workflow_async(
    user_input="Analyze CVE-2024-1234 impact on nginx",
    run_id="analysis_001",
    enable_parallel_execution=True,
    max_plan_iterations=3,
)

# Resume interrupted analysis
state = await get_run_state_async("analysis_001")
if state:
    await run_agent_workflow_async(
        user_input="Continue analysis",
        run_id="analysis_001",
        initial_state=state,
    )
```

---

## Performance Characteristics

- **Single CVE Analysis**: ~30-60 seconds (depends on LLM latency)
- **Asset with 50+ Dependencies**: ~2-3 minutes with parallelization
- **Full Multi-step Analysis**: ~5-10 minutes (3 iterations)

*Actual times vary with LLM API response times and tool availability.*

---

## Future Enhancement Opportunities

1. **Caching Layer**: Memoize CVE lookups to reduce API calls
2. **Graph Persistence**: Store vulnerability dependency graphs in Neo4j
3. **Real-time Streaming**: WebSocket support for live analysis updates
4. **Distributed Execution**: Kubernetes backend for scaling workers
5. **Knowledge Graph**: ML-based pattern detection across vulnerabilities

---

**Author:** VulnGraph Development Team  
**Framework:** LangGraph-based Multi-Agent Architecture  
**License:** MIT
