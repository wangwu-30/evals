"""Generate the research report from scored raw results, without model calls."""
import argparse
import collections
import json
import pathlib
import statistics
from run import ASSETS, ROOT, MODELS, JUDGES, load, conditions
from checks import CHECKS
from followup_report import render as render_followup, conclusion as followup_conclusion


def interval(xs):return '['+', '.join(f'{x:.3f}' for x in xs)+']'
def cell(r):return f"{r['trimmed_mean']:.3f} {interval(r['ci95'])}; n={r['n']}"
def delta(r):return f"{r['delta_vs_full']:+.3f} {interval(r['delta_bootstrap']['ci95'])}"


def table(rows,labels):
    bykey={(r['model'],r['cond']):r for r in rows}
    out=['| 条件 | gpt-5.6-luna（请求名） | GLM-5.3-flash（路由返回名） |','|---|---|---|']
    for cond in conditions():
        if not any((m,cond) in bykey for m in MODELS):continue
        out.append('| '+labels[cond]+' | '+' | '.join(cell(bykey[(m,cond)]) if (m,cond) in bykey else '未计划' for m in MODELS)+' |')
    return '\n'.join(out)


def gain(rows,model):
    r=next(r for r in rows if r['model']==model and r['cond']=='none')
    ci=r['delta_bootstrap']['ci95']
    return f"{-r['delta_vs_full']:+.3f} {interval([-ci[1],-ci[0]])}"


def section_effects(summary,labels):
    out=['| 模型 | 删除段 | dev Δ [95% CI] | validation Δ [95% CI] | 28比较同时区间结论 |','|---|---|---|---|---|']
    findings=[]
    for m in MODELS:
        for c in conditions():
            if not c.startswith('-'):continue
            rs=[next(r for r in summary[s] if r['model']==m and r['cond']==c) for s in ('dev','validation')]
            cis=[r['delta_bootstrap']['simultaneous_ci'] for r in rs]
            signs=[-1 if ci[1]<0 else 1 if ci[0]>0 else 0 for ci in cis]
            verdict='两切分未共同确认'
            if signs==[-1,-1]:verdict='删除后两切分均下降（原段有用）';findings.append((m,c,'helpful',cis))
            elif signs==[1,1]:verdict='删除后两切分均上升（原段可能有害）';findings.append((m,c,'harmful',cis))
            elif any(signs):verdict='仅一个切分或方向不一致；不做通用结论'
            out.append('| '+m+' | '+labels[c]+' | '+delta(rs[0])+' | '+delta(rs[1])+' | '+verdict+'；dev '+interval(cis[0])+' / val '+interval(cis[1])+' |')
    return '\n'.join(out),findings


def calibration_table(samples,heading):
    out=[heading,'','| 裁判请求名 | 样本 | 一致标签/标签数 | 逐项一致率 | 整条完全一致 |','|---|---|---|---|---|']
    for r in samples:
        out.append(f"| {r['judge']} | {r['samples']} | {r['matched_decisions']}/{r['semantic_decisions']} | {r['agreement']:.1%} | {r['exact_sample_matches']}/{r['samples']} ({r['exact_agreement']:.1%}) |")
    return '\n'.join(out)


def diagnostic(root):
    counts=collections.Counter();lengths=collections.defaultdict(list)
    for p in (root/'generations').glob('*/*/*.json'):
        if p.name.endswith('.call.json'):continue
        g=load(p);counts['batches']+=1;counts['missing_answers']+=sum(not a.strip() for a in g['answers'].values())
        counts['recovered_batches']+=g.get('transport_parser')!='strict-json'
        for a in g['answers'].values():lengths[(g['model'],g['cond'])].append(len(a))
    counts['isolated_judge_repairs']=sum(len(load(p).get('isolated_repair_calls',[])) for p in (root/'judgments-shared').glob('*/*/*.json') if not p.name.endswith('.call.json'))
    return dict(counts),lengths


