#!/usr/bin/env python3
"""Discover vibe-coded Android application candidates on GitHub."""

import argparse
import base64
import csv
import json
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


DEFAULT_VIBE_TERMS = (
    '"vibe coded"',
    '"vibe coding"',
    'vibecoded',
    'vibecoding',
)
DEFAULT_QUERY_START_DATE = "2025-02-01"
DEFAULT_CODE_QUERIES = ()
FIELDNAMES = (
    "repo_id",
    "repo_full_name",
    "candidate_url",
    "source",
    "discovery_query",
    "discovery_queries",
    "discovery_date",
    "repo_description",
    "stars",
    "topics",
    "default_branch",
    "vibe_evidence_status",
    "vibe_evidence_text",
    "vibe_evidence_url",
    "matched_patterns",
    "android_detected",
    "android_framework",
    "android_evidence",
    "android_validation_status",
    "auto_project_type",
    "auto_review_status",
    "auto_exclusion_reason",
    "decision_source",
    "project_type",
    "review_status",
    "exclusion_reason",
    "ai_tools",
    "notes",
)
MAX_RETRIES = 4
SEARCH_RESULT_CAP = 1000
MULTI_VALUE_SEPARATOR = " | "
MAX_RATE_LIMIT_WAIT_SECONDS = 120
AI_TOOL_PATTERNS = (
    ("claude code", "Claude Code"),
    ("claude sonnet", "Claude Sonnet"),
    ("claude opus", "Claude Opus"),
    ("claude", "Claude"),
    ("gemini", "Gemini"),
    ("copilot", "GitHub Copilot"),
    ("cursor", "Cursor"),
    ("codex", "Codex"),
    ("gpt-5.5", "GPT-5.5"),
    ("gpt-5", "GPT-5"),
    ("gpt", "GPT"),
)
RAW_VIBE_PATTERNS = (
    ("vibe_coded", r"\bvibe(?:\s|-)?coded\b"),
    ("vibe_coding", r"\bvibe(?:\s|-)?coding\b"),
    ("vibecoded", r"\bvibecoded\b"),
    ("vibecoding", r"\bvibecoding\b"),
    ("built_with_vibe_coding", r"\bbuilt\s+with\s+vibe(?:\s|-)?coding\b"),
    ("made_with_vibe_coding", r"\bmade\s+with\s+vibe(?:\s|-)?coding\b"),
    ("vibe_built", r"\bvibe(?:\s|-)?built\b"),
)
RAW_DECLARATION_PATTERNS = (
    r"\b(?:this|the)\s+(?:app|application|project|repository|repo)\b[^.\n]{0,140}\bvibe(?:\s|-)?cod(?:ed|ing)\b",
    r"\b(?:built|made|created|developed|written|crafted|shipped)\b[^.\n]{0,80}\bvibe(?:\s|-)?coding\b",
    r"\bvibe(?:\s|-)?coded\b[^.\n]{0,80}\b(?:app|application|project|repository|repo|android|flutter|react native)\b",
    r"\b(?:android|flutter|react native)\s+(?:app|application)\b[^.\n]{0,140}\bvibe(?:\s|-)?cod(?:ed|ing)\b",
)
GENERIC_VIBE_CONTEXT_PATTERNS = (
    r"\bwhat\s+is\s+vibe(?:\s|-)?coding\b",
    r"\babout\s+vibe(?:\s|-)?coding\b",
    r"\bvibe(?:\s|-)?coding\s+(?:guide|tutorial|course|tips|workflow|lesson|playbook)\b",
    r"\bhow\s+to\s+vibe(?:\s|-)?code\b",
)
NEGATED_VIBE_PATTERNS = (
    re.compile(r"\bnot\s+vibe(?:\s|-)?cod(?:ed|ing)\b", re.IGNORECASE),
    re.compile(r"\b(?:is|was|are|were|isn't|wasn't|aren't|weren't)\s+not\b[^.\n]{0,30}\bvibe(?:\s|-)?cod(?:ed|ing)\b", re.IGNORECASE),
    re.compile(r"\bnever\s+vibe(?:\s|-)?cod(?:ed|ing)\b", re.IGNORECASE),
)
THIRD_PARTY_VIBE_PATTERNS = (
    re.compile(r"\b(?:lists|list|listing|catalogs|catalog|directory|directories|collection|showcase|examples?)\b[^.\n]{0,80}\bvibe(?:\s|-)?cod(?:ed|ing)\b", re.IGNORECASE),
    re.compile(r"\bvibe(?:\s|-)?cod(?:ed|ing)\b[^.\n]{0,80}\b(?:apps|projects|repositories|repos)\b", re.IGNORECASE),
)
APPLICATION_PLUGIN_PATTERNS = (
    re.compile(r"\bcom\.android\.application\b", re.IGNORECASE),
    re.compile(r"\bid\s*[('\"\s]+com\.android\.application", re.IGNORECASE),
    re.compile(r"\bapplicationId\b", re.IGNORECASE),
)
LIBRARY_PLUGIN_PATTERNS = (
    re.compile(r"\bcom\.android\.library\b", re.IGNORECASE),
    re.compile(r"\bid\s*[('\"\s]+com\.android\.library", re.IGNORECASE),
)


VIBE_PATTERNS = tuple((label, re.compile(pattern, re.IGNORECASE)) for label, pattern in RAW_VIBE_PATTERNS)
DECLARATION_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in RAW_DECLARATION_PATTERNS)
GENERIC_VIBE_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in GENERIC_VIBE_CONTEXT_PATTERNS)
AUTO_PROJECT_TYPES = {
    "android_application",
    "vibe_coding_tool",
    "tutorial_or_guide",
    "template_or_boilerplate",
    "library_or_sdk",
    "prompt_collection",
    "unrelated",
    "uncertain",
}
AUTO_REVIEW_STATUSES = {"eligible", "excluded", "manual_review"}


