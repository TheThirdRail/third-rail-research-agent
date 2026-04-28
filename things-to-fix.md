# Hardening the Third Rail Research Agent

## Executive summary

The biggest thing to fix is not “pick a bigger model and hope.” The biggest thing to fix is the **selection logic**. Right now, your runtime reads machine-readable source data from `config/rss_feeds.yaml` and `config/bias_sources.yaml`, while your much larger root-level `Deep-RSS-Research.md` appears to be documentation, not live input. On top of that, the discovery prompt talks about category focus, but the RSS tool’s keyword path ignores categories entirely; and the analysis-time `source_aggregator` agent does not even have the RSS tool attached. So the code path that is supposed to deliver cross-spectrum coverage is missing hard constraints in exactly the places where you need them. fileciteturn58file0L1-L1 fileciteturn61file0L1-L1 fileciteturn72file0L1-L1 fileciteturn74file0L1-L1 fileciteturn52file0L1-L1

The second big thing is that your architecture already contains the bones of the system you want, but the important parts are dormant or mislocated. The repo already has a profile loader that can parse YAML, JSON, markdown, and text into structured channel scope; the database already has places to store story keywords, relevance scores, and narrative fields; the agent role config already defines `story_parser` and `narrative_analyzer`. That means you do **not** need to invent a brand-new architecture. You need to activate the missing stages and move a few responsibilities out of prompts and into deterministic services. fileciteturn78file0L1-L1 fileciteturn70file0L1-L1 fileciteturn67file0L1-L1

The uploaded sample report is actually useful evidence here. Structurally, it is pretty good: it has a Source Matrix, footnotes, sectioned analysis, and a real attempt to separate allegations from proven facts. But the source base is ideologically narrow—three center-ish sources and one slight-left source—and the report itself explicitly says the available source set is narrow in ideological range. That means your main bottleneck is upstream evidence gathering and evidence routing, not downstream prose alone. fileciteturn50file1

My blunt recommendation is this: make **balanced source retrieval** deterministic, make **bias classification** use one unified resolver, make **fact extraction** output structured claim objects instead of loose prose, add **story parsing**, **relevance scoring**, and **narrative analysis** as real stages, and stop letting the final report writer invent tables and citations from scratch. For model choices, keep smaller models on bounded support work, but use entity["company","OpenAI","ai company"] `gpt-5.5` for fact extraction, rhetorical analysis, narrative analysis, and final synthesis; use `gpt-5.4` or `gpt-5.4-mini` for the more constrained routing and ranking stages. That aligns with OpenAI’s current guidance that `gpt-5.5` is the flagship for complex reasoning and coding, while `gpt-5.4-mini` is intended for faster subagent-style work. citeturn10search2turn10search1turn3search0turn7search1

## Methodology

I started with your selected repository on entity["company","GitHub","code hosting platform"] and inspected the specific files that govern discovery, source gathering, bias resolution, fact extraction, rhetoric analysis, reporting, channel profiles, and agent configuration. I also examined your root-level source inventory markdown, the machine-readable RSS and bias YAML files, and the uploaded sample report and source matrix. For model and temperature recommendations, I relied on current official OpenAI model documentation and API guidance, and on primary decoding research discussing how temperature and sampling affect determinism, repetition, and diversity. fileciteturn52file0L1-L1 fileciteturn57file0L1-L1 fileciteturn59file0L1-L1 fileciteturn60file0L1-L1 fileciteturn70file0L1-L1 fileciteturn50file1 citeturn10search2turn10search0turn10search1turn4search2turn5search0turn6search0

The main information needs were straightforward. I needed to determine which source registries are actually used at runtime; where spectrum-balancing decisions currently happen; whether the repo already has infrastructure for per-user profiles, relevance scoring, and narrative storage; how the sample report failed in practice; and which model configurations best match each stage’s decision criticality. Those questions are what drove the recommendations below. fileciteturn58file0L1-L1 fileciteturn59file0L1-L1 fileciteturn70file0L1-L1 fileciteturn78file0L1-L1 fileciteturn50file1

## What the current code is actually doing

Your current code has three especially important mismatches.

The first mismatch is between **human documentation** and **runtime data**. `Deep-RSS-Research.md` is a large, cross-spectrum inventory of outlets and feeds, but the RSS tool actually loads `settings.config_dir / "rss_feeds.yaml"`, and the local bias classifier loads `settings.config_dir / "bias_sources.yaml"`. In plain English: if your latest source curation only lives in markdown, the runtime is not using it. That explains part of the gap between what you thought the agent should know and what the code can actually act on. fileciteturn52file0L1-L1 fileciteturn58file0L1-L1 fileciteturn61file0L1-L1 fileciteturn88file0L1-L1 fileciteturn89file0L1-L1

