# Ensemble Matching Strategy: XBRL-Level vs Label-Based

## Context
After implementing semantic dimension matching to fix TSLA automotive alignment (see `2025-09-tsla-automotive-alignment.md`), we achieved partial success:
- **Before**: Row "Automotive sales" had only 2 periods (2025/2024)
- **After**: Same row now has 4 periods (2025/2024/2023/2022)
- **Remaining issue**: 2021 data still misaligned, plus other rows with partial coverage

This raises a fundamental question: **Are we attacking the ensemble problem from the wrong angle?**

## Current Approach: XBRL-Level Matching

### Strategy
Match rows across filings based on XBRL semantics:
1. Exact concept match (`us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`)
2. Normalized concept match (strip namespace, lowercase)
3. Dimension signature equality (strict)
4. Dimension signature semantic compatibility (parent-child via hierarchy)
5. Label match (as tie-breaker)
6. Depth and parent path checks

### Pros
- **Theoretically correct**: Matches based on actual XBRL meaning
- **Leverages structured data**: Uses taxonomy relationships
- **Fast when stable**: Exact concept matches are O(1)
- **Semantically sound**: Parent-child dimension relationships are "real"

### Cons (Experienced with TSLA)
- **Concepts change frequently**:
  - 2024: `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`
  - 2022: `ns0:AutomotiveSalesRevenue`
  - 2021: Yet another variant
- **Presentation structures drift**: Same concept at different depths (3 vs 2)
- **Dimensions evolve unpredictably**:
  - 2024: `automotivesalesmember` (granular)
  - 2023: `automotiverevenuesmember` (parent)
  - 2021: Potentially different axis entirely
- **Multiple hierarchies conflict**: A member can have multiple parents in different contexts
- **Fighting the source of truth**: Trying to reverse-engineer what the company intended rather than what they presented

### Real-World Example (TSLA)
```
2024 Filing - "Automotive sales"
  Concept: us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax
  Depth: 3
  Dimension: (productorserviceaxis, automotivesalesmember)

2022 Filing - "Automotive sales"
  Concept: ns0:AutomotiveSalesRevenue  ← DIFFERENT
  Depth: 2  ← DIFFERENT
  Dimension: (productorserviceaxis, automotiverevenuesmember)  ← PARENT MEMBER

2021 Filing - "Automotive sales"
  Concept: ??? (likely another variant)
  Depth: ??? (likely different)
  Dimension: ??? (potentially different axis)
```

Current matching logic rejects these as different rows, creating misalignment.

## Alternative Approach: Label-Based Matching

### Core Insight
**When a human analyst reviews filings, they match rows by:**
1. **What the label says** ("Automotive sales")
2. **Where it appears** (under "Revenues", at depth 3)
3. **What the values look like** (similar magnitude, patterns)

**They do NOT:**
- Check XBRL concept QNames
- Parse dimension member relationships
- Validate taxonomy hierarchies

### Strategy
Match rows primarily on human-readable attributes:

```python
def calculate_match_score(anchor_row, candidate_row):
    score = 0

    # Label match - HIGHEST WEIGHT
    if normalize_label(anchor.label) == normalize_label(candidate.label):
        score += 100  # Exact match
    elif fuzzy_similarity(anchor.label, candidate.label) > 0.9:
        score += 80   # Very similar (typos, formatting)
    elif fuzzy_similarity(anchor.label, candidate.label) > 0.7:
        score += 50   # Somewhat similar

    # Structural position - SECONDARY
    if anchor.depth == candidate.depth:
        score += 20
    if normalize_label(anchor.parent_label) == normalize_label(candidate.parent_label):
        score += 30   # Same parent context

    # Abstract/concrete must match - REQUIREMENT
    if anchor.is_abstract != candidate.is_abstract:
        return 0  # Cannot match abstract with concrete
    else:
        score += 10

    # Dimension similarity - BONUS, NOT BLOCKER
    if dimensions_compatible(anchor.dimension_signature, candidate.dimension_signature):
        score += 20  # Helpful confirmation, but not required

    # Value pattern similarity - VALIDATION
    if values_similar(anchor.cells, candidate.cells):
        score += 15  # Similar magnitude/trend

    return score

# Match if score exceeds threshold
MATCH_THRESHOLD = 100  # Requires at least exact label match + some structure
```

### Matching Tiers

**Tier 1: High Confidence (score >= 150)**
- Exact label match
- Same depth
- Same parent label
- Dimensions compatible
- Result: Auto-merge, no warning

**Tier 2: Medium Confidence (score >= 100)**
- Exact label match
- Similar structure (depth ±1)
- Result: Merge with info log

**Tier 3: Low Confidence (score >= 80)**
- Fuzzy label match
- Different structure
- Result: Merge with warning, require user review

**Below threshold (score < 80)**
- Result: Create separate row (potential duplicate or genuinely different)

### Pros
- **Robust to taxonomy drift**: Labels change less frequently than concepts
- **Intuitive**: Matches how humans read filings
- **Flexible**: Can tune thresholds and weights based on validation
- **Graceful degradation**: Returns confidence scores, not binary yes/no
- **Aligns with presentation-first philosophy**: Already prioritizing human-readable presentation

### Cons
- **Less "pure"**: Not using XBRL semantics as intended
- **Potential false positives**: "Total revenues" might match across different contexts
- **Requires tuning**: Need to validate thresholds across multiple companies
- **More complex**: Multi-factor scoring vs binary checks

### Example: TSLA with Label-Based Matching