def render(summary,run_dir,private_dir,pr,include_holdout,followup=None,followup_private=None):
    labels=load(ASSETS/'eval.json')['cond_labels']
    source=load(ASSETS/'source/provenance.json')
    effects,findings=section_effects(summary,labels)
    tot=summary['cost_ledger']['totals']
    diag,lengths=diagnostic(run_dir/'public')
    private_diag,_=diagnostic(private_dir/'run') if include_holdout else ({},None)
    decisive='；'.join(f"{m}：{labels[c]}{'降低分数，原段有用' if kind=='helpful' else '提高分数，原段可能有害'}" for m,c,kind,cis in findings) or '没有删除段在两个公开切分上都通过28次比较的同时区间检验，不能据此宣布某段必需或应删除。'
    gains=[]
    for m in MODELS:
        cis=[next(r for r in summary[s] if r['model']==m and r['cond']=='none')['delta_bootstrap']['ci95'] for s in ('dev','validation')]
        if all(ci[1]<0 for ci in cis):gains.append(m+'的全文在dev与validation的普通95%区间下均提高得分')
        elif cis[0][1]<0:gains.append(m+'的dev全文收益为正，validation尚未确认')
        else:gains.append(m+'的跨切分全文收益尚未确认')
    out=[
      '# ljg-explain 第一套评测报告',
      '',
      '在这份题库与共同裁判下，'+'；'.join(gains)+'。本次不支持按单段删除的点估计排序或精简skill。',
      '',
      '已完成20题、两类被测模型、三个切分的9条件×5轮，以及保留集一次冻结确认；skill原文未修改。开发集与验证集的 full−none 效果如下，数值是通过率差、括号内为配对95%区间：',
      '',
      '| 模型 | dev full−none | validation full−none |','|---|---|---|',
      *[f'| {m} | {gain(summary["dev"],m)} | {gain(summary["validation"],m)} |' for m in MODELS],
      '',decisive,
      '',
      f"CLI自报费用合计 **${tot['reported_cost_usd']:.6f}**，未核实账单；另有 **{tot['unknown_cost_calls']} 次调用未返回USD**。无法把该小计称为总费用，也无法确认总账单≤$30。已用预留上限控制可观测自报费用，没有把未知费用记成$0。真实输出的裁判校准存在明显分歧，下列结果测量这套评分标准下的输出质量，不能证明读者已经学会。",
      '',
      '## 许可证与来源',
      '',
      f"上游 [lijigang/ljg-skills](https://github.com/lijigang/ljg-skills) 在锁定 commit `{source['commit']}` 的 [LICENSE](https://github.com/lijigang/ljg-skills/blob/{source['commit']}/LICENSE) 为 **MIT**，版权人为 lijigang（2026）。因此可复制并保留版权/许可声明。v1.0.2 的 [SKILL.md](https://github.com/lijigang/ljg-skills/blob/{source['commit']}/skills/ljg-explain/SKILL.md) 原样存于 `data/evals/explain/source/`，同时保存 LICENSE 与来源清单。核实依据是用户已有 upstream 克隆中的固定提交文件，不以最新分支替代锁定版本。",
      '',f"skill SHA256：`{source['skill_sha256']}`；许可证 SHA256：`{source['license_sha256']}`。",
      '',
      '## 题库、条件与统计口径',
      '',
      '20道稳定知识讲解题：dev 8、validation 8、holdout 4；中文10、英文10；概念6、公式9、机制5。领域包括统计、经济学、计算机、信息论、演化和物理。dev的似然、方差、正反馈三题与skill Examples主题重叠，dev可能受现有示范覆盖影响；validation八题换主题，不能只凭dev判定收益。公开题面、事实依据及已知合格参考输出在 cases.json；保留题面、依据、正文、裁判输出、评分和使用账本不公开。仓库中的 splits 注册保留集题数。',
      '',
      '无skill、完整skill与7个`##`段逐段删除。前言及其他段均保留，删除使用标题边界而非任意字符截断。所有公开条件两模型各5轮；每轮新CLI会话、16道公开请求，按固定种子打乱题序。题库oracle/rubric/参考答案不提供给被测模型。dev/validation分别平均当轮8题×10项检查，最终去掉五轮中的一个最高和一个最低后取均值。**n=5是整轮重复数，不是40个回答或400个检查的伪独立样本数。**',
      '',
      '保留集只在最终设计冻结后执行一次基准，覆盖两模型×9条件×5轮，共90个生成请求、360道作答；不在保留集挑选删除段。统一裁判后的预算余量允许保留两模型、20题、所有条件和n≥5。冻结文件包含commit、skill/题库/检查/runner哈希与设计；USAGE.log只有本次基准记账。无skill优化、无看过保留集后改skill或重新生成。',
      '',
      'bootstrap 10,000次，按题目与整轮两个维度同时有放回抽样；删除与full使用相同抽样索引，重算相同截尾统计量。普通区间为2.5%/97.5%分位数；公开28个删除比较另按Bonferroni尾概率给同时区间。固定SHA256导出的种子。区间不包含裁判系统偏差，少量题/五轮下也不能保证标称覆盖率。',
      '',
      '## 检查项',
      '',
      '| ID | 可观察的通过条件 |','|---|---|',
      *[f'| {k} | {v} |' for k,v in CHECKS.items()],
      '',
      '分数=通过项数/10，每题、每轮等权。规则对英文题A1/A2为N/A计通过，造成固定分数底座；不把它解释为理解能力。A1是首句关键词/开场白代理检查，不能保证核心判断语义。A3已在冻结前修复误把考试分数、概率分数式和条件性的“掌握”当自评分的错误；独立测试防止复发。真正漏答的题全10项失败；完整正文的JSON括号/引号/字面反斜线/平面或额外外层封装只按固定键边界恢复，原响应保留，不改正文。',
      '',
      '## 裁判与校准',
      '',
      '最终共同裁判请求名为`codex:gpt-6.1-sol`，看不到候选模型、条件、skill或参考正文，只看原题、事实oracle与回答。逐项给二元标签、理由、正文引句；不允许从别条输出借证据。格式/引句不合格才隔离补判，合法低分不重抽。省略零项占位的引句数组可由1位顺序唯一恢复，不改标签。GLM互裁试跑单批自报费用推算完整矩阵会超预算，保留试跑并计费后改为统一裁判，同一裁判的已完成输出可复用。',
      '',
      'Claude CLI的haiku/sonnet别名探测实际返回`glm-5.3-flash[1m]`，被测GLM使用该显式请求名；没有称其为Claude。Codex只返回请求模型和token，不独立证明实际后端。厂商独立性按名义路由只能对GLM候选成立；OpenAI候选与共同裁判同厂商，可能存在偏向。某些外层模型自称不作为后端身份证据。CLI包装系统提示也不相同，结果测的是本机这两个配置。',
      '',
      '标注由本任务Codex代理逐条写理由，**不是独立人类标注**。12条构造样本的标签在裁判前写入；初轮批量校准串用内容，随后原标签不变，逐样本隔离重校准。首次参考输出漏写后验归一化，已修正参考输出，原校准标签和分歧仍保留，不能把一致率当裁判准确率。另10条跨领域真实输出的标注未查看裁判标签，带独立校准前时间戳和逐项理由。',
      '',calibration_table(summary['calibration'],'### 12条构造样本（历史标签不改）'),
      '',calibration_table(summary['calibration_observed'],'### 10条真实输出（主要校准依据）'),
      '',
      '各分歧的双方逐项理由可在statistics.json及calibration*.json中审计。最终共同裁判真实输出标签一致率见上表，说明细粒度规则仍不稳定，尤其近例/迁移是否充分、缺失推导、简化是否构成事实错误。两个裁判都通过最终16条合格参考输出的全部语义检查，并拒绝16条故意破坏输出；这只是规则可用性，不是独立推广证据。',
      '',
      '## 各条件×模型分数',
      '',
      '每格：截尾均值 [bootstrap 95% CI]；n=5。',
      '', '### dev（8题）','',table(summary['dev'],labels),
      '', '### validation（8题）','',table(summary['validation'],labels),
    ]
    if include_holdout:
        out+=['','### holdout（4题、一次冻结确认）','',table(summary['holdout'],labels),
              '', 'full−none：'+'；'.join(m+' '+gain(summary['holdout'],m) for m in MODELS)+'。删除条件只存档作冻结确认，不据此挑选或改skill。']
    else:
        out+=['','保留集仅公开题数4；题面、分数表与原始结果不公开。']
    out+=['','## 哪些段起作用','',
          'Δ=删除条件−完整skill；负数表示删除后下降、原段有益，正数表示删除后上升。下表同时给普通95%差值区间与28次比较同时区间；只把两个公开切分同向、同时区间均排除0的情况当作本题库下的共同证据。单个切分显著不代表优化能通过验证集。',
          '',effects,'',decisive,
          '', ('[删除效果图]('+str(ROOT/'docs/explain-ablation-2026-10-13.png')+')' if include_holdout else '![删除效果与区间](explain-ablation-2026-10-13.png)'),
          '', '图中细线为配对95%区间，浅色粗线为28次比较同时区间，虚线为0。负差值表示删除后分数下降；所有普通95%区间均包含0。',
          '', '## Token、费用与异常','',
          f"全部探测、废弃校准、互裁试跑、服务重试、裁判隔离修复和最终调用都计入账本：{tot['calls']}次调用；input字段累计{tot['input_tokens']:,}，output字段累计{tot['output_tokens']:,}，缓存读取字段累计{tot['cached_input_tokens']:,}，缓存写入字段累计{tot['cache_creation_input_tokens']:,}。Codex input含缓存，GLM缓存字段另列；这些字段不能不加区别地再次相加。CLI已知自报USD总和${tot['reported_cost_usd']:.6f}，未知USD调用{tot['unknown_cost_calls']}次。路由costBasis为unknown、没有核验账单；Codex USD缺失。订阅分摊和实际结算价未知。",
          '',f"公开批次诊断：{diag.get('batches',0)}个整轮生成记录，{diag.get('recovered_batches',0)}批使用封装恢复，{diag.get('missing_answers',0)}道实际漏答，{diag.get('isolated_judge_repairs',0)}次最终裁判隔离修复。服务429等失败的公开请求单独归档并用同prompt重试；不把服务错误计为回答质量。保留集生成请求不重试。",
          '', '| 模型 | none平均字符数 | full平均字符数 |','|---|---|---|',
          *[f"| {m} | {statistics.mean(lengths[(m,'none')]):.1f} | {statistics.mean(lengths[(m,'full')]):.1f} |" for m in MODELS],
          '', '字符数不是token。full输出长度不同，效果不能全部归因于某条内容指令；没有等长度对照。',
          '', '## 复现与验证','',
          '原始公开CLI响应、usage、正文、裁判理由/引句、失败尝试及提示哈希归档在data/evals/explain/artifacts/public/；结果批次只追加。每轮公开数据生成dev和validation两条记录，费用仅在dev记录记生成费用，完整花费由独立账本汇总，避免重复相加。',
          '', '```sh',
          '# 在仓库根目录运行',
          'python3 scripts/explain/test_explain.py',
          'python3 scripts/explain/replay.py --out-dir .local-runs/explain-replay',
          'python3 scripts/explain/write_report.py --summary .local-runs/explain-replay/summary.json --run-dir data/evals/explain/artifacts --output .local-runs/REPORT.md'+(' --include-holdout' if include_holdout else '')+' --pr '+pr,
          'python3 scripts/build_site.py',
          '```','',
          '不带私有目录时只复现公开分数，写公开报告时去掉--include-holdout；匿名usage/费用收据仍可复现完整的自报费用账本。保留集题面/输出/判分结果始终不进入git。REPORT数字均从脚本和原始记录计算，不要求再调用模型。unit检查覆盖截尾统计量、配对重抽样、区间方向、固定种子、只删一个段、正文引句不可借用、传输恢复与规则误判。预定矩阵完整性、模型工具调用为零、源文件逐字相同、凭据扫描和保留题不泄漏也在交付前核验。',
          '', '## PR与局限','',f'PR：{pr}。只推explain-eval分支、只开PR；未推main、未合并、未发布release。',
          '',
          '本基准测讲解正文是否展示理解所需的关系，没有招募读者，也没有证明理解/学习增益。评测作者、参考答案作者和“人工式”标注者同为代理，非独立人工审核。跨领域真实输出的裁判一致率有限，bootstrap不覆盖判分错误。每轮多题共用上下文，题间可能互相影响；相同重复号题序配对，但模型随机种子/温度不能由CLI完全控制。英文题有中文作答，语言遵从不单独计分；A1/A2的英文N/A和A1表面代理会影响绝对分数。工具被要求禁用，Codex仍有自己的系统包装提示，无法把差异当纯模型能力。厂商分离仅为名义配置，OpenAI候选采用同厂商裁判；实际后端及总账单都缺独立核实。20题与5轮不足以支持广泛结论，没有按保留集改skill，没有宣称可以推广到所有领域。',
          '']
    if include_holdout:
        idx=next(i for i,s in enumerate(out) if s.startswith('公开批次诊断：'))
        out.insert(idx+1,f"保留集诊断：{private_diag.get('batches',0)}批，{private_diag.get('missing_answers',0)}题漏答；冻结记账与原始结果仅在私有目录。")
    if followup:
        out.insert(4, followup_conclusion(followup)+' 分词器参考计数的相关分析见“跨模型分歧”；实际路由分词器版本仍未知。\n')
        idx=out.index('## Token、费用与异常')
        out.insert(idx,render_followup(followup,followup_private if include_holdout else None))
        idx=out.index('python3 scripts/build_site.py')
        out[idx:idx]=[
            '# 分词器仅需首次联网下载；无模型调用。安装与下载命令见 scripts/explain/README.md。',
            '.local-runs/explain-followup-env/bin/python scripts/explain/followup.py --glm-tokenizer .local-runs/explain-followup/tokenizer.json --output .local-runs/explain-followup/public.json',
            '.local-runs/explain-followup-env/bin/python scripts/explain/test_followup.py']
        idx=next(i for i,s in enumerate(out) if s.startswith('python3 scripts/explain/write_report.py'))
        out[idx]+=' --followup .local-runs/explain-followup/public.json'
        # Follow-up must precede its report renderer in the reproduction recipe.
        cmd=out.pop(idx)
        out.insert(out.index('python3 scripts/build_site.py'),cmd)
    return '\n'.join(out)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--summary',type=pathlib.Path,required=True)
    ap.add_argument('--run-dir',type=pathlib.Path,required=True)
    ap.add_argument('--private-dir',type=pathlib.Path)
    ap.add_argument('--output',type=pathlib.Path,required=True)
    ap.add_argument('--include-holdout',action='store_true')
    ap.add_argument('--pr',default='待创建')
    ap.add_argument('--followup',type=pathlib.Path,default=ASSETS/'batches/2026-10-13-explain-followup-v1.json')
    ap.add_argument('--followup-private',type=pathlib.Path)
    args=ap.parse_args()
    if args.include_holdout and args.private_dir is None:
        ap.error('--include-holdout requires --private-dir')
    if args.include_holdout and args.output.resolve().is_relative_to(ROOT.resolve()):
        ap.error('holdout report must stay outside repository')
    text=render(load(args.summary),args.run_dir,args.private_dir,args.pr,args.include_holdout,
                load(args.followup) if args.followup.exists() else None,
                load(args.followup_private) if args.followup_private else None)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text)
    print(args.output)


if __name__=='__main__':main()
