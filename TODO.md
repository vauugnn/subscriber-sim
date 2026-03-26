# TODO

**⚠️ Warning:** This file syncs with GitHub Issues. Only add items you actually want to sync!

Follow the format below to ensure items parse correctly.

## Open

<!-- Character Coherence Improvements — High Priority Training Data -->
- [ ] [DATA-1] Replace generic synthetic augmentation with archetype-specific multi-turn scenarios <!-- issue:77 -->
- [ ] [DATA-3] Add longer multi-turn sessions per archetype (5-15 turns) to prevent early drift <!-- issue:79 -->
- [ ] [DATA-2] Audit heuristically-classified training sessions for label quality <!-- issue:78 -->

<!-- Character Coherence Improvements — High Priority Inference -->
- [ ] [INF-1] Move mid-convo character reminder from user message into system message <!-- issue:80 -->
- [ ] [INF-2] Add per-response style/voice validator to detect subtle drift <!-- issue:81 -->
- [ ] [INF-3] Make fallback responses topic-aware and contextually grounded <!-- issue:82 -->

<!-- Character Coherence Improvements — Medium Priority Prompt Engineering -->
- [ ] [PROMPT-1] Add voice fingerprint section (vocabulary, style, emoji use) to each archetype's system prompt <!-- issue:83 -->
- [ ] [PROMPT-2] Increase system re-injection frequency for conversations over 8 turns <!-- issue:84 -->
- [ ] Fix 120-second startup timeout <!-- issue:85 -->
  > Startup is taking too long and hitting the 120-second timeout. Investigate slow initialization steps (model loading, env setup) and optimize or split them to stay within the limit.
- [ ] Handle Hugging Face download timeout gracefully <!-- issue:86 -->
  > Network connection to Hugging Face times out during model/weight downloads. Add retry logic with exponential backoff, surface a clear error message, and consider caching or pre-downloading assets to avoid repeated failures.
- [ ] Handle spot instance preemption / worker reclaim <!-- issue:87 -->
  > Worker is killed mid-run when the spot instance gets reclaimed. Implement checkpoint saving at regular intervals and add a preemption signal handler so training state can be resumed from the last checkpoint after the instance restarts.
- [ ] Deduplicate quantization config to remove warnings <!-- issue:88 -->
  > Quantization settings are specified in multiple places, causing duplicate/conflicting config warnings. Audit all quantization config locations (Cell 0, Cell 2, Cell 6) and consolidate into a single source of truth.

