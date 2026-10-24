"""Export committed source and a separate local-only real Demo/reference archive."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from planner.common import json_write
from planner.experiment_inputs import verify_seal
from planner.path_safety import file_hash, guard_writes
from planner.runner import versions

TOP={'.gitignore','.gitattributes','.editorconfig','CONTRIBUTING.md','README.md','BASELINE_HANDOFF.md','EXPERIMENTS.md','PROGRESS.md','requirements.txt','requirements-dev.txt','smoke_test.py'}
GITHUB_FILES={'.github/pull_request_template.md','.github/workflows/ci.yml'}
SUFFIXES={'planner':{'.py'},'scripts':{'.py','.mjs'},'tests':{'.py'},'configs':{'.yaml','.json'},'docs':{'.md','.json','.yaml'}}


def source_allowed(name):
    p=PurePosixPath(name)
    if name in TOP or name in GITHUB_FILES: return True
    if p.parts[0] in SUFFIXES: return p.suffix in SUFFIXES[p.parts[0]] and not any(x.startswith('.') or x=='__pycache__' for x in p.parts)
    return name in {'demo/README.md','demo/template.html'} or (p.parent.as_posix()=='examples/synthetic' and p.suffix in {'.csv','.json'})


def safe_name(name):
    p=PurePosixPath(name)
    if p.as_posix()!=name or p.is_absolute() or '\\' in name or not name or any(x in ('..','.') or ':' in x for x in p.parts):
        raise ValueError('unsafe archive member: '+name)
    return p


def archive(destination, payload, metadata):
    """Payload maps relative name to (bytes, purpose, source); manifest excludes itself."""
    entries={}
    for name,(data,purpose,source) in payload.items():
        safe_name(name)
        if name=='MANIFEST.json': raise ValueError('manifest is generated, not a payload')
        entries[name]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),purpose=purpose,source=source)
    manifest=dict(metadata,files=entries,manifest_excludes_self=True)
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name,(data,_,_) in sorted(payload.items()): z.writestr(name,data)
        z.writestr('MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8'))
    verify_archive(destination)
    digest=file_hash(destination)
    destination.with_suffix('.zip.sha256').write_text(digest+'  '+destination.name+'\n',encoding='ascii')
    return dict(path=str(destination),bytes=destination.stat().st_size,sha256=digest,files=len(entries),source_commit=metadata['source_commit'])


def verify_archive(path):
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)): raise ValueError('duplicate archive members')
        for name in names: safe_name(name)
        manifest=json.loads(z.read('MANIFEST.json'))
        if set(names)!=set(manifest['files'])|{'MANIFEST.json'}: raise ValueError('manifest member set differs')
        for name,entry in manifest['files'].items():
            data=z.read(name)
            if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:
                raise ValueError('archive hash mismatch: '+name)
            if (z.getinfo(name).external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('archive symlinks are not supported')
    return manifest


def extract_verified(path, destination):
    verify_archive(path)
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(path) as z: z.extractall(destination)


def build(out, base, commit):
    out=Path(out).resolve();base=Path(base).resolve()
    guard_writes([out],[base])
    if out.exists(): raise ValueError('kit output must be new')
    def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
    commit=git('rev-parse',commit+'^{commit}').decode().strip()
    candidate=git('rev-parse','b0eb3b5^{commit}').decode().strip()
    subprocess.run(['git','merge-base','--is-ancestor',candidate,commit],cwd=ROOT,check=True)
    source={}
    for item in git('ls-tree','-r','-z',commit).split(b'\0'):
        if not item:continue
        header,raw_name=item.split(b'\t',1);mode,kind,oid=header.decode().split();name=raw_name.decode('utf-8')
        if mode not in ('100644','100755') or kind!='blob' or not source_allowed(name):
            raise ValueError('tracked file outside source kit whitelist: '+name)
        source[name]=(git('cat-file','blob',oid),'committed runtime/test/documentation or synthetic example',commit+':'+name)
    for required in ('scripts/team3_run.py','scripts/inspect_team1_input.py','docs/STABLE_HANDOFF.md'):
        if required not in source:raise ValueError('commit lacks handoff entry: '+required)
    for case in ('E3_seed42','E3_seed17','E3_seed23','E4_seed42_late'):verify_seal(base/'experiments'/case)
    verify_seal(base/'E5_common_baseline')
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    if file_hash(base/'demo/index.html')!=read(base/'demo/demo_data_check.json')['html_sha256']:raise ValueError('Demo hash differs')
    local={}
    def add(name,path,purpose):local[name]=(path.read_bytes(),purpose,str(path))
    add('demo/index.html',base/'demo/index.html','historically validated, self-contained E3/E4 real replay')
    for name in read(base/'browser/browser_checks.json')['screenshots']:
        if Path(name).name!=name:raise ValueError('unsafe screenshot name')
        add('screenshots/'+name,base/'browser'/name,'historical actual browser screenshot')
    for label,directory in [('E3_E4','experiments'),('E5','E5_common_baseline')]:
        for name in ('comparison.csv','comparison.md','summary.json'):add('tables/'+label+'/'+name,base/directory/name,'historical result table; absolute paths are provenance only')
    for name in ('targets.csv','stations.csv','windows.csv','metadata.json'):
        add('reference_windows/'+name,base/'experiments/E3_seed42/standard_input'/name,'official frozen reference windows, NOT teammate 1 delivery')
    local['DEMO_SCRIPT.md']=(source['docs/DEMO_SCRIPT.md'][0],'historical narration; open demo/index.html in this kit',commit+':docs/DEMO_SCRIPT.md')
    readme='''# 本地演示与参考包

本包含真实标识，只由用户通过团队渠道转交，不上传Git或云服务。

- [直接打开真实离线Demo](demo/index.html)：双击即可，无需Python、Node、联网或求解。
- [三张截图之一](screenshots/01_seed17_improved_overview.png)、[故障历史](screenshots/02_late_fault_history.png)、[重规划](screenshots/03_late_replanned.png)。
- [E3/E4对比](tables/E3_E4/comparison.md)与[CSV](tables/E3_E4/comparison.csv)；[E5对比](tables/E5/comparison.md)与[CSV](tables/E5/comparison.csv)。
- [演示讲稿](DEMO_SCRIPT.md)：讲稿的旧打开路径替换为本包demo/index.html。
- [参考窗口元数据](reference_windows/metadata.json)：同目录四个文件供3号窗口接口验证；官方冻结参考数据，非1号交付。
- [来源及SHA256清单](MANIFEST.json)。创建时间是打包时间，不是旧实验重跑时间。

Demo展示E3/E4整套初始规划与重规划，旧E4收益11.6分；E5共同初始计划的收益9.6分单独看表。历史TLE检查不等于新窗口物理条件已验证。表中的本机绝对路径只用于追溯，打开页面和本包导航不依赖它们。

接入代码在另一个source_kit.zip。把本包与源码包解压到相邻目录，使用源码包的docs/TEAM3_INTEGRATION.md和scripts/inspect_team1_input.py；先只读试读reference_windows，再用生成的配置运行windows工作流。
'''
    local['README.md']=(readme.encode('utf-8'),'relative local navigation and data boundary','generated by committed build_handoff.py')
    meta=dict(source_commit=commit,algorithm_candidate_commit=candidate,created_at=datetime.now(timezone.utc).isoformat(),
              dependency_versions=versions(),export_mode='source files read exclusively from Git objects; no working-tree payload',historical_base=str(base))
    out.mkdir(parents=True,exist_ok=False)
    result=dict(source_kit=archive(out/'source_kit.zip',source,dict(meta,kind='portable_source_and_synthetic')),
                local_demo_reference_kit=archive(out/'local_demo_reference_kit.zip',local,dict(meta,kind='local_only_real_reference')))
    json_write(out/'packages.json',result)
    print(json.dumps(result,ensure_ascii=False))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True);p.add_argument('--base',required=True);p.add_argument('--commit',default='HEAD');a=p.parse_args()
    try:build(a.out,a.base,a.commit)
    except (ValueError,OSError,KeyError,subprocess.CalledProcessError) as error:
        print('FAIL: '+str(error),file=sys.stderr);raise SystemExit(2)