def build_default_queries(execution_date: str) -> Tuple[str, ...]:
    date_filter = f"created:{DEFAULT_QUERY_START_DATE}..{execution_date}"
    return tuple(
        join_query_tokens(term, "in:readme", "topic:android", date_filter)
        for term in DEFAULT_VIBE_TERMS
    )


class GitHubClientError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def join_query_tokens(*tokens: str) -> str:
    return " ".join(token.strip() for token in tokens if token and token.strip())


def unique_preserving_order(values: Iterable[str]) -> List[str]:
    seen = set()
    ordered = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def parse_rate_limit_wait_seconds(headers, detail: str, now: Optional[float] = None) -> Tuple[Optional[int], str]:
    now = now if now is not None else time.time()
    retry_after = headers.get("Retry-After") if headers else None
    reset_at = headers.get("X-RateLimit-Reset") if headers else None
    remaining = headers.get("X-RateLimit-Remaining") if headers else None
    detail_lower = detail.lower()
    rate_limit_kind = "secondary" if "secondary rate limit" in detail_lower or retry_after else "primary"

    if retry_after:
        try:
            return max(int(float(retry_after)), 0), rate_limit_kind
        except ValueError:
            pass
    if reset_at:
        try:
            return max(int(float(reset_at) - now), 0), rate_limit_kind
        except ValueError:
            pass
    if remaining == "0":
        return 60, rate_limit_kind
    return None, rate_limit_kind


def canonicalize_repo_url(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    if host == "www.github.com":
        host = "github.com"

    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]

    if host:
        return f"https://{host}{path}".lower()
    return url.strip().rstrip("/").removesuffix(".git").lower()


def normalize_text(value: str) -> str:
    return " ".join(value.replace("\n", " ").split())


def split_multi_value(value: str) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(MULTI_VALUE_SEPARATOR) if item.strip()]


def join_multi_value(values: Iterable[str]) -> str:
    seen = set()
    ordered = []
    for value in values:
        cleaned = normalize_text(str(value))
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            ordered.append(cleaned)
    return MULTI_VALUE_SEPARATOR.join(ordered)


def repository_metadata(item: Dict) -> Dict:
    if item.get("full_name") or item.get("html_url", "").startswith("https://github.com/"):
        return item
    return item.get("repository", {})


def repository_url(item: Dict) -> str:
    repo = repository_metadata(item)
    return (repo.get("html_url") or item.get("html_url") or "").strip()


def infer_ai_tools(*texts: str) -> List[str]:
    haystack = " ".join(text for text in texts if text).lower()
    tools = []
    for pattern, label in AI_TOOL_PATTERNS:
        if pattern in haystack and label not in tools:
            tools.append(label)
    return tools


def blank_row() -> Dict[str, str]:
    return {field: "" for field in FIELDNAMES}


def row_identity(row: Dict[str, str]) -> str:
    if row.get("repo_id"):
        return f"repo:{row['repo_id']}"
    if row.get("candidate_url"):
        return f"url:{canonicalize_repo_url(row['candidate_url'])}"
    if row.get("repo_full_name"):
        return f"name:{row['repo_full_name'].lower()}"
    return ""


def normalize_row(row: Dict[str, str]) -> Dict[str, str]:
    normalized = blank_row()
    normalized.update({key: value for key, value in row.items() if key in normalized})
    if not normalized["discovery_queries"] and normalized["discovery_query"]:
        normalized["discovery_queries"] = normalized["discovery_query"]
    if not normalized["discovery_query"] and normalized["discovery_queries"]:
        normalized["discovery_query"] = split_multi_value(normalized["discovery_queries"])[0]
    return normalized


def infer_decision_source(row: Dict[str, str]) -> str:
    explicit = row.get("decision_source", "")
    if explicit in {"manual", "auto"}:
        return explicit

    auto_present = any(row.get(field, "") for field in ("auto_project_type", "auto_review_status", "auto_exclusion_reason"))
    if auto_present:
        if row.get("project_type") and row.get("project_type") != row.get("auto_project_type"):
            return "manual"
        if row.get("review_status") and row.get("review_status") != row.get("auto_review_status"):
            return "manual"
        if row.get("exclusion_reason") and row.get("exclusion_reason") != row.get("auto_exclusion_reason"):
            return "manual"
        return "auto"

    if row.get("project_type") and row["project_type"] not in AUTO_PROJECT_TYPES:
        return "manual"
    if row.get("review_status") and row["review_status"] not in AUTO_REVIEW_STATUSES:
        return "manual"
    return "auto"


def earliest_date(left: str, right: str) -> str:
    values = [value for value in (left, right) if value]
    return min(values) if values else ""


def merge_rows(existing: Optional[Dict[str, str]], new: Dict[str, str]) -> Dict[str, str]:
    if not existing:
        return normalize_row(new)

    merged = normalize_row(existing)
    candidate = normalize_row(new)
    existing_source = infer_decision_source(merged)

    union_fields = {"source", "discovery_queries", "topics", "matched_patterns", "ai_tools", "android_evidence"}
    for field in FIELDNAMES:
        if field in union_fields:
            merged[field] = join_multi_value(split_multi_value(merged[field]) + split_multi_value(candidate[field]))
        elif field == "discovery_date":
            merged[field] = earliest_date(merged[field], candidate[field])
        elif field == "stars":
            merged[field] = str(max(int(merged[field] or 0), int(candidate[field] or 0))) if merged[field] or candidate[field] else ""
        elif field in {"project_type", "review_status", "exclusion_reason"}:
            if existing_source == "manual":
                continue
            if candidate[field]:
                merged[field] = candidate[field]
        elif candidate[field]:
            merged[field] = candidate[field]

    merged["decision_source"] = existing_source if existing_source == "manual" else infer_decision_source(candidate)
    merged["discovery_query"] = split_multi_value(merged["discovery_queries"])[0] if merged["discovery_queries"] else merged["discovery_query"]
    return merged


