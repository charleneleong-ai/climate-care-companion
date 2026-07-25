# Architecture

Drawn from the actual manifests and imports, not an intended design. Where the
diagram and the code disagree, the code is right and this file is a bug.

Diagrams render on GitHub.

---

## 1. The spine

What the system does, end to end. Every arrow is a real call; every label is the
type that crosses.

```mermaid
flowchart LR
    OM[("Open-Meteo<br/>live forecast")]
    PC[("postcodes.io")]

    subgraph predict["L1.5 predict"]
        HW["ThresholdHeatwave<br/><i>EnsembleHeatwave — unclaimed</i>"]
    end

    subgraph expose["L1 exposure"]
        IM["IndoorModel<br/>FR-11"]
        EN["ExposureNormaliser<br/>FR-07/08/09"]
    end

    subgraph score["L2 + L3 — the pure core"]
        VS["VulnerabilityScorer"]
        RS["RiskScorer"]
    end

    subgraph act["L4 act"]
        PB["PreventionPlanBuilder"]
        IT["InteractionTable"]
        QB["QuestionBank"]
    end

    subgraph allocate["L5 allocate"]
        AE["AllocationEngine"]
    end

    OM --> EN
    PC -.->|"not wired yet"| PL
    PL["PersonaLoader<br/>+ dwelling_offset"] --> IM
    EN --> IM
    IM -->|ExposureFeatures| RS
    HW -->|EpisodeForecast<br/>lead_time_hours| PB
    PL -->|Person| VS
    VS -->|VulnerabilityProfile| RS
    RS -->|Assessment| PB
    RS -->|Assessment| QB
    RS -->|Assessment| AE
    IT --> PB
    PB -->|PreventionPlan| OUT["caregiver + cared-for"]
    QB -->|Questionnaire| CH
    CH["CheckinSession"] -->|SelfReport| IM
    CH -->|"red flags,<br/>no answer"| ESC["escalation"]
    AE -->|AllocationPlan| COUNCIL["council"]

    style score fill:#e4f2f1,stroke:#0B7B77
    style RS fill:#0B7B77,color:#fff
```

**The loop worth noticing** is `SelfReport → IndoorModel`. What the person says on
a check-in corrects the modelled indoor estimate, which is the system's dominant
error term. It is the only arrow that goes backwards, and it is the one that moved
Doris from High to Severe.

`RiskScorer` never sees a forecast, a clock, or a database. Everything reaching it
is a frozen dataclass.

---

## 2. Package dependencies

Exactly what the manifests declare. Acyclic — `contracts` at the bottom, nothing
below it.

```mermaid
flowchart BT
    contracts["contracts<br/><i>zero third-party deps</i>"]
    core["core"]
    exposure["exposure"]
    persons["persons"]
    geography["geography"]
    predictors["predictors"]
    actions["actions"]
    checkin["checkin"]
    allocation["allocation"]
    org["org"]
    api["services/api"]
    voice["services/voice"]

    core --> contracts
    exposure --> contracts
    persons --> contracts
    org --> contracts
    actions --> contracts
    actions --> core
    checkin --> contracts
    checkin --> core
    allocation --> contracts
    allocation --> geography
    api --> contracts & core & persons
    voice --> contracts & core & checkin & persons

    style contracts fill:#0B7B77,color:#fff
    style predictors stroke-dasharray: 4 3
    style geography stroke-dasharray: 4 3
```

`predictors` and `geography` depend on nothing — dashed because that is
deliberate, not an oversight. The predictor seam must not import the scoring core
(AC-1), and geography is pure data loading.

**A cycle existed here and was removed.** `core.export` imported
`actions.interactions` through a function-local import, so the manifests showed no
cycle while `core.export` could not run without `actions` installed. The clinical
export now lives in `actions.export`, where the dependency already pointed.

---

## 3. Two engines, one source of truth

The front end scores in TypeScript so it works offline (NFR-04). That is two
implementations of L3 — the thing AC-1 and AC-5 exist to prevent — and it has
already cost once.

