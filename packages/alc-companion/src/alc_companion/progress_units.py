"""Verified within-chapter progress; old runs fall back to chapter counters."""
import json


def unit_fractions(path, chapter_ids, recovery_epoch=0):
    translations, owners, loops = {}, {}, {}
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                data = event.get("data", {})
                if not isinstance(data, dict):
                    continue
                kind = event.get("event")
                if kind == "translation_progress" and data.get("recovery_epoch", 0) == recovery_epoch:
                    prefix = data.get("artifact_prefix", "")
                    chapter = next((c for c in chapter_ids if prefix == f"chapters/{c}/translation"), None)
                    done, total = data.get("completed_units"), data.get("total_units")
                    if chapter and type(done) is int and type(total) is int and total > 0:
                        translations[chapter] = min(.98, max(0, done / total))
                elif kind == "guide_progress_plan" and data.get("recovery_epoch", 0) == recovery_epoch:
                    scope = data.get("execution_scope")
                    planned = data.get("owners", {})
                    if not isinstance(planned, dict):
                        continue
                    for loop, chapter in planned.items():
                        if chapter in chapter_ids:
                            owners[(scope, loop)] = chapter
                elif kind in {"proposer_reviewer_worker_finished", "proposer_reviewer_loop_finished"}:
                    key = (data.get("execution_scope"), data.get("loop_id"))
                    if key in owners and data.get("status") == "succeeded":
                        value = .95 if kind.endswith("loop_finished") else .5
                        loops[key] = max(loops.get(key, 0), value)
    except (OSError, UnicodeError):
        pass
    guides = {}
    for chapter in chapter_ids:
        keys = [key for key, owner in owners.items() if owner == chapter]
        if keys:
            guides[chapter] = sum(loops.get(key, 0) for key in keys) / len(keys)
    return translations, guides