def safe_query_slug(query: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
    return slug[:80] or "query"


def write_raw_snapshot(raw_json_dir: Path, source: str, query: str, payload: Dict) -> Path:
    raw_json_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{source}_{safe_query_slug(query)}.json"
    output_path = raw_json_dir / filename
    snapshot = {
        "source": source,
        "query": query,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        **payload,
    }
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, indent=2, ensure_ascii=False)
    return output_path


class GitHubClient:
    def __init__(self, token: Optional[str], request_delay: float = 0.2, logger=None) -> None:
        self.token = token
        self.request_delay = request_delay
        self.last_request = 0.0
        self.logger = logger or (lambda message: None)

    def request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        query_string = f"?{urlencode(params)}" if params else ""
        for attempt in range(MAX_RETRIES):
            elapsed = time.monotonic() - self.last_request
            if elapsed < self.request_delay:
                time.sleep(self.request_delay - elapsed)

            request = Request(
                f"https://api.github.com{endpoint}{query_string}",
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "vibedroid-discovery",
                    **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
                },
            )

            try:
                with urlopen(request, timeout=30) as response:
                    self.last_request = time.monotonic()
                    remaining = response.headers.get("X-RateLimit-Remaining")
                    reset_at = response.headers.get("X-RateLimit-Reset")
                    if remaining is not None and remaining.isdigit() and int(remaining) <= 5:
                        self.logger(f"warning: GitHub API quota low; remaining={remaining}; reset_at={reset_at}")
                    return json.load(response)
            except HTTPError as error:
                self.last_request = time.monotonic()
                detail = error.read().decode("utf-8", errors="replace")
                if error.code in {403, 429}:
                    wait_seconds, rate_limit_kind = parse_rate_limit_wait_seconds(error.headers, detail)
                    remaining = error.headers.get("X-RateLimit-Remaining")
                    reset_at = error.headers.get("X-RateLimit-Reset")
                    retry_after = error.headers.get("Retry-After")
                    self.logger(
                        f"warning: GitHub {rate_limit_kind} rate limit hit; remaining={remaining}; retry_after={retry_after}; reset_at={reset_at}; wait_seconds={wait_seconds}"
                    )
                    if wait_seconds is None or wait_seconds > MAX_RATE_LIMIT_WAIT_SECONDS or attempt == MAX_RETRIES - 1:
                        suffix = f"; remaining={remaining}; retry_after={retry_after}; reset_at={reset_at}"
                        raise GitHubClientError(f"GitHub {rate_limit_kind} rate limit exhausted{suffix}", error.code) from error
                    time.sleep(wait_seconds)
                    continue
                elif error.code not in {500, 502, 503, 504}:
                    raise GitHubClientError(f"GitHub API returned HTTP {error.code}: {detail}", error.code) from error
            except URLError as error:
                self.last_request = time.monotonic()
                if attempt == MAX_RETRIES - 1:
                    raise GitHubClientError(f"could not reach GitHub API: {error.reason}") from error

            time.sleep(2**attempt)

        raise GitHubClientError("GitHub API request failed after retries")

    def search(self, endpoint: str, query: str, per_page: int, max_pages: int) -> Dict:
        results = []
        total_count = 0
        incomplete_results = False
        pages_fetched = 0
        truncated_by_limit = False
        hit_page_limit = False

        for page in range(1, max_pages + 1):
            payload = self.request(endpoint, {"q": query, "per_page": per_page, "page": page})
            pages_fetched = page
            total_count = payload.get("total_count", total_count)
            incomplete_results = incomplete_results or bool(payload.get("incomplete_results"))
            items = payload.get("items", [])
            remaining = max(SEARCH_RESULT_CAP - len(results), 0)
            if remaining <= 0:
                truncated_by_limit = total_count > SEARCH_RESULT_CAP
                break
            results.extend(items[:remaining])
            if len(results) >= SEARCH_RESULT_CAP:
                truncated_by_limit = total_count > SEARCH_RESULT_CAP
                break
            if len(items) < per_page:
                break
            if page == max_pages:
                hit_page_limit = total_count > len(results)

        return {
            "items": results,
            "count": len(results),
            "total_count": total_count,
            "incomplete_results": incomplete_results,
            "pages_fetched": pages_fetched,
            "truncated_by_limit": truncated_by_limit,
            "hit_page_limit": hit_page_limit,
        }

    def get_repository(self, full_name: str) -> Dict:
        return self.request(f"/repos/{full_name}")

    def get_branch_head_sha(self, full_name: str, branch: str) -> Optional[str]:
        try:
            payload = self.request(f"/repos/{full_name}/branches/{quote(branch, safe='')}")
        except GitHubClientError as error:
            if error.status_code == 404:
                return None
            raise
        return payload.get("commit", {}).get("sha")

    def get_readme(self, full_name: str) -> Optional[Dict]:
        try:
            return self.request(f"/repos/{full_name}/readme")
        except GitHubClientError as error:
            if error.status_code == 404:
                return None
            raise

    def get_git_tree(self, full_name: str, ref: str) -> Dict:
        return self.request(f"/repos/{full_name}/git/trees/{quote(ref, safe='')}", {"recursive": 1})

    def get_text_file(self, full_name: str, path: str, ref: str) -> Optional[str]:
        try:
            payload = self.request(f"/repos/{full_name}/contents/{quote(path, safe='/')}", {"ref": ref})
        except GitHubClientError as error:
            if error.status_code == 404:
                return None
            raise
        if isinstance(payload, list) or payload.get("type") != "file":
            return None
        content = payload.get("content") or ""
        encoding = payload.get("encoding")
        if encoding == "base64":
            return base64.b64decode(content).decode("utf-8", errors="replace")
        return str(content)


