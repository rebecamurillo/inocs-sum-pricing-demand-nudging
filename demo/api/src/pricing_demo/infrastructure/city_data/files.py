import hashlib
import shutil
from pathlib import Path


class LocalDatasetFiles:
    """The data sets' folders: `{data_dir}/datasets/{id}/`."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    def _folder(self, dataset_id: str) -> Path:
        return self._data_dir / "datasets" / dataset_id

    def folder(self, dataset_id: str) -> Path:
        folder = self._folder(dataset_id)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def claim(self, dataset_id: str) -> bool:
        try:
            self._folder(dataset_id).mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            return False
        return True

    def copy_in(self, dataset_id: str, source: Path) -> Path:
        target = self.folder(dataset_id) / source.name
        shutil.copyfile(source, target)
        return target.relative_to(self._data_dir)

    def resolve(self, relative: str) -> Path:
        return self._data_dir / relative

    def relative(self, path: Path) -> str:
        return str(path.relative_to(self._data_dir))

    def sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def remove(self, dataset_id: str) -> None:
        shutil.rmtree(self._folder(dataset_id), ignore_errors=True)