```
Anchor: "Automotive sales" | depth=3 | parent="Revenues" | abstract=False
Candidate (2022): "Automotive sales" | depth=2 | parent="Revenues" | abstract=False

Score calculation:
  Label exact match: +100
  Depth mismatch (3≠2): +0
  Parent match: +30
  Both concrete: +10
  Dimensions (parent-child): +20
  Total: 160 → HIGH CONFIDENCE MATCH ✓

Anchor: "Automotive sales" | depth=3 | parent="Revenues"
Candidate (2022): "Automotive Sales Revenue" | depth=2 | parent="Total Revenues"

Score calculation:
  Fuzzy label (0.92): +80
  Depth mismatch: +0
  Parent fuzzy (0.88): +25
  Both concrete: +10
  Total: 115 → MEDIUM CONFIDENCE MATCH ⚠
```

## Hybrid Approach: Best of Both Worlds

### Recommendation
Use **layered matching strategy** with fallbacks:

```python
def rows_match(anchor, candidate, hierarchy=None):
    # Layer 1: Strict XBRL matching (fast, works for stable taxonomies)
    if exact_concept_match(anchor, candidate):
        if dimensions_match_or_compatible(anchor, candidate, hierarchy):
            return MatchResult(matched=True, confidence="high", method="xbrl")

    # Layer 2: Structural + label matching (handles minor taxonomy changes)
    if normalized_concept_match(anchor, candidate):
        if label_match(anchor, candidate):
            if dimensions_compatible_or_absent(anchor, candidate, hierarchy):
                return MatchResult(matched=True, confidence="high", method="hybrid")

    # Layer 3: Label-based matching (handles major taxonomy drift)
    score = calculate_label_based_score(anchor, candidate)
    if score >= HIGH_CONFIDENCE_THRESHOLD:
        logger.info(f"Label-based match: {anchor.label} (score={score})")
        return MatchResult(matched=True, confidence="high", method="label")
    elif score >= MEDIUM_CONFIDENCE_THRESHOLD:
        logger.warning(f"Fuzzy label match: {anchor.label} (score={score})")
        return MatchResult(matched=True, confidence="medium", method="label")

    # No match
    return MatchResult(matched=False, confidence="none", method=None)
```

### Implementation Phases

**Phase 1: Quick Win (1-2 hours)**
Add label-based fuzzy matching as final fallback in current `_rows_match()`:
```python
# After all existing checks fail...
if anchor.label and candidate.label:
    if fuzzy_match(anchor.label, candidate.label) > 0.9:
        logger.info(f"Fuzzy label match: {anchor.label} ≈ {candidate.label}")
        return True
```

**Phase 2: Scored Matching (4-6 hours)**
Refactor `_rows_match()` to return confidence scores instead of boolean:
- Integrate multi-factor scoring
- Return `MatchResult` with confidence level
- Log match method for analysis

**Phase 3: Excel-Level Ensemble (2-3 days)**
More radical refactor - move ensemble logic to Excel level:
```python
# Old approach (current):
parse_filing(filing_a) → XBRL rows → match_rows() → merge → Excel

# New approach:
parse_filing(filing_a) → Excel_A
parse_filing(filing_b) → Excel_B
match_excel_rows(Excel_A, Excel_B) → merged_Excel
```

Benefits:
- Complete independence from XBRL matching
- Can apply business rules (e.g., "always merge rows with exact label match under same parent")
- Easier to validate (compare Excel files, not XBRL structures)
- More maintainable (fewer XBRL edge cases)

## Key Principles Going Forward

1. **Labels are more stable than concepts** - Prioritize what investors see
2. **Structure matters more than semantics** - "Automotive sales" under "Revenues" ≠ "Automotive sales" under "Cost of revenues"
3. **Dimensions as hints, not gates** - Use to confirm, not to block
4. **Confidence over certainty** - Return scores, let caller decide threshold
5. **Presentation-first consistency** - Ensemble should follow same philosophy as single-filing parser

## Validation Strategy

### Metrics to Track
For each matched row pair, record:
- Match method used (xbrl/hybrid/label)
- Match confidence score
- Label similarity
- Concept similarity
- Dimension compatibility
- Value correlation

### Test Cases
Build validation suite with known-good ensembles:
1. **TSLA 5-year**: Current problem case
2. **AAPL 3-year**: Different company, validate generalization
3. **Stable taxonomy case**: Company with consistent XBRL (should still work)
4. **Restatement case**: Company that restated historical periods (challenging)

### Success Criteria
- **Coverage**: >95% of rows match across filings when human would match them
- **Precision**: <5% false positives (incorrect matches)
- **Transparency**: Clear logging of match method and confidence
- **Performance**: Ensemble generation <5 min for 5-year, 5-company portfolio

## Open Questions

1. **Threshold tuning**: What score thresholds work across different companies?
2. **False positive handling**: How to detect when "Total revenues" from different contexts incorrectly match?
3. **Parent label extraction**: How to reliably get parent label for context checking?
4. **Value validation**: Should we use value similarity to confirm/reject matches?
5. **User control**: Should users be able to set matching aggressiveness (strict/balanced/loose)?

## Next Steps

1. **Immediate** (today): Document current state in `2025-09-tsla-automotive-alignment.md`
2. **Short-term** (this week): Implement Phase 1 fuzzy label fallback, test on TSLA
3. **Medium-term** (next week): Prototype Phase 2 scored matching, validate on TSLA + AAPL
4. **Long-term** (next sprint): Evaluate Phase 3 Excel-level ensemble based on Phase 2 results

## References

- Current implementation: `src/processor/ensemble.py:_rows_match()`
- Semantic dimension matching: `src/processor/ensemble.py:_signatures_semantically_compatible()`
- TSLA case study: `docs/debug/2025-09-tsla-automotive-alignment.md`
- Presentation-first philosophy: `docs/architecture.md`