"""AI Runtime Knowledge Store — persistent learning across workflow generations.

Stores memories (stable rules, software characteristics, risk tips) and skills
(reusable step templates, preconditions, anchor/condition patterns) derived from
previous generations, manual edits, standardization passes, and run outcomes.

Directory structure under ``workspace_dir/ai-runtime/``::

    episodes/           # {timestamp}_{workflow_id}.json — generation records
    memory/
        pending/        # *.md — candidate memories awaiting human approval
        approved/       # *.md — memories used in subsequent generations
    skills/
        pending/        # *.md — candidate skills awaiting human approval
        approved/       # *.md — skills used in subsequent generations
    index.json          # searchable index of all approved items
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# --------------------------------------------------------------------------- #
# Data types
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class KnowledgeItem:
    """A searchable memory or skill entry."""

    slug: str
    item_type: str  # "memory" | "skill"
    category: str
    title: str
    summary: str
    keywords: list[str] = field(default_factory=list)
    applies_to: list[str] = field(default_factory=list)
    approved: bool = False
    created_at: str = ""


@dataclass(slots=True)
class EpisodeRecord:
    """A single generation episode for traceability."""

    episode_id: str
    workflow_id: str
    prompt: str
    hit_memory_ids: list[str] = field(default_factory=list)
    hit_skill_ids: list[str] = field(default_factory=list)
    generation_result: str = ""
    edits_diff: str = ""
    run_outcome: str = ""
    timestamp: str = ""


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #
class AIRuntimeStore:
    """Persistent learning store for AI-driven workflow generation."""

    def __init__(self, workspace_dir: Path) -> None:
        self._root = Path(workspace_dir) / "ai-runtime"
        self._index_path = self._root / "index.json"
        self._index: dict[str, KnowledgeItem] = {}
        self._ensure_dirs()
        self._load_index()

    # -- directories ------------------------------------------------------- #
    def _ensure_dirs(self) -> None:
        for sub in [
            "episodes",
            "memory/pending",
            "memory/approved",
            "skills/pending",
            "skills/approved",
        ]:
            (self._root / sub).mkdir(parents=True, exist_ok=True)

    # -- index ------------------------------------------------------------- #
    def _load_index(self) -> None:
        if not self._index_path.exists():
            return
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            for slug, raw in data.items():
                self._index[slug] = KnowledgeItem(**raw)
        except (json.JSONDecodeError, TypeError):
            self._index = {}

    def _save_index(self) -> None:
        data = {}
        for slug, item in self._index.items():
            data[slug] = {
                "slug": item.slug,
                "item_type": item.item_type,
                "category": item.category,
                "title": item.title,
                "summary": item.summary,
                "keywords": item.keywords,
                "applies_to": item.applies_to,
                "approved": item.approved,
                "created_at": item.created_at,
            }
        self._index_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _upsert_index(self, item: KnowledgeItem) -> None:
        self._index[item.slug] = item
        self._save_index()

    def _remove_index(self, slug: str) -> None:
        self._index.pop(slug, None)
        self._save_index()

    # -- search ------------------------------------------------------------ #
    def search_memories(self, prompt: str, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Search approved memories relevant to the given prompt and context."""
        return self._search("memory", prompt, context)

    def search_skills(self, prompt: str, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Search approved skills relevant to the given prompt and context."""
        return self._search("skill", prompt, context)

    def _search(
        self, item_type: str, prompt: str, context: dict[str, Any] | None
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        query_terms = set(_tokenize(prompt))

        # Add context-derived terms
        if context:
            device = context.get("instrument_profile", "")
            query_terms.update(_tokenize(str(device)))
            for anchor in context.get("anchors", []):
                if isinstance(anchor, dict):
                    query_terms.update(_tokenize(anchor.get("id", "")))

        for slug, item in self._index.items():
            if item.item_type != item_type or not item.approved:
                continue
            score = _match_score(query_terms, item)
            if score > 0:
                content = self._read_item_content(item_type, slug, item.approved)
                results.append({
                    "id": slug,
                    "title": item.title,
                    "category": item.category,
                    "summary": item.summary,
                    "keywords": item.keywords,
                    "score": score,
                    "content": content,
                })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:5]  # Top 5 most relevant

    def _read_item_content(self, item_type: str, slug: str, approved: bool) -> str:
        status = "approved" if approved else "pending"
        path = self._root / item_type / status / f"{slug}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    # -- extraction -------------------------------------------------------- #
    def extract_candidates(
        self,
        workflow_data: dict[str, Any] | None = None,
        *,
        prompt: str = "",
        reasoning: str = "",
        edits_diff: str = "",
        run_outcome: str = "",
    ) -> list[KnowledgeItem]:
        """Create pending memory/skill candidates from a generation or run result."""
        candidates: list[KnowledgeItem] = []

        if workflow_data:
            # Extract step patterns as skill candidates
            steps = workflow_data.get("steps", []) if isinstance(workflow_data, dict) else []
            if len(steps) >= 2:
                step_ids = [s.get("id", "") for s in steps]
                actions = [s.get("action", "") for s in steps]
                slug = _slugify(f"skill-{'-'.join(step_ids[:3])}")
                candidate = KnowledgeItem(
                    slug=slug,
                    item_type="skill",
                    category="step_template",
                    title=f"步骤模板: {' → '.join(actions[:5])}",
                    summary=f"从 prompt「{prompt[:100]}」提取的 {len(steps)} 步模板",
                    keywords=list(set(actions)),
                    approved=False,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
                self._write_pending_item("skill", slug, self._format_skill_md(candidate, workflow_data, prompt))
                self._upsert_index(candidate)
                candidates.append(candidate)

        # Extract memory from reasoning
        if reasoning and "生成失败" not in reasoning:
            slug = _slugify(f"memory-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
            candidate = KnowledgeItem(
                slug=slug,
                item_type="memory",
                category="rule",
                title=f"编排规则 — {prompt[:60]}",
                summary=f"从生成推理中提取的编排规则",
                keywords=_extract_keywords(prompt),
                approved=False,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            self._write_pending_item("memory", slug, self._format_memory_md(candidate, prompt, reasoning, run_outcome))
            self._upsert_index(candidate)
            candidates.append(candidate)

        return candidates

    def _write_pending_item(self, item_type: str, slug: str, content: str) -> None:
        path = self._root / item_type / "pending" / f"{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _format_skill_md(candidate: KnowledgeItem, workflow_data: dict, prompt: str) -> str:
        steps_yaml = ""
        for s in workflow_data.get("steps", []):
            steps_yaml += f"  - id: {s.get('id')}\n"
            steps_yaml += f"    action: {s.get('action')}\n"
            if s.get("target"):
                steps_yaml += f"    target: {s.get('target')}\n"
            if s.get("value") is not None:
                steps_yaml += f"    value: {s.get('value')}\n"
            if s.get("condition"):
                steps_yaml += f"    condition: {json.dumps(s['condition'], ensure_ascii=False)}\n"
        return (
            f"---\n"
            f"type: skill\n"
            f"category: step_template\n"
            f"keywords: [{', '.join(candidate.keywords)}]\n"
            f"created_at: {candidate.created_at}\n"
            f"---\n\n"
            f"# {candidate.title}\n\n"
            f"## 来源 Prompt\n{prompt}\n\n"
            f"## 步骤模板\n```yaml\nsteps:\n{steps_yaml}```\n"
        )

    @staticmethod
    def _format_memory_md(candidate: KnowledgeItem, prompt: str, reasoning: str, run_outcome: str) -> str:
        outcome_section = f"\n## 运行结果\n{run_outcome}\n" if run_outcome else ""
        return (
            f"---\n"
            f"type: memory\n"
            f"category: rule\n"
            f"keywords: [{', '.join(candidate.keywords)}]\n"
            f"created_at: {candidate.created_at}\n"
            f"---\n\n"
            f"# {candidate.title}\n\n"
            f"## 来源 Prompt\n{prompt}\n\n"
            f"## 推理\n{reasoning[:500]}\n"
            f"{outcome_section}"
        )

    # -- approval ---------------------------------------------------------- #
    def approve(self, item_type: str, slug: str) -> None:
        """Move an item from pending to approved."""
        item = self._index.get(slug)
        if item is None or item.approved:
            return
        pending_path = self._root / item_type / "pending" / f"{slug}.md"
        approved_path = self._root / item_type / "approved" / f"{slug}.md"
        if pending_path.exists():
            approved_path.parent.mkdir(parents=True, exist_ok=True)
            pending_path.rename(approved_path)
        item.approved = True
        self._upsert_index(item)

    def reject(self, item_type: str, slug: str) -> None:
        """Delete a pending item."""
        pending_path = self._root / item_type / "pending" / f"{slug}.md"
        if pending_path.exists():
            pending_path.unlink()
        self._remove_index(slug)

    def list_pending(self) -> list[KnowledgeItem]:
        return [item for item in self._index.values() if not item.approved]

    def list_approved(self) -> list[KnowledgeItem]:
        return [item for item in self._index.values() if item.approved]

    # -- episodes ---------------------------------------------------------- #
    def record_episode(
        self,
        *,
        prompt: str,
        workflow_id: str,
        hit_memory_ids: list[str] | None = None,
        hit_skill_ids: list[str] | None = None,
        generation_result: str = "",
        edits_diff: str = "",
        run_outcome: str = "",
    ) -> EpisodeRecord:
        ts = datetime.now(timezone.utc)
        episode_id = f"{ts.strftime('%Y%m%dT%H%M%S')}_{workflow_id}"
        episode = EpisodeRecord(
            episode_id=episode_id,
            workflow_id=workflow_id,
            prompt=prompt,
            hit_memory_ids=hit_memory_ids or [],
            hit_skill_ids=hit_skill_ids or [],
            generation_result=generation_result,
            edits_diff=edits_diff,
            run_outcome=run_outcome,
            timestamp=ts.isoformat(),
        )
        path = self._root / "episodes" / f"{episode_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({
                "episode_id": episode.episode_id,
                "workflow_id": episode.workflow_id,
                "prompt": episode.prompt,
                "hit_memory_ids": episode.hit_memory_ids,
                "hit_skill_ids": episode.hit_skill_ids,
                "generation_result": episode.generation_result,
                "edits_diff": episode.edits_diff,
                "run_outcome": episode.run_outcome,
                "timestamp": episode.timestamp,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return episode

    def get_hits_for_reasoning(self, memory_hits: list[dict], skill_hits: list[dict]) -> list[str]:
        """Format hit IDs for display in the reasoning panel."""
        lines: list[str] = []
        if memory_hits:
            lines.append("### 命中 Memory")
            for h in memory_hits:
                lines.append(f"- `{h['id']}` ({h['category']}): {h['title']}")
        if skill_hits:
            lines.append("### 命中 Skill")
            for h in skill_hits:
                lines.append(f"- `{h['id']}` ({h['category']}): {h['title']}")
        return lines


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _tokenize(text: str) -> list[str]:
    """Crude CJK-aware tokenizer for keyword matching."""
    tokens: list[str] = []
    # Split on non-alphanumeric
    for part in re.split(r"[^A-Za-z0-9一-鿿_]+", text.lower()):
        part = part.strip()
        if not part or len(part) < 2:
            continue
        # For CJK, also add individual bigrams
        if re.search(r"[一-鿿]", part):
            tokens.append(part)
            for i in range(len(part) - 1):
                tokens.append(part[i:i + 2])
        else:
            tokens.append(part)
    return tokens


def _match_score(query_terms: set[str], item: KnowledgeItem) -> int:
    """Simple keyword-overlap score."""
    score = 0
    item_terms = set(item.keywords or [])
    item_terms.update(_tokenize(item.title))
    item_terms.update(_tokenize(item.summary))
    for qt in query_terms:
        for it in item_terms:
            if qt in it or it in qt:
                score += 1
    return score


def _slugify(text: str) -> str:
    """Create a filesystem-safe slug from text."""
    slug = re.sub(r"[^a-z0-9一-鿿-]", "-", text.lower())
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")[:64]


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from a prompt."""
    tokens = _tokenize(text)
    # Filter out common stop words
    stop = {"的", "和", "是", "在", "了", "the", "a", "an", "is", "of", "to", "in", "and"}
    keywords = [t for t in tokens if t not in stop]
    return list(dict.fromkeys(keywords))[:10]
