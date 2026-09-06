# Deep Research Prompt: Hotspot Scoring Formula Multi-Dimensional Fusion Strategy

## Research Question

**Core Problem**: How to design a parent node scoring formula that balances three conflicting dimensions:
- **Coverage Ratio** (dual_hot / total): Penalize irrelevant children
- **Quality** (avg similarity of dual_hot children): Select high-quality nodes
- **Support Count** (absolute dual_hot count): Break perfect coverage advantage

**Conflict Scenario**:
```
Phase 14 Document:
  Parent A: 2 children, 2 dual_hot, coverage=1.0 (perfect), quality=0.53 (low)
  Parent B: 7 children, 5 dual_hot, coverage=0.71 (medium), quality=0.57 (high)

Expected: Select Parent B (more hits)
Actual Results:
  - Linear Addition: Parent A wins (coverage=1.0 dominates)
  - Simple Average: Parent A wins (no irrelevant children penalty)
  - Multiplication: Parent B wins, but fails other scenarios (33.3% accuracy)
```

**Fundamental Contradiction**:
- Phase 14: Support count > Coverage penalty (Parent B should win)
- Extreme Case: Coverage penalty > Support count (Parent C: 95% irrelevant → severe penalty)
- High Quality Low Coverage: Non-linear balance needed

## Research Directions

### 1. Information Retrieval & Hotspot Selection

**Keywords to Search**:
- "hotspot selection scoring formula"
- "parent node ranking tree indexing"
- "multi-dimensional relevance scoring"
- "coverage quality support fusion"

**Specific Questions**:
- How do search engines handle "perfect coverage vs better quality" trade-offs?
- How do tree-based indexes score parent nodes with partial child matches?
- What formulas balance precision (quality) and recall (coverage)?

**Expected References**:
- Elasticsearch/Lucene parent-child scoring
- Solr nested document ranking
- MongoDB nested array filtering
- Tree-based retrieval systems (Hierarchical Indexing)

### 2. Recommender Systems Multi-Objective Optimization

**Keywords to Search**:
- "multi-objective ranking precision coverage diversity"
- "relevance scoring formula trade-offs"
- "weighted harmonic mean vs geometric mean"
- "recommendation system fusion strategies"

**Specific Questions**:
- How do recommender systems balance precision × coverage × novelty?
- What fusion strategies exist beyond linear addition and multiplication?
- How does harmonic mean vs geometric mean vs arithmetic mean perform?

**Expected References**:
- Multi-objective optimization in recommendations
- Diversity-aware ranking algorithms
- Trade-off curves (Pareto frontier) in scoring functions

### 3. Open-Source Projects Parent Node Scoring

**Keywords to Search**:
- "github parent node scoring tree indexing"
- "hierarchical document retrieval scoring"
- "tree traversal hotspot selection code"
- "parent-child aggregation ranking"

**Specific Questions**:
- How does LlamaIndex tree indexing score parent nodes?
- How does Elasticsearch nested query scoring work?
- How does Neo4j graph traversal rank parent nodes?

**Expected Projects to Check**:
- LlamaIndex (tree indexing, parent-child retrieval)
- Elasticsearch (nested document scoring)
- Neo4j (graph hotspot selection)
- Weaviate (tree-based vector index)
- Pinecone (hierarchical index scoring)

### 4. Mathematical Fusion Strategies

**Keywords to Search**:
- "multi-dimensional scoring fusion mathematical methods"
- "harmonic mean geometric mean arithmetic mean comparison"
- "non-linear fusion formula design"
- "weighted product vs weighted sum"

**Specific Questions**:
- When does harmonic mean outperform arithmetic mean?
- How does geometric mean balance three conflicting factors?
- Are there hybrid formulas (sum + product, weighted harmonic)?

**Expected Methods**:
- Weighted Harmonic Mean: 1 / Σ(w_i / x_i)
- Weighted Geometric Mean: Π(x_i^w_i)
- Hybrid Fusion: α * (linear sum) + β * (product)
- Normalized Product: (x1 * x2 * x3) / (max(x1) * max(x2) * max(x3))

## Research Strategy

### Phase 1: Keyword Search on GitHub

**Search Queries**:
```
gh search code "parent coverage scoring" --language python
gh search code "hotspot selection formula" --language python
gh search code "multi-dimensional ranking" --language python
gh search repos "hierarchical document retrieval"
gh search repos "tree indexing hotspot"
```

### Phase 2: Deep Research with Context7/Exa

**Prompt for Deep Research Tool**:
```
Research how information retrieval systems handle multi-dimensional parent node scoring with three conflicting factors:
1. Coverage ratio (how many children match)
2. Quality (average similarity of matching children)
3. Support count (absolute number of matching children)

Specific problem: Parent A has perfect coverage (2/2 children match) but low quality (0.53). Parent B has partial coverage (5/7 children match) but better quality (0.57). How do mature systems select the better parent?

Focus on:
- Elasticsearch nested document scoring
- LlamaIndex tree indexing hotspot selection
- Recommender system multi-objective ranking (precision × coverage × diversity)
- Mathematical fusion strategies (harmonic mean, geometric mean, hybrid formulas)

Expected: Find concrete formulas, code examples, or academic papers explaining the trade-offs.
```

### Phase 3: Academic Literature Search

**Keywords for Google Scholar/arXiv**:
- "hierarchical retrieval scoring trade-offs"
- "parent-child ranking formula information retrieval"
- "multi-objective document ranking"
- "coverage quality diversity fusion"

### Phase 4: Practical Code Analysis

**Projects to Analyze**:
- LlamaIndex: `llama_index.indices.tree.scoring` (parent node selection)
- Elasticsearch: `NestedQueryBuilder` scoring logic
- Neo4j: graph traversal hotspot ranking
- Weaviate: hierarchical vector index scoring

## Expected Output

**Goal**: Find at least one mature solution that:
1. Handles "perfect coverage vs better quality" trade-off correctly
2. Provides a mathematical formula with rationale
3. Has been validated in production systems
4. Can be adapted to Phase 14 scenario

**Alternative**: Confirm Phase 14 is a special case requiring custom tuning (not a general problem)

## Success Criteria

- [ ] Find ≥3 concrete examples of parent node scoring formulas
- [ ] Identify ≥1 mathematical fusion strategy beyond linear/multiplication
- [ ] Discover ≥1 academic paper explaining coverage vs quality trade-offs
- [ ] Extract ≥1 code snippet from mature open-source project
- [ ] Propose a formula that solves Phase 14 + other scenarios

## Constraints

- Focus on practical implementations (not theoretical only)
- Prefer Python/Java examples (accessible code)
- Limit to information retrieval domain (avoid unrelated fields)
- Prioritize formulas validated in production systems

## Next Steps After Research

1. Document findings in `.planning/research/hotspot-scoring-formula-research.md`
2. Compare discovered formulas with current approach (linear addition)
3. Select best candidate formula for Phase 14
4. Validate against 3 test scenarios (Phase 14, extreme case, high-quality-low-coverage)
5. Update task status with research results

---

**Usage**: Copy this entire prompt into your Deep Research tool or use it as a guide for manual GitHub/code search.