The second mismatch is between the **discovery prompt** and the **RSS tool behavior**. The discovery crew tells the agent to fetch stories related to channel topics and “focus on categories: center, libertarian, independent, fringe_conspiracy, religion_spiritual, supernatural.” But `RSSAggregatorTool._run()` takes either `keywords` or `categories`; when `keywords` is present, it calls `search_feeds(keyword_list, ...)` and ignores categories. So the prompt is asking for category-aware behavior that the tool path does not actually implement in keyword mode. That is a real bug, not a style issue. fileciteturn72file0L1-L1 fileciteturn58file0L1-L1

The third mismatch is between the **analysis prompt** and the **real source acquisition path**. The analysis crew says the `source_aggregator` agent should find 5–15 sources across the spectrum, but `AnalysisService` preflights sources first through `SourceAggregatorService`, formats them into a “use only these URLs” block, and passes that block into the crew. `SourceAggregatorService` caps extraction at 5, stops as soon as it has any left/right spread, and searches in a one-month news window with up to four query variants generated from the description, title, summary terms, and URL slug. That is good enough for a prototype, but it is nowhere near the hard-targeted source planning you described. fileciteturn75file0L1-L1 fileciteturn71file0L1-L1 fileciteturn59file0L1-L1

Your sample report shows exactly how those mismatches surface in practice. The final Source Matrix contains entity["organization","USA Today","news outlet"], entity["organization","NBC News","news outlet"], entity["organization","Yahoo News","news outlet"], and entity["organization","Associated Press","news outlet"], with three center-ish entries and one slight-left entry, and the report later admits readers are not getting direct right-leaning, libertarian, civil-liberties, or anti-security-state critique from the supplied materials. That is powerful evidence that the source balancing problem is real and upstream. fileciteturn50file1

## Fixes for the active agent findings

### Discovery and RSS-first source balancing

The most important design decision here is to separate **story discovery** from **balanced source gathering**. Right now, `news_aggregator` is doing story discovery with RSS/search tools, while analysis-time source selection is handled by `SourceAggregatorService` plus a web-search-only `source_aggregator` agent. If the user gives you a seed article and expects balanced coverage around that story, that is primarily a **source aggregation problem**, not a discovery problem. Do not solve that only by making `news_aggregator` smarter. Solve it by adding a deterministic **source planning layer** that runs before analysis and explicitly fills missing bias buckets. fileciteturn73file0L1-L1 fileciteturn74file0L1-L1 fileciteturn75file0L1-L1

What needs to be done:

- Create one canonical machine-readable `source_registry` and stop treating markdown as runtime truth.
  - New file: `config/source_registry.yaml` or `config/source_registry.json`.
  - Merge the useful fields now split across `Deep-RSS-Research.md`, `config/rss_feeds.yaml`, and `config/bias_sources.yaml`.
  - Per outlet, store:
    - `name`
    - `domain`
    - `homepage_url`
    - `bias`
    - `bias_label`
    - `category`
    - `factual_rating`
    - `rss_urls`
    - `search_aliases`
    - `syndication_group`
    - `allow_in_analysis`
    - `notes`
  - Generate the human markdown docs from this registry, not the other way around.

- Add a deterministic `BalancedSourcePlanner` service.
  - Input:
    - seed URL
    - seed bias, if known
    - story packet from `story_parser`
    - channel profile preferences
  - Output:
    - required buckets
    - optional buckets
    - domain target lists per bucket
    - search plan
  - Rules:
    - if seed bias is `-3` or `-4`, require:
      - one center or slight-center source
      - one right/lean-right/far-right source
      - optionally one libertarian or independent source
    - if seed bias is `+3` or `+4`, mirror that logic to the left
    - if seed is center or unknown, require at least:
      - one left or lean-left
      - one center
      - one right or lean-right
    - if a user explicitly wants fringe/conspiracy analysis, make that a separate optional bucket, not a substitute for center/left/right coverage

- Extend `RSSAggregator` so category filters actually work with keywords.
  - The current keyword path ignores categories.
  - Add `search_feeds(keywords, categories=None, ...)`.
  - Or add a dedicated `search_feeds_balanced(...)` method that:
    - searches only target buckets first
    - returns results grouped by bucket
    - enforces per-bucket caps before global caps

- Change the retrieval order for source finding.
  - **First:** curated RSS feeds from required buckets.
  - **Second:** site-targeted web search using only curated outlets in missing buckets.
    - Example behavior:
      - `site:wsj.com "headline terms"`
      - `site:foxnews.com "headline terms"`
      - `site:reason.com "headline terms"`
  - **Third:** broader web search only if a required bucket is still empty.

- Stop using generic similarity alone as the primary selector.
  - Add a scoring function that weighs:
    - event similarity
    - bucket need
    - source novelty
    - factuality
    - freshness
    - duplicate penalty
  - A perfectly matched fourth center source should lose to a slightly noisier right source if the right bucket is still empty.

- Keep RSS first, but be realistic.
  - RSS should be the preferred path because your curation is the whole point.
  - But RSS alone will not always be enough for fast-breaking stories or paywalled outlets.
  - So the real principle should be:
    - **RSS-first**
    - **curated-domain hunt second**
    - **open web last**