## Done
- [ ] CI/CD pipeline <!-- issue:76 -->
- [ ] Mobile app <!-- issue:75 -->
- [ ] Real-time analytics <!-- issue:74 -->
- [ ] User accounts <!-- issue:73 -->
- [ ] Fine-tuning UI <!-- issue:72 -->
- [ ] Multi-model support <!-- issue:71 -->
- [ ] Contributing guide <!-- issue:70 -->
- [ ] Video tutorials <!-- issue:69 -->
- [ ] API documentation <!-- issue:68 -->
- [ ] Archetype customization <!-- issue:67 -->
- [ ] Session analytics <!-- issue:66 -->
- [ ] Export conversations <!-- issue:65 -->
- [ ] Add prompt templates <!-- issue:64 -->
- [ ] Error handling <!-- issue:63 -->
- [ ] Docker optimization <!-- issue:62 -->
- [ ] Improve UI/UX <!-- issue:61 -->
- [ ] Enhance database queries <!-- issue:60 -->
- [ ] Fix D2: Audit double-injection of context cues <!-- issue:59 -->
- [ ] Fix D1: Pin opener in `_normalize_history()` <!-- issue:58 -->
- [ ] Fix R3: Add stop tokens to notebook <!-- issue:57 -->
- [ ] Fix R1: Increase notebook `rep_pen` <!-- issue:56 -->
- [ ] Isolate backend vs adapter <!-- issue:55 -->
- [ ] Verify parameter parity <!-- issue:54 -->
- [ ] Compare LoRA adapter formats <!-- issue:53 -->
- [ ] Load testing <!-- issue:52 -->
- [ ] Monitoring <!-- issue:51 -->
- [ ] CI/CD pipeline <!-- issue:50 -->
- [ ] Mobile app <!-- issue:49 -->
- [ ] Real-time analytics <!-- issue:48 -->
- [ ] User accounts <!-- issue:47 -->
- [ ] Fine-tuning UI <!-- issue:46 -->
- [ ] Multi-model support <!-- issue:45 -->
- [ ] Contributing guide <!-- issue:44 -->
- [ ] Video tutorials <!-- issue:43 -->
- [ ] API documentation <!-- issue:42 -->
- [ ] Archetype customization <!-- issue:41 -->
- [ ] Session analytics <!-- issue:40 -->
- [ ] Export conversations <!-- issue:39 -->
- [ ] Add prompt templates <!-- issue:38 -->
- [ ] Error handling <!-- issue:37 -->
- [ ] Docker optimization <!-- issue:36 -->
- [ ] Improve UI/UX <!-- issue:35 -->
- [ ] Enhance database queries <!-- issue:34 -->
- [ ] Isolate backend vs adapter <!-- issue:33 -->
- [ ] Verify parameter parity <!-- issue:32 -->
- [ ] Compare LoRA adapter formats <!-- issue:31 -->
- [ ] Test context window size <!-- issue:30 -->
- [ ] Analyze response filtering <!-- issue:29 -->
- [ ] Inspect prompt construction <!-- issue:28 -->
- [ ] Analyze generation parameters <!-- issue:27 -->
- [ ] Load testing <!-- issue:26 -->
- [ ] Monitoring <!-- issue:25 -->
- [ ] CI/CD pipeline <!-- issue:24 -->
- [ ] Mobile app <!-- issue:23 -->
- [ ] Real-time analytics <!-- issue:22 -->
- [ ] User accounts <!-- issue:21 -->
- [ ] Fine-tuning UI <!-- issue:20 -->
- [ ] Multi-model support <!-- issue:19 -->
- [ ] Contributing guide <!-- issue:18 -->
- [ ] Video tutorials <!-- issue:17 -->
- [ ] API documentation <!-- issue:16 -->
- [ ] Archetype customization <!-- issue:15 -->
- [ ] Session analytics <!-- issue:14 -->
- [ ] Export conversations <!-- issue:13 -->
- [ ] Add prompt templates <!-- issue:12 -->
- [ ] Error handling <!-- issue:11 -->
- [ ] Docker optimization <!-- issue:10 -->
- [ ] Improve UI/UX <!-- issue:9 -->
- [ ] Enhance database queries <!-- issue:8 -->
- [ ] Isolate backend vs adapter <!-- issue:7 -->
- [ ] Verify parameter parity <!-- issue:6 -->
- [ ] Compare LoRA adapter formats <!-- issue:5 -->
- [ ] Test context window size <!-- issue:4 -->
- [ ] Analyze response filtering <!-- issue:3 -->
- [ ] Inspect prompt construction <!-- issue:2 -->
- [ ] Analyze generation parameters <!-- issue:1 -->

<!-- Completed items go here. Mark with [x] instead of [ ] -->
<!-- Format: - [x] Your completed task description -->

## Reference

### How to Add Todos

**Format for new items:**
```
- [ ] Your task description
```

**After creating a GitHub issue**, link it like this:
```
- [ ] Your task description <!-- issue:123 -->
```

Replace `123` with your actual GitHub issue number.

**Completed items** (checked off):
```
- [x] Your completed task description
```

### Example Format (Reference Only)

After adding real todos, your file structure should look similar to:

```
## Open
- [_] Implement user authentication
- [_] Add dark mode support
- [_] Fix login bug

## Done
- [X] Setup project repository
- [X] Create initial documentation
```

(Replace `[_]` with `[ ]` for unchecked items in your actual file)

**Important:** Only add items to ## Open and ## Done that you actually want to sync to GitHub!

### Important Rules

- ✅ Use `- [ ]` for unchecked items
- ✅ Use `- [x]` for completed items
- ✅ Sections must be `## Open` and `## Done` (with capital O and D)
- ✅ Issue links use `<!-- issue:NUMBER -->` format
- ⚠️ Don't modify the section headers
- ⚠️ Don't change the checkbox format
- ⚠️ Keep issue numbers accurate when syncing