```mermaid
flowchart TB
    subgraph py["Python — source of truth"]
        RULES["core/rules.py<br/>declarative Bounds"]
        SEED[("data/seed/*.csv,yaml")]
        CE["core.export"]
        AX["actions.export"]
    end

    subgraph gen["generated — do not edit"]
        RJ["rules.generated.json"]
        PJ["parity-corpus.generated.json"]
        CJ["clinical.generated.json"]
    end

    subgraph ts["TypeScript — web/app"]
        CL["lib/clinical.ts"]
        RK["lib/risk.ts"]
        AD["lib/advice.ts"]
    end

    GATE{{"test_generated_freshness<br/>regenerates and compares"}}

    RULES --> CE --> RJ & PJ
    SEED --> CE
    SEED --> AX --> CJ
    CJ --> CL --> RK --> AD
    RJ -.->|"not read yet"| RK
    PJ -.->|"not run yet"| RK
    RJ & PJ & CJ --> GATE
    GATE -.->|"stale ⇒ build fails"| CE

    style py fill:#e4f2f1,stroke:#0B7B77
    style gen fill:#FBF0E3,stroke:#A85D18
```

Solid arrows are wired. **Dashed arrows are not**: the TypeScript reads the
clinical content but still carries its own rule literals and has never been run
against the parity corpus. The gate proves the files match Python; it does not yet
prove the app uses them.

---

## 4. A check-in, over time

Messaging is asynchronous, which is why this is a state machine rather than a
function call.

```mermaid
sequenceDiagram
    participant S as Scheduler
    participant Q as QuestionBank
    participant SE as CheckinSession
    participant T as Twilio
    participant P as Person
    participant C as Caregiver

    S->>Q: build_for(person, assessment)
    Q-->>SE: Questionnaire (personalised)
    SE->>T: TemplateMessage (Meta-approved)
    T->>P: opener
    Note over SE,P: 24-hour window is SHUT.<br/>Nothing else may be sent.

    alt they reply
        P->>T: any message
        T->>SE: webhook (signature checked)
        Note over SE: window opens
        loop each question
            SE->>T: ButtonMessage
            T->>P: Yes / No / Not sure
            P->>T: ButtonPayload carries the question code
            T->>SE: recorded against its own question
        end
        SE-->>SE: SelfReport
        SE->>C: red flags → escalate
    else silence past the timeout
        Note over SE: is_overdue → ABANDONED
        SE->>C: caregiver_no_answer template
    end
```

**The unanswered branch is not an error path.** A missed call during a risk window
is the condition the system exists to catch, so it escalates outward rather than
retrying inward.

---

## 5. Surfaces, and who owns them

```mermaid
flowchart LR
    subgraph data["shared data"]
        API["services/api"]
        GENC["clinical.generated.json"]
    end

    APP["web/app<br/><b>the companion</b><br/>Next.js, live weather, map"]
    NAT["web/national<br/>2025 replay, rung 0"]
    EXP["web/explorer<br/>facilities, rungs 5-6"]
    OLD["web/companion/index.html<br/><i>standalone prototype</i>"]

    GENC --> APP
    API -.->|"not wired"| APP
    NAT -.->|"no join key:<br/>LDN vs TLI"| APP
    EXP -.->|"synthetic facilities"| APP
    OLD -.->|"to be retired"| APP

    style APP fill:#0B7B77,color:#fff
    style OLD stroke-dasharray: 4 3
```

The three dashed edges are the honest state of it:

- **`national` cannot join to `app`.** One says `LDN`, the other says `TLI`. There
  is no shared region identifier, so nothing can flow between them without a
  mapping table.
- **`explorer` generates its facilities from a seeded RNG**, not from
  `data/geography/*.yaml`, so it and `AllocationEngine` disagree about what exists.
- **`web/companion/index.html` is superseded** by `web/app` and is due for
  retirement rather than maintenance.

---

## 6. Where the safety constraints are enforced

Not documentation — each of these fails a build.

```mermaid
flowchart LR
    SC1["SC-1<br/>never alter a prescription"]
    SC3["SC-3<br/>red flags only"]
    SC5["SC-5<br/>label modelled values"]
    SC6["SC-6<br/>no real data"]
    AC3["AC-3<br/>every code has an action"]
    FR18["FR-18<br/>zero exposure ⇒ Low"]

    SC1 --> L1["Corpus.load<br/>InteractionTable.load<br/>QuestionBank.load"]
    AC3 --> L1
    SC3 --> L2["test_question_safety<br/>polarity declared, not inferred"]
    SC5 --> L3["API key names<br/>carry _modelled"]
    SC6 --> L4["DryRun default<br/>allowlist fails closed"]
    FR18 --> L5["test_no_cry_wolf<br/>92 days"]

    L1 & L2 & L3 & L4 & L5 --> CI["CI"]

    style CI fill:#0B7B77,color:#fff
```

SC-1 is enforced at **load**, not only in tests: a corpus that advises changing a
prescription refuses to load, so the property holds for any caller — including one
that never runs the suite.