- Add explicit failure modes.
  - If required buckets are missing after exhausting the curated registry and broad fallback, return a structured warning:
    - `missing_required_buckets`
    - `searched_domains`
    - `why_missing`
  - Do not quietly continue as if you built a balanced evidence set.

My model recommendation for this stage is still **not** “slam everything through `gpt-5.5`.” If you move balancing into deterministic code, `news_aggregator` can stay on `gpt-5.4-mini` or move to `gpt-5.4` only if evals show the mini model is still weak at final ranking. OpenAI explicitly positions `gpt-5.4-mini` for subagents and high-volume support tasks; that is a better fit than using a flagship model to compensate for missing hard rules. citeturn10search1turn3search0turn10search2

Done-when criteria for this point:

- A entity["organization","Jacobin","news outlet"] seed produces a planning target that explicitly requires center plus right-side coverage.
- Bucket-filling happens before open-web fallback.
- The code can prove that bucket filters work in keyword mode.
- Missing buckets are surfaced plainly in structured output.
- Your curated markdown is no longer orphaned from runtime behavior. fileciteturn52file0L1-L1 fileciteturn58file0L1-L1 fileciteturn89file0L1-L1

### Final source count and hard diversity quotas

Your instinct is right: **3–5 good sources with real spectrum spread beats 15 low-value clones**. The problem is that the current code collapses two different ideas into one number: how many results to probe, and how many sources to keep. `SourceAggregatorService` already caps retained sources at 5 and stops once it sees any left/right spread, but that spread test is too weak and too coarse. A single lean-left and a single lean-right hit can satisfy it without ensuring a center anchor, without adding a libertarian/independent angle, and without checking whether the articles are near-duplicates or wire rewrites. fileciteturn59file0L1-L1

What needs to be done:

- Split one configuration into three separate knobs.
  - `probe_limit`: how many candidate URLs to search and extract before giving up
  - `final_min_sources`: minimum retained sources
  - `final_max_sources`: maximum retained sources
  - `required_bucket_policy`: which ideological buckets must be represented

- Replace the current “left + right exists” spread check with explicit coverage rules.
  - Example standard policy for general political stories:
    - at least 1 center or slight-center source
    - at least 1 left/lean-left/far-left source
    - at least 1 right/lean-right/far-right source
    - optional 1 libertarian/independent source
    - optional 1 fringe source only when the topic is about fringe narratives
  - Example seed-aware policy:
    - if seed is far-left, do **not** require another far-left source before center/right are satisfied
    - if seed is right, do the mirror image

- Add quality-aware stopping conditions.
  - Stop early only if:
    - all required buckets are filled
    - total retained sources are between 3 and 5
    - average relevance score exceeds threshold
    - duplicate/syndication check passes

- Add duplicate and syndication detection.
  - Detect:
    - same domain duplicates
    - same wire article republished by aggregators
    - near-duplicate body text
  - Use:
    - canonical URL normalization
    - byline/source-wire markers
    - title similarity
    - text MinHash or shingled similarity
  - This matters because your sample matrix is exactly the kind of thing that can look diverse while actually reflecting a very narrow information base. fileciteturn50file1

- Make the report state the actual evidence quality.
  - If only center and slight-left coverage was found, the report should lead with an “evidence limitations” box.
  - Do not bury that admission halfway down in a framing section.

- Tighten the search window around the event.
  - Current source search uses a month-long news window and can fall back to web search if a query returns fewer than four news hits.
  - That is a recipe for semantically adjacent junk results on recurring public figures or recurring policy topics.
  - Switch from fixed month-wide search to:
    - seed-date inferred window, or
    - user-provided date window, or
    - event-window default like ±7 days unless the story is clearly ongoing. fileciteturn59file0L1-L1

Done-when criteria for this point:

- The system can search 15 candidates but still return only 3–5 sources.
- A final source set is rejected if it lacks a center anchor when the policy requires one.
- Near-duplicates do not crowd out missing ideological buckets.
- The report clearly states when required spread was not met.

### Bias classification and heuristic-first routing

You were dead right on this one: the heuristic list should fire first, and fallback methods should only be used when the source is not already on your curated list. The repo is halfway there already. `LocalBiasDatabase` reads `config/bias_sources.yaml`, and `BiasResolutionService` already does dataset lookup, then AllSides lookup, then LLM, then heuristic fallback. The problem is that the standalone `BiasClassifier.classify()` path still returns `Unknown` after local DB lookup and never calls its own heuristic or LLM methods. That is the inconsistency you need to eliminate. fileciteturn61file0L1-L1 fileciteturn60file0L1-L1 fileciteturn88file0L1-L1

What needs to be done:

- Make **one** source of truth for bias resolution.
  - Either:
    - deprecate the current `BiasClassifier.classify()` fallback path and make the tool call `BiasResolutionService`, or
    - move the fallback logic down into `BiasClassifier.classify()` and make the service a thin wrapper
  - I strongly prefer the first option: one service, one path, one audit trail.

