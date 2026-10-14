"""Create public cases and verify the existing four private cases outside the repo.

Use once, before freezing a run. Generated assets are committed, so replay does
not need to execute this authoring utility. Stable textbook cases need no network.
"""
import argparse
import hashlib
import json
import pathlib
from checks import CHECKS

ROOT = pathlib.Path(__file__).resolve().parents[2]
UPSTREAM = '2c82b3d06a2d84405ec971d21c64f71b6a8dd900'

# prompt, oracle, purpose, recognition, mechanism, sensitivity, transfer.
CASES = [
 ('d01','dev','zh','formula','似然', '给只懂高中概率的人讲解似然，以及它和后验概率的关系。',
  '固定数据比较参数；L(theta)=P(data|theta)不是P(theta|data)。假设H1硬币p=.5、H2 p=.8，指定顺序HH的似然.25和.64；后验要先验和归一化。',
  '似然用已经看到的数据比较不同假设对这批数据的解释能力。',
  '假设两枚硬币正面率分别为0.5和0.8，已观察指定顺序HH；比较这份数据的概率是似然，问哪枚硬币更可能还需要先验。',
  '独立抛掷时两次概率相乘，似然为0.25和0.64；这是数据在各假设下的概率，不是硬币的后验。后验要把各似然乘以先验，再除以这些权重之和。',
  '保持HH不变，若第二枚的正面率从0.8改成0.2，它的似然变为0.04，支持次序反转。',
  '在缺陷检测中，也可固定同一批测试结果比较两种故障假设，但决定故障后验仍要故障先验。'),
 ('d02','dev','en','formula','variance', 'Explain population variance to someone who knows averages but no statistics.',
  'Population variance of [1,3] is 1, mean2, squared units; sample unbiased variance2 for n=2. Squaring is not uniquely forced by avoiding cancellation.',
  'Population variance measures spread that an average alone hides.',
  'Assume the complete population is [1,3]; it has mean 2, just like [2,2], but only the first pair is spread out.',
  'Its deviations are -1,+1; squared deviations average to (1+1)/2=1 in squared units. Dividing by n-1 instead estimates population variance from a sample; squaring emphasizes large deviations, rather than being the only possible spread measure.',
  'Keep the mean and population size fixed and change the distance from the mean: [0,4] gives (4+4)/2=4.',
  'Two machines may have the same average delivery time; comparing squared deviations of their complete delivery records reveals which is less consistent.'),
 ('d03','dev','zh','mechanism','正反馈', '讲解正反馈为什么会放大变化，以及为何不等于好事。',
  '反馈正负指方向不是好坏；环路有放大条件和饱和限制，增强不保证无限增长。',
  '正反馈会把初始变化沿回路送回来继续增强，方向的“正”不代表好坏。',
  '教学假设：麦克风拾取扬声器声音后再次放大；温度升高后空调加强降温则是反向作用。',
  '声音经麦克风、放大器、扬声器再回到麦克风，若每圈回来的增量更大就增长；设备饱和会限制增长。',
  '保持位置和音量输入不变，只降低环路增益到衰减区，啸叫会减弱而非持续放大。',
  '传言引来关注、关注又扩大传言传播，也有同向回路；只有反馈足够强且未触及限制时才明显放大。'),
 ('d04','dev','en','concept','opportunity cost', 'Explain opportunity cost for a beginner deciding how to use a free afternoon.',
  'Value of best forgone alternative, not sum of all alternatives or only money already spent; sunk costs excluded.',
  'Opportunity cost is the value of the best alternative you give up when choosing.',
  'Assume you can earn $40 tutoring or enjoy a walk valued at $25 that afternoon; choosing the walk forgoes $40, not $65. A non-refundable fee paid yesterday is a sunk cost.',
  'The same time cannot serve both options, so the feasible next-best choice sets the cost, even when the chosen activity costs no cash.',
  'Hold the afternoon and walk value fixed; if available tutoring pays only $10, the walk now has a lower opportunity cost.',
  'A factory choosing between two products on one machine also sacrifices its best feasible alternative output; an idle machine with no alternative has no such forgone benefit.'),
 ('d05','dev','zh','formula','贝叶斯', '给高中生讲解贝叶斯公式如何从阳性检测推到患病概率。',
  'Teaching example prior1%, sensitivity90%, specificity90%; among1000 9 truepositive99 falsepositive, posterior9/108=8.33%. Not medical advice.',
  '贝叶斯公式把阳性检测和原先患病比例合起来，回答阳性者中有多少真正患病。',
  '假设1000人中10人患病，灵敏度和特异度都为90%；“病人测阳性的概率”与“阳性者患病的概率”方向不同。',
  '10位病人中9人阳性，990位非病人中99人阳性，阳性者患病概率为9/(9+99)≈8.3%。分母合并所有阳性，分子只留患病阳性。',
  '保持两项检测性能不变，只把患病比例改为50%，同样1000人有450个真阳性和50个假阳性，后验变为90%。',
  '垃圾邮件过滤也把某个词在垃圾与正常邮件中的出现率和垃圾邮件先验合并；仅见到这个词还不能直接认定垃圾邮件。'),
 ('d06','dev','en','mechanism','cache', 'Explain cache invalidation in a web application to a beginner.',
  'Stale cached copies after origin mutation; TTL vs explicit invalidation; distributed races and eventual freshness, do not claim perfect TTL consistency.',
  'Cache invalidation prevents an old saved result from outliving the change that made it wrong.',
  'Imagine a shop caching a product price: an unchanged price is a valid cache hit, but a hit after the database price changes can return stale data.',
  'The cache bypasses a database read; deleting or replacing its entry after a price update forces the next read to obtain the new price. A TTL only bounds staleness and does not synchronize all readers.',
  'Hold traffic and update timing fixed; shorten the TTL from ten minutes to one minute, reducing the stale window while increasing database reads.',
  'A DNS record also has cached copies and expiry: the same origin-change/copy-lifetime relation explains why an address change may take time to appear, though its protocol differs.'),
 ('d07','dev','zh','concept','相关', '用一个具体例子讲解相关与因果怎样区分。',
  'Common cause, observational association insufficient, causal interventions need assumptions; icecream/drowning seasonal toy not actualdata.',
  '相关表示一起变化，因果还要求一个变化能在合适条件下改变另一个。',
  '假设夏天冰淇淋销量和溺水事件同时增加；这能体现相关，但共同的炎热天气可同时增加销量和游泳人数。',
  '“炎热→销量”和“炎热→下水人数→溺水”两条路径足以产生一起上升，不需要冰淇淋导致溺水。',
  '保持天气和下水人数固定，只减少冰淇淋销售；上述模型不会因此减少溺水，若真实结果不同还需重新检查模型与干预条件。',
  '学校中课外阅读和成绩一起提高，也需检查家庭支持等共同原因；仅凭成绩相关无法确定阅读的因果效果。'),
 ('d08','dev','en','formula','compound', 'Explain compound growth and why the starting amount matters.',
  'A=P(1+r)^t fixedrate discreteperiods, P100 r10% t2 =>121, not120; r20%=>144, no guaranteedfinancialreturns.',
  'Compound growth applies each period’s growth to the amount already accumulated.',
  'Assume $100 grows at a fixed 10% per year for two years with no withdrawals; simple growth adds $10 each year, while compounding uses the changing balance.',
  'A=P(1+r)^t: P is the starting amount, r the per-period rate, and t the number of periods. $100 becomes $110, then $121 because the second gain is $11, not $10. This is a hypothetical calculation, not a promised return.',
  'Keep the starting amount and two periods fixed; changing the rate to 20% yields 100×1.2²=$144.',
  'A bacterial population under a constant growth factor also multiplies its current size each period; resource limits can break that assumption.'),
 ('v01','validation','zh','concept','过拟合', '给没有机器学习背景的人讲解过拟合。',
  'Low trainingerror not guaranteegeneralization; memorize noise, heldout leakage invalidates evaluation; no claim modelcomplexityalwaysbad.',
  '过拟合会把训练样本里的偶然细节也记住，因此旧题表现好，新题可能变差。',
  '假设模型预测房价；记住每栋训练房子的成交价可做到旧房零误差，学到面积等稳定关系则更有机会用于新房，零误差本身不能判定过拟合。',
  '样本噪声并不稳定；模型用它减少训练误差时，新房不再有相同细节，预测便偏离。',
  '保持模型和评估方式固定，只增加来自同一分布的独立训练样本，偶然细节更难支撑规则，过拟合风险通常下降，但不保证归零。',
  '学生背答案而不会解新题也体现旧样本记忆和新情境应用的差别；这个类比不代表机器像人一样理解，新房评估仍要独立留出数据。'),
 ('v02','validation','en','formula','precision', 'Explain precision and recall using a small search-result example.',
  'TP3 FP1 FN2 ->precision3/4 recall3/5; cannot freely assume threshold guaranteesperformance, bothdenominatorsdefinequestion.',
  'Precision asks how many returned results are relevant; recall asks how many relevant results were found.',
  'Assume a collection has five relevant documents and a search returns four documents, three relevant. The returned set and the full relevant set are different denominators.',
  'Precision is TP/(TP+FP)=3/4; recall is TP/(TP+FN)=3/5. The first measures trust in the returned list, the second coverage of what exists.',
  'Keep the collection fixed and add one missed relevant document to the result set without adding irrelevant ones: precision becomes 4/5 and recall 4/5. Removing a relevant result instead loses coverage.',
  'A factory’s defect detector can use the same ratios for flagged items and all truly defective items; evaluating recall still requires knowing missed defects.'),
 ('v03','validation','zh','mechanism','自然选择', '讲解自然选择如何改变一个种群，避免把它讲成动物主动努力。',
  'Heritablevariation differentialreproduction acrossgenerations, not purposeful individualchange, fitnessenvironment dependent.',
  '自然选择使能遗传且有利于繁殖的差异在多代种群中逐渐增多。',
  '假设甲虫有可遗传的深浅体色，深色背景上鸟更容易发现浅色甲虫；甲虫临时染黑虽相似，却不一定把改变传给后代。',
  '原有差异影响存活和繁殖，深色个体留下更多后代，于是下一代深色比例可能提高；过程没有预定目标，也不是个体主动改变基因。',
  '保持遗传差异和捕食者固定，只把背景改成浅色，隐蔽优势可能转向浅色，原先的判断也随之改变。',
  '细菌群体已有耐药遗传差异时，药物环境会改变不同变体留下后代的机会；条件仍是可遗传差异和繁殖差别。'),
 ('v04','validation','en','concept','idempotency', 'Explain idempotency to a developer who is learning distributed systems.',
  'Repeatedoperation sameeffect not necessarilyresponse; repeatedPUTset vs increment; dedupkeyscope retention atomicity boundaries.',
  'Idempotency means repeating an operation has the same intended effect as performing it once.',
  'Setting a record’s state to “closed” twice is idempotent; incrementing its counter twice is not, even if both calls return “OK”.',
  'A fixed assignment reaches the same state after repetition, while an increment uses the current state and adds again. For hypothetical retries, a stored request key can suppress duplicate increments if the check and update are atomic.',
  'Keep the retried request fixed but expire its stored key: a later retry may increment again, so deduplication only works within its retention and scope.',
  'A payment endpoint can store a transaction key to prevent duplicate charges; the same identity/atomic-record relation applies, but identical text alone does not identify the same payment.'),
 ('v05','validation','zh','formula','熵', '讲解信息熵，说明为什么均匀概率通常更不确定。',
  'H=-sum p log2p bits; faircoin1bit deterministic0; entropyofdistribution not individualsequence meaning/quality.',
  '信息熵衡量一个概率分布下，结果尚未出现时平均有多不确定。',
  '假设一枚公平硬币，正反各半；另一枚总是正面。两者都可能看到正面，但预测难度不同，熵描述分布而非某一次结果的意义。',
  'H=-Σp log₂p：p是各结果概率，单位为比特。公平硬币算得-2×0.5×(-1)=1比特；确定结果为0，零概率项按极限取0。',
  '保持两个可能结果固定，只把概率改成0.9和0.1，熵约0.469比特，因结果更易预测而降低。',
  '明天只有“晴”“雨”两种教学假设时，也可用概率分布算预测不确定性；熵不衡量天气好坏或信息真假。'),
 ('v06','validation','en','mechanism','deadlock', 'Explain deadlock with a small resource-allocation example.',
  'Circularwaiting with exclusive locks and holdandwait, consistentordering breakscycle not allcontention; removingone process not alwaysglobalfailure.',
  'Deadlock occurs when waiting tasks prevent one another from making the progress needed to release resources.',
  'Assume task A holds exclusive lock X and waits for Y, while B holds Y and waits for X. One task waiting for a lock that another will soon release is ordinary contention, not this cycle.',
  'Neither can continue to its release step: A needs B’s resource and B needs A’s. The exclusive locks and hold-while-waiting rule sustain the cycle.',
  'Keep the two tasks and resources, but require both to acquire X before Y: B cannot hold Y while waiting for X, breaking this cycle while contention remains.',
  'Two trains occupying sections and each waiting for the other’s section can share the same exclusive-resource waiting cycle; actual railway rules determine whether that model applies.'),
 ('v07','validation','zh','concept','公共物品', '给初学者讲解经济学里的公共物品和搭便车。',
  'Nonrival and nonexcludable not simplygovernmentprovided or free; congestible tolledroads differ; incentiveproblem not automaticzero provision.',
  '公共物品的关键是使用通常不减少别人可用的份额，也难把未付费者排除。',
  '在简化情境中，一盏街灯照亮整条街，多一个行人不明显减少照明，收费排除路人也难；免费发的一份面包会被吃掉，不能因此算公共物品。',
  '每人都能受益却难单独收费，有人便可能等待别人出钱，导致私人筹资不足；这并不证明无人会自愿贡献。',
  '保持照明服务不变，只让街区可通过门禁排除未付费者，就改变了排他性，成为更接近俱乐部物品的安排。',
  '公开的防灾警报也可能满足共同使用和难排除两项条件；若系统只向付费设备发送，排他条件便不同。'),
 ('v08','validation','en','formula','Little', 'Explain Little’s law for an introductory queueing class.',
  'L=lambda W stable longrun matchingboundaries units;2customers/min*3min=6; noPoissonneeded, waitingtimeversussystemtime match.',
  'Little’s law connects the average number in a stable system to the arrival rate and average time spent there.',
  'Assume a stable café averages two customer arrivals per minute and three minutes from entry to exit. Customers in the café and customers only waiting in line are different system boundaries.',
  'L=λW gives 2 customers/minute × 3 minutes = 6 customers on average. Each arrival contributes its residence time, so the long-run accumulated customer-time divided by observation time yields the same average occupancy; no Poisson assumption is required.',
  'Hold arrival rate and the stable café boundary fixed; reduce average residence to two minutes and L becomes four customers.',
  'Stable network requests in flight obey the same rate-times-latency relation, provided latency and request count refer to the same boundary and arrivals do not exceed sustainable service.'),

]


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--private-dir', required=True, type=pathlib.Path)
    args = ap.parse_args()
    tasks = []
    for cid, split, lang, kind, keyword, prompt, oracle, *sentences in CASES:
        tasks.append(dict(id=cid, split=split, language=lang, kind=kind, keywords=[keyword], prompt=prompt,
                          oracle=oracle, reference=' '.join(sentences), reference_parts=sentences))
    keywords = {'d01':['似然','固定数据'],'d03':['正反馈','同向','放大'],'d05':['贝叶斯','阳性','患病'],'d07':['相关','因果'],'v01':['过拟合','训练','新题'],'v03':['自然选择','遗传','后代'],'v05':['熵','不确定'],'v07':['公共物品','非排他','非竞争']}
    for t in tasks:
        if t['id'] in keywords: t['keywords'] = keywords[t['id']]
    public = [t for t in tasks if t['split'] != 'holdout']
    private = json.loads((args.private_dir/'cases.json').read_text())
    assert len(private) == 4 and all(t['split'] == 'holdout' for t in private)
    write(ROOT/'data/evals/explain/cases.json', public)
    skill_path = ROOT/'data/evals/explain/source/SKILL.md'
    import re
    headings = re.findall(r'(?m)^## (.+)$', skill_path.read_text())
    labels = {'none':'无 skill', 'full':'完整 skill'} | {f'-{i}':'删 '+h for i,h in enumerate(headings,1)}
    for eid, split, title, order in [('explain','dev','ljg-explain · 开发集',8),('explain-validation','validation','ljg-explain · 验证集',9)]:
        write(ROOT/f'data/evals/{eid}/eval.json', dict(id=eid,title=title,kind='matrix',order=order,
              description='20题基准的'+split+'切分；每格5次独立批量作答，每次8题×10项检查等权平均，按5次截尾均值。六项盲裁判语义检查+四项规则；原始正文及裁判理由可审计。',
              task_file='task.md',checks=CHECKS,cond_labels=labels,baseline='full',null_cond='none',split=split))
        (ROOT/f'data/evals/{eid}/task.md').write_text('题面与判定依据见 '+('cases.json' if split=='dev' else '../explain/cases.json')+'，筛选 split='+split+'。任务只要求讲解，不把评分标准或参考答案给被测模型。默认面向有日常经验的成年人。\n每次所有公开题独立作答，JSON仅是传输封装，检查的是每道讲解正文。\n')
    write(ROOT/'data/evals/explain/source/provenance.json',dict(repository='https://github.com/lijigang/ljg-skills',commit=UPSTREAM,
          path='skills/ljg-explain/SKILL.md',version='1.0.2',license='MIT',license_path='LICENSE',
          skill_sha256=hashlib.sha256(skill_path.read_bytes()).hexdigest(),license_sha256=hashlib.sha256((skill_path.parent/'LICENSE').read_bytes()).hexdigest(),sections=headings))
    (ROOT/'data/evals/explain/source/README.md').write_text(f'Vendored verbatim from https://github.com/lijigang/ljg-skills/blob/{UPSTREAM}/skills/ljg-explain/SKILL.md (v1.0.2).\nMIT License, copyright (c) 2026 lijigang. LICENSE preserved alongside SKILL.md. No skill edits were made.\n')
    # Predeclared, agent-written manual-style labels; these are not human review.
    samples = []
    t = public[0]
    for i in range(12):
        parts = list(t['reference_parts'])
        expected = '111111'
        why = ['明确固定数据比较假设的用途','硬币似然与后验对照并指出先验','0.25/0.64计算与条件方向正确','HH固定，仅把p从.8改.2并反转','故障检测是不同情境且沿用固定数据比较','明确假设且没有类比或实证夸大']
        if i in range(1,6):
            removed = i-1
            parts[removed] = ''
            # S1 still appears in recognition; S3 still supports recognition.
            # To create unambiguous negatives, replace with a minimal fragment.
            fragments = {
                1: ('似然是P(D|H)。', '000001', ['无具体问题用途','无典型/混淆对照','无数值或推导','无条件变化','无迁移','稳定定义正确，无额外经验断言']),
                2: ('似然用固定数据比较假设的解释能力。假设硬币H1的p=.5，H2的p=.8，指定顺序HH的概率分别为.25和.64，因为独立概率相乘。保持HH固定，把H2的p改成.2，似然为.04，支持次序反转。缺陷检测也可固定结果比较故障假设，需要独立性和合适概率模型。', '101111', ['用途具体','无混淆对照如后验','HH概率正确且解释乘法','固定数据改变p','缺陷检测共享关系和条件','假设明确且无事实错误']),
                3: ('似然用固定数据比较假设的解释能力。假设硬币H1的p=.5，H2的p=.8；似然问数据在假设下的概率，后验问假设在数据后的概率且需要先验。保持数据HH固定，把H2的p改成.2，就比p=.8更不支持H2。缺陷检测也可固定测试结果比较故障假设，需要相同观测和合适概率模型。', '110111', ['用途具体','明确两个条件方向作对照','没有简单数值计算，公式类失败','固定HH改变p并正确比较','故障检测共享关系和条件','无错误，假设明确']),
                4: (' '.join(t['reference_parts'][:3]+t['reference_parts'][4:]), '111011', ['用途具体','似然后验明确对照','HH乘法和数值正确','未在原情境改变条件','故障检测共享关系和先验边界','假设明确无错误']),
                5: (' '.join(t['reference_parts'][:4]), '111101', ['用途具体','条件方向对照','正确计算','固定HH改变p','没有表面不同的新情境','假设明确无错误']),
            }
            answer, expected, why = fragments[i]
        else:
            answer = ' '.join(parts)
        if i == 6:
            answer = answer.replace('0.25和0.64','0.25和0.16')
            expected = '110110'; why[2]='0.8²误写成0.16'; why[5]='存在实质算术错误'
        if i == 7:
            answer += ' 这些似然就是两枚硬币的后验概率。'; expected='110110'; why[2]='结尾混淆似然和后验，推导整体不正确'; why[5]='结尾与条件方向矛盾'
        if i == 8:
            answer += ' 似然就像给嫌疑人打分，分数越大越可疑。'; expected='111110'; why[5]='新增类比没有说明失效处，且可疑度与似然方向不稳定'
        if i == 9:
            answer = '好的，下面我来解释。 '+answer; why[0] += '；开场规则独立失败'
        if i == 10:
            answer += ' 我给这个讲解自评90分，你已经完全掌握了。'; why[5] += '；理解断言和自评分由A3单独处理'
        if i == 11:
            answer = answer.replace('不是硬币的后验','不是后验概率，而是数据概率')
        samples.append(dict(id=f'cal-{i:02d}', task_id=t['id'], task=t, answer=answer, expected_bits=expected, manual_reasons=why,
                            annotation_mode='agent-manual-style-seeded', annotated_before_judge=True))
    write(ROOT/'data/evals/explain/calibration.json',samples)
    print('Created 16 public + 4 private tasks and 12 pre-annotated calibration samples.')


if __name__ == '__main__':
    main()
