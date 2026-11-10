import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts import search_github


def make_repo(full_name: str, repo_id: int, description: str = "", stars: int = 0, default_branch: str = "main", topics=None):
    return {
        "id": repo_id,
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "description": description,
        "stargazers_count": stars,
        "default_branch": default_branch,
        "topics": topics or [],
    }


class FakeGitHubClient:
    def __init__(self, search_results=None, repos=None, readmes=None, trees=None, files=None, branch_shas=None, failures=None):
        self.search_results = search_results or {}
        self.repos = repos or {}
        self.readmes = readmes or {}
        self.trees = trees or {}
        self.files = files or {}
        self.branch_shas = branch_shas or {}
        self.failures = failures or {}
        self.search_calls = []

    def search(self, endpoint, query, per_page, max_pages):
        self.search_calls.append((endpoint, query, per_page, max_pages))
        return self.search_results[(endpoint, query)]

    def get_repository(self, full_name):
        return self.repos[full_name]

    def get_readme(self, full_name):
        failure = self.failures.get(("readme", full_name))
        if failure:
            raise failure
        return self.readmes.get(full_name)

    def get_branch_head_sha(self, full_name, branch):
        return self.branch_shas.get((full_name, branch), "deadbeef")

    def get_git_tree(self, full_name, ref):
        return self.trees[(full_name, ref)]

    def get_text_file(self, full_name, path, ref):
        failure = self.failures.get(("file", full_name, path, ref))
        if failure:
            raise failure
        return self.files.get((full_name, path, ref))


def search_payload(items):
    return {
        "items": items,
        "count": len(items),
        "total_count": len(items),
        "incomplete_results": False,
        "pages_fetched": 1,
        "truncated_by_limit": False,
        "hit_page_limit": False,
    }


def tree_payload(*paths, truncated=False):
    return {"tree": [{"path": path, "type": "blob"} for path in paths], "truncated": truncated}