- Use the curated registry as the hard primary answer.
  - If a domain exists in your registry:
    - do not ask the model to guess the bias
    - do not hit AllSides live
    - return the curated value with high confidence and provenance
  - If a domain is not in your registry:
    - try AllSides or a cached source map
    - then LLM inference
    - then a cheap heuristic only as a last resort

- Add a curated-source-only mode for source gathering.
  - If the missing bucket can still plausibly be filled from your registry, the system should **not** jump to unknown outlets.
  - Only spill into unknown domains when:
    - the curated bucket is exhausted, and
    - the story really is unreported by the curated outlets.

- Return more metadata with every classification.
  - `bias`
  - `bias_label`
  - `confidence`
  - `method`
  - `provenance_source`
  - `is_curated`
  - `category`
  - `factual_rating`
  - `bucket_group`
  - `bucket_reason`

- Cache unknown-source resolutions.
  - If the LLM has to infer the bias of a new outlet once, save it for later review rather than paying the model again every time.

- Add manual override workflow.
  - You will eventually disagree with a classification.
  - Build the override path now:
    - manual config edit
    - admin endpoint
    - persisted override flag
    - provenance note

- Add strict tests for the path ordering.
  - known domain -> local registry only
  - unknown but AllSides-known domain -> AllSides path
  - unknown domain with article text -> LLM inference
  - LLM failure -> heuristic fallback
  - no path returning `Unknown` if a downstream fallback was available

Recommended model setting for bias inference, when it is truly needed: `gpt-5.4`, `Low`, temperature `0.1`. This is a classification problem where run-to-run stability matters more than expressive range, and OpenAI’s API docs state plainly that lower temperature makes outputs more focused and deterministic. citeturn10search0turn5search0turn6search0

### Fact extraction, asymmetry, and profile-aware angles

This is where your desired behavior is more nuanced than the current design. Right now the fact extractor is asked to create “agreed facts,” “left-only facts,” and “right-only facts.” That is too crude for the behavior you described. If the right is pounding Fact X and omitting Fact Y, while the left is pounding Fact Y and omitting Fact X, that is **not only a facts problem**. It is an asymmetry-of-coverage problem, which should feed narrative and framing analysis. The current prompt structure does not explicitly model that. fileciteturn71file0L1-L1 fileciteturn62file0L1-L1

What needs to be done:

- Replace loose prose buckets with a structured claim schema.
  - For each claim, store:
    - `claim_id`
    - `normalized_claim`
    - `claim_type`
      - observed fact
      - attributed statement
      - allegation
      - causal inference
      - prediction
      - opinion
    - `entities`
    - `time_scope`
    - `source_ids`
    - `bias_buckets_present`
    - `confidence`
    - `evidence_strength`
    - `coverage_status`
      - cross-sourced
      - side-specific
      - disputed
      - asymmetrically-covered

- Add a distinct `coverage_asymmetry` output.
  - This is the answer to your Fact X / Fact Y / Fact Z problem.
  - Example fields:
    - `right_emphasizes`
    - `left_emphasizes`
    - `center_ignores`
    - `fringe_adds`
    - `likely_framing_implication`
  - These should flow into `narrative_analyzer`, not get jammed awkwardly into “right-only facts.”

- Add explicit “attributed-but-unproven” handling.
  - A charge, affidavit, or official allegation should never be flattened into a verified fact.
  - The sample report actually did a decent job with this in places; formalize it so the system does it every time. fileciteturn50file1

- Add claim clustering before judgment.
  - Different outlets will phrase the same proposition differently.
  - Do semantic clustering first, then decide whether two claims are actually the same fact, different layers of the same event, or unrelated noise.

- Use the channel profile only in a downstream layer.
  - Your end-user bias document should influence:
    - what questions are highlighted for the creator
    - what likely audience angles are proposed
    - which omissions get called out as especially relevant to that audience
  - It should **not** influence:
    - whether a claim is treated as factual
    - how bias is classified
    - whether corroboration exists
  - Evidence layer must stay neutral; creator-angle layer can be audience-aware.

- Feed output into narrative analysis.
  - This is the exact junction where `narrative_analyzer` belongs:
    - fact patterns
    - omission patterns
    - side-specific emphases
    - profile-aware creator angles

- Add fixtures based on the scenarios you described.
  - Case A:
    - right emphasizes Fact X
    - left emphasizes Fact Y
    - both acknowledge the event
  - Case B:
    - conspiracy source lightly covers X and Y but strongly centers Z
  - Case C:
    - one side reports an allegation as allegation
    - the other side reports it as implied fact
  - Case D:
    - center outlet omits a contested but newsworthy side-specific fact

Recommended model setting: `gpt-5.5`, `High`, temperature `0.1`. This is the stage where ambiguity handling and disciplined classification matter most, and OpenAI’s current model guide places `gpt-5.5` at the top of the stack for complex reasoning and knowledge work. citeturn10search2turn7search1turn4search2turn5search0