def search_source_name(endpoint: str) -> str:
    return "github_code_search" if endpoint == "/search/code" else "github_repository_search"


def search_label(endpoint: str) -> str:
    return "GitHub code search" if endpoint == "/search/code" else "GitHub repository search"


def log_search_warnings(endpoint: str, query: str, payload: Dict, logger) -> None:
    label = "code search" if endpoint == "/search/code" else "repository search"
    if payload.get("incomplete_results"):
        logger(f"warning: {label} returned incomplete results for {query!r}")
    if payload.get("truncated_by_limit"):
        logger(f"warning: {label} hit GitHub's 1000-result cap for {query!r}")
    elif payload.get("hit_page_limit"):
        logger(f"warning: {label} stopped at --max-pages before exhausting results for {query!r}")


def add_discovery_hit(candidate_map: Dict[str, Dict], item: Dict, query: str, source: str, matched_path: str = "") -> None:
    repo = repository_metadata(item)
    repo_id = str(repo.get("id") or "")
    full_name = repo.get("full_name") or repository_name(repository_url(item))
    url = repository_url(item)
    identity = f"repo:{repo_id}" if repo_id else f"url:{canonicalize_repo_url(url)}"
    candidate = candidate_map.setdefault(
        identity,
        {
            "repo_id": repo_id,
            "repo_full_name": full_name,
            "candidate_url": url,
            "default_branch": repo.get("default_branch", ""),
            "repo_description": normalize_text(repo.get("description") or item.get("description") or ""),
            "stars": int(repo.get("stargazers_count") or 0),
            "queries": [],
            "sources": [],
            "code_match_paths": [],
            "seed_texts": [],
        },
    )

    candidate["repo_id"] = candidate["repo_id"] or repo_id
    candidate["repo_full_name"] = candidate["repo_full_name"] or full_name
    candidate["candidate_url"] = candidate["candidate_url"] or url
    candidate["default_branch"] = candidate["default_branch"] or repo.get("default_branch", "")
    candidate["repo_description"] = candidate["repo_description"] or normalize_text(repo.get("description") or item.get("description") or "")
    candidate["stars"] = max(candidate["stars"], int(repo.get("stargazers_count") or 0))
    candidate["queries"].append(query)
    candidate["sources"].append(source)
    if matched_path:
        candidate["code_match_paths"].append(matched_path)
    candidate["seed_texts"].append(json.dumps(item, ensure_ascii=False))


