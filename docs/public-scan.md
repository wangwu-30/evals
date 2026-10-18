# Public-content pre-push check

Install the hook in each clone:

```sh
git config core.hooksPath scripts/hooks
```

Before pushing, commit the intended content and run:

```sh
python3 scripts/test_check_public.py
python3 scripts/check_public.py
```

The check reads every blob in HEAD and every added line in every outgoing
commit, including content later deleted. The hook supplies ref updates on stdin;
new branches use origin/main as their base. Standalone checks default to
origin/main..HEAD; use `--range BASE..TIP` for another range. Missing objects
or malformed input block the push. Outgoing tip trees are checked as well.

Findings show the file, line, category and a fully masked excerpt. A nonzero
exit code blocks publication. Fix findings first. A demonstrably harmless
match may have an exact `path:line:category  # reason` entry in
`scripts/public_scan_allow.txt`. Review every entry and include it with its
reason in the PR description. An exemption only applies to that exact current
line, so a different historical line at the same position is still blocked.
Pattern definitions and fictitious test samples have no file-wide exemption.

The checker is a heuristic, not proof of absence of sensitive content; review
new data and documentation as well. It does not scan uncommitted changes.
