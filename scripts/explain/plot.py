"""Static scientific forest plot of public deletion effects, no holdout data."""
import argparse
import pathlib
from run import ROOT, ASSETS, MODELS, load


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    ap=argparse.ArgumentParser()
    ap.add_argument('--summary',required=True,type=pathlib.Path)
    ap.add_argument('--output',required=True,type=pathlib.Path)
    args=ap.parse_args()
    data=load(args.summary)
    labels={'-1':'1 Reader / delivery','-2':'2 Understanding','-3':'3 Formulas / principles',
            '-4':'4 Chinese style','-5':'5 Evidence / layout','-6':'6 Gotchas','-7':'7 Examples'}
    font_path=pathlib.Path('/System/Library/Fonts/PingFang.ttc')
    font=FontProperties(fname=str(font_path)) if font_path.exists() else FontProperties()
    conds=[f'-{i}' for i in range(1,8)]
    colors=['#245cb0','#c05c19']
    fig,axes=plt.subplots(1,2,figsize=(12,5.8),sharey=True)
    for ax,split in zip(axes,['dev','validation']):
        for j,m in enumerate(MODELS):
            for i,c in enumerate(conds):
                r=next(r for r in data[split] if r['model']==m and r['cond']==c)
                d=r['delta_vs_full'];low,high=r['delta_bootstrap']['ci95'];sim=r['delta_bootstrap']['simultaneous_ci']
                y=i+(j-.5)*.24
                ax.plot(sim,[y,y],color=colors[j],alpha=.22,lw=5)
                ax.errorbar(d,y,xerr=[[d-low],[high-d]],fmt='o' if j==0 else 'D',capsize=3,color=colors[j],ms=5,
                            label=['gpt-5.6-luna','GLM-5.3-flash'][j] if i==0 else None)
        ax.axvline(0,color='#333333',ls='--',lw=1)
        ax.set_title(split+' · 8 tasks × 5 runs',fontsize=12)
        ax.set_xlabel('Δ score = ablation − full',fontsize=11)
        ax.grid(axis='x',alpha=.2)
        ax.set_yticks(range(7),[labels[c] for c in conds],fontproperties=font,fontsize=11)
        ax.set_ylim(6.65,-.65)
    fig.suptitle('Deletion effects on rubric scores (negative = original section helps)',fontsize=14)
    handles,names=axes[0].get_legend_handles_labels()
    fig.legend(handles,names,loc='upper center',bbox_to_anchor=(.57,.935),ncol=2,fontsize=10)
    fig.text(.5,.01,'Thin bars: paired bootstrap 95% CI. Pale bars: Bonferroni simultaneous intervals (28 comparisons).',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.04,1,.86))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(args.output,dpi=180)
    print(args.output)


if __name__=='__main__':main()