### Rhetorical analysis and hard-case coverage

This agent should absolutely get a top model with high thinking, but I do **not** recommend a middling or high-ish temperature here. This job is interpretive, yes, but it is still a **precision labeling** job. Higher temperature is exactly how you get over-eager “everything is a dog whistle” nonsense. OpenAI’s API reference says lower temperature produces more focused, deterministic outputs, and the classic decoding literature shows that sampling strategy changes text diversity and degeneration behavior materially. For rhetoric detection, that means you want controlled reasoning, not creative drift. fileciteturn77file0L1-L1 citeturn5search0turn6search0

What needs to be done:

- Expand the rubric beyond the current compact list.
  - Keep the existing categories, but add:
    - selective quantification / denominator omission
    - causal laundering
    - attribution laundering
    - euphemism vs dysphemism
    - passive-voice agency concealment
    - definitional retreat / motte-and-bailey
    - base-rate neglect
    - false balance
    - selective sourcing imbalance
    - headline/body tension
    - adversarial labeling
    - emotional anchoring
    - procedural framing
    - demonization-by-association
    - certainty inflation

- Require two-context evidence for coded-language calls.
  - For any suspected dog whistle or coded signal, require:
    - the local quote/snippet
    - a short surrounding-context snippet
  - If both do not support the call, downgrade to `possible signal`.

- Distinguish outlet voice from quoted voice.
  - A source quoting a politician using loaded language is not the same as the source endorsing that language.
  - The prompt should force this distinction.

- Add negative controls to the eval set.
  - This matters a lot.
  - The model should learn not just what to flag, but what **not** to flag.

- Build a hard-case eval pack.
  - Here is a very practical starter set for your coding agent to encode as fixtures:

| Hard case | Why it is hard | Expected handling |
|---|---|---|
| “Officials said the bill would ‘protect democracy’” | Could be mere attribution, could be frame adoption | Label as attributed framing unless outlet voice endorses it |
| “Parents’ rights” | Literal policy phrase or coded coalition signal | Require surrounding context before coded-language label |
| “Election integrity” | Can be neutral administration language or loaded suspicion frame | Context-gated, never keyword-only |
| “Globalist interests” | Sometimes literal geopolitics, sometimes antisemitic-coded rhetoric | Require high threshold and note ambiguity explicitly |
| “Public safety measure” | Could be neutral or euphemistic rights restriction | Look for omitted tradeoffs and agency |
| “Migrant crime wave” | Possible loaded framing through quantifier inflation | Check denominator/base-rate context |
| “Anti-racist reforms” | Could be descriptive or ideologically signaled | Do not pathologize by keyword alone |
| “Deep state actors” | Possible conspiratorial shorthand, but sometimes used descriptively by source audiences | Flag as viewpoint-signaling term with low/medium confidence unless strongly contextualized |
| “Insurrectionist movement” | Legal-description drift versus rhetorical escalation | Distinguish adjudicated facts from moral shorthand |
| “Gender-affirming care for minors” | Literal policy label or euphemistic framing depending context | Require evidence of framing choice, not term alone |

- Expand the logic-fallacy inventory.
  - Keep the repo’s current fallacy list, and add:
    - guilt by association
    - poisoning the well
    - appeal to fear
    - hasty generalization
    - composition/division
    - moving the goalposts
    - appeal to authority without warrant
    - anecdotal overreach
    - suppressed evidence
    - non-sequitur

- Add symmetry tests.
  - The repo’s rubric already says “apply symmetry checks across ideological directions.”
  - Make that real in test fixtures.
  - If you only train the model on right-coded examples, you will get a partisan detector pretending to be a rhetoric analyzer. fileciteturn77file0L1-L1

Recommended model setting here: `gpt-5.5`, `High`, temperature `0.2`. That is low enough to reduce overcalling while still allowing some flexibility in multi-snippet interpretation. citeturn10search2turn7search1turn5search0turn6search0

### Final report generation, rendering, and validation

The current report writer is being asked to do too much. It is writing the narrative, rendering the Source Matrix, constructing footnotes, and trying not to violate the validator—all in one free-text shot. Your uploaded sample shows that the structure can come out serviceable, but it also shows the limits of this approach: the narrative sections can sound more confident and more profile-tailored than the source base actually warrants, because the prompt forces those sections to exist whether or not the evidence base is broad enough. fileciteturn71file0L1-L1 fileciteturn76file0L1-L1 fileciteturn50file1

What needs to be done:

- Split report generation into **analysis JSON** and **deterministic rendering**.
  - The model should output structured sections referencing `source_id`s or `url`s already in the database.
  - A Python renderer should build:
    - the Source Matrix table
    - the footnote block
    - link formatting
    - ordered section headings
  - This instantly reduces URL hallucinations and markdown-formatting drift.

- Stop making the model invent the Source Matrix.
  - The matrix should come straight from persisted `Source` rows and resolved bias metadata.
  - The model can still write the “Key Framing / Claim” summaries if you want, but the row structure should be deterministic.

