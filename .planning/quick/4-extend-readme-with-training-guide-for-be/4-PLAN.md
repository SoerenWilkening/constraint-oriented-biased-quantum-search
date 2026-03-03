---
phase: quick
plan: 4
type: execute
wave: 1
depends_on: []
files_modified: [README.md]
autonomous: true
requirements: [quick-4]
must_haves:
  truths:
    - "README contains a Training Guide section explaining how to train a WeightPredictor offline"
    - "README shows how to use adaptive_solve for online weight refinement"
    - "README covers the full workflow: install ML extra, collect training data, fit, predict, save/load, evaluate"
    - "README documents the transfer learning pipeline (train on small, evaluate on large)"
  artifacts:
    - path: "README.md"
      provides: "Training guide documentation for ML-based branching weight prediction"
      contains: "## Training Guide"
  key_links:
    - from: "README.md training guide"
      to: "cbqs.ml API"
      via: "code examples referencing WeightPredictor, collect_training_data, adaptive_solve, validate_transfer"
      pattern: "from cbqs.ml"
---

<objective>
Extend README.md with a comprehensive training guide explaining how to train the CBQS solver for better biasing weights using the cbqs.ml subpackage.

Purpose: Users currently have no documentation on the ML-based weight prediction and adaptive solve capabilities added in v3.0. The README should teach them the full workflow from installation through offline training, online adaptation, evaluation, and transfer learning.

Output: Updated README.md with a new "Training Guide" section containing working code examples.
</objective>

<execution_context>
@./.claude/get-shit-done/workflows/execute-plan.md
@./.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@README.md
@cbqs/ml/__init__.py
@cbqs/ml/training.py
@cbqs/ml/adaptation.py
@cbqs/ml/features.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add ML training guide section to README</name>
  <files>README.md</files>
  <action>
Add a new "## Training Guide" section to README.md between the existing example and the citation section. The guide should cover the following subsections with working code examples using the actual API:

### Installation
- Show `pip install -e ".[ml]"` to install with the ML optional dependency (scikit-learn)

### Offline Training (WeightPredictor)
Explain the full offline pipeline with a code example:
1. Create multiple Model instances (training set) -- use a simple knapsack loop creating e.g. 5 small instances with random coefficients
2. Call `collect_training_data(models, n_strategies=10, stopping_time=5)` to run diverse weight strategies and find best weights per model
3. Create `WeightPredictor(random_state=42)` and call `.fit(training_pairs)`
4. Use `.predict(new_model)` to get predicted branching weights for a new model
5. Apply predicted weights via `model.set_param('branching_weights', weights)` then `model.solve()`
6. Show `.save('predictor.joblib')` and `WeightPredictor.load('predictor.joblib')` for persistence

### Online Adaptation (adaptive_solve)
Explain multi-round adaptive solving with EMA weight updates:
1. Show basic usage: `adaptive_solve(model, n_rounds=5, stopping_time=5, seed=42)`
2. Explain key parameters: `n_rounds`, `ema_alpha` (smoothing factor, higher = more reward influence), `initial_weights` (can be None for uniform, an ndarray, or a fitted WeightPredictor)
3. Show how to chain offline + online: train a WeightPredictor offline, then pass it as `initial_weights` to adaptive_solve for further refinement
4. Show accessing results: `result.best_result.objective`, `result.best_weights`, `result.history`

### Evaluation
Show how to compare strategies using `evaluate_weights`:
1. Define a dict of strategies: `{'predicted': lambda m: predictor.predict(m)}`
2. Call `evaluate_weights(test_models, strategies, stopping_time=5)`
3. Explain output table columns: Mean Objective, Feasibility Rate, Time-to-Best, Speedup vs Uniform

### Transfer Learning
Show the one-call transfer validation pipeline:
1. Create small training models and larger test models
2. Call `validate_transfer(train_models, test_models, random_state=42)`
3. Explain that it trains on small instances and evaluates on larger ones
4. Show saving the returned predictor for reuse: `predictor.save('transfer_predictor.joblib')`

Use the existing README style (no badges, minimal formatting, code-focused). Keep code examples realistic but concise -- use knapsack as the running example since the existing README already uses it. Import from `cbqs.ml` (the public API) not from submodules directly.
  </action>
  <verify>
    <automated>python3 -c "
import re
with open('README.md') as f:
    content = f.read()
# Check all required sections exist
assert '## Training Guide' in content, 'Missing Training Guide section'
assert 'collect_training_data' in content, 'Missing collect_training_data example'
assert 'WeightPredictor' in content, 'Missing WeightPredictor example'
assert 'adaptive_solve' in content, 'Missing adaptive_solve example'
assert 'evaluate_weights' in content, 'Missing evaluate_weights example'
assert 'validate_transfer' in content, 'Missing validate_transfer example'
assert 'pip install' in content, 'Missing installation instructions'
assert '.save(' in content, 'Missing save example'
assert '.load(' in content, 'Missing load example'
assert 'from cbqs.ml' in content, 'Missing cbqs.ml imports'
# Ensure citation section still exists at the end
assert 'Cite as:' in content, 'Citation section was removed'
# Ensure existing example still exists
assert 'branching_bias' in content, 'Original example was removed'
print('All README checks passed')
"
    </automated>
  </verify>
  <done>
README.md contains a Training Guide section with subsections for Installation, Offline Training, Online Adaptation, Evaluation, and Transfer Learning. All code examples use the public cbqs.ml API. The existing README content (example, citation) is preserved.
  </done>
</task>

</tasks>

<verification>
- README.md contains all new sections with code examples
- Existing README content (intro, build instructions, knapsack example, citation) is preserved
- Code examples reference actual API signatures from cbqs.ml
</verification>

<success_criteria>
- Training Guide section is comprehensive and covers all four ML workflows (offline, online, evaluation, transfer)
- All code examples are syntactically correct and use the real cbqs.ml API
- A new user can follow the guide to train and use branching weight predictions
</success_criteria>

<output>
After completion, create `.planning/quick/4-extend-readme-with-training-guide-for-be/4-SUMMARY.md`
</output>