def repository_name(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    return "/".join(parts[:2])


def strip_markdown(markdown: str) -> str:
    text = markdown or ""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]+`", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^\)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    return normalize_text(text)


def surrounding_snippet(text: str, start: int, end: int, window: int = 180) -> str:
    left = max(0, start - window)
    right = min(len(text), end + window)
    prefix_boundary = max(text.rfind(marker, left, start) for marker in (". ", "! ", "? "))
    if prefix_boundary != -1:
        left = prefix_boundary + 2
    suffix_candidates = [text.find(marker, end, right) for marker in (". ", "! ", "? ")]
    suffix_candidates = [candidate for candidate in suffix_candidates if candidate != -1]
    if suffix_candidates:
        right = min(suffix_candidates) + 1
    return normalize_text(text[left:right])


def snippet_is_generic(snippet: str) -> bool:
    lowered = snippet.lower()
    if any(pattern.search(snippet) for pattern in GENERIC_VIBE_PATTERNS):
        return True
    if any(pattern.search(snippet) for pattern in THIRD_PARTY_VIBE_PATTERNS):
        return True
    generic_terms = ("tutorial", "guide", "course", "tips", "workflow", "prompt", "learn")
    return any(term in lowered for term in generic_terms) and "this app" not in lowered and "this project" not in lowered


def snippet_is_project_declaration(snippet: str, repo_name_text: str) -> bool:
    lowered = snippet.lower()
    if any(pattern.search(snippet) for pattern in NEGATED_VIBE_PATTERNS):
        return False
    if any(pattern.search(snippet) for pattern in THIRD_PARTY_VIBE_PATTERNS):
        return False
    if any(pattern.search(snippet) for pattern in DECLARATION_PATTERNS):
        return True
    repo_slug = repo_name_text.split("/")[-1].replace("-", " ").lower()
    verbs = ("built", "made", "created", "developed", "written", "shipped", "started")
    if repo_slug and repo_slug in lowered and any(verb in lowered for verb in verbs):
        return True
    subject_hints = ("this app", "this application", "this project", "this repository", "this repo")
    return any(subject in lowered for subject in subject_hints) and any(term in lowered for term in ("vibe coded", "vibe-coded", "vibe coding", "vibecoded", "vibecoding", "vibe built"))


def extract_vibe_evidence(markdown: str, repo_name_text: str) -> Dict[str, str]:
    clean_text = strip_markdown(markdown)
    matches = []
    for label, pattern in VIBE_PATTERNS:
        for match in pattern.finditer(clean_text):
            matches.append(
                {
                    "label": label,
                    "snippet": surrounding_snippet(clean_text, match.start(), match.end()),
                }
            )

    if not matches:
        return {"status": "not_found", "text": "", "matched_patterns": ""}

    matched_patterns = join_multi_value(match["label"] for match in matches)
    for match in matches:
        snippet = match["snippet"]
        if snippet_is_project_declaration(snippet, repo_name_text) and not snippet_is_generic(snippet):
            return {"status": "matched", "text": snippet, "matched_patterns": matched_patterns}

    return {"status": "review_required", "text": matches[0]["snippet"], "matched_patterns": matched_patterns}


def detect_build_plugin_kind(build_text: Optional[str]) -> str:
    if not build_text:
        return "unknown"
    if any(pattern.search(build_text) for pattern in APPLICATION_PLUGIN_PATTERNS):
        return "application"
    if any(pattern.search(build_text) for pattern in LIBRARY_PLUGIN_PATTERNS):
        return "library"
    return "unknown"


def build_version_catalog_plugin_map(version_catalog_text: Optional[str]) -> Dict[str, str]:
    if not version_catalog_text:
        return {}
    plugin_map = {}
    for match in re.finditer(r'^\s*([A-Za-z0-9._-]+)\s*=\s*\{[^}]*\bid\s*=\s*"([^"]+)"', version_catalog_text, flags=re.MULTILINE):
        plugin_map[match.group(1)] = match.group(2)
    return plugin_map


def resolve_catalog_alias_kind(build_text: Optional[str], version_catalog_map: Dict[str, str]) -> str:
    if not build_text or not version_catalog_map:
        return "unknown"
    alias_matches = re.findall(r'alias\(\s*libs\.plugins\.([A-Za-z0-9_.]+)\s*\)', build_text)
    for alias_name in alias_matches:
        for key in (alias_name, alias_name.replace(".", "-"), alias_name.replace(".", "_")):
            plugin_id = version_catalog_map.get(key)
            if plugin_id == "com.android.application":
                return "application"
            if plugin_id == "com.android.library":
                return "library"
    return "unknown"


def find_nearest_version_catalog(blob_paths: Sequence[str], module_dir: str) -> Optional[str]:
    current_dir = module_dir
    while True:
        candidate = f"{current_dir}/gradle/libs.versions.toml" if current_dir else "gradle/libs.versions.toml"
        if candidate in blob_paths:
            return candidate
        if not current_dir:
            return None
        current_dir = current_dir.rsplit("/", 1)[0] if "/" in current_dir else ""


def path_prefixes_for(blob_paths: Sequence[str], filename: str) -> List[str]:
    prefixes = []
    suffix = f"/{filename}"
    for path in blob_paths:
        if path == filename:
            prefixes.append("")
        elif path.endswith(suffix):
            prefixes.append(path[: -len(suffix)])
    return prefixes


def verify_native_android(client, full_name: str, default_branch: str, blob_paths: Sequence[str], manifest_paths: Sequence[str]) -> Dict[str, str]:
    evidence = []
    module_results = []
    for manifest_path in manifest_paths:
        module_dir = manifest_path.rsplit("/src/main/AndroidManifest.xml", 1)[0] if "/src/main/AndroidManifest.xml" in manifest_path else ""
        candidate_builds = []
        if module_dir:
            candidate_builds.extend([f"{module_dir}/build.gradle", f"{module_dir}/build.gradle.kts"])
        else:
            candidate_builds.extend(["build.gradle", "build.gradle.kts"])

        build_kind = "unknown"
        for build_path in candidate_builds:
            if build_path not in blob_paths:
                continue
            build_text = client.get_text_file(full_name, build_path, default_branch)
            build_kind = detect_build_plugin_kind(build_text)
            if build_kind == "unknown":
                catalog_path = find_nearest_version_catalog(blob_paths, module_dir)
                catalog_text = client.get_text_file(full_name, catalog_path, default_branch) if catalog_path else None
                build_kind = resolve_catalog_alias_kind(build_text, build_version_catalog_plugin_map(catalog_text))
                if catalog_path and build_kind != "unknown":
                    evidence.append(catalog_path)
            evidence.append(manifest_path)
            evidence.append(build_path)
            if build_kind != "unknown":
                break
        module_results.append(build_kind)

    if any(result == "application" for result in module_results):
        return {
            "android_detected": "true",
            "android_framework": "Native Android",
            "android_evidence": join_multi_value(evidence),
            "android_validation_status": "confirmed",
        }
    if module_results and all(result == "library" for result in module_results if result):
        return {
            "android_detected": "false",
            "android_framework": "Android Library",
            "android_evidence": join_multi_value(evidence or manifest_paths),
            "android_validation_status": "not_android",
        }
    return {
        "android_detected": "false",
        "android_framework": "Native Android",
        "android_evidence": join_multi_value(evidence or manifest_paths),
        "android_validation_status": "review_required",
    }


def verify_flutter(blob_paths: Sequence[str]) -> Optional[Dict[str, str]]:
    provisional_result = None
    for root in path_prefixes_for(blob_paths, "pubspec.yaml"):
        flutter_evidence = [f"{root}/pubspec.yaml" if root else "pubspec.yaml"]
        manifest_path = f"{root}/android/app/src/main/AndroidManifest.xml" if root else "android/app/src/main/AndroidManifest.xml"
        gradle_paths = [
            f"{root}/android/app/build.gradle" if root else "android/app/build.gradle",
            f"{root}/android/app/build.gradle.kts" if root else "android/app/build.gradle.kts",
        ]
        if manifest_path in blob_paths:
            flutter_evidence.append(manifest_path)
        for gradle_path in gradle_paths:
            if gradle_path in blob_paths:
                flutter_evidence.append(gradle_path)
        if len(flutter_evidence) >= 2:
            return {
                "android_detected": "true",
                "android_framework": "Flutter",
                "android_evidence": join_multi_value(flutter_evidence),
                "android_validation_status": "confirmed",
            }
        android_prefix = f"{root}/android/" if root else "android/"
        if any(path.startswith(android_prefix) for path in blob_paths):
            provisional_result = {
                "android_detected": "false",
                "android_framework": "Flutter",
                "android_evidence": join_multi_value(flutter_evidence),
                "android_validation_status": "review_required",
            }
    return provisional_result


def verify_react_native(client, full_name: str, default_branch: str, blob_paths: Sequence[str]) -> Optional[Dict[str, str]]:
    provisional_result = None
    for root in path_prefixes_for(blob_paths, "package.json"):
        android_prefix = f"{root}/android/app/" if root else "android/app/"
        if not any(path.startswith(android_prefix) for path in blob_paths):
            continue
        package_path = f"{root}/package.json" if root else "package.json"
        package_text = client.get_text_file(full_name, package_path, default_branch) or ""
        manifest_path = f"{root}/android/app/src/main/AndroidManifest.xml" if root else "android/app/src/main/AndroidManifest.xml"
        if "react-native" in package_text and manifest_path in blob_paths:
            evidence = [package_path, manifest_path]
            for gradle_path in (
                f"{root}/android/app/build.gradle" if root else "android/app/build.gradle",
                f"{root}/android/app/build.gradle.kts" if root else "android/app/build.gradle.kts",
            ):
                if gradle_path in blob_paths:
                    evidence.append(gradle_path)
            return {
                "android_detected": "true",
                "android_framework": "React Native",
                "android_evidence": join_multi_value(evidence),
                "android_validation_status": "confirmed",
            }
        provisional_result = {
            "android_detected": "false",
            "android_framework": "React Native",
            "android_evidence": join_multi_value([package_path, android_prefix.rstrip("/")]),
            "android_validation_status": "review_required",
        }
    return provisional_result


def verify_android_repository(client, full_name: str, default_branch: str, logger) -> Dict[str, str]:
    if not full_name or not default_branch:
        return {
            "android_detected": "false",
            "android_framework": "",
            "android_evidence": "missing repository metadata",
            "android_validation_status": "review_required",
        }

    try:
        tree = client.get_git_tree(full_name, default_branch)
    except GitHubClientError as error:
        logger(f"warning: android validation failed for {full_name}: {error}")
        return {
            "android_detected": "false",
            "android_framework": "",
            "android_evidence": f"tree fetch failed: {error}",
            "android_validation_status": "review_required",
        }

    blob_paths = [entry.get("path", "") for entry in tree.get("tree", []) if entry.get("type") == "blob"]
    tree_truncated = bool(tree.get("truncated"))
    manifest_paths = [
        path
        for path in blob_paths
        if path.endswith("src/main/AndroidManifest.xml") or path == "AndroidManifest.xml"
    ]

    flutter_result = verify_flutter(blob_paths)
    if flutter_result and flutter_result["android_validation_status"] == "confirmed":
        return flutter_result

    react_native_result = verify_react_native(client, full_name, default_branch, blob_paths)
    if react_native_result and react_native_result["android_validation_status"] == "confirmed":
        return react_native_result

    if manifest_paths:
        native_result = verify_native_android(client, full_name, default_branch, blob_paths, manifest_paths)
        if native_result["android_validation_status"] in {"confirmed", "not_android"}:
            return native_result
        if flutter_result or react_native_result:
            return flutter_result or react_native_result or native_result
        return native_result

    if flutter_result:
        return flutter_result
    if react_native_result:
        return react_native_result
    if tree_truncated:
        return {
            "android_detected": "false",
            "android_framework": "",
            "android_evidence": "repository tree truncated before Android validation completed",
            "android_validation_status": "review_required",
        }
    return {
        "android_detected": "false",
        "android_framework": "",
        "android_evidence": "no Android project structure found",
        "android_validation_status": "not_android",
    }


def classify_project_type(repo_name_text: str, description: str, topics: Sequence[str], readme_markdown: str, android_result: Dict[str, str]) -> Tuple[str, str]:
    if android_result["android_framework"] == "Android Library":
        return "library_or_sdk", "Android library detected without an application module"

    metadata_haystack = " ".join([repo_name_text, description, " ".join(topics)]).lower()
    readme_text = strip_markdown(readme_markdown).lower()

    tool_markers = (
        "ide plugin",
        "editor plugin",
        "android studio plugin",
        "vs code extension",
        "jetbrains plugin",
        "assistant for vibe coding",
        "cli tool for vibe coding",
        "coding assistant",
        "developer tool for vibe coding",
        "gradle plugin",
    )
    tutorial_markers = ("tutorial", "course", "walkthrough", "how to")
    template_markers = ("boilerplate", "starter", "scaffold", "skeleton")
    library_markers = (" sdk", "library", "framework", "package")
    prompt_markers = ("prompt collection", "prompt library", "awesome prompts", "prompts for")
    readme_tool_patterns = (
        r"\b(?:this|the)\s+(?:repo|repository|project)\b[^.\n]{0,80}\b(?:plugin|extension|sdk|library|framework|assistant|template|boilerplate|starter|tutorial|guide|course)\b",
        r"\b(?:plugin|extension|sdk|library|framework|assistant|template|boilerplate|starter|tutorial|guide|course)\b[^.\n]{0,80}\bfor\s+vibe(?:\s|-)?coding\b",
    )

    if any(marker in metadata_haystack for marker in tool_markers):
        return "vibe_coding_tool", "Repository appears to be a vibe-coding tool or plugin"
    if any(marker in metadata_haystack for marker in tutorial_markers):
        return "tutorial_or_guide", "Repository appears to be a tutorial or guide"
    if any(marker in metadata_haystack for marker in template_markers):
        return "template_or_boilerplate", "Repository appears to be a template or starter"
    if any(marker in metadata_haystack for marker in prompt_markers):
        return "prompt_collection", "Repository appears to be a prompt collection"
    if any(marker in metadata_haystack for marker in library_markers):
        return "library_or_sdk", "Repository appears to be a library or SDK"
    if any(re.search(pattern, readme_text, re.IGNORECASE) for pattern in readme_tool_patterns):
        if "plugin" in readme_text or "extension" in readme_text or "assistant" in readme_text:
            return "vibe_coding_tool", "Repository appears to be a vibe-coding tool or plugin"
        if any(term in readme_text for term in ("template", "boilerplate", "starter")):
            return "template_or_boilerplate", "Repository appears to be a template or starter"
        if any(term in readme_text for term in ("tutorial", "course", "walkthrough", "guide")):
            return "tutorial_or_guide", "Repository appears to be a tutorial or guide"
    if android_result["android_validation_status"] == "confirmed":
        return "android_application", ""
    if android_result["android_validation_status"] == "not_android":
        return "unrelated", "No Android application structure found"
    return "uncertain", "Manual review required"


def determine_review_status(project_type: str, vibe_status: str, android_status: str) -> str:
    excluded_types = {
        "vibe_coding_tool",
        "tutorial_or_guide",
        "template_or_boilerplate",
        "library_or_sdk",
        "prompt_collection",
        "unrelated",
    }
    if project_type in excluded_types or android_status == "not_android":
        return "excluded"
    if project_type == "android_application" and vibe_status == "matched" and android_status == "confirmed":
        return "eligible"
    return "manual_review"


def build_notes(row: Dict[str, str], code_match_paths: Sequence[str]) -> str:
    details = []
    if row["vibe_evidence_status"] == "matched":
        details.append("README contains an explicit vibe-coding declaration")
    elif row["vibe_evidence_status"] == "review_required":
        details.append("README evidence is ambiguous or unavailable")
    else:
        details.append("No explicit vibe-coding declaration found in README")

    if row["android_validation_status"] == "confirmed":
        details.append(f"Android app confirmed ({row['android_framework']})")
    elif row["android_validation_status"] == "review_required":
        details.append("Android structure needs manual review")
    else:
        details.append("Android app structure not confirmed")

    if code_match_paths:
        details.append(f"code matches: {join_multi_value(code_match_paths)}")
    if row["project_type"] != "android_application" and row["exclusion_reason"]:
        details.append(row["exclusion_reason"])
    return "; ".join(details)


def enrich_candidate(candidate: Dict, client, today: str, logger) -> Dict[str, str]:
    repo_data = {
        "full_name": candidate.get("repo_full_name", ""),
        "html_url": candidate.get("candidate_url", ""),
        "description": candidate.get("repo_description", ""),
        "stargazers_count": candidate.get("stars", 0),
        "default_branch": candidate.get("default_branch", ""),
        "topics": [],
    }

    if candidate.get("repo_full_name"):
        try:
            repo_data = client.get_repository(candidate["repo_full_name"])
        except GitHubClientError as error:
            logger(f"warning: repository metadata fetch failed for {candidate['repo_full_name']}: {error}")

    full_name = repo_data.get("full_name") or candidate.get("repo_full_name", "")
    candidate_url = repo_data.get("html_url") or candidate.get("candidate_url", "")
    default_branch = repo_data.get("default_branch") or candidate.get("default_branch", "")
    description = normalize_text(repo_data.get("description") or candidate.get("repo_description", ""))
    topics = repo_data.get("topics") or []
    stars = int(repo_data.get("stargazers_count") or candidate.get("stars") or 0)

    readme_markdown = ""
    readme_result = {"status": "review_required", "text": "README not fetched", "matched_patterns": ""}
    readme_url = ""
    try:
        readme_payload = client.get_readme(full_name) if full_name else None
        if readme_payload and readme_payload.get("content"):
            readme_markdown = base64.b64decode(readme_payload["content"]).decode("utf-8", errors="replace")
            readme_result = extract_vibe_evidence(readme_markdown, full_name)
            branch_sha = client.get_branch_head_sha(full_name, default_branch) if default_branch else None
            readme_path = readme_payload.get("path") or "README.md"
            if branch_sha:
                readme_url = f"https://github.com/{full_name}/blob/{branch_sha}/{readme_path}"
            else:
                readme_url = readme_payload.get("html_url") or ""
        elif readme_payload is None:
            readme_result = {"status": "review_required", "text": "README not found", "matched_patterns": ""}
    except GitHubClientError as error:
        logger(f"warning: README fetch failed for {full_name}: {error}")
        readme_result = {"status": "review_required", "text": f"README fetch failed: {error}", "matched_patterns": ""}

    android_result = verify_android_repository(client, full_name, default_branch, logger)
    project_type, exclusion_reason = classify_project_type(full_name, description, topics, readme_markdown, android_result)
    ai_tools = infer_ai_tools(description, readme_markdown, *candidate.get("queries", []), *candidate.get("seed_texts", []))

    row = blank_row()
    row.update(
        {
            "repo_id": str(repo_data.get("id") or candidate.get("repo_id") or ""),
            "repo_full_name": full_name,
            "candidate_url": candidate_url,
            "source": join_multi_value(candidate.get("sources", [])),
            "discovery_queries": join_multi_value(candidate.get("queries", [])),
            "discovery_date": today,
            "repo_description": description,
            "stars": str(stars),
            "topics": join_multi_value(topics),
            "default_branch": default_branch,
            "vibe_evidence_status": readme_result["status"],
            "vibe_evidence_text": readme_result["text"],
            "vibe_evidence_url": readme_url,
            "matched_patterns": readme_result["matched_patterns"],
            "android_detected": android_result["android_detected"],
            "android_framework": android_result["android_framework"],
            "android_evidence": android_result["android_evidence"],
            "android_validation_status": android_result["android_validation_status"],
            "auto_project_type": project_type,
            "auto_exclusion_reason": exclusion_reason,
            "decision_source": "auto",
            "project_type": project_type,
            "exclusion_reason": exclusion_reason,
            "ai_tools": join_multi_value(ai_tools),
        }
    )
    row["discovery_query"] = split_multi_value(row["discovery_queries"])[0] if row["discovery_queries"] else ""
    row["auto_review_status"] = determine_review_status(project_type, row["vibe_evidence_status"], row["android_validation_status"])
    row["review_status"] = row["auto_review_status"]
    row["notes"] = build_notes(row, candidate.get("code_match_paths", []))
    return row


def load_existing(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}

    rows_by_identity = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for raw_row in csv.DictReader(handle):
            row = normalize_row(raw_row)
            identity = row_identity(row)
            if identity:
                rows_by_identity[identity] = merge_rows(rows_by_identity.get(identity), row)
    return rows_by_identity


def sort_rows(rows: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
    return sorted(rows, key=lambda row: (-int(row.get("stars") or 0), row.get("candidate_url") or row.get("repo_full_name") or ""))


def collect_candidates(
    client,
    queries: Sequence[str],
    code_queries: Sequence[str],
    per_query: int,
    max_pages: int,
    raw_json_dir: Optional[Path] = None,
    logger=None,
    include_code_search: bool = True,
) -> List[Dict[str, str]]:
    logger = logger or (lambda message: None)
    candidate_map: Dict[str, Dict] = {}
    today = date.today().isoformat()
    total_search_results = 0

    search_specs = [("/search/repositories", unique_preserving_order(queries))]
    if include_code_search:
        search_specs.append(("/search/code", unique_preserving_order(code_queries)))

    for endpoint, query_list in search_specs:
        for query in query_list:
            try:
                payload = client.search(endpoint, query, per_query, max_pages)
            except GitHubClientError as error:
                logger(f"error: {search_label(endpoint).lower()} failed for {query!r}: {error}")
                raise

            total_search_results += payload.get("count", 0)
            log_search_warnings(endpoint, query, payload, logger)
            if raw_json_dir:
                write_raw_snapshot(raw_json_dir, search_source_name(endpoint), query, payload)

            for item in payload["items"]:
                matched_path = ""
                if endpoint == "/search/code":
                    path = item.get("path", "unknown file")
                    matched_path = f"{repository_name(repository_url(item))}/{path}"
                add_discovery_hit(candidate_map, item, query, search_source_name(endpoint), matched_path)

    logger(f"search_results_total: {total_search_results}")
    logger(f"unique_candidates_total: {len(candidate_map)}")
    return [enrich_candidate(candidate, client, today, logger) for candidate in candidate_map.values()]


def write_rows(path: Path, rows: Sequence[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/github_candidates.csv"),
        help="candidate CSV to create or update",
    )
    parser.add_argument("--query", action="append", dest="queries", help="GitHub repository search query; repeatable")
    parser.add_argument("--code-query", action="append", dest="code_queries", help="GitHub Code Search query; repeatable")
    parser.add_argument("--per-query", type=int, default=100, help="maximum results per query")
    parser.add_argument("--max-pages", type=int, default=3, help="maximum pages per query")
    parser.add_argument("--no-code-search", action="store_true", help="skip GitHub Code Search")
    parser.add_argument(
        "--raw-json-dir",
        type=Path,
        help="optional directory to save raw GitHub API search results as JSON",
    )
    parser.add_argument("--dry-run", action="store_true", help="print discoveries without writing CSV")
    args = parser.parse_args()

    if not 1 <= args.per_query <= 100:
        parser.error("--per-query must be between 1 and 100")
    if not 1 <= args.max_pages <= 10:
        parser.error("--max-pages must be between 1 and 10")

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("warning: GITHUB_TOKEN is not set; GitHub search will have a lower rate limit", file=sys.stderr)

    today = date.today().isoformat()
    queries = args.queries or list(build_default_queries(today))
    code_queries = args.code_queries or list(DEFAULT_CODE_QUERIES)
    client = GitHubClient(token, logger=lambda message: print(message, file=sys.stderr))
    existing_rows = load_existing(args.output)

    try:
        discovered = collect_candidates(
            client,
            queries,
            code_queries,
            args.per_query,
            args.max_pages,
            raw_json_dir=args.raw_json_dir,
            logger=lambda message: print(message, file=sys.stderr),
            include_code_search=not args.no_code_search,
        )
    except GitHubClientError:
        return 1

    if args.dry_run:
        rows = sort_rows(discovered)
    else:
        merged_rows = dict(existing_rows)
        for row in discovered:
            identity = row_identity(row)
            merged_rows[identity] = merge_rows(merged_rows.get(identity), row)
        rows = sort_rows(list(merged_rows.values()))
        write_rows(args.output, rows)

    print(f"new_candidates: {len(discovered)}")
    print(f"total_candidates: {len(rows)}")
    if not args.dry_run:
        print(f"written_to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
