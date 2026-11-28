"""Builds OpenTripPlanner's graph with `docker compose run otp-build` (see demo/otp/README.md)."""

import subprocess
from pathlib import Path

from pricing_demo.application.errors import GraphBuildFailed

SERVICE = "otp-build"
# The folder compose.yaml mounts into the otp-build service, relative to demo/.
MOUNTED_GRAPH_DIR = "otp/data"


def otp_image_from_compose(path: Path) -> str:
    """The `image:` of the `otp-build` service, read by a line scan (no YAML dependency)."""
    in_service = False
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            if indent == 2 and stripped.endswith(":"):
                in_service = stripped == f"{SERVICE}:"
            elif in_service and indent > 2 and stripped.startswith("image:"):
                return stripped.removeprefix("image:").strip().strip("'\"")
    raise GraphBuildFailed(f"{path} has no image for the {SERVICE} service.")


class ComposeGraphBuilder:
    def __init__(
        self, demo_dir: Path, timeout_s: float | None = None, graph_dir: Path | None = None
    ) -> None:
        self._demo_dir = demo_dir
        self._timeout_s = timeout_s
        self._graph_dir = graph_dir

    @property
    def image(self) -> str:
        return otp_image_from_compose(self._demo_dir / "compose.yaml")

    def build(self) -> None:
        mounted = (self._demo_dir / MOUNTED_GRAPH_DIR).resolve()
        if self._graph_dir is not None and self._graph_dir.resolve() != mounted:
            # The service builds from the folder compose.yaml mounts, not from another one.
            raise GraphBuildFailed(
                f"The {SERVICE} service builds in {mounted}, not in {self._graph_dir}: "
                "unset PRICING_DEMO_OTP_GRAPH_DIR to build the graph."
            )
        command = ["docker", "compose", "--profile", "otp", "run", "--rm", SERVICE]
        try:
            # Not captured: the build takes minutes and its output is the progress.
            done = subprocess.run(command, cwd=self._demo_dir, timeout=self._timeout_s, check=False)
        except FileNotFoundError as error:
            raise GraphBuildFailed(f"Docker is not available: {error}") from error
        except subprocess.TimeoutExpired:
            raise GraphBuildFailed(
                f"docker compose run {SERVICE} timed out after {self._timeout_s:g} s"
            ) from None
        if done.returncode != 0:
            raise GraphBuildFailed(
                f"docker compose run {SERVICE} exited with code {done.returncode}"
            )
