import hashlib
import json
import logging
from pathlib import Path

from pricing_demo.domain.trip_planner_graph import GraphFingerprint

logger = logging.getLogger("pricing_demo.worker")

MANIFEST_NAME = "graph-manifest.json"
GRAPH_NAME = "graph.obj"


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class FileGraphFingerprints:
    """The manifest and the hash of `graph.obj` in the graph folder.

    The graph is hundreds of megabytes: it is hashed again only when its size or its
    modification time changed. Nothing here raises: the report loop must not die.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._cached: tuple[tuple[int, int], str] | None = None

    def read(self) -> GraphFingerprint:
        manifest = self._manifest()
        # A graph without a manifest has no known origin: it is not reported.
        if manifest is None:
            return GraphFingerprint(None, None)
        return GraphFingerprint(manifest, self._graph_sha256())

    def _manifest(self) -> dict[str, object] | None:
        path = self._path / MANIFEST_NAME
        try:
            content = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as error:
            logger.warning("Cannot read %s: %s", path, error)
            return None
        if not isinstance(content, dict):
            logger.warning("Cannot read %s: it is not a JSON object", path)
            return None
        return content

    def _graph_sha256(self) -> str | None:
        path = self._path / GRAPH_NAME
        try:
            stat = path.stat()
            key = (stat.st_size, stat.st_mtime_ns)
            if self._cached is None or self._cached[0] != key:
                self._cached = (key, hash_file(path))
        except OSError as error:
            if not isinstance(error, FileNotFoundError):
                logger.warning("Cannot hash %s: %s", path, error)
            self._cached = None
            return None
        return self._cached[1]
