import tarfile
from io import BytesIO

from ampel.abstract.AbsAlertLoader import AbsAlertLoader
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


def test_FileAlertLoader(testing_config):
    loader = FileAlertLoader(files=[str(testing_config)])
    assert next(loader).read() == testing_config.read_bytes()


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
    assert next(loader).read() == value
