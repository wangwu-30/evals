"""Replay only archived public raw data; private holdout is optional, no LLMs."""
import argparse
import pathlib
import subprocess
import sys
import tempfile
from run import ROOT


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--private-dir',type=pathlib.Path,default=None)
    ap.add_argument('--out-dir',type=pathlib.Path,required=True)
    ap.add_argument('--draws',type=int,default=10000)
    args=ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='explain-replay-', dir=args.out_dir) as td:
        root=pathlib.Path(td)
        input_dir = args.private_dir or root/'unused'
        # No copy of holdout ever enters the checkout or temporary public root.
        (root/'public').symlink_to(ROOT/'data/evals/explain/artifacts/public',target_is_directory=True)
        subprocess.run([sys.executable,str(ROOT/'scripts/explain/summarize.py'),'--run-dir',str(root),
                        '--private-dir',str(input_dir),'--out-dir',str(args.out_dir),'--draws',str(args.draws)],check=True)
    print('Includes private holdout:',bool(args.private_dir and (args.private_dir/'run/generations').exists()))


if __name__=='__main__':main()
