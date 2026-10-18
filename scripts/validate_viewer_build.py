"""Offline validation of generated paths, payload limits, and append-only source data."""
from collections import defaultdict
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / 'site'


class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self, tag, attrs):
        for k,v in attrs:
            if (tag=='a' and k=='href') or (tag in ('script','link') and k in ('src','href')):
                self.links.append(v)


html_count=link_count=selection_count=run_count=0
for page in SITE.rglob('*.html'):
    html_count+=1
    text=page.read_text()
    assert 'name="robots" content="noindex' in text
    parser=Links();parser.feed(text)
    for href in parser.links:
        url=urlsplit(href)
        if url.scheme or url.netloc or not url.path:continue
        destination=(page.parent/unquote(url.path)).resolve()
        assert destination.is_relative_to(SITE.resolve()), 'Link leaves site'
        assert destination.exists(), f'Broken local link: {page.relative_to(SITE)}'
        link_count+=1
assets=sum(p.stat().st_size for p in (SITE/'assets').iterdir() if p.is_file())
worst=0
for path in (SITE/'c').glob('*.index.json'):
    index=json.loads(path.read_text())
    grouped=defaultdict(list)
    for section in ('selections','history'):
        for key,entry in index[section].items():
            target=SITE/'c'/unquote(entry['path'])
            assert target.exists(), 'Missing selection file'
            payload=json.loads(target.read_text());selection_count+=1
            sizes=[]
            for run in payload['runs']:
                if run.get('text_url'):
                    detail=SITE/'c'/unquote(run['text_url'])
                    assert detail.exists(), 'Missing answer file'
                    full=json.loads(detail.read_text())
                    assert full['rep']==run['rep']
                    assert bool(full['text'].strip())==run['has_text']
                    sizes.append(detail.stat().st_size)
                run_count+=1
            if section=='selections':
                grouped[tuple(key.split('|')[:2])].append(target.stat().st_size+max(sizes,default=0))
    for values in grouped.values():
        size=assets+path.stat().st_size+(SITE/'c'/(index['id']+'.html')).stat().st_size+sum(sorted(values,reverse=True)[:3])
        worst=max(worst,size)
assert worst <= 300000, f'Phone payload exceeds budget: {worst}'
changes=subprocess.check_output(['git','diff','--name-only','--diff-filter=MDR','main','--','data/'],cwd=ROOT,text=True)
assert not changes, 'Existing data changed'
assert not subprocess.check_output(['git','diff','main','--','.github/workflows'],cwd=ROOT,text=True), 'Workflow changed'
result=dict(html_pages=html_count,local_links_checked=link_count,selections_checked=selection_count,
            run_references_checked=run_count,worst_three_condition_first_load_bytes=worst,
            existing_data_files_modified=0,workflow_changed=False,browser_validation='blocked; not run')
(SITE/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
