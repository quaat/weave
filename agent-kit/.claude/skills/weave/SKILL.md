---
name: weave
description: Write, check, lower, simulate, and test this repository's .weave functional Petri-net files with its bundled prototype.
---

# Weave repository adapter

Read the canonical instructions at
[.agents/skills/weave/SKILL.md](../../../.agents/skills/weave/SKILL.md).
Use the existing runner from the repository root:

```bash
python3 scripts/weave.py check examples/valid/checkout.weave
python3 scripts/weave.py simulate examples/valid/checkout_propagating.weave --entry checkout_propagating --outcome all
```

Keep the implementation and guide in the canonical skill. For standalone use,
copy the entire canonical `.agents/skills/weave/` directory into the destination
`.claude/skills/weave/`; this small repository adapter is not standalone.