- Add an explicit Evidence Limits section near the top.
  - If required ideological buckets are missing, say so immediately.
  - Do not hide the limitation in “Framing & Context Omissions.”
  - The sample report did identify the problem, but too late and too softly. fileciteturn50file1

- Separate evidence-derived narrative from creator-tailored angle.
  - Keep:
    - `Mainstream narrative`
    - `Alternative takes`
    - `Libertarian perspective angle`
  - But split them into:
    - `Evidence-derived narrative patterns`
    - `Profile-aware creator angles`
  - This matters because your sample report proposes a libertarian angle even though the actual source base was mostly center/slight-left. That is fine as creator guidance, but it should not be mistaken for sourced narrative analysis. fileciteturn70file0L1-L1 fileciteturn50file1

- Add stronger validator rules.
  - Keep the current source/footnote whitelist validation.
  - Add new checks for:
    - missing evidence-limit banner when bucket policy failed
    - orphaned citations
    - sections that cite no sources despite factual assertions
    - narrative claims not traceable to source IDs or upstream narrative-analyzer output

- Add provenance tags in the internal representation.
  - Each report statement should be one of:
    - evidence-derived
    - attributed allegation
    - rhetoric analysis
    - creator-angle suggestion
  - That lets the renderer label sections more honestly.

- Upgrade the model here.
  - Because you said no specific latency/cost constraint should be assumed, I would now move `report_writer` to `gpt-5.5`, `High`, temperature `0.2` or `0.3`.
  - If you keep deterministic rendering and lower temperature, the extra reasoning budget helps with coherence and instruction-following more than it harms precision. citeturn10search2turn7search1turn4search2turn5search0

Done-when criteria for this point:

- The model never emits a raw URL that the renderer did not supply.
- The Source Matrix is generated deterministically from source records.
- Missing ideological spread appears as an upfront limitation banner.
- “Creator angle” sections are visibly distinct from evidence-derived sections.
- The validator becomes a guardrail, not the first time anyone notices the report cheated.

## Fixes for the gaps and unfinished architecture

### Documentation and config drift

You need to stop maintaining parallel truths. The repo currently has agent-role definitions, active crew wiring, per-agent config APIs, machine-readable source configs, and large human-readable markdown source lists. That is maintainable only if one source of truth generates the rest. Otherwise your coding agent will be debugging drift forever. fileciteturn67file0L1-L1 fileciteturn68file0L1-L1 fileciteturn69file0L1-L1 fileciteturn79file0L1-L1 fileciteturn87file0L1-L1

What needs to be done:

- Make `source_registry.yaml` the source of truth for outlets.
- Generate:
  - `Deep-RSS-Research.md`
  - bias-source docs
  - operator/admin views
  - maybe even test fixtures
  from the registry.

- Add an architecture doc that distinguishes:
  - active runtime agents
  - configured but dormant agents
  - deterministic services
  - database-backed state

- Update README and step-by-step docs to describe:
  - per-agent model config already exists
  - source preflight happens before analysis
  - report validation is whitelist-based
  - root markdown lists are not runtime input unless transformed

- Add CI checks that fail when:
  - generated docs are out of date
  - registry and YAML bias/feed maps disagree
  - AGENT_ROLES and exported factories drift

### Prompt and runtime contract mismatch

Your prompts and services should stop contradicting each other. The clean fix is to define explicit contracts and use those words everywhere in code, prompts, tests, and docs. Right now “5–15 sources” in the task prompt, “MAX_SOURCES = 5” in the service, and “use only prefetched URLs” in analysis create a fuzzy system where everyone thinks someone else is responsible. fileciteturn71file0L1-L1 fileciteturn59file0L1-L1 fileciteturn75file0L1-L1

What needs to be done:

- Introduce explicit config names:
  - `candidate_probe_limit`
  - `retained_source_min`
  - `retained_source_max`
  - `required_buckets`
  - `strict_bucket_enforcement`
  - `search_time_window_days`

- Rewrite prompts to match services exactly.
  - Example:
    - “Probe up to 15 candidates.”
    - “Retain 3–5 final sources.”
    - “Required buckets: center + left + right.”
    - “If prefetched sources are supplied, do not add more URLs.”

- Return structured status from preflight:
  - `coverage_satisfied`
  - `missing_buckets`
  - `probed_count`
  - `retained_count`
  - `duplicate_count`
  - `broad_fallback_used`

- Fail or warn based on configurable policy, not vague prose.

### Unifying the bias path

This one is simple conceptually and important operationally: you need a single bias-resolution path everywhere. The repo already has the good path in `BiasResolutionService`; wire everything to that and stop letting the tool path lag behind it. fileciteturn60file0L1-L1 fileciteturn61file0L1-L1

What needs to be done:

- Route all classification through `BiasResolutionService`.
- Make `BiasClassifierTool` call the service, not the raw local DB helper.
- Log the method used for every source:
  - curated
  - AllSides
  - LLM
  - heuristic
