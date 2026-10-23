"""Atomic UTF-8 writes using an exclusively created, caller-owned temporary file."""
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def atomic_text_writer(path, *, newline=None):
    """Close the owned descriptor before replacement; never open a legacy temp name.

    This protects serial writes from pre-existing aliases. It does not promise
    durability across power loss or defend against concurrent directory mutation.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name + '.', suffix='.tmp')
    try:
        try:
            stream = os.fdopen(fd, 'w', encoding='utf-8', newline=newline)
        except BaseException:
            os.close(fd)
            raise
        with stream:
            yield stream
        # Windows requires that our open handle has already been closed.
        os.replace(temporary, path)
    except BaseException as error:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        except OSError as cleanup_error:
            error.add_note(f'Owned temporary file cleanup failed: {temporary}: {cleanup_error}')
        raise


def atomic_write_text(path, text):
    with atomic_text_writer(path) as stream:
        stream.write(text)