class SearchGitHubTests(unittest.TestCase):
    def test_default_queries_focus_only_on_vibe_coding_terms(self):
        queries = search_github.build_default_queries("2026-11-10")
        joined = " ".join(queries).lower()
        self.assertIn('"vibe coded" in:readme topic:android created:2025-02-01..2026-11-10', queries)
        self.assertIn('"vibe coding" in:readme topic:android created:2025-02-01..2026-11-10', queries)
        self.assertIn('vibecoded in:readme topic:android created:2025-02-01..2026-11-10', queries)
        self.assertIn('vibecoding in:readme topic:android created:2025-02-01..2026-11-10', queries)
        self.assertNotIn('claude code', joined)
        self.assertNotIn('cursor', joined)
        self.assertNotIn('copilot', joined)
        self.assertNotIn('built with vibe coding', joined)
        self.assertNotIn('made with vibe coding', joined)
        self.assertIn('created:2025-02-01..2026-11-10', joined)
        self.assertNotIn('in:description', joined)
        self.assertNotIn('android in:readme', joined)

    def test_default_queries_match_exact_sampling_frame(self):
        queries = search_github.build_default_queries("2026-11-10")
        self.assertEqual(
            queries,
            (
                '"vibe coded" in:readme topic:android created:2025-02-01..2026-11-10',
                '"vibe coding" in:readme topic:android created:2025-02-01..2026-11-10',
                'vibecoded in:readme topic:android created:2025-02-01..2026-11-10',
                'vibecoding in:readme topic:android created:2025-02-01..2026-11-10',
            ),
        )

    def test_default_queries_are_syntactically_separated_and_unique(self):
        queries = search_github.build_default_queries("2026-11-10")
        self.assertEqual(len(queries), len(set(queries)))
        for query in queries:
            self.assertIn(" created:2025-02-01..2026-11-10", query)
            self.assertNotIn("in:readmecreated:", query)
            self.assertNotIn("in:descriptioncreated:", query)

    def test_readme_explicitly_says_app_was_vibe_coded(self):
        result = search_github.extract_vibe_evidence("This app was vibe-coded in one weekend.", "org/app")
        self.assertEqual(result["status"], "matched")
        self.assertIn("vibe-coded", result["text"].lower())

    def test_readme_discusses_vibe_coding_without_project_claim(self):
        result = search_github.extract_vibe_evidence("This repository includes a guide about vibe coding workflows.", "org/app")
        self.assertEqual(result["status"], "review_required")

    def test_readme_only_mentions_claude_code(self):
        result = search_github.extract_vibe_evidence("Built with Claude Code and a lot of coffee.", "org/app")
        self.assertEqual(result["status"], "not_found")

    def test_readme_negated_vibe_statement_is_not_matched(self):
        result = search_github.extract_vibe_evidence("This app is not vibe coded.", "org/app")
        self.assertEqual(result["status"], "review_required")

    def test_readme_collection_statement_is_not_matched(self):
        result = search_github.extract_vibe_evidence("This repository lists apps that are vibe coded.", "org/catalog")
        self.assertEqual(result["status"], "review_required")

    def test_native_android_application_is_confirmed(self):
        client = FakeGitHubClient(
            trees={("org/app", "main"): tree_payload("app/src/main/AndroidManifest.xml", "app/build.gradle")},
            files={("org/app", "app/build.gradle", "main"): 'plugins { id "com.android.application" }'},
        )
        result = search_github.verify_android_repository(client, "org/app", "main", lambda message: None)
        self.assertEqual(result["android_validation_status"], "confirmed")
        self.assertEqual(result["android_framework"], "Native Android")

    def test_flutter_android_application_is_confirmed(self):
        client = FakeGitHubClient(
            trees={("org/flutter-app", "main"): tree_payload("pubspec.yaml", "android/app/src/main/AndroidManifest.xml", "android/app/build.gradle")}
        )
        result = search_github.verify_android_repository(client, "org/flutter-app", "main", lambda message: None)
        self.assertEqual(result["android_validation_status"], "confirmed")
        self.assertEqual(result["android_framework"], "Flutter")

    def test_flutter_monorepo_application_is_confirmed(self):
        client = FakeGitHubClient(
            trees={
                ("org/flutter-monorepo", "main"): tree_payload(
                    "apps/mobile/pubspec.yaml",
                    "apps/mobile/android/app/src/main/AndroidManifest.xml",
                    "apps/mobile/android/app/build.gradle",
                )
            }
        )
        result = search_github.verify_android_repository(client, "org/flutter-monorepo", "main", lambda message: None)
        self.assertEqual(result["android_validation_status"], "confirmed")
        self.assertEqual(result["android_framework"], "Flutter")

    def test_react_native_android_application_is_confirmed(self):
        client = FakeGitHubClient(
            trees={("org/rn-app", "main"): tree_payload("package.json", "android/app/src/main/AndroidManifest.xml", "android/app/build.gradle")},
            files={("org/rn-app", "package.json", "main"): '{"dependencies": {"react-native": "0.76.0"}}'},
        )
        result = search_github.verify_android_repository(client, "org/rn-app", "main", lambda message: None)
        self.assertEqual(result["android_validation_status"], "confirmed")
        self.assertEqual(result["android_framework"], "React Native")

    def test_react_native_monorepo_application_is_confirmed(self):
        client = FakeGitHubClient(
            trees={
                ("org/rn-monorepo", "main"): tree_payload(
                    "apps/mobile/package.json",
                    "apps/mobile/android/app/src/main/AndroidManifest.xml",
                    "apps/mobile/android/app/build.gradle",
                )
            },
            files={("org/rn-monorepo", "apps/mobile/package.json", "main"): '{"dependencies": {"react-native": "0.76.0"}}'},
        )
        result = search_github.verify_android_repository(client, "org/rn-monorepo", "main", lambda message: None)
        self.assertEqual(result["android_validation_status"], "confirmed")
        self.assertEqual(result["android_framework"], "React Native")

    def test_android_version_catalog_alias_is_confirmed(self):
        client = FakeGitHubClient(
            trees={
                ("org/catalog-app", "main"): tree_payload(
                    "app/src/main/AndroidManifest.xml",
                    "app/build.gradle.kts",
                    "gradle/libs.versions.toml",
                )
            },
            files={
                ("org/catalog-app", "app/build.gradle.kts", "main"): 'plugins { alias(libs.plugins.android.application) }',
                ("org/catalog-app", "gradle/libs.versions.toml", "main"): '[plugins]\nandroid-application = { id = "com.android.application", version = "8.7.0" }',
            },
        )
        result = search_github.verify_android_repository(client, "org/catalog-app", "main", lambda message: None)
        self.assertEqual(result["android_validation_status"], "confirmed")
        self.assertIn("libs.versions.toml", result["android_evidence"])

    def test_android_library_is_not_accepted_as_application(self):
        client = FakeGitHubClient(
            trees={("org/library", "main"): tree_payload("library/src/main/AndroidManifest.xml", "library/build.gradle")},
            files={("org/library", "library/build.gradle", "main"): 'plugins { id "com.android.library" }'},
        )
        result = search_github.verify_android_repository(client, "org/library", "main", lambda message: None)
        self.assertEqual(result["android_validation_status"], "not_android")
        self.assertEqual(result["android_framework"], "Android Library")

    def test_web_only_project_that_mentions_android_is_not_accepted(self):
        client = FakeGitHubClient(trees={("org/web", "main"): tree_payload("package.json", "src/index.ts")})
        result = search_github.verify_android_repository(client, "org/web", "main", lambda message: None)
        self.assertEqual(result["android_validation_status"], "not_android")

    def test_truncated_tree_without_android_files_requires_review(self):
        client = FakeGitHubClient(trees={("org/truncated", "main"): tree_payload("README.md", truncated=True)})
        result = search_github.verify_android_repository(client, "org/truncated", "main", lambda message: None)
        self.assertEqual(result["android_validation_status"], "review_required")

    def test_truncated_tree_with_positive_android_evidence_still_confirms(self):
        client = FakeGitHubClient(
            trees={("org/truncated-app", "main"): tree_payload("app/src/main/AndroidManifest.xml", "app/build.gradle", truncated=True)},
            files={("org/truncated-app", "app/build.gradle", "main"): 'plugins { id "com.android.application" }'},
        )
        result = search_github.verify_android_repository(client, "org/truncated-app", "main", lambda message: None)
        self.assertEqual(result["android_validation_status"], "confirmed")

    def test_vibe_coding_plugin_or_tutorial_is_classified_as_non_app(self):
        android_result = {
            "android_validation_status": "confirmed",
            "android_framework": "Native Android",
        }
        project_type, reason = search_github.classify_project_type(
            "org/vibe-plugin",
            "A VS Code extension for vibe coding",
            ["vibe-coding"],
            "This plugin improves vibe coding workflows.",
            android_result,
        )
        self.assertEqual(project_type, "vibe_coding_tool")
        self.assertIn("tool", reason.lower())

    def test_android_application_named_editor_or_tool_is_kept(self):
        project_type, reason = search_github.classify_project_type(
            "org/photo-editor-tool",
            "A photo editor for Android",
            ["android"],
            "This app was vibe-coded for Android.",
            {
                "android_validation_status": "confirmed",
                "android_framework": "Native Android",
            },
        )
        self.assertEqual(project_type, "android_application")
        self.assertEqual(reason, "")

    def test_hiking_guide_app_is_not_excluded_by_readme_word(self):
        project_type, reason = search_github.classify_project_type(
            "org/hiking-guide",
            "A hiking guide for Android",
            ["android"],
            "This app is a hiking guide. It was vibe coded.",
            {"android_validation_status": "confirmed", "android_framework": "Native Android"},
        )
        self.assertEqual(project_type, "android_application")
        self.assertEqual(reason, "")

    def test_photo_editor_with_tutorial_is_not_excluded(self):
        project_type, reason = search_github.classify_project_type(
            "org/photo-editor",
            "A photo editor for Android",
            ["android"],
            "This is a vibe coded photo editor with a tutorial on filters.",
            {"android_validation_status": "confirmed", "android_framework": "Native Android"},
        )
        self.assertEqual(project_type, "android_application")
        self.assertEqual(reason, "")

    def test_template_gallery_app_is_not_excluded(self):
        project_type, reason = search_github.classify_project_type(
            "org/gallery-app",
            "An Android gallery app",
            ["android"],
            "Built with vibe coding. This app has a template gallery.",
            {"android_validation_status": "confirmed", "android_framework": "Native Android"},
        )
        self.assertEqual(project_type, "android_application")
        self.assertEqual(reason, "")

    def test_multiple_discovery_queries_are_preserved_for_same_repository(self):
        repo = make_repo("org/app", 1, "An Android app", 5)
        readme = {
            "content": "VGhpcyBhcHAgd2FzIHZpYmUtY29kZWQu",
            "path": "README.md",
            "html_url": "https://github.com/org/app/blob/main/README.md",
        }
        client = FakeGitHubClient(
            search_results={
                ("/search/repositories", '"vibe coded" in:readme'): search_payload([repo]),
                ("/search/repositories", '"vibe coding" in:description'): search_payload([repo]),
            },
            repos={"org/app": repo},
            readmes={"org/app": readme},
            trees={("org/app", "main"): tree_payload("app/src/main/AndroidManifest.xml", "app/build.gradle")},
            files={("org/app", "app/build.gradle", "main"): 'plugins { id "com.android.application" }'},
            branch_shas={("org/app", "main"): "abc123"},
        )
        rows = search_github.collect_candidates(
            client,
            ['"vibe coded" in:readme', '"vibe coding" in:description'],
            [],
            per_query=10,
            max_pages=1,
            include_code_search=False,
        )
        self.assertEqual(len(rows), 1)
        self.assertIn('"vibe coded" in:readme', rows[0]["discovery_queries"])
        self.assertIn('"vibe coding" in:description', rows[0]["discovery_queries"])

    def test_default_code_queries_are_not_generic_android_file_searches(self):
        self.assertEqual(search_github.DEFAULT_CODE_QUERIES, ())

    def test_rate_limit_wait_prefers_retry_after(self):
        wait_seconds, kind = search_github.parse_rate_limit_wait_seconds(
            {"Retry-After": "17", "X-RateLimit-Reset": "9999999999"},
            "secondary rate limit",
            now=0,
        )
        self.assertEqual(wait_seconds, 17)
        self.assertEqual(kind, "secondary")

    def test_rate_limit_wait_falls_back_to_reset_time(self):
        wait_seconds, kind = search_github.parse_rate_limit_wait_seconds(
            {"X-RateLimit-Reset": "110"},
            "API rate limit exceeded",
            now=100,
        )
        self.assertEqual(wait_seconds, 10)
        self.assertEqual(kind, "primary")

    def test_collect_candidates_deduplicates_identical_queries_before_execution(self):
        repo = make_repo("org/app", 1, "An Android app", 5)
        readme = {
            "content": "VGhpcyBhcHAgd2FzIHZpYmUtY29kZWQu",
            "path": "README.md",
            "html_url": "https://github.com/org/app/blob/main/README.md",
        }
        client = FakeGitHubClient(
            search_results={("/search/repositories", '"vibe coded" in:readme topic:android created:2025-02-01..2026-11-10'): search_payload([repo])},
            repos={"org/app": repo},
            readmes={"org/app": readme},
            trees={("org/app", "main"): tree_payload("app/src/main/AndroidManifest.xml", "app/build.gradle")},
            files={("org/app", "app/build.gradle", "main"): 'plugins { id "com.android.application" }'},
        )
        rows = search_github.collect_candidates(
            client,
            [
                '"vibe coded" in:readme topic:android created:2025-02-01..2026-11-10',
                '"vibe coded" in:readme topic:android created:2025-02-01..2026-11-10',
            ],
            [],
            per_query=100,
            max_pages=1,
            include_code_search=False,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(client.search_calls), 1)

    def test_collect_candidates_logs_total_results_and_unique_candidates(self):
        repo = make_repo("org/app", 1, "An Android app", 5)
        readme = {
            "content": "VGhpcyBhcHAgd2FzIHZpYmUtY29kZWQu",
            "path": "README.md",
            "html_url": "https://github.com/org/app/blob/main/README.md",
        }
        logs = []
        client = FakeGitHubClient(
            search_results={("/search/repositories", '"vibe coded" in:readme topic:android created:2025-02-01..2026-11-10'): search_payload([repo])},
            repos={"org/app": repo},
            readmes={"org/app": readme},
            trees={("org/app", "main"): tree_payload("app/src/main/AndroidManifest.xml", "app/build.gradle")},
            files={("org/app", "app/build.gradle", "main"): 'plugins { id "com.android.application" }'},
        )
        search_github.collect_candidates(
            client,
            ['"vibe coded" in:readme topic:android created:2025-02-01..2026-11-10'],
            [],
            per_query=100,
            max_pages=1,
            include_code_search=False,
            logger=logs.append,
        )
        self.assertIn('search_results_total: 1', logs)
        self.assertIn('unique_candidates_total: 1', logs)

    def test_missing_readme_is_marked_for_manual_review(self):
        repo = make_repo("org/app", 2, "An Android app", 3)
        client = FakeGitHubClient(
            search_results={("/search/repositories", '"vibe coded" in:readme'): search_payload([repo])},
            repos={"org/app": repo},
            readmes={"org/app": None},
            trees={("org/app", "main"): tree_payload("app/src/main/AndroidManifest.xml", "app/build.gradle")},
            files={("org/app", "app/build.gradle", "main"): 'plugins { id "com.android.application" }'},
        )
        rows = search_github.collect_candidates(
            client,
            ['"vibe coded" in:readme'],
            [],
            per_query=10,
            max_pages=1,
            include_code_search=False,
        )
        self.assertEqual(rows[0]["vibe_evidence_status"], "review_required")
        self.assertIn("README", rows[0]["vibe_evidence_text"])

    def test_manual_review_decisions_are_preserved_on_reload(self):
        with TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "candidates.csv"
            csv_path.write_text(
                "repo_id,repo_full_name,candidate_url,source,discovery_query,discovery_queries,discovery_date,repo_description,stars,topics,default_branch,vibe_evidence_status,vibe_evidence_text,vibe_evidence_url,matched_patterns,android_detected,android_framework,android_evidence,android_validation_status,auto_project_type,auto_review_status,auto_exclusion_reason,decision_source,project_type,review_status,exclusion_reason,ai_tools,notes\n"
                "1,org/app,https://github.com/org/app,github_repository_search,\"q\",\"q\",2026-11-10,Desc,5,android,main,matched,Snippet,url,vibe_coded,true,Native Android,app/build.gradle,confirmed,android_application,eligible,,manual,manual_override,verified,kept by human,Claude,notes\n",
                encoding="utf-8",
            )
            existing = search_github.load_existing(csv_path)
            identity = next(iter(existing))
            updated = search_github.merge_rows(
                existing[identity],
                {
                    "repo_id": "1",
                    "repo_full_name": "org/app",
                    "candidate_url": "https://github.com/org/app",
                    "project_type": "vibe_coding_tool",
                    "review_status": "excluded",
                    "exclusion_reason": "new automatic guess",
                    "auto_project_type": "vibe_coding_tool",
                    "auto_review_status": "excluded",
                    "auto_exclusion_reason": "new automatic guess",
                },
            )
            self.assertEqual(updated["project_type"], "manual_override")
            self.assertEqual(updated["review_status"], "verified")
            self.assertEqual(updated["exclusion_reason"], "kept by human")
            self.assertEqual(updated["auto_project_type"], "vibe_coding_tool")
            self.assertEqual(updated["auto_review_status"], "excluded")
            self.assertEqual(updated["decision_source"], "manual")

    def test_old_automatic_decisions_can_be_recalculated(self):
        existing = {
            "repo_id": "1",
            "repo_full_name": "org/app",
            "candidate_url": "https://github.com/org/app",
            "project_type": "android_application",
            "review_status": "eligible",
            "exclusion_reason": "",
        }
        updated = search_github.merge_rows(
            existing,
            {
                "repo_id": "1",
                "repo_full_name": "org/app",
                "candidate_url": "https://github.com/org/app",
                "auto_project_type": "vibe_coding_tool",
                "auto_review_status": "excluded",
                "auto_exclusion_reason": "Repository appears to be a vibe-coding tool or plugin",
                "project_type": "vibe_coding_tool",
                "review_status": "excluded",
                "exclusion_reason": "Repository appears to be a vibe-coding tool or plugin",
                "decision_source": "auto",
            },
        )
        self.assertEqual(updated["project_type"], "vibe_coding_tool")
        self.assertEqual(updated["review_status"], "excluded")
        self.assertEqual(updated["decision_source"], "auto")


if __name__ == "__main__":
    unittest.main()