- Persist provenance in `Source` rows.
- Add override support and caching.
- Add tests proving that known domains do not invoke the model.

### Activating the unfinished agents correctly

This is where the repo is actually well positioned. The current database model already has a `ChannelProfile` table, a `Story` model with `keywords` and `relevance_score`, and an `Analysis` model with fields for `mainstream_narrative`, `alternative_takes`, `libertarian_angle`, and `opinions_by_side`. In other words, the storage layer already tells you what these unfinished agents were probably meant to do. fileciteturn70file0L1-L1

#### Profile reader

You said the long-term design is per-user upload and saved outlet/channel documents. That direction is correct, and the existing profile loader is already flexible enough to parse YAML, JSON, markdown, and text into structured channel scope with worldview, topics, topic keywords, preferred sources, exclusions, and content-style hints. fileciteturn78file0L1-L1 fileciteturn65file0L1-L1

What needs to be done:

- Do not run the profile-reader agent on every analysis request.
- Run it at **upload time** or **profile update time**.
- Extend `ChannelProfile` with:
  - `owner_user_id`
  - `raw_content`
  - `format`
  - `parsed_json`
  - `version`
  - `is_active`
- Save both raw and normalized profile representations.
- Use deterministic parsing first.
- Only use the model if the upload is messy enough that rule-based parsing leaves fields incomplete.
- Downstream agents should consume the normalized profile object, not the raw file path.

Recommended model:
- `gpt-5.4-mini`, `Low`, temperature `0.2`
- only for normalization of unstructured uploads

#### Relevance scorer

This agent should absolutely exist, and it should sit between discovery and final story selection. The `Story` table already has a `relevance_score` field waiting for it. Your example about a crypto-insider-trading headline pulling unrelated stock-buyback coverage is exactly the kind of drift that happens when search terms are broad and event parsing is weak. `SourceAggregatorService` currently builds a small set of generic queries and uses a month-wide search window, which is part of why this stage matters. fileciteturn70file0L1-L1 fileciteturn59file0L1-L1 fileciteturn66file0L1-L1

What needs to be done:

- Put `relevance_scorer` after discovery and after story parsing.
- Score candidate stories on:
  - entity overlap
  - event/action overlap
  - time overlap
  - place overlap
  - topic/profile match
  - novelty
  - likely audience fit
- Add explicit rejection reasons:
  - same person, wrong event
  - same topic, wrong time
  - stale recurrence
  - adjacent but not same story
- Make it a hybrid stage:
  - deterministic features first
  - small model for tie-breaking or ambiguous cases

Recommended model:
- `gpt-5.4-mini`, `Low`, temperature `0.1`

#### Story parser

The repo’s own config says `story_parser` should “extract and clarify the core details of a news story” and turn vague input into clear, searchable terms. That is exactly what your pipeline is missing. This agent should be first in the analysis path after the profile is loaded and before relevant source search begins. fileciteturn67file0L1-L1

What needs to be done:

- Implement `story_parser` as a real stage before `source_aggregator`.
- Input:
  - story description
  - optional seed URL
  - optional RSS fallback metadata
- Output:
  - canonical headline
  - actor/entity list
  - action/event verbs
  - location
  - date/time window
  - aliases and alternate names
  - must-have terms
  - must-not-have terms
  - query pack
  - disambiguation notes
- Save the output to:
  - `Story.keywords`
  - maybe a new structured story metadata column
- Feed the output into:
  - relevance scorer
  - balanced source planner
  - source aggregator service

Recommended model:
- `gpt-5.4`, `Medium`, temperature `0.2`

#### Narrative analyzer

This agent should be added between rhetorical analysis and report writing. Right now the report writer is being asked to generate mainstream narrative, alternative takes, and libertarian perspective angle directly. That works poorly when the evidence set is thin. The `Analysis` table already has the right fields, so this is a natural stage to implement rather than a speculative addition. fileciteturn70file0L1-L1 fileciteturn67file0L1-L1 fileciteturn71file0L1-L1

What needs to be done:

- Add `narrative_analyzer` after:
  - fact extractor
  - rhetorical analyst
  - source/bias context
- Have it output structured fields:
  - mainstream narrative
  - alternative narrative
  - profile-aware creator angles
  - omission patterns by side
  - headline-level framing differences
  - source-specific opinion clusters
- Feed those structured fields into the database and report renderer.
- Require that narrative claims reference:
  - source IDs
  - or fact/rhetoric findings
- Do not let it hallucinate a narrative from missing ideology buckets.

Recommended model:
- `gpt-5.5`, `High`, temperature `0.4`

That `0.4` is the one place where I agree with your instinct for a middle-ish temperature. Narrative synthesis is still evidence-bound, but it benefits from slightly more flexibility than strict fact extraction or rhetoric labeling. OpenAI’s API guidance says higher temperature increases randomness while lower temperature is more deterministic, so `0.4` is a reasonable compromise for profile-aware synthesis that still needs grounding. citeturn5search0turn6search0

