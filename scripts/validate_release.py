#!/usr/bin/env python3
"""Validate release layout, links, sample hashes and install archive."""
from pathlib import Path
from zipfile import ZipFile
import re,json,hashlib,sys,importlib.util,copy
root=Path(__file__).resolve().parents[1]
errors=[]
required=['README.md','LICENSE','CITATION.cff','docs/usage.md','docs/environment.md','docs/citation.md','docs/third-party-notices.md','examples/lf09-comfort-safety/README.md','examples/lf09-comfort-safety/input.md','examples/lf09-comfort-safety/walkthrough.md','downloads/develop-vocational-learning-tasks-v0.1.0.zip']
for name in required:
 if not (root/name).is_file():errors.append('Missing '+name)
for p in root.rglob('*.md'):
 for link in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
  if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',link) or link.startswith('#'):continue
  target=link.split('#')[0]
  if target and not (p.parent/target).exists():errors.append(f'Broken link {p.relative_to(root)}: {link}')
ex=root/'examples/lf09-comfort-safety'
try:
 manifest=json.loads((ex/'checksums.json').read_text())
 for name,digest in manifest['files'].items():
  if hashlib.sha256((ex/name).read_bytes()).hexdigest()!=digest:errors.append('Sample hash mismatch '+name)
except (OSError,ValueError,KeyError) as e:errors.append(str(e))
skill=root/'skills/develop-vocational-learning-tasks'
install=root/'downloads/develop-vocational-learning-tasks-v0.1.0.zip'
if install.exists():
 with ZipFile(install) as z:
  if z.testzip():errors.append('Corrupt ZIP')
  for p in skill.rglob('*'):
   if p.is_file() and '__pycache__' not in p.parts:
    name='develop-vocational-learning-tasks/'+str(p.relative_to(skill))
    if name not in z.namelist() or z.read(name)!=p.read_bytes():errors.append('Archive differs '+name)
if any(root.rglob('*.pdf')):errors.append('Original or intermediate PDF unexpectedly included')
spec=importlib.util.spec_from_file_location('checker',skill/'scripts/check_design.py')
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
r=json.loads((skill/'assets/design-record-template.json').read_text())
def fill(x):
 if isinstance(x,dict):return {k:fill(v) for k,v in x.items()}
 if isinstance(x,list):return [fill(v) for v in x]
 if isinstance(x,str) and x.startswith('替换为'):return '教学模拟任务的完整说明、具体活动与可检查成果记录'
 return x
r=fill(r);e,_=checker.check(r)
if e:errors.append('Checker valid-record test failed: '+str(e))
d=copy.deepcopy(r);d['assessment']['items'][0]['points']=80
if not checker.check(d)[0]:errors.append('Checker failed to detect scoring error')
d=copy.deepcopy(r);d['sections'][7]='检查交互'
if not checker.check(d)[0]:errors.append('Checker failed to detect incorrect section')
print(json.dumps({'ok':not errors,'errors':errors,'files':sum(p.is_file() for p in root.rglob('*') if '__pycache__' not in p.parts)},ensure_ascii=False,indent=2))
sys.exit(1 if errors else 0)
