"""GitHub API integration for fetching commit and PR metadata."""

from typing import Optional, Dict, Any
import structlog
from github import Github, GithubException

from gitops_audit.config.settings import settings

logger = structlog.get_logger()


class GitHubClient:
    """Client for interacting with GitHub API."""

    def __init__(self, token: Optional[str] = None):
        """
        Initialize GitHub client.

        Args:
            token: GitHub personal access token. If not provided, uses settings.
        """
        self.token = token or settings.github_token
        self.client = Github(self.token) if self.token else None

        if not self.client:
            logger.warning("github_token_not_configured", message="GitHub integration disabled")

    def extract_repo_info(self, git_url: str) -> Optional[tuple[str, str]]:
        """Extract owner and repo from various Git URL formats."""
        try:
            # HTTPS URLs
            if "github.com/" in git_url:
                parts = git_url.split("github.com/")[1]
                parts = parts.replace(".git", "").strip("/")
                owner, repo = parts.split("/")[:2]
                return owner, repo

            # SSH URLs
            if "github.com:" in git_url:
                parts = git_url.split("github.com:")[1]
                parts = parts.replace(".git", "").strip("/")
                owner, repo = parts.split("/")[:2]
                return owner, repo

        except Exception as e:
            logger.warning("failed_to_parse_git_url", url=git_url, error=str(e))

        return None

    def get_commit_info(self, owner: str, repo: str, commit_sha: str) -> Optional[Dict[str, Any]]:
        """Fetch commit information from GitHub."""
        if not self.client:
            return None

        try:
            repository = self.client.get_repo(f"{owner}/{repo}")
            commit = repository.get_commit(commit_sha)

            commit_data = {
                "sha": commit.sha,
                "author": commit.commit.author.name,
                "author_email": commit.commit.author.email,
                "message": commit.commit.message,
                "committed_at": commit.commit.author.date,
                "url": commit.html_url,
            }

            logger.info(
                "fetched_commit_info",
                owner=owner,
                repo=repo,
                sha=commit_sha[:8],
                author=commit_data["author"],
            )

            return commit_data

        except GithubException as e:
            if e.status == 404:
                logger.warning("commit_not_found", owner=owner, repo=repo, sha=commit_sha[:8])
            else:
                logger.error("github_api_error", status=e.status, error=str(e))
            return None
        except Exception as e:
            logger.error("unexpected_error_fetching_commit", error=str(e))
            return None

    def get_pr_info(self, owner: str, repo: str, commit_sha: str) -> Optional[Dict[str, Any]]:
        """Find PR associated with a commit and fetch PR metadata."""
        if not self.client:
            return None

        try:
            repository = self.client.get_repo(f"{owner}/{repo}")

            prs = repository.get_commit(commit_sha).get_pulls()

            for pr in prs:
                if pr.merged:
                    reviews = pr.get_reviews()
                    approvers = [
                        review.user.login for review in reviews if review.state == "APPROVED"
                    ]

                    pr_data = {
                        "number": pr.number,
                        "title": pr.title,
                        "url": pr.html_url,
                        "merged_by": pr.merged_by.login if pr.merged_by else None,
                        "merged_at": pr.merged_at,
                        "approved_by": ", ".join(set(approvers)) if approvers else None,
                    }

                    logger.info(
                        "fetched_pr_info",
                        owner=owner,
                        repo=repo,
                        pr_number=pr.number,
                        approvers=len(approvers),
                    )

                    return pr_data

            logger.debug("no_pr_found_for_commit", owner=owner, repo=repo, sha=commit_sha[:8])
            return None

        except GithubException as e:
            logger.warning("github_api_error_fetching_pr", status=e.status, error=str(e))
            return None
        except Exception as e:
            logger.error("unexpected_error_fetching_pr", error=str(e))
            return None

    def get_commit_and_pr_info(
        self, git_url: str, commit_sha: str
    ) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Convenience method to fetch both commit and PR info."""
        repo_info = self.extract_repo_info(git_url)
        if not repo_info:
            return None, None

        owner, repo = repo_info

        commit_info = self.get_commit_info(owner, repo, commit_sha)
        pr_info = self.get_pr_info(owner, repo, commit_sha) if commit_info else None

        return commit_info, pr_info


_github_client: Optional[GitHubClient] = None


def get_github_client() -> GitHubClient:
    """Get or create GitHub client singleton."""
    global _github_client
    if _github_client is None:
        _github_client = GitHubClient()
    return _github_client