## Recommended target workflow and implementation roadmap

A cleaned-up version of your intended architecture should look like this:

```mermaid
flowchart LR
    A[Profile upload] --> B[profile_reader normalize and persist]
    B --> C[discovery using profile topics]
    C --> D[relevance_scorer filter candidate stories]
    D --> E[story_parser canonicalize selected story]
    E --> F[balanced_source_planner build bucket targets]
    F --> G[RSS-first curated retrieval]
    G --> H[curated-domain web fallback]
    H --> I[source_aggregator_service preflight and dedupe]
    I --> J[bias_resolution_service unified path]
    J --> K[fact_extractor structured claims]
    K --> L[rhetorical_analyst structured findings]
    L --> M[narrative_analyzer evidence-derived narratives plus creator angles]
    M --> N[report_writer structured section content]
    N --> O[deterministic markdown renderer]
    O --> P[report_validator]
```

If I were handing this to a coding agent, I would prioritize it like this:

| Priority | Work item | Main files to touch | Why it is first | Done when |
|---|---|---|---|---|
| P0 | Create canonical source registry | new `config/source_registry.yaml`, `rss_feeds.yaml`, `bias_sources.yaml`, optional generator script | Fixes the documentation/runtime split | One registry drives runtime + docs |
| P0 | Add balanced source planner and hard bucket policy | new service + `source_aggregator_service.py` + `rss_aggregator.py` | Solves the actual cross-spectrum failure | Seed-aware quotas pass evals |
| P0 | Unify bias resolution | `bias_classifier.py`, `bias_resolution_service.py` | Removes inconsistent fallback behavior | All paths use one resolver |
| P0 | Deterministic report rendering | `analysis_service.py`, report renderer module, `report_validator.py` | Prevents source/citation drift | Matrix and footnotes are code-rendered |
| P1 | Implement story parser | new agent/service + `analysis_crew.py` | Fixes query drift and event disambiguation | Canonical story packet exists |
| P1 | Implement relevance scorer | new task/stage + `Story.relevance_score` persistence | Fixes stale/adjacent result pollution | Wrong-event stories are rejected |
| P1 | Implement narrative analyzer | new agent/task + `Analysis` fields | Separates narrative synthesis from final writing | Narrative fields stored before rendering |
| P1 | Make profile upload truly per-user | DB migration + upload endpoints + `channel_profile_loader.py` integration | Matches your real product direction | Active profile is user-scoped |
| P2 | Expand rhetoric eval suite | `analysis_rubric.py`, new tests/fixtures | Improves precision and symmetry | Hard-case eval pack tracked in CI |
| P2 | Add duplicate/syndication detection | source services + tests | Avoids fake diversity | Wire rewrites no longer crowd out buckets |

Recommended model settings for the target workflow are:

| Component | Model | Thinking | Temperature | Why |
|---|---|---:|---:|---|
| `profile_reader` | `gpt-5.4-mini` | Low | 0.2 | Parsing and normalization, mostly bounded |
| `news_aggregator` | `gpt-5.4-mini` initially, `gpt-5.4` if evals require | Low | 0.3 | Discovery is support work once balancing is moved into code |
| `relevance_scorer` | `gpt-5.4-mini` | Low | 0.1 | Stable ranking and rejection behavior |
| `story_parser` | `gpt-5.4` | Medium | 0.2 | Ambiguity resolution and query construction |
| `source_aggregator` | `gpt-5.4` | Medium | 0.2 | Tool-heavy, search-aware, but should be policy-constrained |
| `bias_classifier` | `gpt-5.4` | Low | 0.1 | Stable classification; low randomness |
| `fact_extractor` | `gpt-5.5` | High | 0.1 | Highest truth-discipline requirement |
| `rhetorical_analyst` | `gpt-5.5` | High | 0.2 | Difficult interpretive labeling with high false-positive cost |
| `narrative_analyzer` | `gpt-5.5` | High | 0.4 | Profile-aware synthesis still grounded in evidence |
| `report_writer` | `gpt-5.5` | High | 0.2 to 0.3 | Final user-facing synthesis, but should write from structured inputs |

For the coding agent that will implement this backlog, I would use `gpt-5.3-codex` or `gpt-5.5` to review and refactor the repository, but I would **not** use `gpt-5.3-codex` as a runtime replacement for your analysis agents. OpenAI positions `GPT-5.3-Codex` as the most capable agentic coding model, which is ideal for repo surgery; your runtime pipeline, by contrast, is mostly evidence gathering and analytical synthesis. citeturn9search0turn9search2turn10search2turn7search1

The shortest honest summary is this: the repo is much closer than it looks, but the logic that should be hard policy is currently scattered across prompts, partial configs, and service defaults. Fix the registry, fix bucket enforcement, add story parsing and relevance scoring, make narrative analysis explicit, and stop asking the final writer to improvise structure that code should own. If you do those things, the rest of the system will get dramatically better without needing magical prompt tricks.