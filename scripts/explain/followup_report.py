"""Render only audited numerical follow-up artifacts; no tokenizers required."""
from run import ASSETS, load


def ci(xs):
    return '['+', '.join(f'{x:.3f}' for x in xs)+']'


def table(rows,labels):
    out=['| 删除段 | GPT Δ [95% CI] | GPT p（Holm） | GLM Δ [95% CI] | GLM p（Holm） | 交互 I [95% CI] | I p（原始 / Holm） | 分歧判断 |',
         '|---|---|---|---|---|---|---|---|']
    for row in rows:
        a,b=row['models']; i=row['interaction']
        opposite=a['delta']*b['delta'] < 0 and a['significant'] and b['significant']
        verdict=('显著方向相反' if opposite else '显著幅度不同') if i['significant'] else '未检出显著交互'
        out.append(f"| {labels[row['cond']]} | {a['delta']:+.3f} {ci(a['ci95'])} | {a['p_holm']:.4f} | {b['delta']:+.3f} {ci(b['ci95'])} | {b['p_holm']:.4f} | {i['delta']:+.3f} {ci(i['ci95'])} | {i['p_raw']:.4f} / {i['p_holm']:.4f} | {verdict} |")
    return '\n'.join(out)


def conclusion(data):
    tests=[r['interaction'] for rows in data['splits'].values() for r in rows]
    count=sum(t['significant'] for t in tests)
    if count:
        return f'公开切分的 {len(tests)} 个模型×删段交互项中，{count} 个通过 Holm 校正；显著项见下表，未通过项不标为跨模型分歧。'
    return f'公开切分的 {len(tests)} 个模型×删段交互项均未通过 Holm 校正，未检出显著的跨模型删段分歧；这不证明两模型效果相同。'


