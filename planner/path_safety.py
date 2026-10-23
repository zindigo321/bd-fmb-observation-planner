"""Small read-only path preflight and full-tree evidence helpers."""
import hashlib
import os
from pathlib import Path


def resolved(path):
    return Path(path).expanduser().resolve()


def overlaps(a,b):
    a,b=resolved(a),resolved(b)
    return a==b or a.is_relative_to(b) or b.is_relative_to(a) or (a.exists() and b.exists() and os.path.samefile(a,b))


def guard_writes(targets,protected=()):
    """Check actual destinations, including link aliases, before making directories."""
    protected=[resolved(p) for p in protected]
    for target in targets:
        target=resolved(target)
        for parent in (target,*target.parents):
            if parent.is_dir() and (parent/'evidence_manifest.json').exists():
                raise ValueError('write target is inside sealed evidence: '+str(target))
        for source in protected:
            if overlaps(target,source):
                raise ValueError('write target overlaps protected input: '+str(target)+' <-> '+str(source))


def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def tree_snapshot(directory):
    """Include empty directories and link identities without traversing junctions."""
    directory=Path(directory)
    if directory.is_file():return {'file':file_hash(directory)}
    result={}
    def walk(folder):
        for p in sorted(folder.iterdir()):
            key=p.relative_to(directory).as_posix();stat=p.lstat()
            if p.is_symlink() or getattr(stat,'st_file_attributes',0)&0x400:
                result[key]=dict(type='link',target=str(p.resolve()))
            elif p.is_dir():
                result[key]=dict(type='dir');walk(p)
            else:result[key]=dict(type='file',sha256=file_hash(p))
    walk(directory)
    return result
