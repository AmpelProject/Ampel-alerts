import tarfile
import uuid
from io import BytesIO
from pathlib import Path

import pytest

from ampel.abstract.AbsAlertLoader import AbsAlertLoader
from ampel.alert.load.DirAlertLoader import DirAlertLoader
from ampel.alert.load.DirFileNamesLoader import DirFileNamesLoader
from ampel.alert.load.FileAlertLoader import FileAlertLoader
from ampel.alert.load.TarAlertLoader import TarAlertLoader


def test_dummy():
    class DummyAlertLoader(AbsAlertLoader[int]):
        max: int

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._it = iter(range(self.max))

        def __next__(self) -> int:
            return next(self._it)

    loader = DummyAlertLoader(max=10)
    assert len(list(loader)) == 10


def test_TarAlertLoader():
    value = b"foo"

    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        ti = tarfile.TarInfo(name="value")
        ti.size = len(value)
        tf.addfile(ti, BytesIO(value))
        ...
    buf.seek(0)

    loader = TarAlertLoader(file_obj=buf)
    for item in loader:
        assert item.read() == value


@pytest.fixture
def dummy_alert(tmpdir: Path) -> tuple[Path, bytes]:
    path = Path(tmpdir / "dummy.txt")
    content = uuid.uuid4().hex
    path.write_text(content)
    return path, content.encode()


def test_FileAlertLoader(dummy_alert: tuple[Path, bytes]):
    path, content = dummy_alert
    loader = FileAlertLoader(files=[str(path)])
    for item in loader:
        assert item.read() == content

    with pytest.raises(ValueError, match="Parameter 'files' cannot be empty"):
        FileAlertLoader(files=[])


@pytest.mark.parametrize("klass", [DirAlertLoader, DirFileNamesLoader])
def test_DirAlertLoader(klass, dummy_alert: tuple[Path, bytes]):
    path, content = dummy_alert
    loader = klass(
        folder=str(path.parent),
        extension=path.suffix[1:],
        max_entries=1,
    )
    loader.logger.verbose = 2
    for item in loader:
        assert item.read() == content if klass is DirAlertLoader else str(path)