def render(data,private=None):
    labels=load(ASSETS/'eval.json')['cond_labels']
    provenance=load(ASSETS/'tokenizer-provenance.json')
    out=['## 跨模型分歧','',conclusion(data),'',
        'GLM 已纳入被测模型：`claude:glm-5.3-flash[1m]`，另一配置为 `codex:gpt-5.6-luna`。本轮只重算已有原始输出，新增生成与裁判调用均为 0，新增评测调用费用为 $0；不含本轮执行代理的会话费用（未获账单）。',
        '', '### 模型 × 删段交互检验','',
        'Δ=删除−完整，I=Δ(GLM)−Δ(GPT)，负 I 表示删除对 GLM 更不利。保留每轮五次重复的去一高一低均值；共同抽取题目，在同一模型内对删除与完整条件配对抽取轮次。两模型轮次独立抽样：相同重复号虽使用相同题序，却不能证明两条路由的生成噪声配对。模型内差值沿用原 10,000 次重抽样及种子；交互项重抽样 50,000 次，均给百分位 95% 区间。',
        '',
        '检验零假设 Δ=0 或 I=0，双侧、以零假设为中心的 bootstrap p=(1+#{|T*−T|≥|T|})/(B+1)。对 dev 与 validation 合计 28 个模型内删除检验统一做 Holm 校正，另对两个切分合计 14 个交互检验统一做 Holm 校正；显著门槛为校正 p<0.05。普通 95% 区间用于展示不确定性，显著标记以校正 p 为准；前节保留的 Bonferroni 同时区间属于原有分析。p 值和区间都是少题、少轮、非光滑截尾统计量下的近似推断，不覆盖裁判偏差。仅交互显著才标“幅度不同”；“方向相反”还须两模型差值相反且各自通过校正。',
        '', '### dev（公开）','',table(data['splits']['dev'],labels),
        '', '### validation（公开）','',table(data['splits']['validation'],labels)]
    if private:
        out += ['', '### holdout（只作参考）','',
            '冻结结果离线重算，未重跑、未据此挑选段落。此处模型内 14 项、交互 7 项各自做 Holm 校正，均不进入公开发现或相关性分析。',
            '',table(private['rows'],labels)]
    else:
        out += ['', '保留集交互仅作非公开参考；公开制品不包含保留集分数或题面。']
    gpt=provenance['gpt']; glm=provenance['glm']; tokens=data['tokens']
    out += ['', '### 分词器依据与 token 数','',
        '两条 CLI 路由实际使用的分词器及版本均未获独立确认：原始调用只记录模型请求名/路由返回名与整批 usage，没有分词器标识。GPT 的实际分词器查不到；[官方模型页]('+gpt['sources'][0]+')未指定编码，`tiktoken 0.12.0` 对精确请求名调用 `encoding_for_model` 抛出 `KeyError`。下表 GPT 列使用显式指定的 `o200k_base` **探索代理**，不能称为该路由的真实 token 数。[OpenAI 计数文档]('+gpt['sources'][1]+')也区分本地纯文本计数与含消息格式的模型请求计数。',
        '',
        'GLM 列使用 [Z.ai 官方模型仓库]('+glm['sources'][0]+')的 `tokenizer.json`，锁定 revision `'+glm['revision']+'`，以 `tokenizers 0.22.1` 加载 BPE，关闭额外特殊 token。它是该公开模型的分词器参考，路由部署版本仍未知。文件 SHA256 为 `'+glm['tokenizer_sha256']+'`；GPT 合并表指纹为 `'+gpt['merge_ranks_sha256']+'`，依据与校验方法保存于 `tokenizer-provenance.json`。未使用字符数代替 token 数，也未从整批 usage 减法反推 skill token。',
        '',
        '计数对象是运行器实际拼入的原始 skill 字符串（含前言、标题和空白），不含题面、外层提示、聊天模板或 BOS/EOS。段落按相同 `##` 边界提取。独立段落计数与 full−变体计数可能不同，因为删除边界会改变相邻 token 合并。',
        '', '| skill 变体 | GPT：o200k_base 代理 | GLM：官方公开参考 |','|---|---|---|']
    for c,counts in tokens['variants'].items():
        out.append(f'| {labels[c]} | {counts[0]} | {counts[1]} |')
    out += ['', '| 被删段 | GPT 段落 token | GLM 段落 token | GPT 有效减少量 | GLM 有效减少量 |',
            '|---|---|---|---|---|']
    for c,r in tokens['deleted_sections'].items():
        a,b=r['tokens']; x,y=r['effective_reduction']
        out.append(f'| {labels[c]} | {a} | {b} | {x} | {y} |')
    out += ['', '### “分词器差异能解释分歧”的探索分析','',
        '分析单位为 7 个删除段，dev 与 validation 分开。响应变量为上表 I；主解释变量为 GLM 与 GPT 参考编码的有效减少比例之差：x=(full−变体)/full 的 GLM 值−GPT 值。另给有效减少 token 数之差作长度敏感性检查。Pearson 衡量线性关系，Spearman 衡量秩关系；双侧 p 遍历 7!=5,040 个响应排列，并对 2 切分×2 解释变量×2 相关系数共 8 项统一 Holm 校正。未把同一段在两切分当成 14 个独立样本，保留集不参与。',
        '', '| 切分 | 解释变量 | 方法 | n（段） | 相关系数 | 精确排列 p | p（Holm） |','|---|---|---|---|---|---|---|']
    for r in data['correlations']:
        name='有效减少比例之差' if r['predictor']=='relative_reduction_gap' else '有效减少 token 数之差'
        out.append(f"| {r['split']} | {name} | {r['method']} | {r['n']} | {r['r']:+.3f} | {r['p_raw']:.4f} | {r['p_holm']:.4f} |")
    found=any(r.get('significant') for r in data['correlations'])
    verdict='存在通过校正的探索性相关，仍不能作因果解释。' if found else '没有相关检验通过校正，本轮未得到“分词器差异解释分歧”的证据。'
    out += ['', verdict+'只有 7 个段落，段长、内容与指令功能同时变化，所有删除共享同一全文基线，且响应是含抽样误差的效果估计。排列检验依赖段落可交换的探索假设，并非随机分词器实验；未显式建模各效果估计的不确定性。GPT 实际编码未知，因此这只检验两种参考编码的长度差异，不能否定实际分词器的作用，也不能证明因果解释。',
        '', '本轮新增数字见 `2026-10-13-explain-followup-v1.json`，由原始公开生成/裁判归档重放；原 score、skill、题库和保留集冻结设计均未修改。']
    return '\n'.join(out)+'\n'
