Claude finished the response
Ran 6 commands, viewed a file

Diagnosed multi-day posting outage caused by progress-recap review deadlock.

Investigated regression timeline by analyzing file timestamps and modification history.

Reconciled reconstructed workflow files with actual runtime behavior.

Reconstructed commit timeline and identified problematic code changes.

Untangled commit scope and isolated persistent language-balance bug.

Examined codebase changes and investigated language balance criteria.

Continue
Ran 3 commands, viewed a file

Went through the run logs, the two Telegram exports, and the actual repo in the zip (not just the logs — the zip has the full english-channel-ai project with .git history, so I could check commits too). Here's the picture:

The channel is fully stalled, and has been for days. data/campaign_state.json shows Aug 8–11 all hit their 3-posts/day target fine, then Aug 12 dropped to 1 post, Aug 13 to 0, Aug 14 to 1, and today (Aug 15) is 0-for-7 attempted runs. This isn't random — it's a genuine deadlock.

Why it's deadlocked: progress_recap ("مرور پیشرفت") is scheduled by post-count, not by weekday (RECAP_EVERY_N_POSTS, in schedule_builder.py) — it's due once the 14-post cycle finishes, which it just did after Aug 14's quiz. Since that recap post keeps failing the automated review step, the counter never advances, so every subsequent run — whatever it was originally supposed to post — gets overridden back to the same stuck progress_recap slot and fails again. That's why you're seeing the same "به‌جای X، پست مرور پیشرفت منتشر می‌شه" note over and over.

Why it keeps failing review: almost every rejection cites REVIEW_RULES' language-balance check — the post's narrative comes back mostly Persian, and the rule (applied to every format) demands it be predominantly English. I checked prompts.py: progress_recap's own generation guidance is the one format whose instructions never explicitly say "write it in English" (other formats like micro_scene do say this explicitly) — it just says "turn the list of recent topics into a warm recap," leaning entirely on a shared instruction block to carry the English requirement. That's a real structural weak spot, though it's not new — that guidance text hasn't changed.

What did change, right before this started: a large fix session landed the evening of Aug 11 — commits 101183f ("Claude +100 issues") and 8dbeadb ("Last Claude 101 fixes"), 46 files total, including a 403-line rewrite of main.py and a 501-line rewrite of ai.py. Failures started the very next day. I diffed prompts.py specifically and confirmed the language-balance rule's wording wasn't touched, so the regression is elsewhere — my best guess is quota pressure: several new subsystems were added that session (audience profiling, embeddings dup-check, richer analytics), likely burning through Gemini's 20-request/day free tier earlier in the day, so more generations fall through to the Groq fallback (gpt-oss-120b). I confirmed Groq gets the exact same prompt text (nothing's stripped), but at least one failing run shows Groq-generated content violating two rules at once (Persian-heavy and wrong tag syntax), which points at the fallback model just following the instruction stack less reliably than Gemini.

One thing already fixed: your most recent commit (4e66638, "Fixed Last") patched a real but separate bug — broad-theme topics like "Numbers and time" being wrongly required to have a single bolded word. That failure mode is gone from today's logs. It just didn't touch the language-balance issue, which is why today is still 0/7.

What I'd do, in order:

    Break the deadlock now — either hand-publish one recap and record it in data/campaign_state.json/memory.json, or add an explicit "write this predominantly in English" line to progress_recap's own guidance in prompts.py so the next automatic attempt is more likely to pass.
    Add the same explicit English-first line to any other format that's currently relying only on the shared block (Vocabulary Spotlight and Voice Message both got the same rejection reason on Aug 12–13).
    Check how often you're actually falling back to Groq lately — this is basically your own unfinished item #90 ("dedicated quota tracking") in PROJECT_STATUS.md, and it'd confirm or kill the quota theory directly.
    data/reader_library.json has been at 0 fresh stories since Jul 30 — separate, low-urgency, but worth restocking.

Want me to draft the prompts.py fix for #1/#2, or dig into ai.py's fallback path to confirm the Groq theory?

Let's go
Ran 7 commands, viewed 3 files, edited 3 files

Done. I added an explicit "write the body in English" instruction to the three formats that had actually failed on language balance in your logs — progress_recap, vocab_spotlight, and voice_note — matching how micro_scene/reader_installment/news_relevel already do it. For progress_recap specifically I put the reminder right next to where the recap title list gets inserted, since that's the last thing the model reads before drafting and it's where the Persian-leaning pull is strongest.

Verified it's not just a text edit that looks right: valid Python (ast.parse passes), and I actually rendered a full progress_recap prompt end-to-end with sample data — the new instruction sits exactly where intended, right before the "موضوعاتی که این چند هفته پوشش داده شدن" list, with no formatting breakage.

Two files above:

    prompts.py — the whole file, ready to drop in over your copy.
    prompts_language_balance_fix.patch — same change as a git patch if you'd rather git apply it and review the diff first.

To ship it: replace prompts.py in your repo (or apply the patch), commit, push. You shouldn't need to touch any data files — progress_recap is still next in line by post-count, so your very next scheduled run will just retry it automatically, now with the stronger prompt. If it passes, everything unblocks itself in one shot.

One honest caveat: this raises the odds, it doesn't guarantee the very next attempt passes — model output isn't deterministic. If it's still stuck after this deploys, that's your signal the Groq-fallback-quality theory is the real driver rather than a guidance gap, and I'd go dig into ai.py's fallback path next.
Prompts language balance fix
PATCH 
Prompts
PY 

Is that everything?
Thought for 34s

Inventoried fixes versus unfixed issues comprehensively.

No — that fix closes the specific thing that's blocking you right now, but there's more sitting on the table:

    Two formats have the identical gap, untouched. illustrated_pun and spot_mistake also never say "in English" in their guidance — same pattern as the three I fixed. They just haven't been the one that failed yet, so I left them alone to keep the patch minimal and tied to actual evidence. Quick to add if you want it done defensively.
    The Groq theory is still just a theory. I confirmed Groq gets the identical prompt and found one run where its output broke two rules at once, but I never actually opened ai.py's fallback path to check why — weaker model, different temperature, something else. That's the next place to look if today's fix doesn't fully hold.
    The Gemini quota ceiling itself (20 req/day free tier) is untouched. Even with better prompts, you'll likely keep tripping into Groq multiple times a day at your current call volume. That's a plan/budget call, not something I can fix in code.
    data/reader_library.json has been empty since ~July 30. Unrelated to this incident, just been sitting there — the story-installment format has presumably been silently skipping itself for two weeks.
    Content gaps from your own weekly reports: "Persian transfer errors" and "Phrasal verbs" have never been covered.
    I haven't seen it actually work. Everything above is verified up to "the prompt builds correctly" — whether it actually passes review is only provable once you deploy it and the next scheduled run tries progress_recap for real.

Say the word on any of these — happy to patch the other two formats now, or go dig through ai.py's fallback path next.
You are out of free messages(opens in new tab) until 4:10 PM


Claude is AI and can make mistakes. Please double-check responses.





2026-08-15T18:51:09.0777191Z Current runner version: '2.336.0'
2026-08-15T18:51:09.0801719Z ##[group]Runner Image Provisioner
2026-08-15T18:51:09.0802694Z Hosted Compute Agent
2026-08-15T18:51:09.0803364Z Version: 20260729.566
2026-08-15T18:51:09.0804051Z Commit: cf7153fe6e25b664e8693c24944bf2b00355d109
2026-08-15T18:51:09.0804870Z Build Date: 2026-07-29T19:17:02Z
2026-08-15T18:51:09.0805784Z Worker ID: {e573b64e-e9a4-4c1f-aca5-046ef7cd6ffa}
2026-08-15T18:51:09.0806595Z Azure Region: westus3
2026-08-15T18:51:09.0807241Z ##[endgroup]
2026-08-15T18:51:09.0808808Z ##[group]Operating System
2026-08-15T18:51:09.0809856Z Ubuntu
2026-08-15T18:51:09.0810596Z 24.04.4
2026-08-15T18:51:09.0811163Z LTS
2026-08-15T18:51:09.0811774Z ##[endgroup]
2026-08-15T18:51:09.0812413Z ##[group]Runner Image
2026-08-15T18:51:09.0813125Z Image: ubuntu-24.04
2026-08-15T18:51:09.0813764Z Version: 20260810.271.1
2026-08-15T18:51:09.0815173Z Included Software: https://github.com/actions/runner-images/blob/ubuntu24/20260810.271/images/ubuntu/Ubuntu2404-Readme.md
2026-08-15T18:51:09.0816693Z Image Release: https://github.com/actions/runner-images/releases/tag/ubuntu24%2F20260810.271
2026-08-15T18:51:09.0817673Z ##[endgroup]
2026-08-15T18:51:09.0818921Z ##[group]GITHUB_TOKEN Permissions
2026-08-15T18:51:09.0821139Z Contents: write
2026-08-15T18:51:09.0821858Z Metadata: read
2026-08-15T18:51:09.0822440Z ##[endgroup]
2026-08-15T18:51:09.0824644Z Secret source: Actions
2026-08-15T18:51:09.0825961Z Prepare workflow directory
2026-08-15T18:51:09.1194878Z Prepare all required actions
2026-08-15T18:51:09.1242428Z Getting action download info
2026-08-15T18:51:09.4058243Z Download action repository 'actions/checkout@v4' (SHA:11d5960a326750d5838078e36cf38b85af677262)
2026-08-15T18:51:09.5502462Z Download action repository 'actions/setup-python@v5' (SHA:a26af69be951a213d495a4c3e4e4022e16d87065)
2026-08-15T18:51:09.7720610Z Complete job name: post
2026-08-15T18:51:09.8575749Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T18:51:09.8586808Z ##[group]Run actions/checkout@v4
2026-08-15T18:51:09.8587609Z with:
2026-08-15T18:51:09.8588093Z   fetch-depth: 1
2026-08-15T18:51:09.8588696Z   repository: sajjadisr/ESL-Telegram-channel-automation
2026-08-15T18:51:09.8592553Z   token: ***
2026-08-15T18:51:09.8593049Z   ssh-strict: true
2026-08-15T18:51:09.8593536Z   ssh-user: git
2026-08-15T18:51:09.8594035Z   persist-credentials: true
2026-08-15T18:51:09.8594593Z   clean: true
2026-08-15T18:51:09.8595353Z   sparse-checkout-cone-mode: true
2026-08-15T18:51:09.8596010Z   fetch-tags: false
2026-08-15T18:51:09.8596510Z   show-progress: true
2026-08-15T18:51:09.8597014Z   lfs: false
2026-08-15T18:51:09.8597534Z   submodules: false
2026-08-15T18:51:09.8598017Z   set-safe-directory: true
2026-08-15T18:51:09.8598565Z   allow-unsafe-pr-checkout: false
2026-08-15T18:51:09.8599457Z ##[endgroup]
2026-08-15T18:51:09.9595291Z Syncing repository: sajjadisr/ESL-Telegram-channel-automation
2026-08-15T18:51:09.9597303Z ##[group]Getting Git version info
2026-08-15T18:51:09.9598339Z Working directory is '/home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation'
2026-08-15T18:51:09.9599598Z [command]/usr/bin/git version
2026-08-15T18:51:09.9653480Z git version 2.54.0
2026-08-15T18:51:09.9707762Z ##[endgroup]
2026-08-15T18:51:09.9723738Z Temporarily overriding HOME='/home/runner/work/_temp/6f794321-f875-4102-9099-be0544f6dc42' before making global git config changes
2026-08-15T18:51:09.9726699Z Adding repository directory to the temporary git global config as a safe directory
2026-08-15T18:51:09.9730659Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T18:51:09.9797146Z Deleting the contents of '/home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation'
2026-08-15T18:51:09.9800567Z ##[group]Initializing the repository
2026-08-15T18:51:09.9802435Z [command]/usr/bin/git init /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T18:51:09.9882351Z hint: Using 'master' as the name for the initial branch. This default branch name
2026-08-15T18:51:09.9884143Z hint: will change to "main" in Git 3.0. To configure the initial branch name
2026-08-15T18:51:09.9885796Z hint: to use in all of your new repositories, which will suppress this warning,
2026-08-15T18:51:09.9887096Z hint: call:
2026-08-15T18:51:09.9888192Z hint:
2026-08-15T18:51:09.9889099Z hint: 	git config --global init.defaultBranch <name>
2026-08-15T18:51:09.9890108Z hint:
2026-08-15T18:51:09.9891143Z hint: Names commonly chosen instead of 'master' are 'main', 'trunk' and
2026-08-15T18:51:09.9892869Z hint: 'development'. The just-created branch can be renamed via this command:
2026-08-15T18:51:09.9894244Z hint:
2026-08-15T18:51:09.9895043Z hint: 	git branch -m <name>
2026-08-15T18:51:09.9896113Z hint:
2026-08-15T18:51:09.9897229Z hint: Disable this message with "git config set advice.defaultBranchName false"
2026-08-15T18:51:09.9899575Z Initialized empty Git repository in /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation/.git/
2026-08-15T18:51:09.9903308Z [command]/usr/bin/git remote add origin https://github.com/sajjadisr/ESL-Telegram-channel-automation
2026-08-15T18:51:09.9942634Z ##[endgroup]
2026-08-15T18:51:09.9944615Z ##[group]Disabling automatic garbage collection
2026-08-15T18:51:09.9946575Z [command]/usr/bin/git config --local gc.auto 0
2026-08-15T18:51:09.9975803Z ##[endgroup]
2026-08-15T18:51:09.9977295Z ##[group]Setting up auth
2026-08-15T18:51:09.9981996Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
2026-08-15T18:51:10.0017009Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
2026-08-15T18:51:10.0330994Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
2026-08-15T18:51:10.0368035Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
2026-08-15T18:51:10.0563721Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
2026-08-15T18:51:10.0592615Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
2026-08-15T18:51:10.0770397Z [command]/usr/bin/git config --local http.https://github.com/.extraheader AUTHORIZATION: basic ***
2026-08-15T18:51:10.0803506Z ##[endgroup]
2026-08-15T18:51:10.0804422Z ##[group]Fetching the repository
2026-08-15T18:51:10.0813038Z [command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=1 origin +f0d4193f910198beb35a3f36340ea84ce6bc244d:refs/remotes/origin/main
2026-08-15T18:51:10.7700482Z From https://github.com/sajjadisr/ESL-Telegram-channel-automation
2026-08-15T18:51:10.7703549Z  * [new ref]         f0d4193f910198beb35a3f36340ea84ce6bc244d -> origin/main
2026-08-15T18:51:10.7738305Z ##[endgroup]
2026-08-15T18:51:10.7740310Z ##[group]Determining the checkout info
2026-08-15T18:51:10.7742108Z ##[endgroup]
2026-08-15T18:51:10.7744030Z [command]/usr/bin/git sparse-checkout disable
2026-08-15T18:51:10.7784611Z [command]/usr/bin/git config --local --unset-all extensions.worktreeConfig
2026-08-15T18:51:10.7810359Z ##[group]Checking out the ref
2026-08-15T18:51:10.7815820Z [command]/usr/bin/git checkout --progress --force -B main refs/remotes/origin/main
2026-08-15T18:51:10.7928269Z Switched to a new branch 'main'
2026-08-15T18:51:10.7931431Z branch 'main' set up to track 'origin/main'.
2026-08-15T18:51:10.7937083Z ##[endgroup]
2026-08-15T18:51:10.7980056Z [command]/usr/bin/git log -1 --format=%H
2026-08-15T18:51:10.8001510Z f0d4193f910198beb35a3f36340ea84ce6bc244d
2026-08-15T18:51:10.8326948Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T18:51:10.8332201Z ##[group]Run actions/setup-python@v5
2026-08-15T18:51:10.8333232Z with:
2026-08-15T18:51:10.8334005Z   python-version: 3.12
2026-08-15T18:51:10.8334905Z   check-latest: false
2026-08-15T18:51:10.8344143Z   token: ***
2026-08-15T18:51:10.8344975Z   update-environment: true
2026-08-15T18:51:10.8346055Z   allow-prereleases: false
2026-08-15T18:51:10.8347002Z   freethreaded: false
2026-08-15T18:51:10.8347858Z ##[endgroup]
2026-08-15T18:51:10.9620206Z ##[group]Installed versions
2026-08-15T18:51:10.9702714Z (node:2310) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
2026-08-15T18:51:10.9707175Z (Use `node --trace-deprecation ...` to show where the warning was created)
2026-08-15T18:51:10.9709891Z Successfully set up CPython (3.12.13)
2026-08-15T18:51:10.9712733Z ##[endgroup]
2026-08-15T18:51:10.9928022Z ##[group]Run pip install -r requirements.txt
2026-08-15T18:51:10.9929505Z [36;1mpip install -r requirements.txt[0m
2026-08-15T18:51:10.9974407Z shell: /usr/bin/bash -e {0}
2026-08-15T18:51:10.9976165Z env:
2026-08-15T18:51:10.9977803Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T18:51:10.9980720Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T18:51:10.9983458Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T18:51:10.9985464Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T18:51:10.9986983Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T18:51:10.9988535Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T18:51:10.9989818Z ##[endgroup]
2026-08-15T18:51:11.8229440Z Collecting google-genai==2.14.0 (from -r requirements.txt (line 1))
2026-08-15T18:51:11.8956482Z   Downloading google_genai-2.14.0-py3-none-any.whl.metadata (55 kB)
2026-08-15T18:51:11.9380697Z Collecting httpx==0.28.1 (from -r requirements.txt (line 2))
2026-08-15T18:51:11.9486072Z   Downloading httpx-0.28.1-py3-none-any.whl.metadata (7.1 kB)
2026-08-15T18:51:11.9773645Z Collecting requests==2.32.3 (from -r requirements.txt (line 6))
2026-08-15T18:51:11.9878008Z   Downloading requests-2.32.3-py3-none-any.whl.metadata (4.6 kB)
2026-08-15T18:51:12.0068485Z Collecting feedparser==6.0.11 (from -r requirements.txt (line 7))
2026-08-15T18:51:12.0170845Z   Downloading feedparser-6.0.11-py3-none-any.whl.metadata (2.4 kB)
2026-08-15T18:51:12.2096230Z Collecting Pillow==11.0.0 (from -r requirements.txt (line 8))
2026-08-15T18:51:12.2205545Z   Downloading pillow-11.0.0-cp312-cp312-manylinux_2_28_x86_64.whl.metadata (9.1 kB)
2026-08-15T18:51:12.2408518Z Collecting arabic-reshaper==3.0.0 (from -r requirements.txt (line 9))
2026-08-15T18:51:12.2514739Z   Downloading arabic_reshaper-3.0.0-py3-none-any.whl.metadata (12 kB)
2026-08-15T18:51:12.3295349Z Collecting python-bidi==0.6.3 (from -r requirements.txt (line 10))
2026-08-15T18:51:12.3406720Z   Downloading python_bidi-0.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (4.9 kB)
2026-08-15T18:51:12.3758572Z Collecting telethon==1.36.0 (from -r requirements.txt (line 11))
2026-08-15T18:51:12.3866371Z   Downloading Telethon-1.36.0.tar.gz (606 kB)
2026-08-15T18:51:12.4543476Z      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 606.3/606.3 kB 9.6 MB/s  0:00:00
2026-08-15T18:51:12.5100791Z   Installing build dependencies: started
2026-08-15T18:51:13.2615913Z   Installing build dependencies: finished with status 'done'
2026-08-15T18:51:13.2621383Z   Getting requirements to build wheel: started
2026-08-15T18:51:13.6231975Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T18:51:13.6241166Z   Preparing metadata (pyproject.toml): started
2026-08-15T18:51:13.7971679Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T18:51:13.8204613Z Collecting anyio<5.0.0,>=4.8.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T18:51:13.8306366Z   Downloading anyio-4.14.2-py3-none-any.whl.metadata (4.6 kB)
2026-08-15T18:51:13.8663627Z Collecting google-auth<3.0.0,>=2.56.0 (from google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T18:51:13.8766910Z   Downloading google_auth-2.56.3-py3-none-any.whl.metadata (6.0 kB)
2026-08-15T18:51:13.9869474Z Collecting pydantic<3.0.0,>=2.12.5 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T18:51:13.9973194Z   Downloading pydantic-2.13.4-py3-none-any.whl.metadata (109 kB)
2026-08-15T18:51:14.0307817Z Collecting tenacity<9.2.0,>=8.2.3 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T18:51:14.0410941Z   Downloading tenacity-9.1.4-py3-none-any.whl.metadata (1.2 kB)
2026-08-15T18:51:14.1391140Z Collecting websockets<17.0,>=13.0.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T18:51:14.1496631Z   Downloading websockets-16.1.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl.metadata (6.8 kB)
2026-08-15T18:51:14.1724539Z Collecting typing-extensions<5.0.0,>=4.14.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T18:51:14.1825765Z   Downloading typing_extensions-4.16.0-py3-none-any.whl.metadata (3.3 kB)
2026-08-15T18:51:14.2009502Z Collecting distro<2,>=1.7.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T18:51:14.2116706Z   Downloading distro-1.9.0-py3-none-any.whl.metadata (6.8 kB)
2026-08-15T18:51:14.2303480Z Collecting sniffio (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T18:51:14.2411720Z   Downloading sniffio-1.3.1-py3-none-any.whl.metadata (3.9 kB)
2026-08-15T18:51:14.2690314Z Collecting certifi (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T18:51:14.2791291Z   Downloading certifi-2026.7.22-py3-none-any.whl.metadata (2.5 kB)
2026-08-15T18:51:14.3001422Z Collecting httpcore==1.* (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T18:51:14.3104539Z   Downloading httpcore-1.0.9-py3-none-any.whl.metadata (21 kB)
2026-08-15T18:51:14.3323771Z Collecting idna (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T18:51:14.3427345Z   Downloading idna-3.18-py3-none-any.whl.metadata (6.1 kB)
2026-08-15T18:51:14.4582845Z Collecting charset-normalizer<4,>=2 (from requests==2.32.3->-r requirements.txt (line 6))
2026-08-15T18:51:14.4689787Z   Downloading charset_normalizer-3.5.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (45 kB)
2026-08-15T18:51:14.5006560Z Collecting urllib3<3,>=1.21.1 (from requests==2.32.3->-r requirements.txt (line 6))
2026-08-15T18:51:14.5107569Z   Downloading urllib3-2.7.0-py3-none-any.whl.metadata (6.9 kB)
2026-08-15T18:51:14.5315777Z Collecting sgmllib3k (from feedparser==6.0.11->-r requirements.txt (line 7))
2026-08-15T18:51:14.5418735Z   Downloading sgmllib3k-1.0.0.tar.gz (5.8 kB)
2026-08-15T18:51:14.5470691Z   Installing build dependencies: started
2026-08-15T18:51:15.0226707Z   Installing build dependencies: finished with status 'done'
2026-08-15T18:51:15.0246163Z   Getting requirements to build wheel: started
2026-08-15T18:51:15.3270141Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T18:51:15.3278602Z   Preparing metadata (pyproject.toml): started
2026-08-15T18:51:15.4913661Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T18:51:15.5080041Z Collecting pyaes (from telethon==1.36.0->-r requirements.txt (line 11))
2026-08-15T18:51:15.5181518Z   Downloading pyaes-1.6.1.tar.gz (28 kB)
2026-08-15T18:51:15.5253118Z   Installing build dependencies: started
2026-08-15T18:51:15.9894144Z   Installing build dependencies: finished with status 'done'
2026-08-15T18:51:15.9900729Z   Getting requirements to build wheel: started
2026-08-15T18:51:16.2890057Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T18:51:16.2897981Z   Preparing metadata (pyproject.toml): started
2026-08-15T18:51:16.4540176Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T18:51:16.4732335Z Collecting rsa (from telethon==1.36.0->-r requirements.txt (line 11))
2026-08-15T18:51:16.4836092Z   Downloading rsa-4.9.1-py3-none-any.whl.metadata (5.6 kB)
2026-08-15T18:51:16.5112059Z Collecting pyasn1-modules>=0.2.1 (from google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T18:51:16.5215474Z   Downloading pyasn1_modules-0.4.2-py3-none-any.whl.metadata (3.5 kB)
2026-08-15T18:51:16.7105533Z Collecting cryptography>=38.0.3 (from google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T18:51:16.7208691Z   Downloading cryptography-50.0.0-cp311-abi3-manylinux_2_34_x86_64.whl.metadata (4.3 kB)
2026-08-15T18:51:16.7420928Z Collecting h11>=0.16 (from httpcore==1.*->httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T18:51:16.7524117Z   Downloading h11-0.16.0-py3-none-any.whl.metadata (8.3 kB)
2026-08-15T18:51:16.7703791Z Collecting annotated-types>=0.6.0 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T18:51:16.7805513Z   Downloading annotated_types-0.8.0-py3-none-any.whl.metadata (15 kB)
2026-08-15T18:51:17.3783489Z Collecting pydantic-core==2.46.4 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T18:51:17.3888022Z   Downloading pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (6.6 kB)
2026-08-15T18:51:17.4069297Z Collecting typing-inspection>=0.4.2 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T18:51:17.4171779Z   Downloading typing_inspection-0.4.4-py3-none-any.whl.metadata (2.6 kB)
2026-08-15T18:51:17.5157699Z Collecting cffi>=2.0.0 (from cryptography>=38.0.3->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T18:51:17.5264664Z   Downloading cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl.metadata (2.5 kB)
2026-08-15T18:51:17.5439464Z Collecting pycparser (from cffi>=2.0.0->cryptography>=38.0.3->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T18:51:17.5542429Z   Downloading pycparser-3.0-py3-none-any.whl.metadata (8.2 kB)
2026-08-15T18:51:17.5800851Z Collecting pyasn1<0.7.0,>=0.6.1 (from pyasn1-modules>=0.2.1->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T18:51:17.5906857Z   Downloading pyasn1-0.6.4-py3-none-any.whl.metadata (8.4 kB)
2026-08-15T18:51:17.6096439Z Downloading google_genai-2.14.0-py3-none-any.whl (1.0 MB)
2026-08-15T18:51:17.6865030Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1.0/1.0 MB 14.1 MB/s  0:00:00
2026-08-15T18:51:17.6968832Z Downloading httpx-0.28.1-py3-none-any.whl (73 kB)
2026-08-15T18:51:17.7109218Z Downloading requests-2.32.3-py3-none-any.whl (64 kB)
2026-08-15T18:51:17.7250336Z Downloading feedparser-6.0.11-py3-none-any.whl (81 kB)
2026-08-15T18:51:17.7405933Z Downloading pillow-11.0.0-cp312-cp312-manylinux_2_28_x86_64.whl (4.4 MB)
2026-08-15T18:51:17.9053930Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.4/4.4 MB 27.3 MB/s  0:00:00
2026-08-15T18:51:17.9159367Z Downloading arabic_reshaper-3.0.0-py3-none-any.whl (20 kB)
2026-08-15T18:51:17.9287664Z Downloading python_bidi-0.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (286 kB)
2026-08-15T18:51:17.9456487Z Downloading anyio-4.14.2-py3-none-any.whl (125 kB)
2026-08-15T18:51:17.9591751Z Downloading charset_normalizer-3.5.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (248 kB)
2026-08-15T18:51:17.9746748Z Downloading distro-1.9.0-py3-none-any.whl (20 kB)
2026-08-15T18:51:17.9867022Z Downloading google_auth-2.56.3-py3-none-any.whl (259 kB)
2026-08-15T18:51:18.0040756Z Downloading httpcore-1.0.9-py3-none-any.whl (78 kB)
2026-08-15T18:51:18.0168268Z Downloading idna-3.18-py3-none-any.whl (65 kB)
2026-08-15T18:51:18.0291958Z Downloading pydantic-2.13.4-py3-none-any.whl (472 kB)
2026-08-15T18:51:18.0525913Z Downloading pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (2.1 MB)
2026-08-15T18:51:18.0981988Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.1/2.1 MB 44.9 MB/s  0:00:00
2026-08-15T18:51:18.1084573Z Downloading tenacity-9.1.4-py3-none-any.whl (28 kB)
2026-08-15T18:51:18.1203675Z Downloading typing_extensions-4.16.0-py3-none-any.whl (45 kB)
2026-08-15T18:51:18.1325633Z Downloading urllib3-2.7.0-py3-none-any.whl (131 kB)
2026-08-15T18:51:18.1462278Z Downloading websockets-16.1.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (187 kB)
2026-08-15T18:51:18.1596724Z Downloading annotated_types-0.8.0-py3-none-any.whl (13 kB)
2026-08-15T18:51:18.1721204Z Downloading certifi-2026.7.22-py3-none-any.whl (136 kB)
2026-08-15T18:51:18.1877314Z Downloading cryptography-50.0.0-cp311-abi3-manylinux_2_34_x86_64.whl (4.7 MB)
2026-08-15T18:51:18.2639005Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.7/4.7 MB 61.6 MB/s  0:00:00
2026-08-15T18:51:18.2743558Z Downloading cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (221 kB)
2026-08-15T18:51:18.2894256Z Downloading h11-0.16.0-py3-none-any.whl (37 kB)
2026-08-15T18:51:18.3019080Z Downloading pyasn1_modules-0.4.2-py3-none-any.whl (181 kB)
2026-08-15T18:51:18.3150704Z Downloading pyasn1-0.6.4-py3-none-any.whl (84 kB)
2026-08-15T18:51:18.3276450Z Downloading typing_inspection-0.4.4-py3-none-any.whl (14 kB)
2026-08-15T18:51:18.3397423Z Downloading pycparser-3.0-py3-none-any.whl (48 kB)
2026-08-15T18:51:18.3523490Z Downloading rsa-4.9.1-py3-none-any.whl (34 kB)
2026-08-15T18:51:18.3646924Z Downloading sniffio-1.3.1-py3-none-any.whl (10 kB)
2026-08-15T18:51:18.4531386Z Building wheels for collected packages: telethon, pyaes, sgmllib3k
2026-08-15T18:51:18.4538556Z   Building wheel for telethon (pyproject.toml): started
2026-08-15T18:51:18.7871060Z   Building wheel for telethon (pyproject.toml): finished with status 'done'
2026-08-15T18:51:18.7884993Z   Created wheel for telethon: filename=telethon-1.36.0-py3-none-any.whl size=680976 sha256=e348ca7b9e7e0863987c231753a9dbfcd1e9dfe3e20920e746fd4ea2c080008b
2026-08-15T18:51:18.7888405Z   Stored in directory: /home/runner/.cache/pip/wheels/24/5b/1e/aa9bdcbb6e03ba1af024040fc49464b8b7c5ec432ce1916aa2
2026-08-15T18:51:18.7917199Z   Building wheel for pyaes (pyproject.toml): started
2026-08-15T18:51:18.9882768Z   Building wheel for pyaes (pyproject.toml): finished with status 'done'
2026-08-15T18:51:18.9889138Z   Created wheel for pyaes: filename=pyaes-1.6.1-py3-none-any.whl size=26422 sha256=013f4d2afe69791242dc34b2d30cc257f0651c9cee4727fe4ed9fd2c553888bf
2026-08-15T18:51:18.9890648Z   Stored in directory: /home/runner/.cache/pip/wheels/d9/43/32/ec313dd557e88e419489b9df40c04dad7b99576bde162496f8
2026-08-15T18:51:18.9910822Z   Building wheel for sgmllib3k (pyproject.toml): started
2026-08-15T18:51:19.1886629Z   Building wheel for sgmllib3k (pyproject.toml): finished with status 'done'
2026-08-15T18:51:19.1893466Z   Created wheel for sgmllib3k: filename=sgmllib3k-1.0.0-py3-none-any.whl size=6090 sha256=7bfe02dbd6f6627bc0373af06bb0dc772f697f260f284df7295420e28e82f211
2026-08-15T18:51:19.1895577Z   Stored in directory: /home/runner/.cache/pip/wheels/03/f5/1a/23761066dac1d0e8e683e5fdb27e12de53209d05a4a37e6246
2026-08-15T18:51:19.1912913Z Successfully built telethon pyaes sgmllib3k
2026-08-15T18:51:19.2514646Z Installing collected packages: sgmllib3k, python-bidi, pyaes, arabic-reshaper, websockets, urllib3, typing-extensions, tenacity, sniffio, pycparser, pyasn1, Pillow, idna, h11, feedparser, distro, charset-normalizer, certifi, annotated-types, typing-inspection, rsa, requests, pydantic-core, pyasn1-modules, httpcore, cffi, anyio, telethon, pydantic, httpx, cryptography, google-auth, google-genai
2026-08-15T18:51:22.5133053Z 
2026-08-15T18:51:22.5161745Z Successfully installed Pillow-11.0.0 annotated-types-0.8.0 anyio-4.14.2 arabic-reshaper-3.0.0 certifi-2026.7.22 cffi-2.1.1 charset-normalizer-3.5.1 cryptography-50.0.0 distro-1.9.0 feedparser-6.0.11 google-auth-2.56.3 google-genai-2.14.0 h11-0.16.0 httpcore-1.0.9 httpx-0.28.1 idna-3.18 pyaes-1.6.1 pyasn1-0.6.4 pyasn1-modules-0.4.2 pycparser-3.0 pydantic-2.13.4 pydantic-core-2.46.4 python-bidi-0.6.3 requests-2.32.3 rsa-4.9.1 sgmllib3k-1.0.0 sniffio-1.3.1 telethon-1.36.0 tenacity-9.1.4 typing-extensions-4.16.0 typing-inspection-0.4.4 urllib3-2.7.0 websockets-16.1.1
2026-08-15T18:51:22.6589924Z ##[group]Run python main.py
2026-08-15T18:51:22.6590247Z [36;1mpython main.py[0m
2026-08-15T18:51:22.6614689Z shell: /usr/bin/bash -e {0}
2026-08-15T18:51:22.6615246Z env:
2026-08-15T18:51:22.6615568Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T18:51:22.6616048Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T18:51:22.6616484Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T18:51:22.6616882Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T18:51:22.6617283Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T18:51:22.6617679Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T18:51:22.6618317Z   TELEGRAM_BOT_TOKEN: ***
2026-08-15T18:51:22.6618607Z   TELEGRAM_CHANNEL_ID: ***
2026-08-15T18:51:22.6618888Z   TELEGRAM_ADMIN_CHAT_ID: ***
2026-08-15T18:51:22.6619265Z   GEMINI_API_KEY: ***
2026-08-15T18:51:22.6619700Z   GEMINI_API_KEY_BACKUP: ***
2026-08-15T18:51:22.6620098Z   GROQ_API_KEY: ***
2026-08-15T18:51:22.6620403Z   CLOUDFLARE_ACCOUNT_ID: ***
2026-08-15T18:51:22.6620796Z   CLOUDFLARE_API_TOKEN: ***
2026-08-15T18:51:22.6621138Z   EITAA_TOKEN: ***
2026-08-15T18:51:22.6621393Z   EITAA_CHANNEL_ID: ***
2026-08-15T18:51:22.6621718Z   BALE_BOT_TOKEN: ***
2026-08-15T18:51:22.6621989Z   BALE_CHAT_ID: ***
2026-08-15T18:51:22.6622216Z ##[endgroup]
2026-08-15T18:52:15.2412330Z engagement_harvest: TELEGRAM_API_ID / TELEGRAM_API_HASH / TELETHON_SESSION_STRING not fully configured — skipping (see scripts/generate_telethon_session.py to set this up once; every other part of the pipeline is unaffected either way).
2026-08-15T18:52:15.2418137Z Gemini call to gemini-3.5-flash: call failed (attempt 1/3) on the primary key: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 21.016583375s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-3.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '21s'}]}}. Retrying...
2026-08-15T18:52:15.2433751Z Gemini call to gemini-3.5-flash: call failed (attempt 2/3) on the primary key: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 17.950892835s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-3.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '17s'}]}}. Retrying...
2026-08-15T18:52:15.2441074Z generate_reviewed_text: giving up on progress_recap after 3 attempts — still not ok: بخش عمده متن به زبان فارسی روایت شده و عبارات انگلیسی فقط به صورت کلمات یا مثال‌های پراکنده در آن قرار گرفته‌اند. طبق معیار ۶، روایت یا بدنه اصلی پست باید به انگلیسی باشد و فارسی فقط برای توضیحات بسیار کوتاه یا ترجمه کلمات سخت به کار رود.
2026-08-15T18:52:15.4661092Z ##[group]Run set -euo pipefail
2026-08-15T18:52:15.4661508Z [36;1mset -euo pipefail[0m
2026-08-15T18:52:15.4661859Z [36;1mgit config user.name "channel-bot"[0m
2026-08-15T18:52:15.4662280Z [36;1mgit config user.email "actions@github.com"[0m
2026-08-15T18:52:15.4662672Z [36;1mgit add data/[0m
2026-08-15T18:52:15.4662992Z [36;1mif git diff --staged --quiet; then[0m
2026-08-15T18:52:15.4663371Z [36;1m  echo "No data changes to commit."[0m
2026-08-15T18:52:15.4663726Z [36;1m  exit 0[0m
2026-08-15T18:52:15.4663995Z [36;1mfi[0m
2026-08-15T18:52:15.4664348Z [36;1mgit commit -m "Daily post: update memory and database"[0m
2026-08-15T18:52:15.4664777Z [36;1mfor i in 1 2 3 4 5; do[0m
2026-08-15T18:52:15.4665357Z [36;1m  if git pull --rebase origin main && git push; then[0m
2026-08-15T18:52:15.4665813Z [36;1m    echo "Pushed successfully."[0m
2026-08-15T18:52:15.4666169Z [36;1m    exit 0[0m
2026-08-15T18:52:15.4666443Z [36;1m  fi[0m
2026-08-15T18:52:15.4666799Z [36;1m  echo "Push attempt $i failed, retrying..."[0m
2026-08-15T18:52:15.4667185Z [36;1m  sleep $((RANDOM % 10 + 5))[0m
2026-08-15T18:52:15.4667508Z [36;1mdone[0m
2026-08-15T18:52:15.4667837Z [36;1mecho "::error::Could not push after 5 attempts."[0m
2026-08-15T18:52:15.4668355Z [36;1m# A post can go out to Telegram successfully above even though the[0m
2026-08-15T18:52:15.4668892Z [36;1m# data/ commit that records it never lands — that leaves[0m
2026-08-15T18:52:15.4669429Z [36;1m# memory.json/posts.db/analytics.json/campaign_state.json stale on[0m
2026-08-15T18:52:15.4669983Z [36;1m# origin/main, and every downstream feature that reads them[0m
2026-08-15T18:52:15.4670503Z [36;1m# (dedup, review scheduling, weekly strategy) is stale until[0m
2026-08-15T18:52:15.4671015Z [36;1m# someone notices. This is the only thing that catches that[0m
2026-08-15T18:52:15.4671459Z [36;1m# specific failure mode.[0m
2026-08-15T18:52:15.4671920Z [36;1mif [ -n "$TELEGRAM_ADMIN_CHAT_ID" ] && [ -n "$TELEGRAM_BOT_TOKEN" ]; then[0m
2026-08-15T18:52:15.4672579Z [36;1m  curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \[0m
2026-08-15T18:52:15.4673148Z [36;1m    -d chat_id="${TELEGRAM_ADMIN_CHAT_ID}" \[0m
2026-08-15T18:52:15.4674152Z [36;1m    -d text="🔴 پست امروز احتمالاً منتشر شد، ولی ثبت تغییرات data/ توی گیت بعد از ۵ بار تلاش شکست خورد. یعنی memory.json/posts.db/analytics.json فعلاً روی origin/main قدیمی مونده — لازمه دستی چک و درست بشه، وگرنه ممکنه یه موضوع/جوک دوباره تکرار بشه." \[0m
2026-08-15T18:52:15.4675397Z [36;1m    > /dev/null || echo "::warning::Admin alert send also failed."[0m
2026-08-15T18:52:15.4675834Z [36;1melse[0m
2026-08-15T18:52:15.4676399Z [36;1m  echo "::warning::TELEGRAM_ADMIN_CHAT_ID or TELEGRAM_BOT_TOKEN not set — no admin alert sent for the push failure."[0m
2026-08-15T18:52:15.4677198Z [36;1mfi[0m
2026-08-15T18:52:15.4677455Z [36;1mexit 1[0m
2026-08-15T18:52:15.4700571Z shell: /usr/bin/bash -e {0}
2026-08-15T18:52:15.4700854Z env:
2026-08-15T18:52:15.4701177Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T18:52:15.4701626Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T18:52:15.4702070Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T18:52:15.4702470Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T18:52:15.4702861Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T18:52:15.4703257Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T18:52:15.4703802Z   TELEGRAM_BOT_TOKEN: ***
2026-08-15T18:52:15.4704093Z   TELEGRAM_ADMIN_CHAT_ID: ***
2026-08-15T18:52:15.4704355Z ##[endgroup]
2026-08-15T18:52:15.4909440Z No data changes to commit.
2026-08-15T18:52:15.4997156Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T18:52:15.4998324Z Post job cleanup.
2026-08-15T18:52:15.6155342Z (node:2449) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
2026-08-15T18:52:15.6156101Z (Use `node --trace-deprecation ...` to show where the warning was created)
2026-08-15T18:52:15.6324613Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T18:52:15.6325888Z Post job cleanup.
2026-08-15T18:52:15.7165245Z [command]/usr/bin/git version
2026-08-15T18:52:15.7185342Z git version 2.54.0
2026-08-15T18:52:15.7253015Z Temporarily overriding HOME='/home/runner/work/_temp/17aa2320-acd0-4bac-8842-d7af33703613' before making global git config changes
2026-08-15T18:52:15.7254550Z Adding repository directory to the temporary git global config as a safe directory
2026-08-15T18:52:15.7260095Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T18:52:15.7295543Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
2026-08-15T18:52:15.7327562Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
2026-08-15T18:52:15.7531568Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
2026-08-15T18:52:15.7558413Z http.https://github.com/.extraheader
2026-08-15T18:52:15.7567229Z [command]/usr/bin/git config --local --unset-all http.https://github.com/.extraheader
2026-08-15T18:52:15.7604250Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
2026-08-15T18:52:15.7817079Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
2026-08-15T18:52:15.7858461Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
2026-08-15T18:52:15.8217254Z Cleaning up orphan processes
2026-08-15T18:52:15.8477635Z ##[warning]Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4, actions/setup-python@v5. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/






2026-08-15T17:53:36.7978651Z Current runner version: '2.336.0'
2026-08-15T17:53:36.8012242Z ##[group]Runner Image Provisioner
2026-08-15T17:53:36.8013816Z Hosted Compute Agent
2026-08-15T17:53:36.8014958Z Version: 20260729.566
2026-08-15T17:53:36.8016204Z Commit: cf7153fe6e25b664e8693c24944bf2b00355d109
2026-08-15T17:53:36.8017521Z Build Date: 2026-07-29T19:17:02Z
2026-08-15T17:53:36.8018853Z Worker ID: {56afcb81-72aa-496e-b1bd-d1a735d97777}
2026-08-15T17:53:36.8020584Z Azure Region: eastus
2026-08-15T17:53:36.8021921Z ##[endgroup]
2026-08-15T17:53:36.8024575Z ##[group]Operating System
2026-08-15T17:53:36.8025865Z Ubuntu
2026-08-15T17:53:36.8026947Z 24.04.4
2026-08-15T17:53:36.8027871Z LTS
2026-08-15T17:53:36.8028806Z ##[endgroup]
2026-08-15T17:53:36.8029938Z ##[group]Runner Image
2026-08-15T17:53:36.8031072Z Image: ubuntu-24.04
2026-08-15T17:53:36.8032409Z Version: 20260810.271.1
2026-08-15T17:53:36.8034650Z Included Software: https://github.com/actions/runner-images/blob/ubuntu24/20260810.271/images/ubuntu/Ubuntu2404-Readme.md
2026-08-15T17:53:36.8037356Z Image Release: https://github.com/actions/runner-images/releases/tag/ubuntu24%2F20260810.271
2026-08-15T17:53:36.8039233Z ##[endgroup]
2026-08-15T17:53:36.8041228Z ##[group]GITHUB_TOKEN Permissions
2026-08-15T17:53:36.8044658Z Contents: write
2026-08-15T17:53:36.8045757Z Metadata: read
2026-08-15T17:53:36.8046767Z ##[endgroup]
2026-08-15T17:53:36.8049807Z Secret source: Actions
2026-08-15T17:53:36.8051923Z Prepare workflow directory
2026-08-15T17:53:36.8501378Z Prepare all required actions
2026-08-15T17:53:36.8574747Z Getting action download info
2026-08-15T17:53:37.0231556Z Download action repository 'actions/checkout@v4' (SHA:11d5960a326750d5838078e36cf38b85af677262)
2026-08-15T17:53:37.1549037Z Download action repository 'actions/setup-python@v5' (SHA:a26af69be951a213d495a4c3e4e4022e16d87065)
2026-08-15T17:53:37.3396245Z Complete job name: post
2026-08-15T17:53:37.4151271Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T17:53:37.4160180Z ##[group]Run actions/checkout@v4
2026-08-15T17:53:37.4160963Z with:
2026-08-15T17:53:37.4161462Z   fetch-depth: 1
2026-08-15T17:53:37.4162283Z   repository: sajjadisr/ESL-Telegram-channel-automation
2026-08-15T17:53:37.4166636Z   token: ***
2026-08-15T17:53:37.4167162Z   ssh-strict: true
2026-08-15T17:53:37.4167694Z   ssh-user: git
2026-08-15T17:53:37.4168227Z   persist-credentials: true
2026-08-15T17:53:37.4168808Z   clean: true
2026-08-15T17:53:37.4169350Z   sparse-checkout-cone-mode: true
2026-08-15T17:53:37.4169959Z   fetch-tags: false
2026-08-15T17:53:37.4170484Z   show-progress: true
2026-08-15T17:53:37.4171009Z   lfs: false
2026-08-15T17:53:37.4171541Z   submodules: false
2026-08-15T17:53:37.4172409Z   set-safe-directory: true
2026-08-15T17:53:37.4173000Z   allow-unsafe-pr-checkout: false
2026-08-15T17:53:37.4173913Z ##[endgroup]
2026-08-15T17:53:37.5173434Z Syncing repository: sajjadisr/ESL-Telegram-channel-automation
2026-08-15T17:53:37.5175443Z ##[group]Getting Git version info
2026-08-15T17:53:37.5176523Z Working directory is '/home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation'
2026-08-15T17:53:37.5177996Z [command]/usr/bin/git version
2026-08-15T17:53:37.5214385Z git version 2.54.0
2026-08-15T17:53:37.5244385Z ##[endgroup]
2026-08-15T17:53:37.5251623Z Temporarily overriding HOME='/home/runner/work/_temp/61d7f828-2302-43ae-bba7-43ef8dbab2e5' before making global git config changes
2026-08-15T17:53:37.5254263Z Adding repository directory to the temporary git global config as a safe directory
2026-08-15T17:53:37.5259050Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T17:53:37.5319762Z Deleting the contents of '/home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation'
2026-08-15T17:53:37.5332228Z ##[group]Initializing the repository
2026-08-15T17:53:37.5333379Z [command]/usr/bin/git init /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T17:53:37.5402888Z hint: Using 'master' as the name for the initial branch. This default branch name
2026-08-15T17:53:37.5404628Z hint: will change to "main" in Git 3.0. To configure the initial branch name
2026-08-15T17:53:37.5405699Z hint: to use in all of your new repositories, which will suppress this warning,
2026-08-15T17:53:37.5406533Z hint: call:
2026-08-15T17:53:37.5407146Z hint:
2026-08-15T17:53:37.5408079Z hint: 	git config --global init.defaultBranch <name>
2026-08-15T17:53:37.5409139Z hint:
2026-08-15T17:53:37.5409999Z hint: Names commonly chosen instead of 'master' are 'main', 'trunk' and
2026-08-15T17:53:37.5411686Z hint: 'development'. The just-created branch can be renamed via this command:
2026-08-15T17:53:37.5413189Z hint:
2026-08-15T17:53:37.5413995Z hint: 	git branch -m <name>
2026-08-15T17:53:37.5414886Z hint:
2026-08-15T17:53:37.5416088Z hint: Disable this message with "git config set advice.defaultBranchName false"
2026-08-15T17:53:37.5418361Z Initialized empty Git repository in /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation/.git/
2026-08-15T17:53:37.5433362Z [command]/usr/bin/git remote add origin https://github.com/sajjadisr/ESL-Telegram-channel-automation
2026-08-15T17:53:37.5465515Z ##[endgroup]
2026-08-15T17:53:37.5466850Z ##[group]Disabling automatic garbage collection
2026-08-15T17:53:37.5469313Z [command]/usr/bin/git config --local gc.auto 0
2026-08-15T17:53:37.5535177Z ##[endgroup]
2026-08-15T17:53:37.5536421Z ##[group]Setting up auth
2026-08-15T17:53:37.5541675Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
2026-08-15T17:53:37.5583603Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
2026-08-15T17:53:37.5935224Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
2026-08-15T17:53:37.5977023Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
2026-08-15T17:53:37.6230504Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
2026-08-15T17:53:37.6269171Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
2026-08-15T17:53:37.6507382Z [command]/usr/bin/git config --local http.https://github.com/.extraheader AUTHORIZATION: basic ***
2026-08-15T17:53:37.6548397Z ##[endgroup]
2026-08-15T17:53:37.6556712Z ##[group]Fetching the repository
2026-08-15T17:53:37.6558337Z [command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=1 origin +f0d4193f910198beb35a3f36340ea84ce6bc244d:refs/remotes/origin/main
2026-08-15T17:53:38.0054141Z From https://github.com/sajjadisr/ESL-Telegram-channel-automation
2026-08-15T17:53:38.0056312Z  * [new ref]         f0d4193f910198beb35a3f36340ea84ce6bc244d -> origin/main
2026-08-15T17:53:38.0086248Z ##[endgroup]
2026-08-15T17:53:38.0087266Z ##[group]Determining the checkout info
2026-08-15T17:53:38.0088502Z ##[endgroup]
2026-08-15T17:53:38.0094702Z [command]/usr/bin/git sparse-checkout disable
2026-08-15T17:53:38.0144560Z [command]/usr/bin/git config --local --unset-all extensions.worktreeConfig
2026-08-15T17:53:38.0180084Z ##[group]Checking out the ref
2026-08-15T17:53:38.0183604Z [command]/usr/bin/git checkout --progress --force -B main refs/remotes/origin/main
2026-08-15T17:53:38.0318951Z Switched to a new branch 'main'
2026-08-15T17:53:38.0320534Z branch 'main' set up to track 'origin/main'.
2026-08-15T17:53:38.0333994Z ##[endgroup]
2026-08-15T17:53:38.0375307Z [command]/usr/bin/git log -1 --format=%H
2026-08-15T17:53:38.0403433Z f0d4193f910198beb35a3f36340ea84ce6bc244d
2026-08-15T17:53:38.0693990Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T17:53:38.0697216Z ##[group]Run actions/setup-python@v5
2026-08-15T17:53:38.0697889Z with:
2026-08-15T17:53:38.0769207Z   python-version: 3.12
2026-08-15T17:53:38.0769963Z   check-latest: false
2026-08-15T17:53:38.0774893Z   token: ***
2026-08-15T17:53:38.0775477Z   update-environment: true
2026-08-15T17:53:38.0776130Z   allow-prereleases: false
2026-08-15T17:53:38.0776761Z   freethreaded: false
2026-08-15T17:53:38.0777339Z ##[endgroup]
2026-08-15T17:53:38.2104677Z ##[group]Installed versions
2026-08-15T17:53:38.2192063Z (node:2186) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
2026-08-15T17:53:38.2194185Z (Use `node --trace-deprecation ...` to show where the warning was created)
2026-08-15T17:53:38.2195790Z Successfully set up CPython (3.12.13)
2026-08-15T17:53:38.2197594Z ##[endgroup]
2026-08-15T17:53:38.2412804Z ##[group]Run pip install -r requirements.txt
2026-08-15T17:53:38.2413778Z [36;1mpip install -r requirements.txt[0m
2026-08-15T17:53:38.2475590Z shell: /usr/bin/bash -e {0}
2026-08-15T17:53:38.2476769Z env:
2026-08-15T17:53:38.2477840Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T17:53:38.2479596Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T17:53:38.2481182Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T17:53:38.2482769Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T17:53:38.2484955Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T17:53:38.2486706Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T17:53:38.2487999Z ##[endgroup]
2026-08-15T17:53:38.9823464Z Collecting google-genai==2.14.0 (from -r requirements.txt (line 1))
2026-08-15T17:53:39.0456698Z   Downloading google_genai-2.14.0-py3-none-any.whl.metadata (55 kB)
2026-08-15T17:53:39.0773495Z Collecting httpx==0.28.1 (from -r requirements.txt (line 2))
2026-08-15T17:53:39.0803555Z   Downloading httpx-0.28.1-py3-none-any.whl.metadata (7.1 kB)
2026-08-15T17:53:39.1002976Z Collecting requests==2.32.3 (from -r requirements.txt (line 6))
2026-08-15T17:53:39.1032023Z   Downloading requests-2.32.3-py3-none-any.whl.metadata (4.6 kB)
2026-08-15T17:53:39.1146399Z Collecting feedparser==6.0.11 (from -r requirements.txt (line 7))
2026-08-15T17:53:39.1177544Z   Downloading feedparser-6.0.11-py3-none-any.whl.metadata (2.4 kB)
2026-08-15T17:53:39.2752682Z Collecting Pillow==11.0.0 (from -r requirements.txt (line 8))
2026-08-15T17:53:39.2806281Z   Downloading pillow-11.0.0-cp312-cp312-manylinux_2_28_x86_64.whl.metadata (9.1 kB)
2026-08-15T17:53:39.2947233Z Collecting arabic-reshaper==3.0.0 (from -r requirements.txt (line 9))
2026-08-15T17:53:39.2977806Z   Downloading arabic_reshaper-3.0.0-py3-none-any.whl.metadata (12 kB)
2026-08-15T17:53:39.3618718Z Collecting python-bidi==0.6.3 (from -r requirements.txt (line 10))
2026-08-15T17:53:39.3659398Z   Downloading python_bidi-0.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (4.9 kB)
2026-08-15T17:53:39.3914992Z Collecting telethon==1.36.0 (from -r requirements.txt (line 11))
2026-08-15T17:53:39.3963083Z   Downloading Telethon-1.36.0.tar.gz (606 kB)
2026-08-15T17:53:39.4052080Z      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 606.3/606.3 kB 83.6 MB/s  0:00:00
2026-08-15T17:53:39.4686564Z   Installing build dependencies: started
2026-08-15T17:53:40.2513417Z   Installing build dependencies: finished with status 'done'
2026-08-15T17:53:40.2518572Z   Getting requirements to build wheel: started
2026-08-15T17:53:40.6913276Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T17:53:40.6923352Z   Preparing metadata (pyproject.toml): started
2026-08-15T17:53:40.8965271Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T17:53:40.9114334Z Collecting anyio<5.0.0,>=4.8.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T17:53:40.9145896Z   Downloading anyio-4.14.2-py3-none-any.whl.metadata (4.6 kB)
2026-08-15T17:53:40.9410335Z Collecting google-auth<3.0.0,>=2.56.0 (from google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T17:53:40.9440259Z   Downloading google_auth-2.56.3-py3-none-any.whl.metadata (6.0 kB)
2026-08-15T17:53:41.0353342Z Collecting pydantic<3.0.0,>=2.12.5 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T17:53:41.0386444Z   Downloading pydantic-2.13.4-py3-none-any.whl.metadata (109 kB)
2026-08-15T17:53:41.0576251Z Collecting tenacity<9.2.0,>=8.2.3 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T17:53:41.0608347Z   Downloading tenacity-9.1.4-py3-none-any.whl.metadata (1.2 kB)
2026-08-15T17:53:41.1452997Z Collecting websockets<17.0,>=13.0.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T17:53:41.1496448Z   Downloading websockets-16.1.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl.metadata (6.8 kB)
2026-08-15T17:53:41.1638056Z Collecting typing-extensions<5.0.0,>=4.14.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T17:53:41.1679826Z   Downloading typing_extensions-4.16.0-py3-none-any.whl.metadata (3.3 kB)
2026-08-15T17:53:41.1784537Z Collecting distro<2,>=1.7.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T17:53:41.1816056Z   Downloading distro-1.9.0-py3-none-any.whl.metadata (6.8 kB)
2026-08-15T17:53:41.1916263Z Collecting sniffio (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T17:53:41.1946483Z   Downloading sniffio-1.3.1-py3-none-any.whl.metadata (3.9 kB)
2026-08-15T17:53:41.2115580Z Collecting certifi (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T17:53:41.2144777Z   Downloading certifi-2026.7.22-py3-none-any.whl.metadata (2.5 kB)
2026-08-15T17:53:41.2279040Z Collecting httpcore==1.* (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T17:53:41.2312242Z   Downloading httpcore-1.0.9-py3-none-any.whl.metadata (21 kB)
2026-08-15T17:53:41.2451631Z Collecting idna (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T17:53:41.2481316Z   Downloading idna-3.18-py3-none-any.whl.metadata (6.1 kB)
2026-08-15T17:53:41.3530880Z Collecting charset-normalizer<4,>=2 (from requests==2.32.3->-r requirements.txt (line 6))
2026-08-15T17:53:41.3566224Z   Downloading charset_normalizer-3.5.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (45 kB)
2026-08-15T17:53:41.3810996Z Collecting urllib3<3,>=1.21.1 (from requests==2.32.3->-r requirements.txt (line 6))
2026-08-15T17:53:41.3842651Z   Downloading urllib3-2.7.0-py3-none-any.whl.metadata (6.9 kB)
2026-08-15T17:53:41.3972671Z Collecting sgmllib3k (from feedparser==6.0.11->-r requirements.txt (line 7))
2026-08-15T17:53:41.4006331Z   Downloading sgmllib3k-1.0.0.tar.gz (5.8 kB)
2026-08-15T17:53:41.4060611Z   Installing build dependencies: started
2026-08-15T17:53:41.9240658Z   Installing build dependencies: finished with status 'done'
2026-08-15T17:53:41.9247237Z   Getting requirements to build wheel: started
2026-08-15T17:53:42.2880514Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T17:53:42.2889133Z   Preparing metadata (pyproject.toml): started
2026-08-15T17:53:42.4761658Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T17:53:42.4862578Z Collecting pyaes (from telethon==1.36.0->-r requirements.txt (line 11))
2026-08-15T17:53:42.4892928Z   Downloading pyaes-1.6.1.tar.gz (28 kB)
2026-08-15T17:53:42.4960621Z   Installing build dependencies: started
2026-08-15T17:53:43.0143442Z   Installing build dependencies: finished with status 'done'
2026-08-15T17:53:43.0149023Z   Getting requirements to build wheel: started
2026-08-15T17:53:43.3639994Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T17:53:43.3648115Z   Preparing metadata (pyproject.toml): started
2026-08-15T17:53:43.5475499Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T17:53:43.5690671Z Collecting rsa (from telethon==1.36.0->-r requirements.txt (line 11))
2026-08-15T17:53:43.5721483Z   Downloading rsa-4.9.1-py3-none-any.whl.metadata (5.6 kB)
2026-08-15T17:53:43.5925252Z Collecting pyasn1-modules>=0.2.1 (from google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T17:53:43.5957717Z   Downloading pyasn1_modules-0.4.2-py3-none-any.whl.metadata (3.5 kB)
2026-08-15T17:53:43.7701096Z Collecting cryptography>=38.0.3 (from google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T17:53:43.7735532Z   Downloading cryptography-50.0.0-cp311-abi3-manylinux_2_34_x86_64.whl.metadata (4.3 kB)
2026-08-15T17:53:43.7873022Z Collecting h11>=0.16 (from httpcore==1.*->httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T17:53:43.7903582Z   Downloading h11-0.16.0-py3-none-any.whl.metadata (8.3 kB)
2026-08-15T17:53:43.8012418Z Collecting annotated-types>=0.6.0 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T17:53:43.8042601Z   Downloading annotated_types-0.8.0-py3-none-any.whl.metadata (15 kB)
2026-08-15T17:53:44.3983107Z Collecting pydantic-core==2.46.4 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T17:53:44.4015686Z   Downloading pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (6.6 kB)
2026-08-15T17:53:44.4146785Z Collecting typing-inspection>=0.4.2 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T17:53:44.4175214Z   Downloading typing_inspection-0.4.4-py3-none-any.whl.metadata (2.6 kB)
2026-08-15T17:53:44.5093357Z Collecting cffi>=2.0.0 (from cryptography>=38.0.3->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T17:53:44.5129180Z   Downloading cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl.metadata (2.5 kB)
2026-08-15T17:53:44.5240975Z Collecting pycparser (from cffi>=2.0.0->cryptography>=38.0.3->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T17:53:44.5272008Z   Downloading pycparser-3.0-py3-none-any.whl.metadata (8.2 kB)
2026-08-15T17:53:44.5483924Z Collecting pyasn1<0.7.0,>=0.6.1 (from pyasn1-modules>=0.2.1->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T17:53:44.5516298Z   Downloading pyasn1-0.6.4-py3-none-any.whl.metadata (8.4 kB)
2026-08-15T17:53:44.5647663Z Downloading google_genai-2.14.0-py3-none-any.whl (1.0 MB)
2026-08-15T17:53:44.5719793Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1.0/1.0 MB 155.5 MB/s  0:00:00
2026-08-15T17:53:44.5751004Z Downloading httpx-0.28.1-py3-none-any.whl (73 kB)
2026-08-15T17:53:44.5801095Z Downloading requests-2.32.3-py3-none-any.whl (64 kB)
2026-08-15T17:53:44.5848536Z Downloading feedparser-6.0.11-py3-none-any.whl (81 kB)
2026-08-15T17:53:44.5925241Z Downloading pillow-11.0.0-cp312-cp312-manylinux_2_28_x86_64.whl (4.4 MB)
2026-08-15T17:53:44.6116192Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.4/4.4 MB 243.8 MB/s  0:00:00
2026-08-15T17:53:44.6145149Z Downloading arabic_reshaper-3.0.0-py3-none-any.whl (20 kB)
2026-08-15T17:53:44.6197503Z Downloading python_bidi-0.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (286 kB)
2026-08-15T17:53:44.6258375Z Downloading anyio-4.14.2-py3-none-any.whl (125 kB)
2026-08-15T17:53:44.6308757Z Downloading charset_normalizer-3.5.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (248 kB)
2026-08-15T17:53:44.6360034Z Downloading distro-1.9.0-py3-none-any.whl (20 kB)
2026-08-15T17:53:44.6407800Z Downloading google_auth-2.56.3-py3-none-any.whl (259 kB)
2026-08-15T17:53:44.6463238Z Downloading httpcore-1.0.9-py3-none-any.whl (78 kB)
2026-08-15T17:53:44.6511960Z Downloading idna-3.18-py3-none-any.whl (65 kB)
2026-08-15T17:53:44.6561119Z Downloading pydantic-2.13.4-py3-none-any.whl (472 kB)
2026-08-15T17:53:44.6619115Z Downloading pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (2.1 MB)
2026-08-15T17:53:44.6698800Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.1/2.1 MB 313.7 MB/s  0:00:00
2026-08-15T17:53:44.6727294Z Downloading tenacity-9.1.4-py3-none-any.whl (28 kB)
2026-08-15T17:53:44.6779244Z Downloading typing_extensions-4.16.0-py3-none-any.whl (45 kB)
2026-08-15T17:53:44.6827298Z Downloading urllib3-2.7.0-py3-none-any.whl (131 kB)
2026-08-15T17:53:44.6876978Z Downloading websockets-16.1.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (187 kB)
2026-08-15T17:53:44.6928987Z Downloading annotated_types-0.8.0-py3-none-any.whl (13 kB)
2026-08-15T17:53:44.6973494Z Downloading certifi-2026.7.22-py3-none-any.whl (136 kB)
2026-08-15T17:53:44.7028819Z Downloading cryptography-50.0.0-cp311-abi3-manylinux_2_34_x86_64.whl (4.7 MB)
2026-08-15T17:53:44.7173083Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.7/4.7 MB 364.0 MB/s  0:00:00
2026-08-15T17:53:44.7203660Z Downloading cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (221 kB)
2026-08-15T17:53:44.7293019Z Downloading h11-0.16.0-py3-none-any.whl (37 kB)
2026-08-15T17:53:44.7339228Z Downloading pyasn1_modules-0.4.2-py3-none-any.whl (181 kB)
2026-08-15T17:53:44.7388377Z Downloading pyasn1-0.6.4-py3-none-any.whl (84 kB)
2026-08-15T17:53:44.7436032Z Downloading typing_inspection-0.4.4-py3-none-any.whl (14 kB)
2026-08-15T17:53:44.7489016Z Downloading pycparser-3.0-py3-none-any.whl (48 kB)
2026-08-15T17:53:44.7534442Z Downloading rsa-4.9.1-py3-none-any.whl (34 kB)
2026-08-15T17:53:44.7612921Z Downloading sniffio-1.3.1-py3-none-any.whl (10 kB)
2026-08-15T17:53:44.8517190Z Building wheels for collected packages: telethon, pyaes, sgmllib3k
2026-08-15T17:53:44.8525399Z   Building wheel for telethon (pyproject.toml): started
2026-08-15T17:53:45.2520560Z   Building wheel for telethon (pyproject.toml): finished with status 'done'
2026-08-15T17:53:45.2531483Z   Created wheel for telethon: filename=telethon-1.36.0-py3-none-any.whl size=680976 sha256=238c163558438e70a5542f0586bad3ddcc448945250a39f2cb627bf630c80027
2026-08-15T17:53:45.2533238Z   Stored in directory: /home/runner/.cache/pip/wheels/24/5b/1e/aa9bdcbb6e03ba1af024040fc49464b8b7c5ec432ce1916aa2
2026-08-15T17:53:45.2564309Z   Building wheel for pyaes (pyproject.toml): started
2026-08-15T17:53:45.4807846Z   Building wheel for pyaes (pyproject.toml): finished with status 'done'
2026-08-15T17:53:45.4812920Z   Created wheel for pyaes: filename=pyaes-1.6.1-py3-none-any.whl size=26422 sha256=7c5f87fc7cf7934c69bb5f67d0fa095de4b90ad7c7557db479f4db846e2a022f
2026-08-15T17:53:45.4814412Z   Stored in directory: /home/runner/.cache/pip/wheels/d9/43/32/ec313dd557e88e419489b9df40c04dad7b99576bde162496f8
2026-08-15T17:53:45.4835774Z   Building wheel for sgmllib3k (pyproject.toml): started
2026-08-15T17:53:45.7012903Z   Building wheel for sgmllib3k (pyproject.toml): finished with status 'done'
2026-08-15T17:53:45.7018189Z   Created wheel for sgmllib3k: filename=sgmllib3k-1.0.0-py3-none-any.whl size=6090 sha256=c14ebfc0c890659081fa9ed72d7c1d0c4cf84395b7932264b97c08fd34690d6b
2026-08-15T17:53:45.7019930Z   Stored in directory: /home/runner/.cache/pip/wheels/03/f5/1a/23761066dac1d0e8e683e5fdb27e12de53209d05a4a37e6246
2026-08-15T17:53:45.7034942Z Successfully built telethon pyaes sgmllib3k
2026-08-15T17:53:45.7663394Z Installing collected packages: sgmllib3k, python-bidi, pyaes, arabic-reshaper, websockets, urllib3, typing-extensions, tenacity, sniffio, pycparser, pyasn1, Pillow, idna, h11, feedparser, distro, charset-normalizer, certifi, annotated-types, typing-inspection, rsa, requests, pydantic-core, pyasn1-modules, httpcore, cffi, anyio, telethon, pydantic, httpx, cryptography, google-auth, google-genai
2026-08-15T17:53:49.6360741Z 
2026-08-15T17:53:49.6391307Z Successfully installed Pillow-11.0.0 annotated-types-0.8.0 anyio-4.14.2 arabic-reshaper-3.0.0 certifi-2026.7.22 cffi-2.1.1 charset-normalizer-3.5.1 cryptography-50.0.0 distro-1.9.0 feedparser-6.0.11 google-auth-2.56.3 google-genai-2.14.0 h11-0.16.0 httpcore-1.0.9 httpx-0.28.1 idna-3.18 pyaes-1.6.1 pyasn1-0.6.4 pyasn1-modules-0.4.2 pycparser-3.0 pydantic-2.13.4 pydantic-core-2.46.4 python-bidi-0.6.3 requests-2.32.3 rsa-4.9.1 sgmllib3k-1.0.0 sniffio-1.3.1 telethon-1.36.0 tenacity-9.1.4 typing-extensions-4.16.0 typing-inspection-0.4.4 urllib3-2.7.0 websockets-16.1.1
2026-08-15T17:53:49.8030891Z ##[group]Run python main.py
2026-08-15T17:53:49.8031238Z [36;1mpython main.py[0m
2026-08-15T17:53:49.8074360Z shell: /usr/bin/bash -e {0}
2026-08-15T17:53:49.8074687Z env:
2026-08-15T17:53:49.8075015Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T17:53:49.8075522Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T17:53:49.8076029Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T17:53:49.8076470Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T17:53:49.8076925Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T17:53:49.8077354Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T17:53:49.8078115Z   TELEGRAM_BOT_TOKEN: ***
2026-08-15T17:53:49.8078426Z   TELEGRAM_CHANNEL_ID: ***
2026-08-15T17:53:49.8078744Z   TELEGRAM_ADMIN_CHAT_ID: ***
2026-08-15T17:53:49.8079152Z   GEMINI_API_KEY: ***
2026-08-15T17:53:49.8079585Z   GEMINI_API_KEY_BACKUP: ***
2026-08-15T17:53:49.8080005Z   GROQ_API_KEY: ***
2026-08-15T17:53:49.8080325Z   CLOUDFLARE_ACCOUNT_ID: ***
2026-08-15T17:53:49.8080764Z   CLOUDFLARE_API_TOKEN: ***
2026-08-15T17:53:49.8081134Z   EITAA_TOKEN: ***
2026-08-15T17:53:49.8081399Z   EITAA_CHANNEL_ID: ***
2026-08-15T17:53:49.8081994Z   BALE_BOT_TOKEN: ***
2026-08-15T17:53:49.8082317Z   BALE_CHAT_ID: ***
2026-08-15T17:53:49.8082565Z ##[endgroup]
2026-08-15T17:55:38.4302389Z engagement_harvest: TELEGRAM_API_ID / TELEGRAM_API_HASH / TELETHON_SESSION_STRING not fully configured — skipping (see scripts/generate_telethon_session.py to set this up once; every other part of the pipeline is unaffected either way).
2026-08-15T17:55:38.4304077Z Gemini call to gemini-3.5-flash: call failed (attempt 1/3) on the primary key: 504 DEADLINE_EXCEEDED. {'error': {'code': 504, 'message': 'Deadline expired before operation could complete.', 'status': 'DEADLINE_EXCEEDED'}}. Retrying...
2026-08-15T17:55:38.4305862Z generate_reviewed_text: giving up on progress_recap after 3 attempts — still not ok: بخش عمده متن به زبان فارسی نوشته شده و انگلیسی بسیار کمی دارد. طبق معیار تعادل زبان، بیشتر متن (روایت یا دیالوگ اصلی) باید به انگلیسی باشد و فارسی فقط برای توضیح کلمات سخت یا یک جمله کوتاه به کار رود.
2026-08-15T17:55:38.6475022Z ##[group]Run set -euo pipefail
2026-08-15T17:55:38.6475432Z [36;1mset -euo pipefail[0m
2026-08-15T17:55:38.6475747Z [36;1mgit config user.name "channel-bot"[0m
2026-08-15T17:55:38.6476137Z [36;1mgit config user.email "actions@github.com"[0m
2026-08-15T17:55:38.6476495Z [36;1mgit add data/[0m
2026-08-15T17:55:38.6476803Z [36;1mif git diff --staged --quiet; then[0m
2026-08-15T17:55:38.6477160Z [36;1m  echo "No data changes to commit."[0m
2026-08-15T17:55:38.6477499Z [36;1m  exit 0[0m
2026-08-15T17:55:38.6477741Z [36;1mfi[0m
2026-08-15T17:55:38.6478064Z [36;1mgit commit -m "Daily post: update memory and database"[0m
2026-08-15T17:55:38.6478453Z [36;1mfor i in 1 2 3 4 5; do[0m
2026-08-15T17:55:38.6478798Z [36;1m  if git pull --rebase origin main && git push; then[0m
2026-08-15T17:55:38.6479178Z [36;1m    echo "Pushed successfully."[0m
2026-08-15T17:55:38.6479486Z [36;1m    exit 0[0m
2026-08-15T17:55:38.6479940Z [36;1m  fi[0m
2026-08-15T17:55:38.6480260Z [36;1m  echo "Push attempt $i failed, retrying..."[0m
2026-08-15T17:55:38.6480633Z [36;1m  sleep $((RANDOM % 10 + 5))[0m
2026-08-15T17:55:38.6480928Z [36;1mdone[0m
2026-08-15T17:55:38.6481227Z [36;1mecho "::error::Could not push after 5 attempts."[0m
2026-08-15T17:55:38.6481928Z [36;1m# A post can go out to Telegram successfully above even though the[0m
2026-08-15T17:55:38.6482438Z [36;1m# data/ commit that records it never lands — that leaves[0m
2026-08-15T17:55:38.6482941Z [36;1m# memory.json/posts.db/analytics.json/campaign_state.json stale on[0m
2026-08-15T17:55:38.6483442Z [36;1m# origin/main, and every downstream feature that reads them[0m
2026-08-15T17:55:38.6483911Z [36;1m# (dedup, review scheduling, weekly strategy) is stale until[0m
2026-08-15T17:55:38.6484375Z [36;1m# someone notices. This is the only thing that catches that[0m
2026-08-15T17:55:38.6484762Z [36;1m# specific failure mode.[0m
2026-08-15T17:55:38.6485195Z [36;1mif [ -n "$TELEGRAM_ADMIN_CHAT_ID" ] && [ -n "$TELEGRAM_BOT_TOKEN" ]; then[0m
2026-08-15T17:55:38.6485829Z [36;1m  curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \[0m
2026-08-15T17:55:38.6486408Z [36;1m    -d chat_id="${TELEGRAM_ADMIN_CHAT_ID}" \[0m
2026-08-15T17:55:38.6487331Z [36;1m    -d text="🔴 پست امروز احتمالاً منتشر شد، ولی ثبت تغییرات data/ توی گیت بعد از ۵ بار تلاش شکست خورد. یعنی memory.json/posts.db/analytics.json فعلاً روی origin/main قدیمی مونده — لازمه دستی چک و درست بشه، وگرنه ممکنه یه موضوع/جوک دوباره تکرار بشه." \[0m
2026-08-15T17:55:38.6488267Z [36;1m    > /dev/null || echo "::warning::Admin alert send also failed."[0m
2026-08-15T17:55:38.6488661Z [36;1melse[0m
2026-08-15T17:55:38.6489171Z [36;1m  echo "::warning::TELEGRAM_ADMIN_CHAT_ID or TELEGRAM_BOT_TOKEN not set — no admin alert sent for the push failure."[0m
2026-08-15T17:55:38.6489721Z [36;1mfi[0m
2026-08-15T17:55:38.6489944Z [36;1mexit 1[0m
2026-08-15T17:55:38.6530463Z shell: /usr/bin/bash -e {0}
2026-08-15T17:55:38.6530763Z env:
2026-08-15T17:55:38.6531103Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T17:55:38.6531602Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T17:55:38.6532261Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T17:55:38.6532689Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T17:55:38.6533117Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T17:55:38.6533535Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T17:55:38.6534130Z   TELEGRAM_BOT_TOKEN: ***
2026-08-15T17:55:38.6534427Z   TELEGRAM_ADMIN_CHAT_ID: ***
2026-08-15T17:55:38.6534709Z ##[endgroup]
2026-08-15T17:55:38.6731858Z No data changes to commit.
2026-08-15T17:55:38.6826786Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T17:55:38.6828045Z Post job cleanup.
2026-08-15T17:55:38.8003087Z (node:2340) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
2026-08-15T17:55:38.8003962Z (Use `node --trace-deprecation ...` to show where the warning was created)
2026-08-15T17:55:38.8248137Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T17:55:38.8250248Z Post job cleanup.
2026-08-15T17:55:38.9172824Z [command]/usr/bin/git version
2026-08-15T17:55:38.9219492Z git version 2.54.0
2026-08-15T17:55:38.9286340Z Temporarily overriding HOME='/home/runner/work/_temp/ac03e705-d9f7-4d2b-b234-27c7e2154785' before making global git config changes
2026-08-15T17:55:38.9287445Z Adding repository directory to the temporary git global config as a safe directory
2026-08-15T17:55:38.9288596Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T17:55:38.9302687Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
2026-08-15T17:55:38.9329221Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
2026-08-15T17:55:38.9612797Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
2026-08-15T17:55:38.9639867Z http.https://github.com/.extraheader
2026-08-15T17:55:38.9651252Z [command]/usr/bin/git config --local --unset-all http.https://github.com/.extraheader
2026-08-15T17:55:38.9687198Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
2026-08-15T17:55:38.9998131Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
2026-08-15T17:55:39.0036827Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
2026-08-15T17:55:39.0442379Z Cleaning up orphan processes
2026-08-15T17:55:39.0746449Z ##[warning]Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4, actions/setup-python@v5. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/




2026-08-15T12:54:48.6982939Z Current runner version: '2.336.0'
2026-08-15T12:54:48.7009403Z ##[group]Runner Image Provisioner
2026-08-15T12:54:48.7010791Z Hosted Compute Agent
2026-08-15T12:54:48.7011677Z Version: 20260729.566
2026-08-15T12:54:48.7012751Z Commit: cf7153fe6e25b664e8693c24944bf2b00355d109
2026-08-15T12:54:48.7013734Z Build Date: 2026-07-29T19:17:02Z
2026-08-15T12:54:48.7014572Z Worker ID: {86369889-cd17-454b-8b07-88c8a1c8ff39}
2026-08-15T12:54:48.7015483Z Azure Region: eastus
2026-08-15T12:54:48.7016136Z ##[endgroup]
2026-08-15T12:54:48.7019296Z ##[group]Operating System
2026-08-15T12:54:48.7020034Z Ubuntu
2026-08-15T12:54:48.7020792Z 24.04.4
2026-08-15T12:54:48.7021447Z LTS
2026-08-15T12:54:48.7022125Z ##[endgroup]
2026-08-15T12:54:48.7023057Z ##[group]Runner Image
2026-08-15T12:54:48.7023850Z Image: ubuntu-24.04
2026-08-15T12:54:48.7024535Z Version: 20260810.271.1
2026-08-15T12:54:48.7026011Z Included Software: https://github.com/actions/runner-images/blob/ubuntu24/20260810.271/images/ubuntu/Ubuntu2404-Readme.md
2026-08-15T12:54:48.7027724Z Image Release: https://github.com/actions/runner-images/releases/tag/ubuntu24%2F20260810.271
2026-08-15T12:54:48.7028811Z ##[endgroup]
2026-08-15T12:54:48.7030148Z ##[group]GITHUB_TOKEN Permissions
2026-08-15T12:54:48.7032639Z Contents: write
2026-08-15T12:54:48.7033473Z Metadata: read
2026-08-15T12:54:48.7034120Z ##[endgroup]
2026-08-15T12:54:48.7036695Z Secret source: Actions
2026-08-15T12:54:48.7038025Z Prepare workflow directory
2026-08-15T12:54:48.7372891Z Prepare all required actions
2026-08-15T12:54:48.7422232Z Getting action download info
2026-08-15T12:54:48.9620578Z Download action repository 'actions/checkout@v4' (SHA:11d5960a326750d5838078e36cf38b85af677262)
2026-08-15T12:54:49.1024940Z Download action repository 'actions/setup-python@v5' (SHA:a26af69be951a213d495a4c3e4e4022e16d87065)
2026-08-15T12:54:49.3223513Z Complete job name: post
2026-08-15T12:54:49.4018969Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T12:54:49.4028161Z ##[group]Run actions/checkout@v4
2026-08-15T12:54:49.4028996Z with:
2026-08-15T12:54:49.4029492Z   fetch-depth: 1
2026-08-15T12:54:49.4030123Z   repository: sajjadisr/ESL-Telegram-channel-automation
2026-08-15T12:54:49.4034229Z   token: ***
2026-08-15T12:54:49.4034736Z   ssh-strict: true
2026-08-15T12:54:49.4035237Z   ssh-user: git
2026-08-15T12:54:49.4035756Z   persist-credentials: true
2026-08-15T12:54:49.4036315Z   clean: true
2026-08-15T12:54:49.4036821Z   sparse-checkout-cone-mode: true
2026-08-15T12:54:49.4037408Z   fetch-tags: false
2026-08-15T12:54:49.4037919Z   show-progress: true
2026-08-15T12:54:49.4038437Z   lfs: false
2026-08-15T12:54:49.4038956Z   submodules: false
2026-08-15T12:54:49.4039481Z   set-safe-directory: true
2026-08-15T12:54:49.4040051Z   allow-unsafe-pr-checkout: false
2026-08-15T12:54:49.4040938Z ##[endgroup]
2026-08-15T12:54:49.5046219Z Syncing repository: sajjadisr/ESL-Telegram-channel-automation
2026-08-15T12:54:49.5050089Z ##[group]Getting Git version info
2026-08-15T12:54:49.5051911Z Working directory is '/home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation'
2026-08-15T12:54:49.5054728Z [command]/usr/bin/git version
2026-08-15T12:54:49.5090907Z git version 2.54.0
2026-08-15T12:54:49.5114308Z ##[endgroup]
2026-08-15T12:54:49.5129776Z Temporarily overriding HOME='/home/runner/work/_temp/85e8510c-bcde-4944-a385-cda0efde3917' before making global git config changes
2026-08-15T12:54:49.5132553Z Adding repository directory to the temporary git global config as a safe directory
2026-08-15T12:54:49.5135893Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T12:54:49.5184371Z Deleting the contents of '/home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation'
2026-08-15T12:54:49.5188041Z ##[group]Initializing the repository
2026-08-15T12:54:49.5193640Z [command]/usr/bin/git init /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T12:54:49.5286104Z hint: Using 'master' as the name for the initial branch. This default branch name
2026-08-15T12:54:49.5288019Z hint: will change to "main" in Git 3.0. To configure the initial branch name
2026-08-15T12:54:49.5289881Z hint: to use in all of your new repositories, which will suppress this warning,
2026-08-15T12:54:49.5291386Z hint: call:
2026-08-15T12:54:49.5292541Z hint:
2026-08-15T12:54:49.5293604Z hint: 	git config --global init.defaultBranch <name>
2026-08-15T12:54:49.5294942Z hint:
2026-08-15T12:54:49.5296428Z hint: Names commonly chosen instead of 'master' are 'main', 'trunk' and
2026-08-15T12:54:49.5298408Z hint: 'development'. The just-created branch can be renamed via this command:
2026-08-15T12:54:49.5300479Z hint:
2026-08-15T12:54:49.5301500Z hint: 	git branch -m <name>
2026-08-15T12:54:49.5302809Z hint:
2026-08-15T12:54:49.5304195Z hint: Disable this message with "git config set advice.defaultBranchName false"
2026-08-15T12:54:49.5307898Z Initialized empty Git repository in /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation/.git/
2026-08-15T12:54:49.5311647Z [command]/usr/bin/git remote add origin https://github.com/sajjadisr/ESL-Telegram-channel-automation
2026-08-15T12:54:49.5351684Z ##[endgroup]
2026-08-15T12:54:49.5353638Z ##[group]Disabling automatic garbage collection
2026-08-15T12:54:49.5355641Z [command]/usr/bin/git config --local gc.auto 0
2026-08-15T12:54:49.5388476Z ##[endgroup]
2026-08-15T12:54:49.5390128Z ##[group]Setting up auth
2026-08-15T12:54:49.5396490Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
2026-08-15T12:54:49.5431684Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
2026-08-15T12:54:49.5785408Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
2026-08-15T12:54:49.5825879Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
2026-08-15T12:54:49.6087310Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
2026-08-15T12:54:49.6127072Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
2026-08-15T12:54:49.6357050Z [command]/usr/bin/git config --local http.https://github.com/.extraheader AUTHORIZATION: basic ***
2026-08-15T12:54:49.6397713Z ##[endgroup]
2026-08-15T12:54:49.6398867Z ##[group]Fetching the repository
2026-08-15T12:54:49.6408727Z [command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=1 origin +f0d4193f910198beb35a3f36340ea84ce6bc244d:refs/remotes/origin/main
2026-08-15T12:54:49.9506292Z From https://github.com/sajjadisr/ESL-Telegram-channel-automation
2026-08-15T12:54:49.9508592Z  * [new ref]         f0d4193f910198beb35a3f36340ea84ce6bc244d -> origin/main
2026-08-15T12:54:49.9540295Z ##[endgroup]
2026-08-15T12:54:49.9542561Z ##[group]Determining the checkout info
2026-08-15T12:54:49.9544815Z ##[endgroup]
2026-08-15T12:54:49.9550678Z [command]/usr/bin/git sparse-checkout disable
2026-08-15T12:54:49.9599348Z [command]/usr/bin/git config --local --unset-all extensions.worktreeConfig
2026-08-15T12:54:49.9632852Z ##[group]Checking out the ref
2026-08-15T12:54:49.9637927Z [command]/usr/bin/git checkout --progress --force -B main refs/remotes/origin/main
2026-08-15T12:54:49.9772589Z Switched to a new branch 'main'
2026-08-15T12:54:49.9776613Z branch 'main' set up to track 'origin/main'.
2026-08-15T12:54:49.9782040Z ##[endgroup]
2026-08-15T12:54:49.9835817Z [command]/usr/bin/git log -1 --format=%H
2026-08-15T12:54:49.9864237Z f0d4193f910198beb35a3f36340ea84ce6bc244d
2026-08-15T12:54:50.0258349Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T12:54:50.0265515Z ##[group]Run actions/setup-python@v5
2026-08-15T12:54:50.0266431Z with:
2026-08-15T12:54:50.0267013Z   python-version: 3.12
2026-08-15T12:54:50.0267713Z   check-latest: false
2026-08-15T12:54:50.0277061Z   token: ***
2026-08-15T12:54:50.0277722Z   update-environment: true
2026-08-15T12:54:50.0278498Z   allow-prereleases: false
2026-08-15T12:54:50.0279249Z   freethreaded: false
2026-08-15T12:54:50.0279925Z ##[endgroup]
2026-08-15T12:54:50.1615992Z ##[group]Installed versions
2026-08-15T12:54:50.2198127Z (node:2181) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
2026-08-15T12:54:50.2202786Z (Use `node --trace-deprecation ...` to show where the warning was created)
2026-08-15T12:54:50.2205059Z Successfully set up CPython (3.12.13)
2026-08-15T12:54:50.2207186Z ##[endgroup]
2026-08-15T12:54:50.2438775Z ##[group]Run pip install -r requirements.txt
2026-08-15T12:54:50.2440564Z [36;1mpip install -r requirements.txt[0m
2026-08-15T12:54:50.2552061Z shell: /usr/bin/bash -e {0}
2026-08-15T12:54:50.2553888Z env:
2026-08-15T12:54:50.2555277Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T12:54:50.2557506Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T12:54:50.2560186Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T12:54:50.2562464Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T12:54:50.2564471Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T12:54:50.2566512Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T12:54:50.2568234Z ##[endgroup]
2026-08-15T12:54:52.9650278Z Collecting google-genai==2.14.0 (from -r requirements.txt (line 1))
2026-08-15T12:54:53.0188655Z   Downloading google_genai-2.14.0-py3-none-any.whl.metadata (55 kB)
2026-08-15T12:54:53.0524716Z Collecting httpx==0.28.1 (from -r requirements.txt (line 2))
2026-08-15T12:54:53.0561169Z   Downloading httpx-0.28.1-py3-none-any.whl.metadata (7.1 kB)
2026-08-15T12:54:53.0825097Z Collecting requests==2.32.3 (from -r requirements.txt (line 6))
2026-08-15T12:54:53.0860183Z   Downloading requests-2.32.3-py3-none-any.whl.metadata (4.6 kB)
2026-08-15T12:54:53.1005494Z Collecting feedparser==6.0.11 (from -r requirements.txt (line 7))
2026-08-15T12:54:53.1041970Z   Downloading feedparser-6.0.11-py3-none-any.whl.metadata (2.4 kB)
2026-08-15T12:54:53.2816114Z Collecting Pillow==11.0.0 (from -r requirements.txt (line 8))
2026-08-15T12:54:53.2859556Z   Downloading pillow-11.0.0-cp312-cp312-manylinux_2_28_x86_64.whl.metadata (9.1 kB)
2026-08-15T12:54:53.3019481Z Collecting arabic-reshaper==3.0.0 (from -r requirements.txt (line 9))
2026-08-15T12:54:53.3055560Z   Downloading arabic_reshaper-3.0.0-py3-none-any.whl.metadata (12 kB)
2026-08-15T12:54:53.3832069Z Collecting python-bidi==0.6.3 (from -r requirements.txt (line 10))
2026-08-15T12:54:53.3879540Z   Downloading python_bidi-0.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (4.9 kB)
2026-08-15T12:54:53.4165615Z Collecting telethon==1.36.0 (from -r requirements.txt (line 11))
2026-08-15T12:54:53.4212241Z   Downloading Telethon-1.36.0.tar.gz (606 kB)
2026-08-15T12:54:53.4329006Z      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 606.3/606.3 kB 62.7 MB/s  0:00:00
2026-08-15T12:54:53.5083957Z   Installing build dependencies: started
2026-08-15T12:54:54.9607838Z   Installing build dependencies: finished with status 'done'
2026-08-15T12:54:54.9613889Z   Getting requirements to build wheel: started
2026-08-15T12:54:55.4134513Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T12:54:55.4143548Z   Preparing metadata (pyproject.toml): started
2026-08-15T12:54:55.6199463Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T12:54:55.6366431Z Collecting anyio<5.0.0,>=4.8.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T12:54:55.6398882Z   Downloading anyio-4.14.2-py3-none-any.whl.metadata (4.6 kB)
2026-08-15T12:54:55.6688570Z Collecting google-auth<3.0.0,>=2.56.0 (from google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T12:54:55.6724727Z   Downloading google_auth-2.56.3-py3-none-any.whl.metadata (6.0 kB)
2026-08-15T12:54:55.7816065Z Collecting pydantic<3.0.0,>=2.12.5 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T12:54:55.7853601Z   Downloading pydantic-2.13.4-py3-none-any.whl.metadata (109 kB)
2026-08-15T12:54:55.8073689Z Collecting tenacity<9.2.0,>=8.2.3 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T12:54:55.8110188Z   Downloading tenacity-9.1.4-py3-none-any.whl.metadata (1.2 kB)
2026-08-15T12:54:55.9101378Z Collecting websockets<17.0,>=13.0.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T12:54:55.9141699Z   Downloading websockets-16.1.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl.metadata (6.8 kB)
2026-08-15T12:54:55.9320205Z Collecting typing-extensions<5.0.0,>=4.14.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T12:54:55.9357726Z   Downloading typing_extensions-4.16.0-py3-none-any.whl.metadata (3.3 kB)
2026-08-15T12:54:55.9475298Z Collecting distro<2,>=1.7.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T12:54:55.9510045Z   Downloading distro-1.9.0-py3-none-any.whl.metadata (6.8 kB)
2026-08-15T12:54:55.9618213Z Collecting sniffio (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T12:54:55.9650592Z   Downloading sniffio-1.3.1-py3-none-any.whl.metadata (3.9 kB)
2026-08-15T12:54:55.9849308Z Collecting certifi (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T12:54:55.9882980Z   Downloading certifi-2026.7.22-py3-none-any.whl.metadata (2.5 kB)
2026-08-15T12:54:56.0035525Z Collecting httpcore==1.* (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T12:54:56.0070190Z   Downloading httpcore-1.0.9-py3-none-any.whl.metadata (21 kB)
2026-08-15T12:54:56.0228727Z Collecting idna (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T12:54:56.0262444Z   Downloading idna-3.18-py3-none-any.whl.metadata (6.1 kB)
2026-08-15T12:54:56.1417105Z Collecting charset-normalizer<4,>=2 (from requests==2.32.3->-r requirements.txt (line 6))
2026-08-15T12:54:56.1455289Z   Downloading charset_normalizer-3.5.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (45 kB)
2026-08-15T12:54:56.1718136Z Collecting urllib3<3,>=1.21.1 (from requests==2.32.3->-r requirements.txt (line 6))
2026-08-15T12:54:56.1754942Z   Downloading urllib3-2.7.0-py3-none-any.whl.metadata (6.9 kB)
2026-08-15T12:54:56.1905488Z Collecting sgmllib3k (from feedparser==6.0.11->-r requirements.txt (line 7))
2026-08-15T12:54:56.1937981Z   Downloading sgmllib3k-1.0.0.tar.gz (5.8 kB)
2026-08-15T12:54:56.1996862Z   Installing build dependencies: started
2026-08-15T12:54:57.2351820Z   Installing build dependencies: finished with status 'done'
2026-08-15T12:54:57.2357524Z   Getting requirements to build wheel: started
2026-08-15T12:54:57.5854360Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T12:54:57.5863137Z   Preparing metadata (pyproject.toml): started
2026-08-15T12:54:57.7759971Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T12:54:57.7865227Z Collecting pyaes (from telethon==1.36.0->-r requirements.txt (line 11))
2026-08-15T12:54:57.7899951Z   Downloading pyaes-1.6.1.tar.gz (28 kB)
2026-08-15T12:54:57.7968652Z   Installing build dependencies: started
2026-08-15T12:54:58.5710761Z   Installing build dependencies: finished with status 'done'
2026-08-15T12:54:58.5716922Z   Getting requirements to build wheel: started
2026-08-15T12:54:58.9209040Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T12:54:58.9218016Z   Preparing metadata (pyproject.toml): started
2026-08-15T12:54:59.1123985Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T12:54:59.1254773Z Collecting rsa (from telethon==1.36.0->-r requirements.txt (line 11))
2026-08-15T12:54:59.1291867Z   Downloading rsa-4.9.1-py3-none-any.whl.metadata (5.6 kB)
2026-08-15T12:54:59.1529305Z Collecting pyasn1-modules>=0.2.1 (from google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T12:54:59.1567833Z   Downloading pyasn1_modules-0.4.2-py3-none-any.whl.metadata (3.5 kB)
2026-08-15T12:54:59.3575624Z Collecting cryptography>=38.0.3 (from google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T12:54:59.3611861Z   Downloading cryptography-50.0.0-cp311-abi3-manylinux_2_34_x86_64.whl.metadata (4.3 kB)
2026-08-15T12:54:59.3768554Z Collecting h11>=0.16 (from httpcore==1.*->httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T12:54:59.3804610Z   Downloading h11-0.16.0-py3-none-any.whl.metadata (8.3 kB)
2026-08-15T12:54:59.3948463Z Collecting annotated-types>=0.6.0 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T12:54:59.3983297Z   Downloading annotated_types-0.8.0-py3-none-any.whl.metadata (15 kB)
2026-08-15T12:55:00.0776023Z Collecting pydantic-core==2.46.4 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T12:55:00.0813563Z   Downloading pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (6.6 kB)
2026-08-15T12:55:00.0944012Z Collecting typing-inspection>=0.4.2 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T12:55:00.0978559Z   Downloading typing_inspection-0.4.4-py3-none-any.whl.metadata (2.6 kB)
2026-08-15T12:55:00.2087682Z Collecting cffi>=2.0.0 (from cryptography>=38.0.3->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T12:55:00.2128083Z   Downloading cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl.metadata (2.5 kB)
2026-08-15T12:55:00.2253769Z Collecting pycparser (from cffi>=2.0.0->cryptography>=38.0.3->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T12:55:00.2287133Z   Downloading pycparser-3.0-py3-none-any.whl.metadata (8.2 kB)
2026-08-15T12:55:00.2514511Z Collecting pyasn1<0.7.0,>=0.6.1 (from pyasn1-modules>=0.2.1->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T12:55:00.2555232Z   Downloading pyasn1-0.6.4-py3-none-any.whl.metadata (8.4 kB)
2026-08-15T12:55:00.2686108Z Downloading google_genai-2.14.0-py3-none-any.whl (1.0 MB)
2026-08-15T12:55:00.2783562Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1.0/1.0 MB 107.1 MB/s  0:00:00
2026-08-15T12:55:00.2819000Z Downloading httpx-0.28.1-py3-none-any.whl (73 kB)
2026-08-15T12:55:00.2876965Z Downloading requests-2.32.3-py3-none-any.whl (64 kB)
2026-08-15T12:55:00.2931897Z Downloading feedparser-6.0.11-py3-none-any.whl (81 kB)
2026-08-15T12:55:00.2991901Z Downloading pillow-11.0.0-cp312-cp312-manylinux_2_28_x86_64.whl (4.4 MB)
2026-08-15T12:55:00.3196227Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.4/4.4 MB 234.7 MB/s  0:00:00
2026-08-15T12:55:00.3232575Z Downloading arabic_reshaper-3.0.0-py3-none-any.whl (20 kB)
2026-08-15T12:55:00.3312579Z Downloading python_bidi-0.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (286 kB)
2026-08-15T12:55:00.3377652Z Downloading anyio-4.14.2-py3-none-any.whl (125 kB)
2026-08-15T12:55:00.3449961Z Downloading charset_normalizer-3.5.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (248 kB)
2026-08-15T12:55:00.3510779Z Downloading distro-1.9.0-py3-none-any.whl (20 kB)
2026-08-15T12:55:00.3569065Z Downloading google_auth-2.56.3-py3-none-any.whl (259 kB)
2026-08-15T12:55:00.3644257Z Downloading httpcore-1.0.9-py3-none-any.whl (78 kB)
2026-08-15T12:55:00.3701113Z Downloading idna-3.18-py3-none-any.whl (65 kB)
2026-08-15T12:55:00.3770359Z Downloading pydantic-2.13.4-py3-none-any.whl (472 kB)
2026-08-15T12:55:00.3840016Z Downloading pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (2.1 MB)
2026-08-15T12:55:00.3947331Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.1/2.1 MB 221.6 MB/s  0:00:00
2026-08-15T12:55:00.3981122Z Downloading tenacity-9.1.4-py3-none-any.whl (28 kB)
2026-08-15T12:55:00.4035741Z Downloading typing_extensions-4.16.0-py3-none-any.whl (45 kB)
2026-08-15T12:55:00.4105993Z Downloading urllib3-2.7.0-py3-none-any.whl (131 kB)
2026-08-15T12:55:00.4164524Z Downloading websockets-16.1.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (187 kB)
2026-08-15T12:55:00.4226570Z Downloading annotated_types-0.8.0-py3-none-any.whl (13 kB)
2026-08-15T12:55:00.4288728Z Downloading certifi-2026.7.22-py3-none-any.whl (136 kB)
2026-08-15T12:55:00.4353000Z Downloading cryptography-50.0.0-cp311-abi3-manylinux_2_34_x86_64.whl (4.7 MB)
2026-08-15T12:55:00.4549513Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.7/4.7 MB 262.1 MB/s  0:00:00
2026-08-15T12:55:00.4588594Z Downloading cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (221 kB)
2026-08-15T12:55:00.4650869Z Downloading h11-0.16.0-py3-none-any.whl (37 kB)
2026-08-15T12:55:00.4707539Z Downloading pyasn1_modules-0.4.2-py3-none-any.whl (181 kB)
2026-08-15T12:55:00.4766453Z Downloading pyasn1-0.6.4-py3-none-any.whl (84 kB)
2026-08-15T12:55:00.4823370Z Downloading typing_inspection-0.4.4-py3-none-any.whl (14 kB)
2026-08-15T12:55:00.4876819Z Downloading pycparser-3.0-py3-none-any.whl (48 kB)
2026-08-15T12:55:00.4932225Z Downloading rsa-4.9.1-py3-none-any.whl (34 kB)
2026-08-15T12:55:00.4986451Z Downloading sniffio-1.3.1-py3-none-any.whl (10 kB)
2026-08-15T12:55:00.5940903Z Building wheels for collected packages: telethon, pyaes, sgmllib3k
2026-08-15T12:55:00.5950063Z   Building wheel for telethon (pyproject.toml): started
2026-08-15T12:55:01.0125146Z   Building wheel for telethon (pyproject.toml): finished with status 'done'
2026-08-15T12:55:01.0136080Z   Created wheel for telethon: filename=telethon-1.36.0-py3-none-any.whl size=680976 sha256=b3b57aca0457d4f8f9b95935418efa30b744d682e92b14e3cb91cfbf478d8c22
2026-08-15T12:55:01.0137427Z   Stored in directory: /home/runner/.cache/pip/wheels/24/5b/1e/aa9bdcbb6e03ba1af024040fc49464b8b7c5ec432ce1916aa2
2026-08-15T12:55:01.0170180Z   Building wheel for pyaes (pyproject.toml): started
2026-08-15T12:55:01.2519807Z   Building wheel for pyaes (pyproject.toml): finished with status 'done'
2026-08-15T12:55:01.2526476Z   Created wheel for pyaes: filename=pyaes-1.6.1-py3-none-any.whl size=26422 sha256=098bc1953a1baf0b59a8a856d1befba6b3cfc40987a905a685bb25689618f83c
2026-08-15T12:55:01.2528055Z   Stored in directory: /home/runner/.cache/pip/wheels/d9/43/32/ec313dd557e88e419489b9df40c04dad7b99576bde162496f8
2026-08-15T12:55:01.2551506Z   Building wheel for sgmllib3k (pyproject.toml): started
2026-08-15T12:55:01.4853895Z   Building wheel for sgmllib3k (pyproject.toml): finished with status 'done'
2026-08-15T12:55:01.4860573Z   Created wheel for sgmllib3k: filename=sgmllib3k-1.0.0-py3-none-any.whl size=6090 sha256=84f0e22483d3c5a7c13e061771489abcd7bf2f6e68705f7a2edfe3ef4c9f482b
2026-08-15T12:55:01.4862991Z   Stored in directory: /home/runner/.cache/pip/wheels/03/f5/1a/23761066dac1d0e8e683e5fdb27e12de53209d05a4a37e6246
2026-08-15T12:55:01.4879066Z Successfully built telethon pyaes sgmllib3k
2026-08-15T12:55:01.5549486Z Installing collected packages: sgmllib3k, python-bidi, pyaes, arabic-reshaper, websockets, urllib3, typing-extensions, tenacity, sniffio, pycparser, pyasn1, Pillow, idna, h11, feedparser, distro, charset-normalizer, certifi, annotated-types, typing-inspection, rsa, requests, pydantic-core, pyasn1-modules, httpcore, cffi, anyio, telethon, pydantic, httpx, cryptography, google-auth, google-genai
2026-08-15T12:55:05.7315329Z 
2026-08-15T12:55:05.7349084Z Successfully installed Pillow-11.0.0 annotated-types-0.8.0 anyio-4.14.2 arabic-reshaper-3.0.0 certifi-2026.7.22 cffi-2.1.1 charset-normalizer-3.5.1 cryptography-50.0.0 distro-1.9.0 feedparser-6.0.11 google-auth-2.56.3 google-genai-2.14.0 h11-0.16.0 httpcore-1.0.9 httpx-0.28.1 idna-3.18 pyaes-1.6.1 pyasn1-0.6.4 pyasn1-modules-0.4.2 pycparser-3.0 pydantic-2.13.4 pydantic-core-2.46.4 python-bidi-0.6.3 requests-2.32.3 rsa-4.9.1 sgmllib3k-1.0.0 sniffio-1.3.1 telethon-1.36.0 tenacity-9.1.4 typing-extensions-4.16.0 typing-inspection-0.4.4 urllib3-2.7.0 websockets-16.1.1
2026-08-15T12:55:05.9647210Z ##[group]Run python main.py
2026-08-15T12:55:05.9647562Z [36;1mpython main.py[0m
2026-08-15T12:55:05.9687918Z shell: /usr/bin/bash -e {0}
2026-08-15T12:55:05.9688232Z env:
2026-08-15T12:55:05.9688546Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T12:55:05.9689047Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T12:55:05.9689525Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T12:55:05.9689962Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T12:55:05.9690394Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T12:55:05.9690825Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T12:55:05.9691593Z   TELEGRAM_BOT_TOKEN: ***
2026-08-15T12:55:05.9691904Z   TELEGRAM_CHANNEL_ID: ***
2026-08-15T12:55:05.9692198Z   TELEGRAM_ADMIN_CHAT_ID: ***
2026-08-15T12:55:05.9692915Z   GEMINI_API_KEY: ***
2026-08-15T12:55:05.9693357Z   GEMINI_API_KEY_BACKUP: ***
2026-08-15T12:55:05.9693776Z   GROQ_API_KEY: ***
2026-08-15T12:55:05.9694076Z   CLOUDFLARE_ACCOUNT_ID: ***
2026-08-15T12:55:05.9694488Z   CLOUDFLARE_API_TOKEN: ***
2026-08-15T12:55:05.9694830Z   EITAA_TOKEN: ***
2026-08-15T12:55:05.9695078Z   EITAA_CHANNEL_ID: ***
2026-08-15T12:55:05.9695415Z   BALE_BOT_TOKEN: ***
2026-08-15T12:55:05.9695685Z   BALE_CHAT_ID: ***
2026-08-15T12:55:05.9695917Z ##[endgroup]
2026-08-15T12:55:35.0147183Z engagement_harvest: TELEGRAM_API_ID / TELEGRAM_API_HASH / TELETHON_SESSION_STRING not fully configured — skipping (see scripts/generate_telethon_session.py to set this up once; every other part of the pipeline is unaffected either way).
2026-08-15T12:55:35.0149271Z generate_reviewed_text: giving up on progress_recap after 3 attempts — still not ok: بخش عمده‌ی متن به زبان فارسی نوشته شده و جملات انگلیسی بسیار کمی در آن به کار رفته است (عدم رعایت تعادل زبانی به نفع انگلیسی). همچنین یک غلط املایی در عبارت «ک کلی هم» وجود دارد که احتمالاً منظور «و کلی هم» بوده است.
2026-08-15T12:55:35.3775987Z ##[group]Run set -euo pipefail
2026-08-15T12:55:35.3776402Z [36;1mset -euo pipefail[0m
2026-08-15T12:55:35.3776722Z [36;1mgit config user.name "channel-bot"[0m
2026-08-15T12:55:35.3777136Z [36;1mgit config user.email "actions@github.com"[0m
2026-08-15T12:55:35.3777483Z [36;1mgit add data/[0m
2026-08-15T12:55:35.3777769Z [36;1mif git diff --staged --quiet; then[0m
2026-08-15T12:55:35.3778111Z [36;1m  echo "No data changes to commit."[0m
2026-08-15T12:55:35.3778435Z [36;1m  exit 0[0m
2026-08-15T12:55:35.3778668Z [36;1mfi[0m
2026-08-15T12:55:35.3778979Z [36;1mgit commit -m "Daily post: update memory and database"[0m
2026-08-15T12:55:35.3779371Z [36;1mfor i in 1 2 3 4 5; do[0m
2026-08-15T12:55:35.3779719Z [36;1m  if git pull --rebase origin main && git push; then[0m
2026-08-15T12:55:35.3780093Z [36;1m    echo "Pushed successfully."[0m
2026-08-15T12:55:35.3780396Z [36;1m    exit 0[0m
2026-08-15T12:55:35.3780635Z [36;1m  fi[0m
2026-08-15T12:55:35.3780936Z [36;1m  echo "Push attempt $i failed, retrying..."[0m
2026-08-15T12:55:35.3781285Z [36;1m  sleep $((RANDOM % 10 + 5))[0m
2026-08-15T12:55:35.3781569Z [36;1mdone[0m
2026-08-15T12:55:35.3782028Z [36;1mecho "::error::Could not push after 5 attempts."[0m
2026-08-15T12:55:35.3782882Z [36;1m# A post can go out to Telegram successfully above even though the[0m
2026-08-15T12:55:35.3783387Z [36;1m# data/ commit that records it never lands — that leaves[0m
2026-08-15T12:55:35.3783879Z [36;1m# memory.json/posts.db/analytics.json/campaign_state.json stale on[0m
2026-08-15T12:55:35.3784381Z [36;1m# origin/main, and every downstream feature that reads them[0m
2026-08-15T12:55:35.3784848Z [36;1m# (dedup, review scheduling, weekly strategy) is stale until[0m
2026-08-15T12:55:35.3785313Z [36;1m# someone notices. This is the only thing that catches that[0m
2026-08-15T12:55:35.3785718Z [36;1m# specific failure mode.[0m
2026-08-15T12:55:35.3786134Z [36;1mif [ -n "$TELEGRAM_ADMIN_CHAT_ID" ] && [ -n "$TELEGRAM_BOT_TOKEN" ]; then[0m
2026-08-15T12:55:35.3786747Z [36;1m  curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \[0m
2026-08-15T12:55:35.3787289Z [36;1m    -d chat_id="${TELEGRAM_ADMIN_CHAT_ID}" \[0m
2026-08-15T12:55:35.3788185Z [36;1m    -d text="🔴 پست امروز احتمالاً منتشر شد، ولی ثبت تغییرات data/ توی گیت بعد از ۵ بار تلاش شکست خورد. یعنی memory.json/posts.db/analytics.json فعلاً روی origin/main قدیمی مونده — لازمه دستی چک و درست بشه، وگرنه ممکنه یه موضوع/جوک دوباره تکرار بشه." \[0m
2026-08-15T12:55:35.3789114Z [36;1m    > /dev/null || echo "::warning::Admin alert send also failed."[0m
2026-08-15T12:55:35.3789505Z [36;1melse[0m
2026-08-15T12:55:35.3790007Z [36;1m  echo "::warning::TELEGRAM_ADMIN_CHAT_ID or TELEGRAM_BOT_TOKEN not set — no admin alert sent for the push failure."[0m
2026-08-15T12:55:35.3790563Z [36;1mfi[0m
2026-08-15T12:55:35.3790781Z [36;1mexit 1[0m
2026-08-15T12:55:35.3830130Z shell: /usr/bin/bash -e {0}
2026-08-15T12:55:35.3830437Z env:
2026-08-15T12:55:35.3830779Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T12:55:35.3831269Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T12:55:35.3831768Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T12:55:35.3832198Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T12:55:35.3832960Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T12:55:35.3833399Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T12:55:35.3834037Z   TELEGRAM_BOT_TOKEN: ***
2026-08-15T12:55:35.3834329Z   TELEGRAM_ADMIN_CHAT_ID: ***
2026-08-15T12:55:35.3834605Z ##[endgroup]
2026-08-15T12:55:35.4013437Z No data changes to commit.
2026-08-15T12:55:35.4136935Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T12:55:35.4138250Z Post job cleanup.
2026-08-15T12:55:35.5407788Z (node:2318) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
2026-08-15T12:55:35.5408630Z (Use `node --trace-deprecation ...` to show where the warning was created)
2026-08-15T12:55:35.5667448Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T12:55:35.5669698Z Post job cleanup.
2026-08-15T12:55:35.6713615Z [command]/usr/bin/git version
2026-08-15T12:55:35.6767015Z git version 2.54.0
2026-08-15T12:55:35.6853232Z Temporarily overriding HOME='/home/runner/work/_temp/63fb515c-1139-4eb1-8c86-1fb6669b7804' before making global git config changes
2026-08-15T12:55:35.6856073Z Adding repository directory to the temporary git global config as a safe directory
2026-08-15T12:55:35.6862932Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T12:55:35.6928626Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
2026-08-15T12:55:35.6980529Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
2026-08-15T12:55:35.7299007Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
2026-08-15T12:55:35.7335632Z http.https://github.com/.extraheader
2026-08-15T12:55:35.7360267Z [command]/usr/bin/git config --local --unset-all http.https://github.com/.extraheader
2026-08-15T12:55:35.7419815Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
2026-08-15T12:55:35.7715746Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
2026-08-15T12:55:35.7774076Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
2026-08-15T12:55:35.8191908Z Cleaning up orphan processes
2026-08-15T12:55:35.8525326Z ##[warning]Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4, actions/setup-python@v5. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/





2026-08-15T11:38:19.4788980Z Current runner version: '2.336.0'
2026-08-15T11:38:19.4814137Z ##[group]Runner Image Provisioner
2026-08-15T11:38:19.4815163Z Hosted Compute Agent
2026-08-15T11:38:19.4815928Z Version: 20260729.566
2026-08-15T11:38:19.4816808Z Commit: cf7153fe6e25b664e8693c24944bf2b00355d109
2026-08-15T11:38:19.4817716Z Build Date: 2026-07-29T19:17:02Z
2026-08-15T11:38:19.4818938Z Worker ID: {3fb3bc21-c6ec-4711-951f-0e1165f993e6}
2026-08-15T11:38:19.4819997Z Azure Region: westus2
2026-08-15T11:38:19.4820846Z ##[endgroup]
2026-08-15T11:38:19.4822559Z ##[group]Operating System
2026-08-15T11:38:19.4823424Z Ubuntu
2026-08-15T11:38:19.4824485Z 24.04.4
2026-08-15T11:38:19.4825155Z LTS
2026-08-15T11:38:19.4825880Z ##[endgroup]
2026-08-15T11:38:19.4826623Z ##[group]Runner Image
2026-08-15T11:38:19.4827399Z Image: ubuntu-24.04
2026-08-15T11:38:19.4828158Z Version: 20260810.271.1
2026-08-15T11:38:19.4829908Z Included Software: https://github.com/actions/runner-images/blob/ubuntu24/20260810.271/images/ubuntu/Ubuntu2404-Readme.md
2026-08-15T11:38:19.4831594Z Image Release: https://github.com/actions/runner-images/releases/tag/ubuntu24%2F20260810.271
2026-08-15T11:38:19.4832815Z ##[endgroup]
2026-08-15T11:38:19.4834090Z ##[group]GITHUB_TOKEN Permissions
2026-08-15T11:38:19.4836357Z Contents: write
2026-08-15T11:38:19.4837166Z Metadata: read
2026-08-15T11:38:19.4837909Z ##[endgroup]
2026-08-15T11:38:19.4840486Z Secret source: Actions
2026-08-15T11:38:19.4842021Z Prepare workflow directory
2026-08-15T11:38:19.5196517Z Prepare all required actions
2026-08-15T11:38:19.5269785Z Getting action download info
2026-08-15T11:38:19.8743358Z Download action repository 'actions/checkout@v4' (SHA:11d5960a326750d5838078e36cf38b85af677262)
2026-08-15T11:38:20.0083702Z Download action repository 'actions/setup-python@v5' (SHA:a26af69be951a213d495a4c3e4e4022e16d87065)
2026-08-15T11:38:20.1876058Z Complete job name: post
2026-08-15T11:38:20.2652406Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T11:38:20.2661335Z ##[group]Run actions/checkout@v4
2026-08-15T11:38:20.2662162Z with:
2026-08-15T11:38:20.2662671Z   fetch-depth: 1
2026-08-15T11:38:20.2663300Z   repository: sajjadisr/ESL-Telegram-channel-automation
2026-08-15T11:38:20.2667500Z   token: ***
2026-08-15T11:38:20.2668013Z   ssh-strict: true
2026-08-15T11:38:20.2668722Z   ssh-user: git
2026-08-15T11:38:20.2669277Z   persist-credentials: true
2026-08-15T11:38:20.2669850Z   clean: true
2026-08-15T11:38:20.2670367Z   sparse-checkout-cone-mode: true
2026-08-15T11:38:20.2670985Z   fetch-tags: false
2026-08-15T11:38:20.2671526Z   show-progress: true
2026-08-15T11:38:20.2672069Z   lfs: false
2026-08-15T11:38:20.2672606Z   submodules: false
2026-08-15T11:38:20.2673147Z   set-safe-directory: true
2026-08-15T11:38:20.2673736Z   allow-unsafe-pr-checkout: false
2026-08-15T11:38:20.2674612Z ##[endgroup]
2026-08-15T11:38:20.3687653Z Syncing repository: sajjadisr/ESL-Telegram-channel-automation
2026-08-15T11:38:20.3690958Z ##[group]Getting Git version info
2026-08-15T11:38:20.3692730Z Working directory is '/home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation'
2026-08-15T11:38:20.3695220Z [command]/usr/bin/git version
2026-08-15T11:38:20.3764430Z git version 2.54.0
2026-08-15T11:38:20.3788259Z ##[endgroup]
2026-08-15T11:38:20.3804273Z Temporarily overriding HOME='/home/runner/work/_temp/b68ac4a1-19b4-4e8d-bfa0-781447677d7a' before making global git config changes
2026-08-15T11:38:20.3806062Z Adding repository directory to the temporary git global config as a safe directory
2026-08-15T11:38:20.3810775Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T11:38:20.3876219Z Deleting the contents of '/home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation'
2026-08-15T11:38:20.3885130Z ##[group]Initializing the repository
2026-08-15T11:38:20.3890466Z [command]/usr/bin/git init /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T11:38:20.4001702Z hint: Using 'master' as the name for the initial branch. This default branch name
2026-08-15T11:38:20.4003528Z hint: will change to "main" in Git 3.0. To configure the initial branch name
2026-08-15T11:38:20.4005379Z hint: to use in all of your new repositories, which will suppress this warning,
2026-08-15T11:38:20.4006795Z hint: call:
2026-08-15T11:38:20.4007542Z hint:
2026-08-15T11:38:20.4008765Z hint: 	git config --global init.defaultBranch <name>
2026-08-15T11:38:20.4009882Z hint:
2026-08-15T11:38:20.4010912Z hint: Names commonly chosen instead of 'master' are 'main', 'trunk' and
2026-08-15T11:38:20.4012584Z hint: 'development'. The just-created branch can be renamed via this command:
2026-08-15T11:38:20.4013918Z hint:
2026-08-15T11:38:20.4014709Z hint: 	git branch -m <name>
2026-08-15T11:38:20.4015569Z hint:
2026-08-15T11:38:20.4016685Z hint: Disable this message with "git config set advice.defaultBranchName false"
2026-08-15T11:38:20.4020459Z Initialized empty Git repository in /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation/.git/
2026-08-15T11:38:20.4024274Z [command]/usr/bin/git remote add origin https://github.com/sajjadisr/ESL-Telegram-channel-automation
2026-08-15T11:38:20.4065681Z ##[endgroup]
2026-08-15T11:38:20.4067236Z ##[group]Disabling automatic garbage collection
2026-08-15T11:38:20.4070763Z [command]/usr/bin/git config --local gc.auto 0
2026-08-15T11:38:20.4135693Z ##[endgroup]
2026-08-15T11:38:20.4137113Z ##[group]Setting up auth
2026-08-15T11:38:20.4143051Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
2026-08-15T11:38:20.4214318Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
2026-08-15T11:38:20.4624040Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
2026-08-15T11:38:20.4661940Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
2026-08-15T11:38:20.4886064Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
2026-08-15T11:38:20.4924269Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
2026-08-15T11:38:20.5150216Z [command]/usr/bin/git config --local http.https://github.com/.extraheader AUTHORIZATION: basic ***
2026-08-15T11:38:20.5190011Z ##[endgroup]
2026-08-15T11:38:20.5191648Z ##[group]Fetching the repository
2026-08-15T11:38:20.5201898Z [command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=1 origin +f0d4193f910198beb35a3f36340ea84ce6bc244d:refs/remotes/origin/main
2026-08-15T11:38:21.0186588Z From https://github.com/sajjadisr/ESL-Telegram-channel-automation
2026-08-15T11:38:21.0187774Z  * [new ref]         f0d4193f910198beb35a3f36340ea84ce6bc244d -> origin/main
2026-08-15T11:38:21.0223136Z ##[endgroup]
2026-08-15T11:38:21.0224539Z ##[group]Determining the checkout info
2026-08-15T11:38:21.0226143Z ##[endgroup]
2026-08-15T11:38:21.0231658Z [command]/usr/bin/git sparse-checkout disable
2026-08-15T11:38:21.0278887Z [command]/usr/bin/git config --local --unset-all extensions.worktreeConfig
2026-08-15T11:38:21.0310733Z ##[group]Checking out the ref
2026-08-15T11:38:21.0314664Z [command]/usr/bin/git checkout --progress --force -B main refs/remotes/origin/main
2026-08-15T11:38:21.0448962Z Switched to a new branch 'main'
2026-08-15T11:38:21.0452466Z branch 'main' set up to track 'origin/main'.
2026-08-15T11:38:21.0457504Z ##[endgroup]
2026-08-15T11:38:21.0499837Z [command]/usr/bin/git log -1 --format=%H
2026-08-15T11:38:21.0526037Z f0d4193f910198beb35a3f36340ea84ce6bc244d
2026-08-15T11:38:21.0869994Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T11:38:21.0874876Z ##[group]Run actions/setup-python@v5
2026-08-15T11:38:21.0876010Z with:
2026-08-15T11:38:21.0876834Z   python-version: 3.12
2026-08-15T11:38:21.0877802Z   check-latest: false
2026-08-15T11:38:21.0884049Z   token: ***
2026-08-15T11:38:21.0884612Z   update-environment: true
2026-08-15T11:38:21.0885207Z   allow-prereleases: false
2026-08-15T11:38:21.0885783Z   freethreaded: false
2026-08-15T11:38:21.0886314Z ##[endgroup]
2026-08-15T11:38:21.2197897Z ##[group]Installed versions
2026-08-15T11:38:21.2297685Z (node:2144) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
2026-08-15T11:38:21.2300272Z (Use `node --trace-deprecation ...` to show where the warning was created)
2026-08-15T11:38:21.2301932Z Successfully set up CPython (3.12.13)
2026-08-15T11:38:21.2303880Z ##[endgroup]
2026-08-15T11:38:21.2490568Z ##[group]Run pip install -r requirements.txt
2026-08-15T11:38:21.2491404Z [36;1mpip install -r requirements.txt[0m
2026-08-15T11:38:21.2544701Z shell: /usr/bin/bash -e {0}
2026-08-15T11:38:21.2545321Z env:
2026-08-15T11:38:21.2545923Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T11:38:21.2546859Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T11:38:21.2547762Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T11:38:21.2548937Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T11:38:21.2549823Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T11:38:21.2550703Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T11:38:21.2551425Z ##[endgroup]
2026-08-15T11:38:22.1448116Z Collecting google-genai==2.14.0 (from -r requirements.txt (line 1))
2026-08-15T11:38:22.2032787Z   Downloading google_genai-2.14.0-py3-none-any.whl.metadata (55 kB)
2026-08-15T11:38:22.2411368Z Collecting httpx==0.28.1 (from -r requirements.txt (line 2))
2026-08-15T11:38:22.2476161Z   Downloading httpx-0.28.1-py3-none-any.whl.metadata (7.1 kB)
2026-08-15T11:38:22.2832047Z Collecting requests==2.32.3 (from -r requirements.txt (line 6))
2026-08-15T11:38:22.2899036Z   Downloading requests-2.32.3-py3-none-any.whl.metadata (4.6 kB)
2026-08-15T11:38:22.3158063Z Collecting feedparser==6.0.11 (from -r requirements.txt (line 7))
2026-08-15T11:38:22.3230991Z   Downloading feedparser-6.0.11-py3-none-any.whl.metadata (2.4 kB)
2026-08-15T11:38:22.5282192Z Collecting Pillow==11.0.0 (from -r requirements.txt (line 8))
2026-08-15T11:38:22.5359689Z   Downloading pillow-11.0.0-cp312-cp312-manylinux_2_28_x86_64.whl.metadata (9.1 kB)
2026-08-15T11:38:22.5619004Z Collecting arabic-reshaper==3.0.0 (from -r requirements.txt (line 9))
2026-08-15T11:38:22.5692064Z   Downloading arabic_reshaper-3.0.0-py3-none-any.whl.metadata (12 kB)
2026-08-15T11:38:22.6545546Z Collecting python-bidi==0.6.3 (from -r requirements.txt (line 10))
2026-08-15T11:38:22.6622209Z   Downloading python_bidi-0.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (4.9 kB)
2026-08-15T11:38:22.6959887Z Collecting telethon==1.36.0 (from -r requirements.txt (line 11))
2026-08-15T11:38:22.7034339Z   Downloading Telethon-1.36.0.tar.gz (606 kB)
2026-08-15T11:38:22.7463041Z      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 606.3/606.3 kB 14.6 MB/s  0:00:00
2026-08-15T11:38:22.8241208Z   Installing build dependencies: started
2026-08-15T11:38:23.7348227Z   Installing build dependencies: finished with status 'done'
2026-08-15T11:38:23.7354155Z   Getting requirements to build wheel: started
2026-08-15T11:38:24.1534622Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T11:38:24.1556425Z   Preparing metadata (pyproject.toml): started
2026-08-15T11:38:24.3483722Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T11:38:24.3694836Z Collecting anyio<5.0.0,>=4.8.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T11:38:24.3761765Z   Downloading anyio-4.14.2-py3-none-any.whl.metadata (4.6 kB)
2026-08-15T11:38:24.4096995Z Collecting google-auth<3.0.0,>=2.56.0 (from google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T11:38:24.4163289Z   Downloading google_auth-2.56.3-py3-none-any.whl.metadata (6.0 kB)
2026-08-15T11:38:24.5325375Z Collecting pydantic<3.0.0,>=2.12.5 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T11:38:24.5392356Z   Downloading pydantic-2.13.4-py3-none-any.whl.metadata (109 kB)
2026-08-15T11:38:24.5673344Z Collecting tenacity<9.2.0,>=8.2.3 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T11:38:24.5740823Z   Downloading tenacity-9.1.4-py3-none-any.whl.metadata (1.2 kB)
2026-08-15T11:38:24.6815696Z Collecting websockets<17.0,>=13.0.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T11:38:24.6886011Z   Downloading websockets-16.1.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl.metadata (6.8 kB)
2026-08-15T11:38:24.7079454Z Collecting typing-extensions<5.0.0,>=4.14.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T11:38:24.7143766Z   Downloading typing_extensions-4.16.0-py3-none-any.whl.metadata (3.3 kB)
2026-08-15T11:38:24.7317942Z Collecting distro<2,>=1.7.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T11:38:24.7384052Z   Downloading distro-1.9.0-py3-none-any.whl.metadata (6.8 kB)
2026-08-15T11:38:24.7556797Z Collecting sniffio (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T11:38:24.7620379Z   Downloading sniffio-1.3.1-py3-none-any.whl.metadata (3.9 kB)
2026-08-15T11:38:24.7849146Z Collecting certifi (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T11:38:24.7916364Z   Downloading certifi-2026.7.22-py3-none-any.whl.metadata (2.5 kB)
2026-08-15T11:38:24.8174627Z Collecting httpcore==1.* (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T11:38:24.8242248Z   Downloading httpcore-1.0.9-py3-none-any.whl.metadata (21 kB)
2026-08-15T11:38:24.8461708Z Collecting idna (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T11:38:24.8524938Z   Downloading idna-3.18-py3-none-any.whl.metadata (6.1 kB)
2026-08-15T11:38:24.9754247Z Collecting charset-normalizer<4,>=2 (from requests==2.32.3->-r requirements.txt (line 6))
2026-08-15T11:38:24.9825037Z   Downloading charset_normalizer-3.5.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (45 kB)
2026-08-15T11:38:25.0119953Z Collecting urllib3<3,>=1.21.1 (from requests==2.32.3->-r requirements.txt (line 6))
2026-08-15T11:38:25.0190483Z   Downloading urllib3-2.7.0-py3-none-any.whl.metadata (6.9 kB)
2026-08-15T11:38:25.0383869Z Collecting sgmllib3k (from feedparser==6.0.11->-r requirements.txt (line 7))
2026-08-15T11:38:25.0448968Z   Downloading sgmllib3k-1.0.0.tar.gz (5.8 kB)
2026-08-15T11:38:25.0506419Z   Installing build dependencies: started
2026-08-15T11:38:25.5783344Z   Installing build dependencies: finished with status 'done'
2026-08-15T11:38:25.5789356Z   Getting requirements to build wheel: started
2026-08-15T11:38:25.9147146Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T11:38:25.9155756Z   Preparing metadata (pyproject.toml): started
2026-08-15T11:38:26.1010412Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T11:38:26.1170839Z Collecting pyaes (from telethon==1.36.0->-r requirements.txt (line 11))
2026-08-15T11:38:26.1234423Z   Downloading pyaes-1.6.1.tar.gz (28 kB)
2026-08-15T11:38:26.1305047Z   Installing build dependencies: started
2026-08-15T11:38:26.6719836Z   Installing build dependencies: finished with status 'done'
2026-08-15T11:38:26.6729569Z   Getting requirements to build wheel: started
2026-08-15T11:38:27.0239903Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T11:38:27.0248010Z   Preparing metadata (pyproject.toml): started
2026-08-15T11:38:27.2069492Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T11:38:27.2230956Z Collecting rsa (from telethon==1.36.0->-r requirements.txt (line 11))
2026-08-15T11:38:27.2300467Z   Downloading rsa-4.9.1-py3-none-any.whl.metadata (5.6 kB)
2026-08-15T11:38:27.2571543Z Collecting pyasn1-modules>=0.2.1 (from google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T11:38:27.2639727Z   Downloading pyasn1_modules-0.4.2-py3-none-any.whl.metadata (3.5 kB)
2026-08-15T11:38:27.4705822Z Collecting cryptography>=38.0.3 (from google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T11:38:27.4771269Z   Downloading cryptography-50.0.0-cp311-abi3-manylinux_2_34_x86_64.whl.metadata (4.3 kB)
2026-08-15T11:38:27.4955381Z Collecting h11>=0.16 (from httpcore==1.*->httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T11:38:27.5019682Z   Downloading h11-0.16.0-py3-none-any.whl.metadata (8.3 kB)
2026-08-15T11:38:27.5176388Z Collecting annotated-types>=0.6.0 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T11:38:27.5240813Z   Downloading annotated_types-0.8.0-py3-none-any.whl.metadata (15 kB)
2026-08-15T11:38:28.1974304Z Collecting pydantic-core==2.46.4 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T11:38:28.2044785Z   Downloading pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (6.6 kB)
2026-08-15T11:38:28.2209311Z Collecting typing-inspection>=0.4.2 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T11:38:28.2276464Z   Downloading typing_inspection-0.4.4-py3-none-any.whl.metadata (2.6 kB)
2026-08-15T11:38:28.3366894Z Collecting cffi>=2.0.0 (from cryptography>=38.0.3->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T11:38:28.3434973Z   Downloading cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl.metadata (2.5 kB)
2026-08-15T11:38:28.3588074Z Collecting pycparser (from cffi>=2.0.0->cryptography>=38.0.3->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T11:38:28.3652591Z   Downloading pycparser-3.0-py3-none-any.whl.metadata (8.2 kB)
2026-08-15T11:38:28.3901896Z Collecting pyasn1<0.7.0,>=0.6.1 (from pyasn1-modules>=0.2.1->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T11:38:28.3973630Z   Downloading pyasn1-0.6.4-py3-none-any.whl.metadata (8.4 kB)
2026-08-15T11:38:28.4149239Z Downloading google_genai-2.14.0-py3-none-any.whl (1.0 MB)
2026-08-15T11:38:28.4602213Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1.0/1.0 MB 23.7 MB/s  0:00:00
2026-08-15T11:38:28.4668783Z Downloading httpx-0.28.1-py3-none-any.whl (73 kB)
2026-08-15T11:38:28.4762480Z Downloading requests-2.32.3-py3-none-any.whl (64 kB)
2026-08-15T11:38:28.4852377Z Downloading feedparser-6.0.11-py3-none-any.whl (81 kB)
2026-08-15T11:38:28.4964323Z Downloading pillow-11.0.0-cp312-cp312-manylinux_2_28_x86_64.whl (4.4 MB)
2026-08-15T11:38:28.5967802Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.4/4.4 MB 44.8 MB/s  0:00:00
2026-08-15T11:38:28.6035276Z Downloading arabic_reshaper-3.0.0-py3-none-any.whl (20 kB)
2026-08-15T11:38:28.6130911Z Downloading python_bidi-0.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (286 kB)
2026-08-15T11:38:28.6238077Z Downloading anyio-4.14.2-py3-none-any.whl (125 kB)
2026-08-15T11:38:28.6339289Z Downloading charset_normalizer-3.5.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (248 kB)
2026-08-15T11:38:28.6433274Z Downloading distro-1.9.0-py3-none-any.whl (20 kB)
2026-08-15T11:38:28.6518851Z Downloading google_auth-2.56.3-py3-none-any.whl (259 kB)
2026-08-15T11:38:28.6629329Z Downloading httpcore-1.0.9-py3-none-any.whl (78 kB)
2026-08-15T11:38:28.6719553Z Downloading idna-3.18-py3-none-any.whl (65 kB)
2026-08-15T11:38:28.6807144Z Downloading pydantic-2.13.4-py3-none-any.whl (472 kB)
2026-08-15T11:38:28.6952843Z Downloading pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (2.1 MB)
2026-08-15T11:38:28.7247455Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.1/2.1 MB 74.4 MB/s  0:00:00
2026-08-15T11:38:28.7314984Z Downloading tenacity-9.1.4-py3-none-any.whl (28 kB)
2026-08-15T11:38:28.7401680Z Downloading typing_extensions-4.16.0-py3-none-any.whl (45 kB)
2026-08-15T11:38:28.7491674Z Downloading urllib3-2.7.0-py3-none-any.whl (131 kB)
2026-08-15T11:38:28.7583009Z Downloading websockets-16.1.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (187 kB)
2026-08-15T11:38:28.7673149Z Downloading annotated_types-0.8.0-py3-none-any.whl (13 kB)
2026-08-15T11:38:28.7758410Z Downloading certifi-2026.7.22-py3-none-any.whl (136 kB)
2026-08-15T11:38:28.7849292Z Downloading cryptography-50.0.0-cp311-abi3-manylinux_2_34_x86_64.whl (4.7 MB)
2026-08-15T11:38:28.8308381Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.7/4.7 MB 104.0 MB/s  0:00:00
2026-08-15T11:38:28.8378296Z Downloading cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (221 kB)
2026-08-15T11:38:28.8466397Z Downloading h11-0.16.0-py3-none-any.whl (37 kB)
2026-08-15T11:38:28.8552942Z Downloading pyasn1_modules-0.4.2-py3-none-any.whl (181 kB)
2026-08-15T11:38:28.8646367Z Downloading pyasn1-0.6.4-py3-none-any.whl (84 kB)
2026-08-15T11:38:28.8738269Z Downloading typing_inspection-0.4.4-py3-none-any.whl (14 kB)
2026-08-15T11:38:28.8822909Z Downloading pycparser-3.0-py3-none-any.whl (48 kB)
2026-08-15T11:38:28.8908327Z Downloading rsa-4.9.1-py3-none-any.whl (34 kB)
2026-08-15T11:38:28.8993517Z Downloading sniffio-1.3.1-py3-none-any.whl (10 kB)
2026-08-15T11:38:28.9930112Z Building wheels for collected packages: telethon, pyaes, sgmllib3k
2026-08-15T11:38:28.9937852Z   Building wheel for telethon (pyproject.toml): started
2026-08-15T11:38:29.3949804Z   Building wheel for telethon (pyproject.toml): finished with status 'done'
2026-08-15T11:38:29.3960993Z   Created wheel for telethon: filename=telethon-1.36.0-py3-none-any.whl size=680976 sha256=2f7514805b15e119b46b3e17b2c00638b1600cb2b1d07ceaf96df4cd0da3cce6
2026-08-15T11:38:29.3962890Z   Stored in directory: /home/runner/.cache/pip/wheels/24/5b/1e/aa9bdcbb6e03ba1af024040fc49464b8b7c5ec432ce1916aa2
2026-08-15T11:38:29.3995527Z   Building wheel for pyaes (pyproject.toml): started
2026-08-15T11:38:29.6219183Z   Building wheel for pyaes (pyproject.toml): finished with status 'done'
2026-08-15T11:38:29.6240105Z   Created wheel for pyaes: filename=pyaes-1.6.1-py3-none-any.whl size=26422 sha256=e4728fb59f02c81747d822ed37266b8f11ab7f95e1a01de31579a8550c931743
2026-08-15T11:38:29.6242029Z   Stored in directory: /home/runner/.cache/pip/wheels/d9/43/32/ec313dd557e88e419489b9df40c04dad7b99576bde162496f8
2026-08-15T11:38:29.6250287Z   Building wheel for sgmllib3k (pyproject.toml): started
2026-08-15T11:38:29.8417553Z   Building wheel for sgmllib3k (pyproject.toml): finished with status 'done'
2026-08-15T11:38:29.8423919Z   Created wheel for sgmllib3k: filename=sgmllib3k-1.0.0-py3-none-any.whl size=6090 sha256=94bd5f86e55d3cded1d20cac79a220e3f6b93ea80535aa71ff095c9ac0f1bf5c
2026-08-15T11:38:29.8425837Z   Stored in directory: /home/runner/.cache/pip/wheels/03/f5/1a/23761066dac1d0e8e683e5fdb27e12de53209d05a4a37e6246
2026-08-15T11:38:29.8442032Z Successfully built telethon pyaes sgmllib3k
2026-08-15T11:38:29.9109660Z Installing collected packages: sgmllib3k, python-bidi, pyaes, arabic-reshaper, websockets, urllib3, typing-extensions, tenacity, sniffio, pycparser, pyasn1, Pillow, idna, h11, feedparser, distro, charset-normalizer, certifi, annotated-types, typing-inspection, rsa, requests, pydantic-core, pyasn1-modules, httpcore, cffi, anyio, telethon, pydantic, httpx, cryptography, google-auth, google-genai
2026-08-15T11:38:33.6951351Z 
2026-08-15T11:38:33.6985975Z Successfully installed Pillow-11.0.0 annotated-types-0.8.0 anyio-4.14.2 arabic-reshaper-3.0.0 certifi-2026.7.22 cffi-2.1.1 charset-normalizer-3.5.1 cryptography-50.0.0 distro-1.9.0 feedparser-6.0.11 google-auth-2.56.3 google-genai-2.14.0 h11-0.16.0 httpcore-1.0.9 httpx-0.28.1 idna-3.18 pyaes-1.6.1 pyasn1-0.6.4 pyasn1-modules-0.4.2 pycparser-3.0 pydantic-2.13.4 pydantic-core-2.46.4 python-bidi-0.6.3 requests-2.32.3 rsa-4.9.1 sgmllib3k-1.0.0 sniffio-1.3.1 telethon-1.36.0 tenacity-9.1.4 typing-extensions-4.16.0 typing-inspection-0.4.4 urllib3-2.7.0 websockets-16.1.1
2026-08-15T11:38:33.8596886Z ##[group]Run python main.py
2026-08-15T11:38:33.8597233Z [36;1mpython main.py[0m
2026-08-15T11:38:33.8636352Z shell: /usr/bin/bash -e {0}
2026-08-15T11:38:33.8636655Z env:
2026-08-15T11:38:33.8636954Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T11:38:33.8637431Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T11:38:33.8637901Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T11:38:33.8638329Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T11:38:33.8639380Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T11:38:33.8639835Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T11:38:33.8640635Z   TELEGRAM_BOT_TOKEN: ***
2026-08-15T11:38:33.8640937Z   TELEGRAM_CHANNEL_ID: ***
2026-08-15T11:38:33.8641224Z   TELEGRAM_ADMIN_CHAT_ID: ***
2026-08-15T11:38:33.8641617Z   GEMINI_API_KEY: ***
2026-08-15T11:38:33.8642065Z   GEMINI_API_KEY_BACKUP: ***
2026-08-15T11:38:33.8642480Z   GROQ_API_KEY: ***
2026-08-15T11:38:33.8642785Z   CLOUDFLARE_ACCOUNT_ID: ***
2026-08-15T11:38:33.8643211Z   CLOUDFLARE_API_TOKEN: ***
2026-08-15T11:38:33.8643574Z   EITAA_TOKEN: ***
2026-08-15T11:38:33.8643838Z   EITAA_CHANNEL_ID: ***
2026-08-15T11:38:33.8644183Z   BALE_BOT_TOKEN: ***
2026-08-15T11:38:33.8644460Z   BALE_CHAT_ID: ***
2026-08-15T11:38:33.8644696Z ##[endgroup]
2026-08-15T11:41:02.1460754Z engagement_harvest: TELEGRAM_API_ID / TELEGRAM_API_HASH / TELETHON_SESSION_STRING not fully configured — skipping (see scripts/generate_telethon_session.py to set this up once; every other part of the pipeline is unaffected either way).
2026-08-15T11:41:02.1462927Z Gemini call to gemini-3.5-flash: call failed (attempt 1/3) on the primary key: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.', 'status': 'UNAVAILABLE'}}. Retrying...
2026-08-15T11:41:02.1464540Z Gemini call to gemini-3.5-flash: call failed (attempt 1/3) on the primary key: The read operation timed out. Retrying...
2026-08-15T11:41:02.1465924Z Gemini call to gemini-3.5-flash: call failed (attempt 2/3) on the primary key: 504 DEADLINE_EXCEEDED. {'error': {'code': 504, 'message': 'Deadline expired before operation could complete.', 'status': 'DEADLINE_EXCEEDED'}}. Retrying...
2026-08-15T11:41:02.1468058Z generate_reviewed_text: giving up on progress_recap after 3 attempts — still not ok: بیشتر متن به زبان فارسی روایت شده و بخش انگلیسی آن بسیار ناچیز و در حد چند کلمه کوتاه است. طبق معیار ۶، برای حفظ تعادل زبانی، بدنه اصلی متن یا دیالوگ‌ها باید به انگلیسی باشند و فارسی فقط برای توضیحات کوتاه یا معنی کلمات به کار رود.
2026-08-15T11:41:02.3653242Z ##[group]Run set -euo pipefail
2026-08-15T11:41:02.3653641Z [36;1mset -euo pipefail[0m
2026-08-15T11:41:02.3653964Z [36;1mgit config user.name "channel-bot"[0m
2026-08-15T11:41:02.3654345Z [36;1mgit config user.email "actions@github.com"[0m
2026-08-15T11:41:02.3654694Z [36;1mgit add data/[0m
2026-08-15T11:41:02.3654981Z [36;1mif git diff --staged --quiet; then[0m
2026-08-15T11:41:02.3655320Z [36;1m  echo "No data changes to commit."[0m
2026-08-15T11:41:02.3655820Z [36;1m  exit 0[0m
2026-08-15T11:41:02.3656043Z [36;1mfi[0m
2026-08-15T11:41:02.3656346Z [36;1mgit commit -m "Daily post: update memory and database"[0m
2026-08-15T11:41:02.3656721Z [36;1mfor i in 1 2 3 4 5; do[0m
2026-08-15T11:41:02.3657051Z [36;1m  if git pull --rebase origin main && git push; then[0m
2026-08-15T11:41:02.3657418Z [36;1m    echo "Pushed successfully."[0m
2026-08-15T11:41:02.3657713Z [36;1m    exit 0[0m
2026-08-15T11:41:02.3657942Z [36;1m  fi[0m
2026-08-15T11:41:02.3658242Z [36;1m  echo "Push attempt $i failed, retrying..."[0m
2026-08-15T11:41:02.3658881Z [36;1m  sleep $((RANDOM % 10 + 5))[0m
2026-08-15T11:41:02.3659165Z [36;1mdone[0m
2026-08-15T11:41:02.3659443Z [36;1mecho "::error::Could not push after 5 attempts."[0m
2026-08-15T11:41:02.3659924Z [36;1m# A post can go out to Telegram successfully above even though the[0m
2026-08-15T11:41:02.3660408Z [36;1m# data/ commit that records it never lands — that leaves[0m
2026-08-15T11:41:02.3660903Z [36;1m# memory.json/posts.db/analytics.json/campaign_state.json stale on[0m
2026-08-15T11:41:02.3661400Z [36;1m# origin/main, and every downstream feature that reads them[0m
2026-08-15T11:41:02.3661865Z [36;1m# (dedup, review scheduling, weekly strategy) is stale until[0m
2026-08-15T11:41:02.3662351Z [36;1m# someone notices. This is the only thing that catches that[0m
2026-08-15T11:41:02.3662742Z [36;1m# specific failure mode.[0m
2026-08-15T11:41:02.3663149Z [36;1mif [ -n "$TELEGRAM_ADMIN_CHAT_ID" ] && [ -n "$TELEGRAM_BOT_TOKEN" ]; then[0m
2026-08-15T11:41:02.3663752Z [36;1m  curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \[0m
2026-08-15T11:41:02.3664326Z [36;1m    -d chat_id="${TELEGRAM_ADMIN_CHAT_ID}" \[0m
2026-08-15T11:41:02.3665231Z [36;1m    -d text="🔴 پست امروز احتمالاً منتشر شد، ولی ثبت تغییرات data/ توی گیت بعد از ۵ بار تلاش شکست خورد. یعنی memory.json/posts.db/analytics.json فعلاً روی origin/main قدیمی مونده — لازمه دستی چک و درست بشه، وگرنه ممکنه یه موضوع/جوک دوباره تکرار بشه." \[0m
2026-08-15T11:41:02.3666170Z [36;1m    > /dev/null || echo "::warning::Admin alert send also failed."[0m
2026-08-15T11:41:02.3666549Z [36;1melse[0m
2026-08-15T11:41:02.3667046Z [36;1m  echo "::warning::TELEGRAM_ADMIN_CHAT_ID or TELEGRAM_BOT_TOKEN not set — no admin alert sent for the push failure."[0m
2026-08-15T11:41:02.3667599Z [36;1mfi[0m
2026-08-15T11:41:02.3667806Z [36;1mexit 1[0m
2026-08-15T11:41:02.3707161Z shell: /usr/bin/bash -e {0}
2026-08-15T11:41:02.3707447Z env:
2026-08-15T11:41:02.3707769Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T11:41:02.3708258Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T11:41:02.3709033Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T11:41:02.3709476Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T11:41:02.3709908Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T11:41:02.3710337Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T11:41:02.3710902Z   TELEGRAM_BOT_TOKEN: ***
2026-08-15T11:41:02.3711190Z   TELEGRAM_ADMIN_CHAT_ID: ***
2026-08-15T11:41:02.3711456Z ##[endgroup]
2026-08-15T11:41:02.3895046Z No data changes to commit.
2026-08-15T11:41:02.3990833Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T11:41:02.3992165Z Post job cleanup.
2026-08-15T11:41:02.5165859Z (node:2367) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
2026-08-15T11:41:02.5166817Z (Use `node --trace-deprecation ...` to show where the warning was created)
2026-08-15T11:41:02.5367392Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T11:41:02.5369283Z Post job cleanup.
2026-08-15T11:41:02.6269326Z [command]/usr/bin/git version
2026-08-15T11:41:02.6297525Z git version 2.54.0
2026-08-15T11:41:02.6369362Z Temporarily overriding HOME='/home/runner/work/_temp/9531d385-1701-4f1b-8a8a-8aaa9fa876cb' before making global git config changes
2026-08-15T11:41:02.6370845Z Adding repository directory to the temporary git global config as a safe directory
2026-08-15T11:41:02.6375918Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T11:41:02.6416020Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
2026-08-15T11:41:02.6457389Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
2026-08-15T11:41:02.6711078Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
2026-08-15T11:41:02.6740017Z http.https://github.com/.extraheader
2026-08-15T11:41:02.6752491Z [command]/usr/bin/git config --local --unset-all http.https://github.com/.extraheader
2026-08-15T11:41:02.6791855Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
2026-08-15T11:41:02.7060179Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
2026-08-15T11:41:02.7101993Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
2026-08-15T11:41:02.7506463Z Cleaning up orphan processes
2026-08-15T11:41:02.7803112Z ##[warning]Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4, actions/setup-python@v5. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/






2026-08-15T09:44:17.9577194Z Current runner version: '2.336.0'
2026-08-15T09:44:17.9617543Z ##[group]Runner Image Provisioner
2026-08-15T09:44:17.9619096Z Hosted Compute Agent
2026-08-15T09:44:17.9620174Z Version: 20260729.566
2026-08-15T09:44:17.9621556Z Commit: cf7153fe6e25b664e8693c24944bf2b00355d109
2026-08-15T09:44:17.9623009Z Build Date: 2026-07-29T19:17:02Z
2026-08-15T09:44:17.9624787Z Worker ID: {a47cd67d-97fb-4873-a823-ef5c220b8787}
2026-08-15T09:44:17.9626270Z Azure Region: eastus2
2026-08-15T09:44:17.9627963Z ##[endgroup]
2026-08-15T09:44:17.9630708Z ##[group]Operating System
2026-08-15T09:44:17.9632023Z Ubuntu
2026-08-15T09:44:17.9633069Z 24.04.4
2026-08-15T09:44:17.9634496Z LTS
2026-08-15T09:44:17.9635564Z ##[endgroup]
2026-08-15T09:44:17.9636761Z ##[group]Runner Image
2026-08-15T09:44:17.9637977Z Image: ubuntu-24.04
2026-08-15T09:44:17.9639154Z Version: 20260810.271.1
2026-08-15T09:44:17.9641509Z Included Software: https://github.com/actions/runner-images/blob/ubuntu24/20260810.271/images/ubuntu/Ubuntu2404-Readme.md
2026-08-15T09:44:17.9644743Z Image Release: https://github.com/actions/runner-images/releases/tag/ubuntu24%2F20260810.271
2026-08-15T09:44:17.9646791Z ##[endgroup]
2026-08-15T09:44:17.9648906Z ##[group]GITHUB_TOKEN Permissions
2026-08-15T09:44:17.9652152Z Contents: write
2026-08-15T09:44:17.9653573Z Metadata: read
2026-08-15T09:44:17.9654896Z ##[endgroup]
2026-08-15T09:44:17.9658457Z Secret source: Actions
2026-08-15T09:44:17.9661073Z Prepare workflow directory
2026-08-15T09:44:18.0143877Z Prepare all required actions
2026-08-15T09:44:18.0216735Z Getting action download info
2026-08-15T09:44:18.2068789Z Download action repository 'actions/checkout@v4' (SHA:11d5960a326750d5838078e36cf38b85af677262)
2026-08-15T09:44:18.3492386Z Download action repository 'actions/setup-python@v5' (SHA:a26af69be951a213d495a4c3e4e4022e16d87065)
2026-08-15T09:44:18.5402939Z Complete job name: post
2026-08-15T09:44:18.6183951Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T09:44:18.6192907Z ##[group]Run actions/checkout@v4
2026-08-15T09:44:18.6194034Z with:
2026-08-15T09:44:18.6194540Z   fetch-depth: 1
2026-08-15T09:44:18.6195167Z   repository: sajjadisr/ESL-Telegram-channel-automation
2026-08-15T09:44:18.6199360Z   token: ***
2026-08-15T09:44:18.6199862Z   ssh-strict: true
2026-08-15T09:44:18.6200377Z   ssh-user: git
2026-08-15T09:44:18.6200906Z   persist-credentials: true
2026-08-15T09:44:18.6201476Z   clean: true
2026-08-15T09:44:18.6201993Z   sparse-checkout-cone-mode: true
2026-08-15T09:44:18.6202582Z   fetch-tags: false
2026-08-15T09:44:18.6203098Z   show-progress: true
2026-08-15T09:44:18.6203805Z   lfs: false
2026-08-15T09:44:18.6204344Z   submodules: false
2026-08-15T09:44:18.6204863Z   set-safe-directory: true
2026-08-15T09:44:18.6205438Z   allow-unsafe-pr-checkout: false
2026-08-15T09:44:18.6206320Z ##[endgroup]
2026-08-15T09:44:18.7235419Z Syncing repository: sajjadisr/ESL-Telegram-channel-automation
2026-08-15T09:44:18.7238835Z ##[group]Getting Git version info
2026-08-15T09:44:18.7240684Z Working directory is '/home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation'
2026-08-15T09:44:18.7243051Z [command]/usr/bin/git version
2026-08-15T09:44:18.7293807Z git version 2.54.0
2026-08-15T09:44:18.7317295Z ##[endgroup]
2026-08-15T09:44:18.7331462Z Temporarily overriding HOME='/home/runner/work/_temp/f9aad08c-736a-45aa-83c6-bf13062b40c2' before making global git config changes
2026-08-15T09:44:18.7334311Z Adding repository directory to the temporary git global config as a safe directory
2026-08-15T09:44:18.7339268Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T09:44:18.7398590Z Deleting the contents of '/home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation'
2026-08-15T09:44:18.7402743Z ##[group]Initializing the repository
2026-08-15T09:44:18.7408885Z [command]/usr/bin/git init /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T09:44:18.7505551Z hint: Using 'master' as the name for the initial branch. This default branch name
2026-08-15T09:44:18.7507504Z hint: will change to "main" in Git 3.0. To configure the initial branch name
2026-08-15T09:44:18.7508611Z hint: to use in all of your new repositories, which will suppress this warning,
2026-08-15T09:44:18.7509781Z hint: call:
2026-08-15T09:44:18.7510692Z hint:
2026-08-15T09:44:18.7511667Z hint: 	git config --global init.defaultBranch <name>
2026-08-15T09:44:18.7512956Z hint:
2026-08-15T09:44:18.7514444Z hint: Names commonly chosen instead of 'master' are 'main', 'trunk' and
2026-08-15T09:44:18.7516386Z hint: 'development'. The just-created branch can be renamed via this command:
2026-08-15T09:44:18.7517971Z hint:
2026-08-15T09:44:18.7518929Z hint: 	git branch -m <name>
2026-08-15T09:44:18.7519954Z hint:
2026-08-15T09:44:18.7521235Z hint: Disable this message with "git config set advice.defaultBranchName false"
2026-08-15T09:44:18.7523934Z Initialized empty Git repository in /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation/.git/
2026-08-15T09:44:18.7530374Z [command]/usr/bin/git remote add origin https://github.com/sajjadisr/ESL-Telegram-channel-automation
2026-08-15T09:44:18.7578981Z ##[endgroup]
2026-08-15T09:44:18.7580531Z ##[group]Disabling automatic garbage collection
2026-08-15T09:44:18.7583632Z [command]/usr/bin/git config --local gc.auto 0
2026-08-15T09:44:18.7619243Z ##[endgroup]
2026-08-15T09:44:18.7620100Z ##[group]Setting up auth
2026-08-15T09:44:18.7629114Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
2026-08-15T09:44:18.7669093Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
2026-08-15T09:44:18.8038276Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
2026-08-15T09:44:18.8085385Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
2026-08-15T09:44:18.8332225Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
2026-08-15T09:44:18.8370625Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
2026-08-15T09:44:18.8596147Z [command]/usr/bin/git config --local http.https://github.com/.extraheader AUTHORIZATION: basic ***
2026-08-15T09:44:18.8636055Z ##[endgroup]
2026-08-15T09:44:18.8636980Z ##[group]Fetching the repository
2026-08-15T09:44:18.8645530Z [command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=1 origin +f0d4193f910198beb35a3f36340ea84ce6bc244d:refs/remotes/origin/main
2026-08-15T09:44:19.3355609Z From https://github.com/sajjadisr/ESL-Telegram-channel-automation
2026-08-15T09:44:19.3358502Z  * [new ref]         f0d4193f910198beb35a3f36340ea84ce6bc244d -> origin/main
2026-08-15T09:44:19.3391852Z ##[endgroup]
2026-08-15T09:44:19.3394038Z ##[group]Determining the checkout info
2026-08-15T09:44:19.3396035Z ##[endgroup]
2026-08-15T09:44:19.3400646Z [command]/usr/bin/git sparse-checkout disable
2026-08-15T09:44:19.3448890Z [command]/usr/bin/git config --local --unset-all extensions.worktreeConfig
2026-08-15T09:44:19.3485080Z ##[group]Checking out the ref
2026-08-15T09:44:19.3488724Z [command]/usr/bin/git checkout --progress --force -B main refs/remotes/origin/main
2026-08-15T09:44:19.3620735Z Switched to a new branch 'main'
2026-08-15T09:44:19.3623141Z branch 'main' set up to track 'origin/main'.
2026-08-15T09:44:19.3632475Z ##[endgroup]
2026-08-15T09:44:19.3676349Z [command]/usr/bin/git log -1 --format=%H
2026-08-15T09:44:19.3703870Z f0d4193f910198beb35a3f36340ea84ce6bc244d
2026-08-15T09:44:19.4155493Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T09:44:19.4163928Z ##[group]Run actions/setup-python@v5
2026-08-15T09:44:19.4165188Z with:
2026-08-15T09:44:19.4166113Z   python-version: 3.12
2026-08-15T09:44:19.4167183Z   check-latest: false
2026-08-15T09:44:19.4178084Z   token: ***
2026-08-15T09:44:19.4179074Z   update-environment: true
2026-08-15T09:44:19.4180235Z   allow-prereleases: false
2026-08-15T09:44:19.4181378Z   freethreaded: false
2026-08-15T09:44:19.4182407Z ##[endgroup]
2026-08-15T09:44:19.5538273Z ##[group]Installed versions
2026-08-15T09:44:19.5630109Z (node:2164) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
2026-08-15T09:44:19.5638911Z (Use `node --trace-deprecation ...` to show where the warning was created)
2026-08-15T09:44:19.5640796Z Successfully set up CPython (3.12.13)
2026-08-15T09:44:19.5644301Z ##[endgroup]
2026-08-15T09:44:19.5862009Z ##[group]Run pip install -r requirements.txt
2026-08-15T09:44:19.5864046Z [36;1mpip install -r requirements.txt[0m
2026-08-15T09:44:19.5932270Z shell: /usr/bin/bash -e {0}
2026-08-15T09:44:19.5934559Z env:
2026-08-15T09:44:19.5937838Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T09:44:19.5941122Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T09:44:19.5945184Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T09:44:19.5950854Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T09:44:19.5953206Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T09:44:19.5956508Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T09:44:19.5959731Z ##[endgroup]
2026-08-15T09:44:20.4517906Z Collecting google-genai==2.14.0 (from -r requirements.txt (line 1))
2026-08-15T09:44:20.5140709Z   Downloading google_genai-2.14.0-py3-none-any.whl.metadata (55 kB)
2026-08-15T09:44:20.5540902Z Collecting httpx==0.28.1 (from -r requirements.txt (line 2))
2026-08-15T09:44:20.5613833Z   Downloading httpx-0.28.1-py3-none-any.whl.metadata (7.1 kB)
2026-08-15T09:44:20.5895174Z Collecting requests==2.32.3 (from -r requirements.txt (line 6))
2026-08-15T09:44:20.5966459Z   Downloading requests-2.32.3-py3-none-any.whl.metadata (4.6 kB)
2026-08-15T09:44:20.6141034Z Collecting feedparser==6.0.11 (from -r requirements.txt (line 7))
2026-08-15T09:44:20.6215205Z   Downloading feedparser-6.0.11-py3-none-any.whl.metadata (2.4 kB)
2026-08-15T09:44:20.8303906Z Collecting Pillow==11.0.0 (from -r requirements.txt (line 8))
2026-08-15T09:44:20.8396925Z   Downloading pillow-11.0.0-cp312-cp312-manylinux_2_28_x86_64.whl.metadata (9.1 kB)
2026-08-15T09:44:20.8586299Z Collecting arabic-reshaper==3.0.0 (from -r requirements.txt (line 9))
2026-08-15T09:44:20.8665203Z   Downloading arabic_reshaper-3.0.0-py3-none-any.whl.metadata (12 kB)
2026-08-15T09:44:20.9543108Z Collecting python-bidi==0.6.3 (from -r requirements.txt (line 10))
2026-08-15T09:44:20.9627423Z   Downloading python_bidi-0.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (4.9 kB)
2026-08-15T09:44:20.9964813Z Collecting telethon==1.36.0 (from -r requirements.txt (line 11))
2026-08-15T09:44:21.0056150Z   Downloading Telethon-1.36.0.tar.gz (606 kB)
2026-08-15T09:44:21.0606443Z      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 606.3/606.3 kB 11.4 MB/s  0:00:00
2026-08-15T09:44:21.1284697Z   Installing build dependencies: started
2026-08-15T09:44:21.9966989Z   Installing build dependencies: finished with status 'done'
2026-08-15T09:44:21.9973073Z   Getting requirements to build wheel: started
2026-08-15T09:44:22.3985485Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T09:44:22.3997121Z   Preparing metadata (pyproject.toml): started
2026-08-15T09:44:22.6032784Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T09:44:22.6244645Z Collecting anyio<5.0.0,>=4.8.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T09:44:22.6320353Z   Downloading anyio-4.14.2-py3-none-any.whl.metadata (4.6 kB)
2026-08-15T09:44:22.6682098Z Collecting google-auth<3.0.0,>=2.56.0 (from google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T09:44:22.6759600Z   Downloading google_auth-2.56.3-py3-none-any.whl.metadata (6.0 kB)
2026-08-15T09:44:22.7972212Z Collecting pydantic<3.0.0,>=2.12.5 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T09:44:22.8050938Z   Downloading pydantic-2.13.4-py3-none-any.whl.metadata (109 kB)
2026-08-15T09:44:22.8346424Z Collecting tenacity<9.2.0,>=8.2.3 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T09:44:22.8421340Z   Downloading tenacity-9.1.4-py3-none-any.whl.metadata (1.2 kB)
2026-08-15T09:44:22.9529602Z Collecting websockets<17.0,>=13.0.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T09:44:22.9606426Z   Downloading websockets-16.1.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl.metadata (6.8 kB)
2026-08-15T09:44:22.9809490Z Collecting typing-extensions<5.0.0,>=4.14.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T09:44:22.9881903Z   Downloading typing_extensions-4.16.0-py3-none-any.whl.metadata (3.3 kB)
2026-08-15T09:44:23.0034081Z Collecting distro<2,>=1.7.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T09:44:23.0105951Z   Downloading distro-1.9.0-py3-none-any.whl.metadata (6.8 kB)
2026-08-15T09:44:23.0259424Z Collecting sniffio (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T09:44:23.0332194Z   Downloading sniffio-1.3.1-py3-none-any.whl.metadata (3.9 kB)
2026-08-15T09:44:23.0580866Z Collecting certifi (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T09:44:23.0652904Z   Downloading certifi-2026.7.22-py3-none-any.whl.metadata (2.5 kB)
2026-08-15T09:44:23.0852177Z Collecting httpcore==1.* (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T09:44:23.0923456Z   Downloading httpcore-1.0.9-py3-none-any.whl.metadata (21 kB)
2026-08-15T09:44:23.1134245Z Collecting idna (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T09:44:23.1206001Z   Downloading idna-3.18-py3-none-any.whl.metadata (6.1 kB)
2026-08-15T09:44:23.2480218Z Collecting charset-normalizer<4,>=2 (from requests==2.32.3->-r requirements.txt (line 6))
2026-08-15T09:44:23.2559878Z   Downloading charset_normalizer-3.5.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (45 kB)
2026-08-15T09:44:23.2869841Z Collecting urllib3<3,>=1.21.1 (from requests==2.32.3->-r requirements.txt (line 6))
2026-08-15T09:44:23.2942214Z   Downloading urllib3-2.7.0-py3-none-any.whl.metadata (6.9 kB)
2026-08-15T09:44:23.3137102Z Collecting sgmllib3k (from feedparser==6.0.11->-r requirements.txt (line 7))
2026-08-15T09:44:23.3210696Z   Downloading sgmllib3k-1.0.0.tar.gz (5.8 kB)
2026-08-15T09:44:23.3272081Z   Installing build dependencies: started
2026-08-15T09:44:23.8685634Z   Installing build dependencies: finished with status 'done'
2026-08-15T09:44:23.8691378Z   Getting requirements to build wheel: started
2026-08-15T09:44:24.2150260Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T09:44:24.2159600Z   Preparing metadata (pyproject.toml): started
2026-08-15T09:44:24.4019510Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T09:44:24.4158628Z Collecting pyaes (from telethon==1.36.0->-r requirements.txt (line 11))
2026-08-15T09:44:24.4229140Z   Downloading pyaes-1.6.1.tar.gz (28 kB)
2026-08-15T09:44:24.4300811Z   Installing build dependencies: started
2026-08-15T09:44:24.9696494Z   Installing build dependencies: finished with status 'done'
2026-08-15T09:44:24.9703055Z   Getting requirements to build wheel: started
2026-08-15T09:44:25.3179383Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T09:44:25.3188919Z   Preparing metadata (pyproject.toml): started
2026-08-15T09:44:25.5044839Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T09:44:25.5214409Z Collecting rsa (from telethon==1.36.0->-r requirements.txt (line 11))
2026-08-15T09:44:25.5284116Z   Downloading rsa-4.9.1-py3-none-any.whl.metadata (5.6 kB)
2026-08-15T09:44:25.5556323Z Collecting pyasn1-modules>=0.2.1 (from google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T09:44:25.5631483Z   Downloading pyasn1_modules-0.4.2-py3-none-any.whl.metadata (3.5 kB)
2026-08-15T09:44:25.7751368Z Collecting cryptography>=38.0.3 (from google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T09:44:25.7827190Z   Downloading cryptography-50.0.0-cp311-abi3-manylinux_2_34_x86_64.whl.metadata (4.3 kB)
2026-08-15T09:44:25.8017176Z Collecting h11>=0.16 (from httpcore==1.*->httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T09:44:25.8087684Z   Downloading h11-0.16.0-py3-none-any.whl.metadata (8.3 kB)
2026-08-15T09:44:25.8277880Z Collecting annotated-types>=0.6.0 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T09:44:25.8346747Z   Downloading annotated_types-0.8.0-py3-none-any.whl.metadata (15 kB)
2026-08-15T09:44:26.5176271Z Collecting pydantic-core==2.46.4 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T09:44:26.5251868Z   Downloading pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (6.6 kB)
2026-08-15T09:44:26.5416022Z Collecting typing-inspection>=0.4.2 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T09:44:26.5487335Z   Downloading typing_inspection-0.4.4-py3-none-any.whl.metadata (2.6 kB)
2026-08-15T09:44:26.6618469Z Collecting cffi>=2.0.0 (from cryptography>=38.0.3->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T09:44:26.6694951Z   Downloading cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl.metadata (2.5 kB)
2026-08-15T09:44:26.6861854Z Collecting pycparser (from cffi>=2.0.0->cryptography>=38.0.3->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T09:44:26.6958348Z   Downloading pycparser-3.0-py3-none-any.whl.metadata (8.2 kB)
2026-08-15T09:44:26.7214668Z Collecting pyasn1<0.7.0,>=0.6.1 (from pyasn1-modules>=0.2.1->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T09:44:26.7285855Z   Downloading pyasn1-0.6.4-py3-none-any.whl.metadata (8.4 kB)
2026-08-15T09:44:26.7465160Z Downloading google_genai-2.14.0-py3-none-any.whl (1.0 MB)
2026-08-15T09:44:26.8003797Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1.0/1.0 MB 20.0 MB/s  0:00:00
2026-08-15T09:44:26.8078350Z Downloading httpx-0.28.1-py3-none-any.whl (73 kB)
2026-08-15T09:44:26.8178610Z Downloading requests-2.32.3-py3-none-any.whl (64 kB)
2026-08-15T09:44:26.8271775Z Downloading feedparser-6.0.11-py3-none-any.whl (81 kB)
2026-08-15T09:44:26.8388672Z Downloading pillow-11.0.0-cp312-cp312-manylinux_2_28_x86_64.whl (4.4 MB)
2026-08-15T09:44:26.9502620Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.4/4.4 MB 41.7 MB/s  0:00:00
2026-08-15T09:44:26.9588625Z Downloading arabic_reshaper-3.0.0-py3-none-any.whl (20 kB)
2026-08-15T09:44:26.9693666Z Downloading python_bidi-0.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (286 kB)
2026-08-15T09:44:26.9811518Z Downloading anyio-4.14.2-py3-none-any.whl (125 kB)
2026-08-15T09:44:26.9906768Z Downloading charset_normalizer-3.5.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (248 kB)
2026-08-15T09:44:27.0021032Z Downloading distro-1.9.0-py3-none-any.whl (20 kB)
2026-08-15T09:44:27.0112926Z Downloading google_auth-2.56.3-py3-none-any.whl (259 kB)
2026-08-15T09:44:27.0230115Z Downloading httpcore-1.0.9-py3-none-any.whl (78 kB)
2026-08-15T09:44:27.0342731Z Downloading idna-3.18-py3-none-any.whl (65 kB)
2026-08-15T09:44:27.0435277Z Downloading pydantic-2.13.4-py3-none-any.whl (472 kB)
2026-08-15T09:44:27.0594967Z Downloading pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (2.1 MB)
2026-08-15T09:44:27.0912727Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.1/2.1 MB 65.6 MB/s  0:00:00
2026-08-15T09:44:27.0984097Z Downloading tenacity-9.1.4-py3-none-any.whl (28 kB)
2026-08-15T09:44:27.1101517Z Downloading typing_extensions-4.16.0-py3-none-any.whl (45 kB)
2026-08-15T09:44:27.1193949Z Downloading urllib3-2.7.0-py3-none-any.whl (131 kB)
2026-08-15T09:44:27.1290624Z Downloading websockets-16.1.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (187 kB)
2026-08-15T09:44:27.1387301Z Downloading annotated_types-0.8.0-py3-none-any.whl (13 kB)
2026-08-15T09:44:27.1478211Z Downloading certifi-2026.7.22-py3-none-any.whl (136 kB)
2026-08-15T09:44:27.1572542Z Downloading cryptography-50.0.0-cp311-abi3-manylinux_2_34_x86_64.whl (4.7 MB)
2026-08-15T09:44:27.2115453Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.7/4.7 MB 88.2 MB/s  0:00:00
2026-08-15T09:44:27.2193254Z Downloading cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (221 kB)
2026-08-15T09:44:27.2295413Z Downloading h11-0.16.0-py3-none-any.whl (37 kB)
2026-08-15T09:44:27.2391003Z Downloading pyasn1_modules-0.4.2-py3-none-any.whl (181 kB)
2026-08-15T09:44:27.2489945Z Downloading pyasn1-0.6.4-py3-none-any.whl (84 kB)
2026-08-15T09:44:27.2585694Z Downloading typing_inspection-0.4.4-py3-none-any.whl (14 kB)
2026-08-15T09:44:27.2676428Z Downloading pycparser-3.0-py3-none-any.whl (48 kB)
2026-08-15T09:44:27.2774048Z Downloading rsa-4.9.1-py3-none-any.whl (34 kB)
2026-08-15T09:44:27.2877428Z Downloading sniffio-1.3.1-py3-none-any.whl (10 kB)
2026-08-15T09:44:27.3830100Z Building wheels for collected packages: telethon, pyaes, sgmllib3k
2026-08-15T09:44:27.3838892Z   Building wheel for telethon (pyproject.toml): started
2026-08-15T09:44:27.7962859Z   Building wheel for telethon (pyproject.toml): finished with status 'done'
2026-08-15T09:44:27.7974215Z   Created wheel for telethon: filename=telethon-1.36.0-py3-none-any.whl size=680976 sha256=f492e477e9519ba533659ac7b92d3182003735df17b7eebd94ff65b2b9b1c6dc
2026-08-15T09:44:27.7976041Z   Stored in directory: /home/runner/.cache/pip/wheels/24/5b/1e/aa9bdcbb6e03ba1af024040fc49464b8b7c5ec432ce1916aa2
2026-08-15T09:44:27.8008567Z   Building wheel for pyaes (pyproject.toml): started
2026-08-15T09:44:28.0263290Z   Building wheel for pyaes (pyproject.toml): finished with status 'done'
2026-08-15T09:44:28.0270270Z   Created wheel for pyaes: filename=pyaes-1.6.1-py3-none-any.whl size=26422 sha256=9cf63558db87c5b92a644e773e8fdd068cdcd693e3cf5418153b5a75730f3291
2026-08-15T09:44:28.0272811Z   Stored in directory: /home/runner/.cache/pip/wheels/d9/43/32/ec313dd557e88e419489b9df40c04dad7b99576bde162496f8
2026-08-15T09:44:28.0295316Z   Building wheel for sgmllib3k (pyproject.toml): started
2026-08-15T09:44:28.2528998Z   Building wheel for sgmllib3k (pyproject.toml): finished with status 'done'
2026-08-15T09:44:28.2534398Z   Created wheel for sgmllib3k: filename=sgmllib3k-1.0.0-py3-none-any.whl size=6090 sha256=6e694df564543b08503b4335c0438872ea7d271b69242e30de40a0dd6359af57
2026-08-15T09:44:28.2536561Z   Stored in directory: /home/runner/.cache/pip/wheels/03/f5/1a/23761066dac1d0e8e683e5fdb27e12de53209d05a4a37e6246
2026-08-15T09:44:28.2552008Z Successfully built telethon pyaes sgmllib3k
2026-08-15T09:44:28.3225610Z Installing collected packages: sgmllib3k, python-bidi, pyaes, arabic-reshaper, websockets, urllib3, typing-extensions, tenacity, sniffio, pycparser, pyasn1, Pillow, idna, h11, feedparser, distro, charset-normalizer, certifi, annotated-types, typing-inspection, rsa, requests, pydantic-core, pyasn1-modules, httpcore, cffi, anyio, telethon, pydantic, httpx, cryptography, google-auth, google-genai
2026-08-15T09:44:32.4239215Z 
2026-08-15T09:44:32.4272603Z Successfully installed Pillow-11.0.0 annotated-types-0.8.0 anyio-4.14.2 arabic-reshaper-3.0.0 certifi-2026.7.22 cffi-2.1.1 charset-normalizer-3.5.1 cryptography-50.0.0 distro-1.9.0 feedparser-6.0.11 google-auth-2.56.3 google-genai-2.14.0 h11-0.16.0 httpcore-1.0.9 httpx-0.28.1 idna-3.18 pyaes-1.6.1 pyasn1-0.6.4 pyasn1-modules-0.4.2 pycparser-3.0 pydantic-2.13.4 pydantic-core-2.46.4 python-bidi-0.6.3 requests-2.32.3 rsa-4.9.1 sgmllib3k-1.0.0 sniffio-1.3.1 telethon-1.36.0 tenacity-9.1.4 typing-extensions-4.16.0 typing-inspection-0.4.4 urllib3-2.7.0 websockets-16.1.1
2026-08-15T09:44:32.6211451Z ##[group]Run python main.py
2026-08-15T09:44:32.6211799Z [36;1mpython main.py[0m
2026-08-15T09:44:32.6251748Z shell: /usr/bin/bash -e {0}
2026-08-15T09:44:32.6252062Z env:
2026-08-15T09:44:32.6252378Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T09:44:32.6252862Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T09:44:32.6253503Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T09:44:32.6253953Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T09:44:32.6254391Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T09:44:32.6254822Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T09:44:32.6255454Z   TELEGRAM_BOT_TOKEN: ***
2026-08-15T09:44:32.6255754Z   TELEGRAM_CHANNEL_ID: ***
2026-08-15T09:44:32.6256049Z   TELEGRAM_ADMIN_CHAT_ID: ***
2026-08-15T09:44:32.6256439Z   GEMINI_API_KEY: ***
2026-08-15T09:44:32.6256868Z   GEMINI_API_KEY_BACKUP: ***
2026-08-15T09:44:32.6257274Z   GROQ_API_KEY: ***
2026-08-15T09:44:32.6257575Z   CLOUDFLARE_ACCOUNT_ID: ***
2026-08-15T09:44:32.6257987Z   CLOUDFLARE_API_TOKEN: ***
2026-08-15T09:44:32.6258331Z   EITAA_TOKEN: ***
2026-08-15T09:44:32.6258583Z   EITAA_CHANNEL_ID: ***
2026-08-15T09:44:32.6258907Z   BALE_BOT_TOKEN: ***
2026-08-15T09:44:32.6259175Z   BALE_CHAT_ID: ***
2026-08-15T09:44:32.6259408Z ##[endgroup]
2026-08-15T09:45:48.1535482Z engagement_harvest: TELEGRAM_API_ID / TELEGRAM_API_HASH / TELETHON_SESSION_STRING not fully configured — skipping (see scripts/generate_telethon_session.py to set this up once; every other part of the pipeline is unaffected either way).
2026-08-15T09:45:48.1537859Z Gemini call to gemini-3.5-flash: call failed (attempt 1/3) on the primary key: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.', 'status': 'UNAVAILABLE'}}. Retrying...
2026-08-15T09:45:48.1540238Z Gemini call to gemini-3.5-flash: call failed (attempt 2/3) on the primary key: 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.', 'status': 'UNAVAILABLE'}}. Retrying...
2026-08-15T09:45:48.1543007Z generate_reviewed_text: giving up on progress_recap after 3 attempts — still not ok: برخی از واژگان و جملات استفاده شده در بندهای ۴ و ۶ (مانند hosepipe ban، conservation herd و Royal Golden Guernsey Goats) بسیار فراتر از سطح مبتدی (A1-A2) و در حد متوسط به بالا (B2/C1) هستند که برای زبان‌آموز مبتدی گنگ و دلسردکننده است.
2026-08-15T09:45:48.3971108Z ##[group]Run set -euo pipefail
2026-08-15T09:45:48.3971495Z [36;1mset -euo pipefail[0m
2026-08-15T09:45:48.3971809Z [36;1mgit config user.name "channel-bot"[0m
2026-08-15T09:45:48.3972191Z [36;1mgit config user.email "actions@github.com"[0m
2026-08-15T09:45:48.3972537Z [36;1mgit add data/[0m
2026-08-15T09:45:48.3972831Z [36;1mif git diff --staged --quiet; then[0m
2026-08-15T09:45:48.3973172Z [36;1m  echo "No data changes to commit."[0m
2026-08-15T09:45:48.3973809Z [36;1m  exit 0[0m
2026-08-15T09:45:48.3974264Z [36;1mfi[0m
2026-08-15T09:45:48.3974579Z [36;1mgit commit -m "Daily post: update memory and database"[0m
2026-08-15T09:45:48.3974964Z [36;1mfor i in 1 2 3 4 5; do[0m
2026-08-15T09:45:48.3975307Z [36;1m  if git pull --rebase origin main && git push; then[0m
2026-08-15T09:45:48.3975705Z [36;1m    echo "Pushed successfully."[0m
2026-08-15T09:45:48.3976024Z [36;1m    exit 0[0m
2026-08-15T09:45:48.3976259Z [36;1m  fi[0m
2026-08-15T09:45:48.3976568Z [36;1m  echo "Push attempt $i failed, retrying..."[0m
2026-08-15T09:45:48.3976914Z [36;1m  sleep $((RANDOM % 10 + 5))[0m
2026-08-15T09:45:48.3977194Z [36;1mdone[0m
2026-08-15T09:45:48.3977476Z [36;1mecho "::error::Could not push after 5 attempts."[0m
2026-08-15T09:45:48.3977948Z [36;1m# A post can go out to Telegram successfully above even though the[0m
2026-08-15T09:45:48.3978448Z [36;1m# data/ commit that records it never lands — that leaves[0m
2026-08-15T09:45:48.3978936Z [36;1m# memory.json/posts.db/analytics.json/campaign_state.json stale on[0m
2026-08-15T09:45:48.3979444Z [36;1m# origin/main, and every downstream feature that reads them[0m
2026-08-15T09:45:48.3979915Z [36;1m# (dedup, review scheduling, weekly strategy) is stale until[0m
2026-08-15T09:45:48.3980384Z [36;1m# someone notices. This is the only thing that catches that[0m
2026-08-15T09:45:48.3980769Z [36;1m# specific failure mode.[0m
2026-08-15T09:45:48.3981186Z [36;1mif [ -n "$TELEGRAM_ADMIN_CHAT_ID" ] && [ -n "$TELEGRAM_BOT_TOKEN" ]; then[0m
2026-08-15T09:45:48.3981800Z [36;1m  curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \[0m
2026-08-15T09:45:48.3982308Z [36;1m    -d chat_id="${TELEGRAM_ADMIN_CHAT_ID}" \[0m
2026-08-15T09:45:48.3983212Z [36;1m    -d text="🔴 پست امروز احتمالاً منتشر شد، ولی ثبت تغییرات data/ توی گیت بعد از ۵ بار تلاش شکست خورد. یعنی memory.json/posts.db/analytics.json فعلاً روی origin/main قدیمی مونده — لازمه دستی چک و درست بشه، وگرنه ممکنه یه موضوع/جوک دوباره تکرار بشه." \[0m
2026-08-15T09:45:48.3984398Z [36;1m    > /dev/null || echo "::warning::Admin alert send also failed."[0m
2026-08-15T09:45:48.3984781Z [36;1melse[0m
2026-08-15T09:45:48.3985280Z [36;1m  echo "::warning::TELEGRAM_ADMIN_CHAT_ID or TELEGRAM_BOT_TOKEN not set — no admin alert sent for the push failure."[0m
2026-08-15T09:45:48.3985837Z [36;1mfi[0m
2026-08-15T09:45:48.3986052Z [36;1mexit 1[0m
2026-08-15T09:45:48.4024432Z shell: /usr/bin/bash -e {0}
2026-08-15T09:45:48.4024759Z env:
2026-08-15T09:45:48.4025086Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T09:45:48.4025571Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T09:45:48.4026042Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T09:45:48.4026467Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T09:45:48.4026898Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T09:45:48.4027324Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T09:45:48.4027881Z   TELEGRAM_BOT_TOKEN: ***
2026-08-15T09:45:48.4028166Z   TELEGRAM_ADMIN_CHAT_ID: ***
2026-08-15T09:45:48.4028434Z ##[endgroup]
2026-08-15T09:45:48.4196243Z No data changes to commit.
2026-08-15T09:45:48.4299738Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T09:45:48.4301036Z Post job cleanup.
2026-08-15T09:45:48.5504342Z (node:2343) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
2026-08-15T09:45:48.5505357Z (Use `node --trace-deprecation ...` to show where the warning was created)
2026-08-15T09:45:48.5695878Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T09:45:48.5698377Z Post job cleanup.
2026-08-15T09:45:48.6640134Z [command]/usr/bin/git version
2026-08-15T09:45:48.6689014Z git version 2.54.0
2026-08-15T09:45:48.6735355Z Temporarily overriding HOME='/home/runner/work/_temp/88055d4a-8631-418f-8caf-8b952d577b2f' before making global git config changes
2026-08-15T09:45:48.6736754Z Adding repository directory to the temporary git global config as a safe directory
2026-08-15T09:45:48.6742055Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T09:45:48.6785055Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
2026-08-15T09:45:48.6822688Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
2026-08-15T09:45:48.7099808Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
2026-08-15T09:45:48.7131549Z http.https://github.com/.extraheader
2026-08-15T09:45:48.7145077Z [command]/usr/bin/git config --local --unset-all http.https://github.com/.extraheader
2026-08-15T09:45:48.7183120Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
2026-08-15T09:45:48.7495949Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
2026-08-15T09:45:48.7538669Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
2026-08-15T09:45:48.7957736Z Cleaning up orphan processes
2026-08-15T09:45:48.8363978Z ##[warning]Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4, actions/setup-python@v5. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/






2026-08-15T06:14:36.2596302Z Current runner version: '2.336.0'
2026-08-15T06:14:36.2631598Z ##[group]Runner Image Provisioner
2026-08-15T06:14:36.2633008Z Hosted Compute Agent
2026-08-15T06:14:36.2634267Z Version: 20260729.566
2026-08-15T06:14:36.2635451Z Commit: cf7153fe6e25b664e8693c24944bf2b00355d109
2026-08-15T06:14:36.2636963Z Build Date: 2026-07-29T19:17:02Z
2026-08-15T06:14:36.2638314Z Worker ID: {f3ac8ac5-499f-458e-9ece-f00bc87a9ab2}
2026-08-15T06:14:36.2639809Z Azure Region: centralus
2026-08-15T06:14:36.2641199Z ##[endgroup]
2026-08-15T06:14:36.2643632Z ##[group]Operating System
2026-08-15T06:14:36.2645515Z Ubuntu
2026-08-15T06:14:36.2646531Z 24.04.4
2026-08-15T06:14:36.2647519Z LTS
2026-08-15T06:14:36.2648712Z ##[endgroup]
2026-08-15T06:14:36.2649763Z ##[group]Runner Image
2026-08-15T06:14:36.2651260Z Image: ubuntu-24.04
2026-08-15T06:14:36.2652305Z Version: 20260810.271.1
2026-08-15T06:14:36.2654672Z Included Software: https://github.com/actions/runner-images/blob/ubuntu24/20260810.271/images/ubuntu/Ubuntu2404-Readme.md
2026-08-15T06:14:36.2657645Z Image Release: https://github.com/actions/runner-images/releases/tag/ubuntu24%2F20260810.271
2026-08-15T06:14:36.2659413Z ##[endgroup]
2026-08-15T06:14:36.2661887Z ##[group]GITHUB_TOKEN Permissions
2026-08-15T06:14:36.2664996Z Contents: write
2026-08-15T06:14:36.2666249Z Metadata: read
2026-08-15T06:14:36.2667333Z ##[endgroup]
2026-08-15T06:14:36.2670536Z Secret source: Actions
2026-08-15T06:14:36.2673047Z Prepare workflow directory
2026-08-15T06:14:36.3013085Z Prepare all required actions
2026-08-15T06:14:36.3081947Z Getting action download info
2026-08-15T06:14:36.5447613Z Download action repository 'actions/checkout@v4' (SHA:11d5960a326750d5838078e36cf38b85af677262)
2026-08-15T06:14:36.6445913Z Download action repository 'actions/setup-python@v5' (SHA:a26af69be951a213d495a4c3e4e4022e16d87065)
2026-08-15T06:14:36.8293452Z Complete job name: post
2026-08-15T06:14:36.9052950Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T06:14:36.9062016Z ##[group]Run actions/checkout@v4
2026-08-15T06:14:36.9062784Z with:
2026-08-15T06:14:36.9063299Z   fetch-depth: 1
2026-08-15T06:14:36.9063934Z   repository: sajjadisr/ESL-Telegram-channel-automation
2026-08-15T06:14:36.9068350Z   token: ***
2026-08-15T06:14:36.9068880Z   ssh-strict: true
2026-08-15T06:14:36.9069399Z   ssh-user: git
2026-08-15T06:14:36.9070092Z   persist-credentials: true
2026-08-15T06:14:36.9070667Z   clean: true
2026-08-15T06:14:36.9071198Z   sparse-checkout-cone-mode: true
2026-08-15T06:14:36.9071799Z   fetch-tags: false
2026-08-15T06:14:36.9072320Z   show-progress: true
2026-08-15T06:14:36.9072847Z   lfs: false
2026-08-15T06:14:36.9073380Z   submodules: false
2026-08-15T06:14:36.9073960Z   set-safe-directory: true
2026-08-15T06:14:36.9074542Z   allow-unsafe-pr-checkout: false
2026-08-15T06:14:36.9075383Z ##[endgroup]
2026-08-15T06:14:37.0095353Z Syncing repository: sajjadisr/ESL-Telegram-channel-automation
2026-08-15T06:14:37.0098146Z ##[group]Getting Git version info
2026-08-15T06:14:37.0100159Z Working directory is '/home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation'
2026-08-15T06:14:37.0102451Z [command]/usr/bin/git version
2026-08-15T06:14:37.0174660Z git version 2.54.0
2026-08-15T06:14:37.0195540Z ##[endgroup]
2026-08-15T06:14:37.0217424Z Temporarily overriding HOME='/home/runner/work/_temp/24bdcc63-1e09-4c1f-8faa-8d441bd6c4eb' before making global git config changes
2026-08-15T06:14:37.0219756Z Adding repository directory to the temporary git global config as a safe directory
2026-08-15T06:14:37.0229502Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T06:14:37.0280474Z Deleting the contents of '/home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation'
2026-08-15T06:14:37.0284363Z ##[group]Initializing the repository
2026-08-15T06:14:37.0289393Z [command]/usr/bin/git init /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T06:14:37.0399571Z hint: Using 'master' as the name for the initial branch. This default branch name
2026-08-15T06:14:37.0401479Z hint: will change to "main" in Git 3.0. To configure the initial branch name
2026-08-15T06:14:37.0403112Z hint: to use in all of your new repositories, which will suppress this warning,
2026-08-15T06:14:37.0404395Z hint: call:
2026-08-15T06:14:37.0405136Z hint:
2026-08-15T06:14:37.0406029Z hint: 	git config --global init.defaultBranch <name>
2026-08-15T06:14:37.0407101Z hint:
2026-08-15T06:14:37.0408116Z hint: Names commonly chosen instead of 'master' are 'main', 'trunk' and
2026-08-15T06:14:37.0409761Z hint: 'development'. The just-created branch can be renamed via this command:
2026-08-15T06:14:37.0411411Z hint:
2026-08-15T06:14:37.0412181Z hint: 	git branch -m <name>
2026-08-15T06:14:37.0413031Z hint:
2026-08-15T06:14:37.0414144Z hint: Disable this message with "git config set advice.defaultBranchName false"
2026-08-15T06:14:37.0416407Z Initialized empty Git repository in /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation/.git/
2026-08-15T06:14:37.0419699Z [command]/usr/bin/git remote add origin https://github.com/sajjadisr/ESL-Telegram-channel-automation
2026-08-15T06:14:37.0462399Z ##[endgroup]
2026-08-15T06:14:37.0463352Z ##[group]Disabling automatic garbage collection
2026-08-15T06:14:37.0466669Z [command]/usr/bin/git config --local gc.auto 0
2026-08-15T06:14:37.0498996Z ##[endgroup]
2026-08-15T06:14:37.0500177Z ##[group]Setting up auth
2026-08-15T06:14:37.0506360Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
2026-08-15T06:14:37.0543252Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
2026-08-15T06:14:37.0971553Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
2026-08-15T06:14:37.1009084Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
2026-08-15T06:14:37.1254670Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
2026-08-15T06:14:37.1293302Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
2026-08-15T06:14:37.1533012Z [command]/usr/bin/git config --local http.https://github.com/.extraheader AUTHORIZATION: basic ***
2026-08-15T06:14:37.1575090Z ##[endgroup]
2026-08-15T06:14:37.1576460Z ##[group]Fetching the repository
2026-08-15T06:14:37.1586400Z [command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=1 origin +f0d4193f910198beb35a3f36340ea84ce6bc244d:refs/remotes/origin/main
2026-08-15T06:14:37.6258155Z From https://github.com/sajjadisr/ESL-Telegram-channel-automation
2026-08-15T06:14:37.6259324Z  * [new ref]         f0d4193f910198beb35a3f36340ea84ce6bc244d -> origin/main
2026-08-15T06:14:37.6295563Z ##[endgroup]
2026-08-15T06:14:37.6296465Z ##[group]Determining the checkout info
2026-08-15T06:14:37.6298212Z ##[endgroup]
2026-08-15T06:14:37.6304468Z [command]/usr/bin/git sparse-checkout disable
2026-08-15T06:14:37.6413512Z [command]/usr/bin/git config --local --unset-all extensions.worktreeConfig
2026-08-15T06:14:37.6416989Z ##[group]Checking out the ref
2026-08-15T06:14:37.6419656Z [command]/usr/bin/git checkout --progress --force -B main refs/remotes/origin/main
2026-08-15T06:14:37.6553065Z Switched to a new branch 'main'
2026-08-15T06:14:37.6555096Z branch 'main' set up to track 'origin/main'.
2026-08-15T06:14:37.6569238Z ##[endgroup]
2026-08-15T06:14:37.6611233Z [command]/usr/bin/git log -1 --format=%H
2026-08-15T06:14:37.6641225Z f0d4193f910198beb35a3f36340ea84ce6bc244d
2026-08-15T06:14:37.7082093Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T06:14:37.7088103Z ##[group]Run actions/setup-python@v5
2026-08-15T06:14:37.7089323Z with:
2026-08-15T06:14:37.7090376Z   python-version: 3.12
2026-08-15T06:14:37.7091426Z   check-latest: false
2026-08-15T06:14:37.7102000Z   token: ***
2026-08-15T06:14:37.7102996Z   update-environment: true
2026-08-15T06:14:37.7104142Z   allow-prereleases: false
2026-08-15T06:14:37.7105249Z   freethreaded: false
2026-08-15T06:14:37.7106251Z ##[endgroup]
2026-08-15T06:14:37.8429650Z ##[group]Installed versions
2026-08-15T06:14:37.8528058Z (node:2299) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
2026-08-15T06:14:37.8532526Z (Use `node --trace-deprecation ...` to show where the warning was created)
2026-08-15T06:14:37.8534660Z Successfully set up CPython (3.12.13)
2026-08-15T06:14:37.8536719Z ##[endgroup]
2026-08-15T06:14:37.8692510Z ##[group]Run pip install -r requirements.txt
2026-08-15T06:14:37.8694017Z [36;1mpip install -r requirements.txt[0m
2026-08-15T06:14:37.8751245Z shell: /usr/bin/bash -e {0}
2026-08-15T06:14:37.8752335Z env:
2026-08-15T06:14:37.8753447Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T06:14:37.8755300Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T06:14:37.8757168Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T06:14:37.8758859Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T06:14:37.8760713Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T06:14:37.8762437Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T06:14:37.8764116Z ##[endgroup]
2026-08-15T06:14:38.8143579Z Collecting google-genai==2.14.0 (from -r requirements.txt (line 1))
2026-08-15T06:14:38.8908429Z   Downloading google_genai-2.14.0-py3-none-any.whl.metadata (55 kB)
2026-08-15T06:14:38.9417102Z Collecting httpx==0.28.1 (from -r requirements.txt (line 2))
2026-08-15T06:14:38.9547603Z   Downloading httpx-0.28.1-py3-none-any.whl.metadata (7.1 kB)
2026-08-15T06:14:38.9895349Z Collecting requests==2.32.3 (from -r requirements.txt (line 6))
2026-08-15T06:14:39.0028422Z   Downloading requests-2.32.3-py3-none-any.whl.metadata (4.6 kB)
2026-08-15T06:14:39.0324550Z Collecting feedparser==6.0.11 (from -r requirements.txt (line 7))
2026-08-15T06:14:39.0459431Z   Downloading feedparser-6.0.11-py3-none-any.whl.metadata (2.4 kB)
2026-08-15T06:14:39.2588775Z Collecting Pillow==11.0.0 (from -r requirements.txt (line 8))
2026-08-15T06:14:39.2722764Z   Downloading pillow-11.0.0-cp312-cp312-manylinux_2_28_x86_64.whl.metadata (9.1 kB)
2026-08-15T06:14:39.3001175Z Collecting arabic-reshaper==3.0.0 (from -r requirements.txt (line 9))
2026-08-15T06:14:39.3136053Z   Downloading arabic_reshaper-3.0.0-py3-none-any.whl.metadata (12 kB)
2026-08-15T06:14:39.3914506Z Collecting python-bidi==0.6.3 (from -r requirements.txt (line 10))
2026-08-15T06:14:39.4050879Z   Downloading python_bidi-0.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (4.9 kB)
2026-08-15T06:14:39.4436733Z Collecting telethon==1.36.0 (from -r requirements.txt (line 11))
2026-08-15T06:14:39.4568649Z   Downloading Telethon-1.36.0.tar.gz (606 kB)
2026-08-15T06:14:39.5398696Z      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 606.3/606.3 kB 8.0 MB/s  0:00:00
2026-08-15T06:14:39.6046824Z   Installing build dependencies: started
2026-08-15T06:14:40.5629496Z   Installing build dependencies: finished with status 'done'
2026-08-15T06:14:40.5635642Z   Getting requirements to build wheel: started
2026-08-15T06:14:40.9850317Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T06:14:40.9861347Z   Preparing metadata (pyproject.toml): started
2026-08-15T06:14:41.1918543Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T06:14:41.2196040Z Collecting anyio<5.0.0,>=4.8.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T06:14:41.2328328Z   Downloading anyio-4.14.2-py3-none-any.whl.metadata (4.6 kB)
2026-08-15T06:14:41.2718352Z Collecting google-auth<3.0.0,>=2.56.0 (from google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T06:14:41.2849547Z   Downloading google_auth-2.56.3-py3-none-any.whl.metadata (6.0 kB)
2026-08-15T06:14:41.3900179Z Collecting pydantic<3.0.0,>=2.12.5 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T06:14:41.4033192Z   Downloading pydantic-2.13.4-py3-none-any.whl.metadata (109 kB)
2026-08-15T06:14:41.4487089Z Collecting tenacity<9.2.0,>=8.2.3 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T06:14:41.4620203Z   Downloading tenacity-9.1.4-py3-none-any.whl.metadata (1.2 kB)
2026-08-15T06:14:41.5594367Z Collecting websockets<17.0,>=13.0.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T06:14:41.5728579Z   Downloading websockets-16.1.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl.metadata (6.8 kB)
2026-08-15T06:14:41.5997527Z Collecting typing-extensions<5.0.0,>=4.14.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T06:14:41.6127674Z   Downloading typing_extensions-4.16.0-py3-none-any.whl.metadata (3.3 kB)
2026-08-15T06:14:41.6348514Z Collecting distro<2,>=1.7.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T06:14:41.6482096Z   Downloading distro-1.9.0-py3-none-any.whl.metadata (6.8 kB)
2026-08-15T06:14:41.6724312Z Collecting sniffio (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T06:14:41.6860673Z   Downloading sniffio-1.3.1-py3-none-any.whl.metadata (3.9 kB)
2026-08-15T06:14:41.7179657Z Collecting certifi (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T06:14:41.7309276Z   Downloading certifi-2026.7.22-py3-none-any.whl.metadata (2.5 kB)
2026-08-15T06:14:41.7570927Z Collecting httpcore==1.* (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T06:14:41.7701380Z   Downloading httpcore-1.0.9-py3-none-any.whl.metadata (21 kB)
2026-08-15T06:14:41.7966783Z Collecting idna (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T06:14:41.8096434Z   Downloading idna-3.18-py3-none-any.whl.metadata (6.1 kB)
2026-08-15T06:14:41.9161430Z Collecting charset-normalizer<4,>=2 (from requests==2.32.3->-r requirements.txt (line 6))
2026-08-15T06:14:41.9295004Z   Downloading charset_normalizer-3.5.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (44 kB)
2026-08-15T06:14:41.9667824Z Collecting urllib3<3,>=1.21.1 (from requests==2.32.3->-r requirements.txt (line 6))
2026-08-15T06:14:41.9798077Z   Downloading urllib3-2.7.0-py3-none-any.whl.metadata (6.9 kB)
2026-08-15T06:14:42.0060574Z Collecting sgmllib3k (from feedparser==6.0.11->-r requirements.txt (line 7))
2026-08-15T06:14:42.0194795Z   Downloading sgmllib3k-1.0.0.tar.gz (5.8 kB)
2026-08-15T06:14:42.0249372Z   Installing build dependencies: started
2026-08-15T06:14:42.5456452Z   Installing build dependencies: finished with status 'done'
2026-08-15T06:14:42.5462843Z   Getting requirements to build wheel: started
2026-08-15T06:14:42.9020551Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T06:14:42.9028772Z   Preparing metadata (pyproject.toml): started
2026-08-15T06:14:43.0845659Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T06:14:43.1102686Z Collecting pyaes (from telethon==1.36.0->-r requirements.txt (line 11))
2026-08-15T06:14:43.1232199Z   Downloading pyaes-1.6.1.tar.gz (28 kB)
2026-08-15T06:14:43.1318180Z   Installing build dependencies: started
2026-08-15T06:14:43.6502418Z   Installing build dependencies: finished with status 'done'
2026-08-15T06:14:43.6507638Z   Getting requirements to build wheel: started
2026-08-15T06:14:43.9979810Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T06:14:43.9988081Z   Preparing metadata (pyproject.toml): started
2026-08-15T06:14:44.1824597Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T06:14:44.2067197Z Collecting rsa (from telethon==1.36.0->-r requirements.txt (line 11))
2026-08-15T06:14:44.2197915Z   Downloading rsa-4.9.1-py3-none-any.whl.metadata (5.6 kB)
2026-08-15T06:14:44.2527838Z Collecting pyasn1-modules>=0.2.1 (from google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T06:14:44.2661514Z   Downloading pyasn1_modules-0.4.2-py3-none-any.whl.metadata (3.5 kB)
2026-08-15T06:14:44.4515471Z Collecting cryptography>=38.0.3 (from google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T06:14:44.4647849Z   Downloading cryptography-50.0.0-cp311-abi3-manylinux_2_34_x86_64.whl.metadata (4.3 kB)
2026-08-15T06:14:44.4903992Z Collecting h11>=0.16 (from httpcore==1.*->httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T06:14:44.5033130Z   Downloading h11-0.16.0-py3-none-any.whl.metadata (8.3 kB)
2026-08-15T06:14:44.5267175Z Collecting annotated-types>=0.6.0 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T06:14:44.5396798Z   Downloading annotated_types-0.8.0-py3-none-any.whl.metadata (15 kB)
2026-08-15T06:14:45.1448464Z Collecting pydantic-core==2.46.4 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T06:14:45.1582325Z   Downloading pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (6.6 kB)
2026-08-15T06:14:45.1817980Z Collecting typing-inspection>=0.4.2 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T06:14:45.1947966Z   Downloading typing_inspection-0.4.4-py3-none-any.whl.metadata (2.6 kB)
2026-08-15T06:14:45.2992372Z Collecting cffi>=2.0.0 (from cryptography>=38.0.3->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T06:14:45.3126160Z   Downloading cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl.metadata (2.5 kB)
2026-08-15T06:14:45.3357703Z Collecting pycparser (from cffi>=2.0.0->cryptography>=38.0.3->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T06:14:45.3486686Z   Downloading pycparser-3.0-py3-none-any.whl.metadata (8.2 kB)
2026-08-15T06:14:45.3799278Z Collecting pyasn1<0.7.0,>=0.6.1 (from pyasn1-modules>=0.2.1->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T06:14:45.3929687Z   Downloading pyasn1-0.6.4-py3-none-any.whl.metadata (8.4 kB)
2026-08-15T06:14:45.4139055Z Downloading google_genai-2.14.0-py3-none-any.whl (1.0 MB)
2026-08-15T06:14:45.5057325Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1.0/1.0 MB 12.1 MB/s  0:00:00
2026-08-15T06:14:45.5188597Z Downloading httpx-0.28.1-py3-none-any.whl (73 kB)
2026-08-15T06:14:45.5371227Z Downloading requests-2.32.3-py3-none-any.whl (64 kB)
2026-08-15T06:14:45.5541486Z Downloading feedparser-6.0.11-py3-none-any.whl (81 kB)
2026-08-15T06:14:45.5732386Z Downloading pillow-11.0.0-cp312-cp312-manylinux_2_28_x86_64.whl (4.4 MB)
2026-08-15T06:14:45.7807526Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.4/4.4 MB 21.8 MB/s  0:00:00
2026-08-15T06:14:45.7938979Z Downloading arabic_reshaper-3.0.0-py3-none-any.whl (20 kB)
2026-08-15T06:14:45.8088554Z Downloading python_bidi-0.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (286 kB)
2026-08-15T06:14:45.8298367Z Downloading anyio-4.14.2-py3-none-any.whl (125 kB)
2026-08-15T06:14:45.8471614Z Downloading charset_normalizer-3.5.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (247 kB)
2026-08-15T06:14:45.8671556Z Downloading distro-1.9.0-py3-none-any.whl (20 kB)
2026-08-15T06:14:45.8820766Z Downloading google_auth-2.56.3-py3-none-any.whl (259 kB)
2026-08-15T06:14:45.9020328Z Downloading httpcore-1.0.9-py3-none-any.whl (78 kB)
2026-08-15T06:14:45.9174969Z Downloading idna-3.18-py3-none-any.whl (65 kB)
2026-08-15T06:14:45.9327530Z Downloading pydantic-2.13.4-py3-none-any.whl (472 kB)
2026-08-15T06:14:45.9607268Z Downloading pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (2.1 MB)
2026-08-15T06:14:46.0180519Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.1/2.1 MB 36.4 MB/s  0:00:00
2026-08-15T06:14:46.0310275Z Downloading tenacity-9.1.4-py3-none-any.whl (28 kB)
2026-08-15T06:14:46.0461923Z Downloading typing_extensions-4.16.0-py3-none-any.whl (45 kB)
2026-08-15T06:14:46.0611889Z Downloading urllib3-2.7.0-py3-none-any.whl (131 kB)
2026-08-15T06:14:46.0776955Z Downloading websockets-16.1.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (187 kB)
2026-08-15T06:14:46.0950808Z Downloading annotated_types-0.8.0-py3-none-any.whl (13 kB)
2026-08-15T06:14:46.1100613Z Downloading certifi-2026.7.22-py3-none-any.whl (136 kB)
2026-08-15T06:14:46.1263243Z Downloading cryptography-50.0.0-cp311-abi3-manylinux_2_34_x86_64.whl (4.7 MB)
2026-08-15T06:14:46.2264369Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.7/4.7 MB 47.3 MB/s  0:00:00
2026-08-15T06:14:46.2396436Z Downloading cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (221 kB)
2026-08-15T06:14:46.2564749Z Downloading h11-0.16.0-py3-none-any.whl (37 kB)
2026-08-15T06:14:46.2713315Z Downloading pyasn1_modules-0.4.2-py3-none-any.whl (181 kB)
2026-08-15T06:14:46.2876841Z Downloading pyasn1-0.6.4-py3-none-any.whl (84 kB)
2026-08-15T06:14:46.3029810Z Downloading typing_inspection-0.4.4-py3-none-any.whl (14 kB)
2026-08-15T06:14:46.3178513Z Downloading pycparser-3.0-py3-none-any.whl (48 kB)
2026-08-15T06:14:46.3327328Z Downloading rsa-4.9.1-py3-none-any.whl (34 kB)
2026-08-15T06:14:46.3475324Z Downloading sniffio-1.3.1-py3-none-any.whl (10 kB)
2026-08-15T06:14:46.4397357Z Building wheels for collected packages: telethon, pyaes, sgmllib3k
2026-08-15T06:14:46.4405597Z   Building wheel for telethon (pyproject.toml): started
2026-08-15T06:14:46.8403086Z   Building wheel for telethon (pyproject.toml): finished with status 'done'
2026-08-15T06:14:46.8413844Z   Created wheel for telethon: filename=telethon-1.36.0-py3-none-any.whl size=680976 sha256=1c2ebec932cc55f85e6ac8fc485a0ff0b35c509bebcb86f0281bdd0c4a8dc8dc
2026-08-15T06:14:46.8415466Z   Stored in directory: /home/runner/.cache/pip/wheels/24/5b/1e/aa9bdcbb6e03ba1af024040fc49464b8b7c5ec432ce1916aa2
2026-08-15T06:14:46.8447075Z   Building wheel for pyaes (pyproject.toml): started
2026-08-15T06:14:47.0717724Z   Building wheel for pyaes (pyproject.toml): finished with status 'done'
2026-08-15T06:14:47.0723405Z   Created wheel for pyaes: filename=pyaes-1.6.1-py3-none-any.whl size=26422 sha256=795de433f489f049b3397f7b733909a6acd6061b60c922d37fae403b83240968
2026-08-15T06:14:47.0725083Z   Stored in directory: /home/runner/.cache/pip/wheels/d9/43/32/ec313dd557e88e419489b9df40c04dad7b99576bde162496f8
2026-08-15T06:14:47.0746786Z   Building wheel for sgmllib3k (pyproject.toml): started
2026-08-15T06:14:47.2993658Z   Building wheel for sgmllib3k (pyproject.toml): finished with status 'done'
2026-08-15T06:14:47.2999322Z   Created wheel for sgmllib3k: filename=sgmllib3k-1.0.0-py3-none-any.whl size=6090 sha256=ac854b8f130c2a0aa3099cf6ba38fd41683955dd7209702cfb9493f531313b47
2026-08-15T06:14:47.3001439Z   Stored in directory: /home/runner/.cache/pip/wheels/03/f5/1a/23761066dac1d0e8e683e5fdb27e12de53209d05a4a37e6246
2026-08-15T06:14:47.3016754Z Successfully built telethon pyaes sgmllib3k
2026-08-15T06:14:47.3643229Z Installing collected packages: sgmllib3k, python-bidi, pyaes, arabic-reshaper, websockets, urllib3, typing-extensions, tenacity, sniffio, pycparser, pyasn1, Pillow, idna, h11, feedparser, distro, charset-normalizer, certifi, annotated-types, typing-inspection, rsa, requests, pydantic-core, pyasn1-modules, httpcore, cffi, anyio, telethon, pydantic, httpx, cryptography, google-auth, google-genai
2026-08-15T06:14:51.3319602Z 
2026-08-15T06:14:51.3351783Z Successfully installed Pillow-11.0.0 annotated-types-0.8.0 anyio-4.14.2 arabic-reshaper-3.0.0 certifi-2026.7.22 cffi-2.1.1 charset-normalizer-3.5.0 cryptography-50.0.0 distro-1.9.0 feedparser-6.0.11 google-auth-2.56.3 google-genai-2.14.0 h11-0.16.0 httpcore-1.0.9 httpx-0.28.1 idna-3.18 pyaes-1.6.1 pyasn1-0.6.4 pyasn1-modules-0.4.2 pycparser-3.0 pydantic-2.13.4 pydantic-core-2.46.4 python-bidi-0.6.3 requests-2.32.3 rsa-4.9.1 sgmllib3k-1.0.0 sniffio-1.3.1 telethon-1.36.0 tenacity-9.1.4 typing-extensions-4.16.0 typing-inspection-0.4.4 urllib3-2.7.0 websockets-16.1.1
2026-08-15T06:14:51.5075970Z ##[group]Run python main.py
2026-08-15T06:14:51.5076303Z [36;1mpython main.py[0m
2026-08-15T06:14:51.5119365Z shell: /usr/bin/bash -e {0}
2026-08-15T06:14:51.5119681Z env:
2026-08-15T06:14:51.5120185Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T06:14:51.5120680Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T06:14:51.5121146Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T06:14:51.5121568Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T06:14:51.5121989Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T06:14:51.5122408Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T06:14:51.5123066Z   TELEGRAM_BOT_TOKEN: ***
2026-08-15T06:14:51.5123376Z   TELEGRAM_CHANNEL_ID: ***
2026-08-15T06:14:51.5123679Z   TELEGRAM_ADMIN_CHAT_ID: ***
2026-08-15T06:14:51.5124078Z   GEMINI_API_KEY: ***
2026-08-15T06:14:51.5124528Z   GEMINI_API_KEY_BACKUP: ***
2026-08-15T06:14:51.5124958Z   GROQ_API_KEY: ***
2026-08-15T06:14:51.5125276Z   CLOUDFLARE_ACCOUNT_ID: ***
2026-08-15T06:14:51.5125687Z   CLOUDFLARE_API_TOKEN: ***
2026-08-15T06:14:51.5126047Z   EITAA_TOKEN: ***
2026-08-15T06:14:51.5126318Z   EITAA_CHANNEL_ID: ***
2026-08-15T06:14:51.5126660Z   BALE_BOT_TOKEN: ***
2026-08-15T06:14:51.5126943Z   BALE_CHAT_ID: ***
2026-08-15T06:14:51.5127196Z ##[endgroup]
2026-08-15T06:15:27.7698468Z engagement_harvest: TELEGRAM_API_ID / TELEGRAM_API_HASH / TELETHON_SESSION_STRING not fully configured — skipping (see scripts/generate_telethon_session.py to set this up once; every other part of the pipeline is unaffected either way).
2026-08-15T06:15:27.7706183Z Gemini call to gemini-3.5-flash: call failed (attempt 1/3) on the primary key: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 4.066279665s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'model': 'gemini-3.5-flash', 'location': 'global'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '4s'}]}}. Retrying...
2026-08-15T06:15:27.7717355Z Gemini call to gemini-3.5-flash: call failed (attempt 2/3) on the primary key: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 986.600753ms.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-3.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '0s'}]}}. Retrying...
2026-08-15T06:15:27.7726503Z Gemini call to gemini-3.5-flash: call failed (attempt 1/3) on the primary key: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 46.302402216s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-3.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '46s'}]}}. Retrying...
2026-08-15T06:15:27.7734170Z Gemini call to gemini-3.5-flash: call failed (attempt 2/3) on the primary key: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 43.241817869s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'model': 'gemini-3.5-flash', 'location': 'global'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '43s'}]}}. Retrying...
2026-08-15T06:15:27.7741800Z Gemini call to gemini-3.5-flash: call failed after 3 attempts on the primary key: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 37.146680204s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-3.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '37s'}]}}
2026-08-15T06:15:27.7749580Z generate_content_smart: Gemini failed (429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 37.146680204s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-3.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '37s'}]}}); trying Groq fallback.
2026-08-15T06:15:39.2482510Z Gemini call to gemini-3.5-flash: call failed (attempt 1/3) on the primary key: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 32.240657306s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'model': 'gemini-3.5-flash', 'location': 'global'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '32s'}]}}. Retrying...
2026-08-15T06:15:39.2490342Z Gemini call to gemini-3.5-flash: call failed (attempt 2/3) on the primary key: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 29.190754526s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'model': 'gemini-3.5-flash', 'location': 'global'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '29s'}]}}. Retrying...
2026-08-15T06:15:39.2498316Z Gemini call to gemini-3.5-flash: call failed after 3 attempts on the primary key: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 23.074101987s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-3.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '23s'}]}}
2026-08-15T06:15:39.2505750Z generate_content_smart: Gemini failed (429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 23.074101987s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-3.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '23s'}]}}); trying Groq fallback.
2026-08-15T06:15:39.2511032Z generate_reviewed_text: giving up on progress_recap after 3 attempts — still not ok: متن بیشتر به فارسی نوشته شده و فقط چند مثال انگلیسی داخل آن هستند؛ تعادل زبان مورد نیاز (بیشتر انگلیسی) رعایت نشده. علاوه بر این از تگ‌های <tg-spoiler> (HTML‑like) استفاده شده که خلاف استفاده از Markdown است.
2026-08-15T06:15:39.4958446Z ##[group]Run set -euo pipefail
2026-08-15T06:15:39.4958838Z [36;1mset -euo pipefail[0m
2026-08-15T06:15:39.4959152Z [36;1mgit config user.name "channel-bot"[0m
2026-08-15T06:15:39.4959543Z [36;1mgit config user.email "actions@github.com"[0m
2026-08-15T06:15:39.4960173Z [36;1mgit add data/[0m
2026-08-15T06:15:39.4960478Z [36;1mif git diff --staged --quiet; then[0m
2026-08-15T06:15:39.4960825Z [36;1m  echo "No data changes to commit."[0m
2026-08-15T06:15:39.4961181Z [36;1m  exit 0[0m
2026-08-15T06:15:39.4961428Z [36;1mfi[0m
2026-08-15T06:15:39.4961767Z [36;1mgit commit -m "Daily post: update memory and database"[0m
2026-08-15T06:15:39.4962154Z [36;1mfor i in 1 2 3 4 5; do[0m
2026-08-15T06:15:39.4962495Z [36;1m  if git pull --rebase origin main && git push; then[0m
2026-08-15T06:15:39.4962873Z [36;1m    echo "Pushed successfully."[0m
2026-08-15T06:15:39.4963191Z [36;1m    exit 0[0m
2026-08-15T06:15:39.4963441Z [36;1m  fi[0m
2026-08-15T06:15:39.4963765Z [36;1m  echo "Push attempt $i failed, retrying..."[0m
2026-08-15T06:15:39.4964136Z [36;1m  sleep $((RANDOM % 10 + 5))[0m
2026-08-15T06:15:39.4964439Z [36;1mdone[0m
2026-08-15T06:15:39.4964741Z [36;1mecho "::error::Could not push after 5 attempts."[0m
2026-08-15T06:15:39.4965212Z [36;1m# A post can go out to Telegram successfully above even though the[0m
2026-08-15T06:15:39.4965708Z [36;1m# data/ commit that records it never lands — that leaves[0m
2026-08-15T06:15:39.4966397Z [36;1m# memory.json/posts.db/analytics.json/campaign_state.json stale on[0m
2026-08-15T06:15:39.4966891Z [36;1m# origin/main, and every downstream feature that reads them[0m
2026-08-15T06:15:39.4967364Z [36;1m# (dedup, review scheduling, weekly strategy) is stale until[0m
2026-08-15T06:15:39.4967830Z [36;1m# someone notices. This is the only thing that catches that[0m
2026-08-15T06:15:39.4968215Z [36;1m# specific failure mode.[0m
2026-08-15T06:15:39.4968635Z [36;1mif [ -n "$TELEGRAM_ADMIN_CHAT_ID" ] && [ -n "$TELEGRAM_BOT_TOKEN" ]; then[0m
2026-08-15T06:15:39.4969234Z [36;1m  curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \[0m
2026-08-15T06:15:39.4969792Z [36;1m    -d chat_id="${TELEGRAM_ADMIN_CHAT_ID}" \[0m
2026-08-15T06:15:39.4970891Z [36;1m    -d text="🔴 پست امروز احتمالاً منتشر شد، ولی ثبت تغییرات data/ توی گیت بعد از ۵ بار تلاش شکست خورد. یعنی memory.json/posts.db/analytics.json فعلاً روی origin/main قدیمی مونده — لازمه دستی چک و درست بشه، وگرنه ممکنه یه موضوع/جوک دوباره تکرار بشه." \[0m
2026-08-15T06:15:39.4971828Z [36;1m    > /dev/null || echo "::warning::Admin alert send also failed."[0m
2026-08-15T06:15:39.4972229Z [36;1melse[0m
2026-08-15T06:15:39.4972742Z [36;1m  echo "::warning::TELEGRAM_ADMIN_CHAT_ID or TELEGRAM_BOT_TOKEN not set — no admin alert sent for the push failure."[0m
2026-08-15T06:15:39.4973291Z [36;1mfi[0m
2026-08-15T06:15:39.4973518Z [36;1mexit 1[0m
2026-08-15T06:15:39.5013953Z shell: /usr/bin/bash -e {0}
2026-08-15T06:15:39.5014252Z env:
2026-08-15T06:15:39.5014595Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T06:15:39.5015088Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T06:15:39.5015559Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T06:15:39.5015981Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T06:15:39.5016407Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T06:15:39.5016850Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T06:15:39.5017438Z   TELEGRAM_BOT_TOKEN: ***
2026-08-15T06:15:39.5017742Z   TELEGRAM_ADMIN_CHAT_ID: ***
2026-08-15T06:15:39.5018025Z ##[endgroup]
2026-08-15T06:15:39.5213519Z No data changes to commit.
2026-08-15T06:15:39.5310203Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T06:15:39.5311423Z Post job cleanup.
2026-08-15T06:15:39.6476746Z (node:2444) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
2026-08-15T06:15:39.6477521Z (Use `node --trace-deprecation ...` to show where the warning was created)
2026-08-15T06:15:39.6672123Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T06:15:39.6673364Z Post job cleanup.
2026-08-15T06:15:39.7620694Z [command]/usr/bin/git version
2026-08-15T06:15:39.7660598Z git version 2.54.0
2026-08-15T06:15:39.7746424Z Temporarily overriding HOME='/home/runner/work/_temp/4ba005c0-0bb5-4c17-a6c6-7f94459a2550' before making global git config changes
2026-08-15T06:15:39.7748163Z Adding repository directory to the temporary git global config as a safe directory
2026-08-15T06:15:39.7749845Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T06:15:39.7755931Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
2026-08-15T06:15:39.7792273Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
2026-08-15T06:15:39.8058309Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
2026-08-15T06:15:39.8088257Z http.https://github.com/.extraheader
2026-08-15T06:15:39.8098787Z [command]/usr/bin/git config --local --unset-all http.https://github.com/.extraheader
2026-08-15T06:15:39.8133784Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
2026-08-15T06:15:39.8402860Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
2026-08-15T06:15:39.8445568Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
2026-08-15T06:15:39.8886143Z Cleaning up orphan processes
2026-08-15T06:15:39.9197327Z ##[warning]Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4, actions/setup-python@v5. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/





2026-08-15T05:33:12.4866579Z Current runner version: '2.336.0'
2026-08-15T05:33:12.4892208Z ##[group]Runner Image Provisioner
2026-08-15T05:33:12.4893621Z Hosted Compute Agent
2026-08-15T05:33:12.4894755Z Version: 20260729.566
2026-08-15T05:33:12.4895776Z Commit: cf7153fe6e25b664e8693c24944bf2b00355d109
2026-08-15T05:33:12.4897064Z Build Date: 2026-07-29T19:17:02Z
2026-08-15T05:33:12.4898265Z Worker ID: {a7a6f4b7-fd56-44be-8356-a94f011eb14f}
2026-08-15T05:33:12.4899468Z Azure Region: northcentralus
2026-08-15T05:33:12.4900487Z ##[endgroup]
2026-08-15T05:33:12.4902602Z ##[group]Operating System
2026-08-15T05:33:12.4904259Z Ubuntu
2026-08-15T05:33:12.4905260Z 24.04.4
2026-08-15T05:33:12.4906118Z LTS
2026-08-15T05:33:12.4907085Z ##[endgroup]
2026-08-15T05:33:12.4907970Z ##[group]Runner Image
2026-08-15T05:33:12.4908943Z Image: ubuntu-24.04
2026-08-15T05:33:12.4909878Z Version: 20260810.271.1
2026-08-15T05:33:12.4911835Z Included Software: https://github.com/actions/runner-images/blob/ubuntu24/20260810.271/images/ubuntu/Ubuntu2404-Readme.md
2026-08-15T05:33:12.4914381Z Image Release: https://github.com/actions/runner-images/releases/tag/ubuntu24%2F20260810.271
2026-08-15T05:33:12.4915995Z ##[endgroup]
2026-08-15T05:33:12.4917840Z ##[group]GITHUB_TOKEN Permissions
2026-08-15T05:33:12.4920818Z Contents: write
2026-08-15T05:33:12.4921751Z Metadata: read
2026-08-15T05:33:12.4922609Z ##[endgroup]
2026-08-15T05:33:12.4925964Z Secret source: Actions
2026-08-15T05:33:12.4928139Z Prepare workflow directory
2026-08-15T05:33:12.5445760Z Prepare all required actions
2026-08-15T05:33:12.5493331Z Getting action download info
2026-08-15T05:33:12.7715093Z Download action repository 'actions/checkout@v4' (SHA:11d5960a326750d5838078e36cf38b85af677262)
2026-08-15T05:33:13.2566759Z Download action repository 'actions/setup-python@v5' (SHA:a26af69be951a213d495a4c3e4e4022e16d87065)
2026-08-15T05:33:13.8239943Z Complete job name: post
2026-08-15T05:33:13.9030810Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T05:33:13.9041430Z ##[group]Run actions/checkout@v4
2026-08-15T05:33:13.9042538Z with:
2026-08-15T05:33:13.9043165Z   fetch-depth: 1
2026-08-15T05:33:13.9044488Z   repository: sajjadisr/ESL-Telegram-channel-automation
2026-08-15T05:33:13.9053860Z   token: ***
2026-08-15T05:33:13.9054664Z   ssh-strict: true
2026-08-15T05:33:13.9055589Z   ssh-user: git
2026-08-15T05:33:13.9056434Z   persist-credentials: true
2026-08-15T05:33:13.9057238Z   clean: true
2026-08-15T05:33:13.9057886Z   sparse-checkout-cone-mode: true
2026-08-15T05:33:13.9058780Z   fetch-tags: false
2026-08-15T05:33:13.9059506Z   show-progress: true
2026-08-15T05:33:13.9060264Z   lfs: false
2026-08-15T05:33:13.9061018Z   submodules: false
2026-08-15T05:33:13.9061756Z   set-safe-directory: true
2026-08-15T05:33:13.9062629Z   allow-unsafe-pr-checkout: false
2026-08-15T05:33:13.9063842Z ##[endgroup]
2026-08-15T05:33:14.0080552Z Syncing repository: sajjadisr/ESL-Telegram-channel-automation
2026-08-15T05:33:14.0084454Z ##[group]Getting Git version info
2026-08-15T05:33:14.0087010Z Working directory is '/home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation'
2026-08-15T05:33:14.0090401Z [command]/usr/bin/git version
2026-08-15T05:33:14.0092969Z git version 2.54.0
2026-08-15T05:33:14.0113924Z ##[endgroup]
2026-08-15T05:33:14.0127132Z Temporarily overriding HOME='/home/runner/work/_temp/b4f425d7-ee2e-4035-bfea-0f5416870ea6' before making global git config changes
2026-08-15T05:33:14.0130873Z Adding repository directory to the temporary git global config as a safe directory
2026-08-15T05:33:14.0134668Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T05:33:14.0179989Z Deleting the contents of '/home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation'
2026-08-15T05:33:14.0190819Z ##[group]Initializing the repository
2026-08-15T05:33:14.0193897Z [command]/usr/bin/git init /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T05:33:14.0283535Z hint: Using 'master' as the name for the initial branch. This default branch name
2026-08-15T05:33:14.0285944Z hint: will change to "main" in Git 3.0. To configure the initial branch name
2026-08-15T05:33:14.0287861Z hint: to use in all of your new repositories, which will suppress this warning,
2026-08-15T05:33:14.0290075Z hint: call:
2026-08-15T05:33:14.0291204Z hint:
2026-08-15T05:33:14.0292711Z hint: 	git config --global init.defaultBranch <name>
2026-08-15T05:33:14.0294854Z hint:
2026-08-15T05:33:14.0297510Z hint: Names commonly chosen instead of 'master' are 'main', 'trunk' and
2026-08-15T05:33:14.0299980Z hint: 'development'. The just-created branch can be renamed via this command:
2026-08-15T05:33:14.0301755Z hint:
2026-08-15T05:33:14.0302676Z hint: 	git branch -m <name>
2026-08-15T05:33:14.0303714Z hint:
2026-08-15T05:33:14.0305559Z hint: Disable this message with "git config set advice.defaultBranchName false"
2026-08-15T05:33:14.0309456Z Initialized empty Git repository in /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation/.git/
2026-08-15T05:33:14.0314461Z [command]/usr/bin/git remote add origin https://github.com/sajjadisr/ESL-Telegram-channel-automation
2026-08-15T05:33:14.0360836Z ##[endgroup]
2026-08-15T05:33:14.0362429Z ##[group]Disabling automatic garbage collection
2026-08-15T05:33:14.0364698Z [command]/usr/bin/git config --local gc.auto 0
2026-08-15T05:33:14.0393230Z ##[endgroup]
2026-08-15T05:33:14.0395121Z ##[group]Setting up auth
2026-08-15T05:33:14.0401177Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
2026-08-15T05:33:14.0434479Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
2026-08-15T05:33:14.0801458Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
2026-08-15T05:33:14.0836489Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
2026-08-15T05:33:14.1048158Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
2026-08-15T05:33:14.1081018Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
2026-08-15T05:33:14.1269707Z [command]/usr/bin/git config --local http.https://github.com/.extraheader AUTHORIZATION: basic ***
2026-08-15T05:33:14.1307076Z ##[endgroup]
2026-08-15T05:33:14.1308953Z ##[group]Fetching the repository
2026-08-15T05:33:14.1316696Z [command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=1 origin +4e66638eb0d5053c79985f3973fd5b55578c22f7:refs/remotes/origin/main
2026-08-15T05:33:14.5346098Z From https://github.com/sajjadisr/ESL-Telegram-channel-automation
2026-08-15T05:33:14.5350025Z  * [new ref]         4e66638eb0d5053c79985f3973fd5b55578c22f7 -> origin/main
2026-08-15T05:33:14.5384491Z ##[endgroup]
2026-08-15T05:33:14.5387430Z ##[group]Determining the checkout info
2026-08-15T05:33:14.5390259Z ##[endgroup]
2026-08-15T05:33:14.5391944Z [command]/usr/bin/git sparse-checkout disable
2026-08-15T05:33:14.5437878Z [command]/usr/bin/git config --local --unset-all extensions.worktreeConfig
2026-08-15T05:33:14.5467411Z ##[group]Checking out the ref
2026-08-15T05:33:14.5470803Z [command]/usr/bin/git checkout --progress --force -B main refs/remotes/origin/main
2026-08-15T05:33:14.5587624Z Switched to a new branch 'main'
2026-08-15T05:33:14.5589754Z branch 'main' set up to track 'origin/main'.
2026-08-15T05:33:14.5595596Z ##[endgroup]
2026-08-15T05:33:14.5629719Z [command]/usr/bin/git log -1 --format=%H
2026-08-15T05:33:14.5651557Z 4e66638eb0d5053c79985f3973fd5b55578c22f7
2026-08-15T05:33:14.5997454Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T05:33:14.6002196Z ##[group]Run actions/setup-python@v5
2026-08-15T05:33:14.6003530Z with:
2026-08-15T05:33:14.6004960Z   python-version: 3.12
2026-08-15T05:33:14.6006436Z   check-latest: false
2026-08-15T05:33:14.6020736Z   token: ***
2026-08-15T05:33:14.6022206Z   update-environment: true
2026-08-15T05:33:14.6023733Z   allow-prereleases: false
2026-08-15T05:33:14.6025332Z   freethreaded: false
2026-08-15T05:33:14.6026568Z ##[endgroup]
2026-08-15T05:33:14.7355707Z ##[group]Installed versions
2026-08-15T05:33:15.0026231Z (node:2298) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
2026-08-15T05:33:15.0029678Z (Use `node --trace-deprecation ...` to show where the warning was created)
2026-08-15T05:33:15.0031480Z Successfully set up CPython (3.12.13)
2026-08-15T05:33:15.0033580Z ##[endgroup]
2026-08-15T05:33:15.0211459Z ##[group]Run pip install -r requirements.txt
2026-08-15T05:33:15.0213124Z [36;1mpip install -r requirements.txt[0m
2026-08-15T05:33:15.0449911Z shell: /usr/bin/bash -e {0}
2026-08-15T05:33:15.0451266Z env:
2026-08-15T05:33:15.0452644Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T05:33:15.0454760Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T05:33:15.0456598Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T05:33:15.0458269Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T05:33:15.0459985Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T05:33:15.0461735Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T05:33:15.0463242Z ##[endgroup]
2026-08-15T05:33:21.8591471Z Collecting google-genai==2.14.0 (from -r requirements.txt (line 1))
2026-08-15T05:33:21.9220490Z   Downloading google_genai-2.14.0-py3-none-any.whl.metadata (55 kB)
2026-08-15T05:33:21.9553376Z Collecting httpx==0.28.1 (from -r requirements.txt (line 2))
2026-08-15T05:33:21.9585820Z   Downloading httpx-0.28.1-py3-none-any.whl.metadata (7.1 kB)
2026-08-15T05:33:21.9777329Z Collecting requests==2.32.3 (from -r requirements.txt (line 6))
2026-08-15T05:33:21.9808847Z   Downloading requests-2.32.3-py3-none-any.whl.metadata (4.6 kB)
2026-08-15T05:33:21.9935106Z Collecting feedparser==6.0.11 (from -r requirements.txt (line 7))
2026-08-15T05:33:21.9965496Z   Downloading feedparser-6.0.11-py3-none-any.whl.metadata (2.4 kB)
2026-08-15T05:33:22.1427980Z Collecting Pillow==11.0.0 (from -r requirements.txt (line 8))
2026-08-15T05:33:22.1460996Z   Downloading pillow-11.0.0-cp312-cp312-manylinux_2_28_x86_64.whl.metadata (9.1 kB)
2026-08-15T05:33:22.1599238Z Collecting arabic-reshaper==3.0.0 (from -r requirements.txt (line 9))
2026-08-15T05:33:22.1633111Z   Downloading arabic_reshaper-3.0.0-py3-none-any.whl.metadata (12 kB)
2026-08-15T05:33:22.2259712Z Collecting python-bidi==0.6.3 (from -r requirements.txt (line 10))
2026-08-15T05:33:22.2296554Z   Downloading python_bidi-0.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (4.9 kB)
2026-08-15T05:33:22.2548115Z Collecting telethon==1.36.0 (from -r requirements.txt (line 11))
2026-08-15T05:33:22.2602309Z   Downloading Telethon-1.36.0.tar.gz (606 kB)
2026-08-15T05:33:22.2738076Z      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 606.3/606.3 kB 51.6 MB/s  0:00:00
2026-08-15T05:33:22.3331293Z   Installing build dependencies: started
2026-08-15T05:33:24.2445835Z   Installing build dependencies: finished with status 'done'
2026-08-15T05:33:24.2449641Z   Getting requirements to build wheel: started
2026-08-15T05:33:24.9523448Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T05:33:24.9533093Z   Preparing metadata (pyproject.toml): started
2026-08-15T05:33:25.2006884Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T05:33:25.2173552Z Collecting anyio<5.0.0,>=4.8.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T05:33:25.2207536Z   Downloading anyio-4.14.2-py3-none-any.whl.metadata (4.6 kB)
2026-08-15T05:33:25.2461510Z Collecting google-auth<3.0.0,>=2.56.0 (from google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T05:33:25.2496534Z   Downloading google_auth-2.56.3-py3-none-any.whl.metadata (6.0 kB)
2026-08-15T05:33:25.3351546Z Collecting pydantic<3.0.0,>=2.12.5 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T05:33:25.3384902Z   Downloading pydantic-2.13.4-py3-none-any.whl.metadata (109 kB)
2026-08-15T05:33:25.3609745Z Collecting tenacity<9.2.0,>=8.2.3 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T05:33:25.3646062Z   Downloading tenacity-9.1.4-py3-none-any.whl.metadata (1.2 kB)
2026-08-15T05:33:25.4674872Z Collecting websockets<17.0,>=13.0.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T05:33:25.4709046Z   Downloading websockets-16.1.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl.metadata (6.8 kB)
2026-08-15T05:33:25.4859496Z Collecting typing-extensions<5.0.0,>=4.14.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T05:33:25.4891174Z   Downloading typing_extensions-4.16.0-py3-none-any.whl.metadata (3.3 kB)
2026-08-15T05:33:25.4998742Z Collecting distro<2,>=1.7.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T05:33:25.5035037Z   Downloading distro-1.9.0-py3-none-any.whl.metadata (6.8 kB)
2026-08-15T05:33:25.5140861Z Collecting sniffio (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T05:33:25.5170464Z   Downloading sniffio-1.3.1-py3-none-any.whl.metadata (3.9 kB)
2026-08-15T05:33:25.5338259Z Collecting certifi (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T05:33:25.5369477Z   Downloading certifi-2026.7.22-py3-none-any.whl.metadata (2.5 kB)
2026-08-15T05:33:25.5514658Z Collecting httpcore==1.* (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T05:33:25.5548885Z   Downloading httpcore-1.0.9-py3-none-any.whl.metadata (21 kB)
2026-08-15T05:33:25.5690423Z Collecting idna (from httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T05:33:25.5721419Z   Downloading idna-3.18-py3-none-any.whl.metadata (6.1 kB)
2026-08-15T05:33:25.7438965Z Collecting charset-normalizer<4,>=2 (from requests==2.32.3->-r requirements.txt (line 6))
2026-08-15T05:33:25.7472970Z   Downloading charset_normalizer-3.5.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (44 kB)
2026-08-15T05:33:25.7709931Z Collecting urllib3<3,>=1.21.1 (from requests==2.32.3->-r requirements.txt (line 6))
2026-08-15T05:33:25.7741155Z   Downloading urllib3-2.7.0-py3-none-any.whl.metadata (6.9 kB)
2026-08-15T05:33:25.7876957Z Collecting sgmllib3k (from feedparser==6.0.11->-r requirements.txt (line 7))
2026-08-15T05:33:25.7907838Z   Downloading sgmllib3k-1.0.0.tar.gz (5.8 kB)
2026-08-15T05:33:25.8415489Z   Installing build dependencies: started
2026-08-15T05:33:26.8066910Z   Installing build dependencies: finished with status 'done'
2026-08-15T05:33:26.8071227Z   Getting requirements to build wheel: started
2026-08-15T05:33:27.1155559Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T05:33:27.1162943Z   Preparing metadata (pyproject.toml): started
2026-08-15T05:33:27.2831873Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T05:33:27.2931591Z Collecting pyaes (from telethon==1.36.0->-r requirements.txt (line 11))
2026-08-15T05:33:27.2962229Z   Downloading pyaes-1.6.1.tar.gz (28 kB)
2026-08-15T05:33:27.3022827Z   Installing build dependencies: started
2026-08-15T05:33:28.2835840Z   Installing build dependencies: finished with status 'done'
2026-08-15T05:33:28.2840858Z   Getting requirements to build wheel: started
2026-08-15T05:33:28.5918784Z   Getting requirements to build wheel: finished with status 'done'
2026-08-15T05:33:28.5926095Z   Preparing metadata (pyproject.toml): started
2026-08-15T05:33:28.7616855Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-15T05:33:28.7746165Z Collecting rsa (from telethon==1.36.0->-r requirements.txt (line 11))
2026-08-15T05:33:28.7779537Z   Downloading rsa-4.9.1-py3-none-any.whl.metadata (5.6 kB)
2026-08-15T05:33:28.7981122Z Collecting pyasn1-modules>=0.2.1 (from google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T05:33:28.8023712Z   Downloading pyasn1_modules-0.4.2-py3-none-any.whl.metadata (3.5 kB)
2026-08-15T05:33:28.9674289Z Collecting cryptography>=38.0.3 (from google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T05:33:28.9707171Z   Downloading cryptography-50.0.0-cp311-abi3-manylinux_2_34_x86_64.whl.metadata (4.3 kB)
2026-08-15T05:33:28.9921238Z Collecting h11>=0.16 (from httpcore==1.*->httpx==0.28.1->-r requirements.txt (line 2))
2026-08-15T05:33:28.9954349Z   Downloading h11-0.16.0-py3-none-any.whl.metadata (8.3 kB)
2026-08-15T05:33:29.0076894Z Collecting annotated-types>=0.6.0 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T05:33:29.0107294Z   Downloading annotated_types-0.8.0-py3-none-any.whl.metadata (15 kB)
2026-08-15T05:33:29.5494675Z Collecting pydantic-core==2.46.4 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T05:33:29.5528994Z   Downloading pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (6.6 kB)
2026-08-15T05:33:29.5650614Z Collecting typing-inspection>=0.4.2 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T05:33:29.5682098Z   Downloading typing_inspection-0.4.4-py3-none-any.whl.metadata (2.6 kB)
2026-08-15T05:33:29.6533158Z Collecting cffi>=2.0.0 (from cryptography>=38.0.3->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T05:33:29.6566940Z   Downloading cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl.metadata (2.5 kB)
2026-08-15T05:33:29.6700655Z Collecting pycparser (from cffi>=2.0.0->cryptography>=38.0.3->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T05:33:29.6731917Z   Downloading pycparser-3.0-py3-none-any.whl.metadata (8.2 kB)
2026-08-15T05:33:29.6928061Z Collecting pyasn1<0.7.0,>=0.6.1 (from pyasn1-modules>=0.2.1->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-15T05:33:29.6960259Z   Downloading pyasn1-0.6.4-py3-none-any.whl.metadata (8.4 kB)
2026-08-15T05:33:29.7765192Z Downloading google_genai-2.14.0-py3-none-any.whl (1.0 MB)
2026-08-15T05:33:29.7897331Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1.0/1.0 MB 72.7 MB/s  0:00:00
2026-08-15T05:33:29.7931568Z Downloading httpx-0.28.1-py3-none-any.whl (73 kB)
2026-08-15T05:33:29.7991567Z Downloading requests-2.32.3-py3-none-any.whl (64 kB)
2026-08-15T05:33:29.8052960Z Downloading feedparser-6.0.11-py3-none-any.whl (81 kB)
2026-08-15T05:33:29.8115274Z Downloading pillow-11.0.0-cp312-cp312-manylinux_2_28_x86_64.whl (4.4 MB)
2026-08-15T05:33:29.8509666Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.4/4.4 MB 111.6 MB/s  0:00:00
2026-08-15T05:33:29.8545950Z Downloading arabic_reshaper-3.0.0-py3-none-any.whl (20 kB)
2026-08-15T05:33:29.8612985Z Downloading python_bidi-0.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (286 kB)
2026-08-15T05:33:29.8692326Z Downloading anyio-4.14.2-py3-none-any.whl (125 kB)
2026-08-15T05:33:29.8751598Z Downloading charset_normalizer-3.5.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (247 kB)
2026-08-15T05:33:29.8810543Z Downloading distro-1.9.0-py3-none-any.whl (20 kB)
2026-08-15T05:33:29.8862935Z Downloading google_auth-2.56.3-py3-none-any.whl (259 kB)
2026-08-15T05:33:29.8930624Z Downloading httpcore-1.0.9-py3-none-any.whl (78 kB)
2026-08-15T05:33:29.8987193Z Downloading idna-3.18-py3-none-any.whl (65 kB)
2026-08-15T05:33:29.9042737Z Downloading pydantic-2.13.4-py3-none-any.whl (472 kB)
2026-08-15T05:33:29.9124827Z Downloading pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (2.1 MB)
2026-08-15T05:33:29.9313695Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.1/2.1 MB 110.6 MB/s  0:00:00
2026-08-15T05:33:29.9348338Z Downloading tenacity-9.1.4-py3-none-any.whl (28 kB)
2026-08-15T05:33:29.9401939Z Downloading typing_extensions-4.16.0-py3-none-any.whl (45 kB)
2026-08-15T05:33:29.9667365Z Downloading urllib3-2.7.0-py3-none-any.whl (131 kB)
2026-08-15T05:33:29.9722495Z Downloading websockets-16.1.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (187 kB)
2026-08-15T05:33:29.9779829Z Downloading annotated_types-0.8.0-py3-none-any.whl (13 kB)
2026-08-15T05:33:29.9834173Z Downloading certifi-2026.7.22-py3-none-any.whl (136 kB)
2026-08-15T05:33:29.9897361Z Downloading cryptography-50.0.0-cp311-abi3-manylinux_2_34_x86_64.whl (4.7 MB)
2026-08-15T05:33:30.0278795Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.7/4.7 MB 124.7 MB/s  0:00:00
2026-08-15T05:33:30.0314415Z Downloading cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (221 kB)
2026-08-15T05:33:30.0381335Z Downloading h11-0.16.0-py3-none-any.whl (37 kB)
2026-08-15T05:33:30.0436263Z Downloading pyasn1_modules-0.4.2-py3-none-any.whl (181 kB)
2026-08-15T05:33:30.0492090Z Downloading pyasn1-0.6.4-py3-none-any.whl (84 kB)
2026-08-15T05:33:30.0547605Z Downloading typing_inspection-0.4.4-py3-none-any.whl (14 kB)
2026-08-15T05:33:30.0603811Z Downloading pycparser-3.0-py3-none-any.whl (48 kB)
2026-08-15T05:33:30.0665545Z Downloading rsa-4.9.1-py3-none-any.whl (34 kB)
2026-08-15T05:33:30.0719628Z Downloading sniffio-1.3.1-py3-none-any.whl (10 kB)
2026-08-15T05:33:30.1556774Z Building wheels for collected packages: telethon, pyaes, sgmllib3k
2026-08-15T05:33:30.1564318Z   Building wheel for telethon (pyproject.toml): started
2026-08-15T05:33:30.4955758Z   Building wheel for telethon (pyproject.toml): finished with status 'done'
2026-08-15T05:33:30.4967086Z   Created wheel for telethon: filename=telethon-1.36.0-py3-none-any.whl size=680976 sha256=dcb71efd0982c0f36e0f58064343a05146ecd2058237079ea6c2cca4f516e704
2026-08-15T05:33:30.4968611Z   Stored in directory: /home/runner/.cache/pip/wheels/24/5b/1e/aa9bdcbb6e03ba1af024040fc49464b8b7c5ec432ce1916aa2
2026-08-15T05:33:30.4997257Z   Building wheel for pyaes (pyproject.toml): started
2026-08-15T05:33:30.7025980Z   Building wheel for pyaes (pyproject.toml): finished with status 'done'
2026-08-15T05:33:30.7031038Z   Created wheel for pyaes: filename=pyaes-1.6.1-py3-none-any.whl size=26422 sha256=ccd0a5cfc7ab9a5789325fdee79e58aa141c305e4c02fd907b771af7c3faf7ec
2026-08-15T05:33:30.7032272Z   Stored in directory: /home/runner/.cache/pip/wheels/d9/43/32/ec313dd557e88e419489b9df40c04dad7b99576bde162496f8
2026-08-15T05:33:30.7051803Z   Building wheel for sgmllib3k (pyproject.toml): started
2026-08-15T05:33:30.9138183Z   Building wheel for sgmllib3k (pyproject.toml): finished with status 'done'
2026-08-15T05:33:30.9143502Z   Created wheel for sgmllib3k: filename=sgmllib3k-1.0.0-py3-none-any.whl size=6090 sha256=bd149e94c8a781c001985ee4b7bc348685aa4fcb16f2e384eaa45cb6d352fdbf
2026-08-15T05:33:30.9145123Z   Stored in directory: /home/runner/.cache/pip/wheels/03/f5/1a/23761066dac1d0e8e683e5fdb27e12de53209d05a4a37e6246
2026-08-15T05:33:30.9158355Z Successfully built telethon pyaes sgmllib3k
2026-08-15T05:33:30.9745275Z Installing collected packages: sgmllib3k, python-bidi, pyaes, arabic-reshaper, websockets, urllib3, typing-extensions, tenacity, sniffio, pycparser, pyasn1, Pillow, idna, h11, feedparser, distro, charset-normalizer, certifi, annotated-types, typing-inspection, rsa, requests, pydantic-core, pyasn1-modules, httpcore, cffi, anyio, telethon, pydantic, httpx, cryptography, google-auth, google-genai
2026-08-15T05:33:34.6007672Z 
2026-08-15T05:33:34.6036102Z Successfully installed Pillow-11.0.0 annotated-types-0.8.0 anyio-4.14.2 arabic-reshaper-3.0.0 certifi-2026.7.22 cffi-2.1.1 charset-normalizer-3.5.0 cryptography-50.0.0 distro-1.9.0 feedparser-6.0.11 google-auth-2.56.3 google-genai-2.14.0 h11-0.16.0 httpcore-1.0.9 httpx-0.28.1 idna-3.18 pyaes-1.6.1 pyasn1-0.6.4 pyasn1-modules-0.4.2 pycparser-3.0 pydantic-2.13.4 pydantic-core-2.46.4 python-bidi-0.6.3 requests-2.32.3 rsa-4.9.1 sgmllib3k-1.0.0 sniffio-1.3.1 telethon-1.36.0 tenacity-9.1.4 typing-extensions-4.16.0 typing-inspection-0.4.4 urllib3-2.7.0 websockets-16.1.1
2026-08-15T05:33:34.7548600Z ##[group]Run python main.py
2026-08-15T05:33:34.7549048Z [36;1mpython main.py[0m
2026-08-15T05:33:34.7573871Z shell: /usr/bin/bash -e {0}
2026-08-15T05:33:34.7574425Z env:
2026-08-15T05:33:34.7574839Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T05:33:34.7575449Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T05:33:34.7575985Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T05:33:34.7576544Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T05:33:34.7577030Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T05:33:34.7577524Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T05:33:34.7578272Z   TELEGRAM_BOT_TOKEN: ***
2026-08-15T05:33:34.7578713Z   TELEGRAM_CHANNEL_ID: ***
2026-08-15T05:33:34.7579119Z   TELEGRAM_ADMIN_CHAT_ID: ***
2026-08-15T05:33:34.7579615Z   GEMINI_API_KEY: ***
2026-08-15T05:33:34.7580213Z   GEMINI_API_KEY_BACKUP: ***
2026-08-15T05:33:34.7580764Z   GROQ_API_KEY: ***
2026-08-15T05:33:34.7581208Z   CLOUDFLARE_ACCOUNT_ID: ***
2026-08-15T05:33:34.7581748Z   CLOUDFLARE_API_TOKEN: ***
2026-08-15T05:33:34.7582199Z   EITAA_TOKEN: ***
2026-08-15T05:33:34.7582568Z   EITAA_CHANNEL_ID: ***
2026-08-15T05:33:34.7582995Z   BALE_BOT_TOKEN: ***
2026-08-15T05:33:34.7583451Z   BALE_CHAT_ID: ***
2026-08-15T05:33:34.7583791Z ##[endgroup]
2026-08-15T05:34:11.6027971Z engagement_harvest: TELEGRAM_API_ID / TELEGRAM_API_HASH / TELETHON_SESSION_STRING not fully configured — skipping (see scripts/generate_telethon_session.py to set this up once; every other part of the pipeline is unaffected either way).
2026-08-15T05:34:11.6032860Z Gemini call to gemini-3.5-flash: call failed (attempt 1/3) on the primary key: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 10.432163088s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-3.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '10s'}]}}. Retrying...
2026-08-15T05:34:11.6042268Z Gemini call to gemini-3.5-flash: call failed (attempt 2/3) on the primary key: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 7.357506948s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-3.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '7s'}]}}. Retrying...
2026-08-15T05:34:11.6050626Z Gemini call to gemini-3.5-flash: call failed after 3 attempts on the primary key: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 1.254587247s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-3.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '1s'}]}}
2026-08-15T05:34:11.6058924Z generate_content_smart: Gemini failed (429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 1.254587247s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-3.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '1s'}]}}); trying Groq fallback.
2026-08-15T05:34:11.6066655Z Gemini call to gemini-3.5-flash: call failed (attempt 1/3) on the primary key: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 57.582558779s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'model': 'gemini-3.5-flash', 'location': 'global'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '57s'}]}}. Retrying...
2026-08-15T05:34:11.6075206Z Gemini call to gemini-3.5-flash: call failed (attempt 2/3) on the primary key: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 54.512081787s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-3.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '54s'}]}}. Retrying...
2026-08-15T05:34:13.6255560Z Gemini call to gemini-3.5-flash: call failed after 3 attempts on the primary key: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 48.408664681s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-3.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '48s'}]}}
2026-08-15T05:34:13.6274694Z generate_content_smart: Gemini failed (429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-3.5-flash\nPlease retry in 48.408664681s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-3.5-flash'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '48s'}]}}); trying Groq fallback.
2026-08-15T05:34:13.6286492Z generate_reviewed_text: giving up on progress_recap after 3 attempts — still not ok: متن بیشتر به فارسی است و فقط چند جمله کوتاه انگلیسی دارد؛ بنابر معیار تعادل زبان باید بیشتر به انگلیسی باشد. همچنین از تگ‌های HTML (<b>) استفاده شده که جایگزین Markdown نیست.
2026-08-15T05:34:13.8983165Z ##[group]Run set -euo pipefail
2026-08-15T05:34:13.8983754Z [36;1mset -euo pipefail[0m
2026-08-15T05:34:13.8984506Z [36;1mgit config user.name "channel-bot"[0m
2026-08-15T05:34:13.8984987Z [36;1mgit config user.email "actions@github.com"[0m
2026-08-15T05:34:13.8985476Z [36;1mgit add data/[0m
2026-08-15T05:34:13.8985915Z [36;1mif git diff --staged --quiet; then[0m
2026-08-15T05:34:13.8986372Z [36;1m  echo "No data changes to commit."[0m
2026-08-15T05:34:13.8986824Z [36;1m  exit 0[0m
2026-08-15T05:34:13.8987170Z [36;1mfi[0m
2026-08-15T05:34:13.8987605Z [36;1mgit commit -m "Daily post: update memory and database"[0m
2026-08-15T05:34:13.8988101Z [36;1mfor i in 1 2 3 4 5; do[0m
2026-08-15T05:34:13.8988562Z [36;1m  if git pull --rebase origin main && git push; then[0m
2026-08-15T05:34:13.8989086Z [36;1m    echo "Pushed successfully."[0m
2026-08-15T05:34:13.8989556Z [36;1m    exit 0[0m
2026-08-15T05:34:13.8989910Z [36;1m  fi[0m
2026-08-15T05:34:13.8990448Z [36;1m  echo "Push attempt $i failed, retrying..."[0m
2026-08-15T05:34:13.8990937Z [36;1m  sleep $((RANDOM % 10 + 5))[0m
2026-08-15T05:34:13.8991362Z [36;1mdone[0m
2026-08-15T05:34:13.8991746Z [36;1mecho "::error::Could not push after 5 attempts."[0m
2026-08-15T05:34:13.8992308Z [36;1m# A post can go out to Telegram successfully above even though the[0m
2026-08-15T05:34:13.8992923Z [36;1m# data/ commit that records it never lands — that leaves[0m
2026-08-15T05:34:13.8993508Z [36;1m# memory.json/posts.db/analytics.json/campaign_state.json stale on[0m
2026-08-15T05:34:13.8994245Z [36;1m# origin/main, and every downstream feature that reads them[0m
2026-08-15T05:34:13.8994847Z [36;1m# (dedup, review scheduling, weekly strategy) is stale until[0m
2026-08-15T05:34:13.8995430Z [36;1m# someone notices. This is the only thing that catches that[0m
2026-08-15T05:34:13.8995870Z [36;1m# specific failure mode.[0m
2026-08-15T05:34:13.8996413Z [36;1mif [ -n "$TELEGRAM_ADMIN_CHAT_ID" ] && [ -n "$TELEGRAM_BOT_TOKEN" ]; then[0m
2026-08-15T05:34:13.8997063Z [36;1m  curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \[0m
2026-08-15T05:34:13.8997695Z [36;1m    -d chat_id="${TELEGRAM_ADMIN_CHAT_ID}" \[0m
2026-08-15T05:34:13.8998581Z [36;1m    -d text="🔴 پست امروز احتمالاً منتشر شد، ولی ثبت تغییرات data/ توی گیت بعد از ۵ بار تلاش شکست خورد. یعنی memory.json/posts.db/analytics.json فعلاً روی origin/main قدیمی مونده — لازمه دستی چک و درست بشه، وگرنه ممکنه یه موضوع/جوک دوباره تکرار بشه." \[0m
2026-08-15T05:34:13.8999544Z [36;1m    > /dev/null || echo "::warning::Admin alert send also failed."[0m
2026-08-15T05:34:13.9000000Z [36;1melse[0m
2026-08-15T05:34:13.9000622Z [36;1m  echo "::warning::TELEGRAM_ADMIN_CHAT_ID or TELEGRAM_BOT_TOKEN not set — no admin alert sent for the push failure."[0m
2026-08-15T05:34:13.9001220Z [36;1mfi[0m
2026-08-15T05:34:13.9001572Z [36;1mexit 1[0m
2026-08-15T05:34:13.9026896Z shell: /usr/bin/bash -e {0}
2026-08-15T05:34:13.9027324Z env:
2026-08-15T05:34:13.9027793Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T05:34:13.9028411Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-15T05:34:13.9028998Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T05:34:13.9029519Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T05:34:13.9030061Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-15T05:34:13.9030624Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-15T05:34:13.9031526Z   TELEGRAM_BOT_TOKEN: ***
2026-08-15T05:34:13.9031947Z   TELEGRAM_ADMIN_CHAT_ID: ***
2026-08-15T05:34:13.9032335Z ##[endgroup]
2026-08-15T05:34:13.9799769Z [main f0d4193] Daily post: update memory and database
2026-08-15T05:34:13.9801048Z  1 file changed, 3 insertions(+), 74 deletions(-)
2026-08-15T05:34:14.3177989Z From https://github.com/sajjadisr/ESL-Telegram-channel-automation
2026-08-15T05:34:14.3179391Z  * branch            main       -> FETCH_HEAD
2026-08-15T05:34:14.3258921Z Current branch main is up to date.
2026-08-15T05:34:15.4087310Z To https://github.com/sajjadisr/ESL-Telegram-channel-automation
2026-08-15T05:34:15.4088217Z    4e66638..f0d4193  main -> main
2026-08-15T05:34:15.4122823Z Pushed successfully.
2026-08-15T05:34:15.4229830Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T05:34:15.4231087Z Post job cleanup.
2026-08-15T05:34:15.5456138Z (node:2448) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
2026-08-15T05:34:15.5457552Z (Use `node --trace-deprecation ...` to show where the warning was created)
2026-08-15T05:34:15.5612177Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-15T05:34:15.5613469Z Post job cleanup.
2026-08-15T05:34:15.6667758Z [command]/usr/bin/git version
2026-08-15T05:34:15.6725290Z git version 2.54.0
2026-08-15T05:34:15.6753164Z Temporarily overriding HOME='/home/runner/work/_temp/5089b2d0-e09a-4518-b934-fc4a63cf992e' before making global git config changes
2026-08-15T05:34:15.6755893Z Adding repository directory to the temporary git global config as a safe directory
2026-08-15T05:34:15.6757648Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-15T05:34:15.6787105Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
2026-08-15T05:34:15.6819603Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
2026-08-15T05:34:15.7062404Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
2026-08-15T05:34:15.7093579Z http.https://github.com/.extraheader
2026-08-15T05:34:15.7103400Z [command]/usr/bin/git config --local --unset-all http.https://github.com/.extraheader
2026-08-15T05:34:15.7137195Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
2026-08-15T05:34:15.7348233Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
2026-08-15T05:34:15.7385034Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
2026-08-15T05:34:15.7752185Z Cleaning up orphan processes
2026-08-15T05:34:15.8005026Z ##[warning]Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4, actions/setup-python@v5. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/







2026-08-14T20:36:14.5932738Z Current runner version: '2.336.0'
2026-08-14T20:36:14.5955570Z ##[group]Runner Image Provisioner
2026-08-14T20:36:14.5956482Z Hosted Compute Agent
2026-08-14T20:36:14.5957098Z Version: 20260729.566
2026-08-14T20:36:14.5957713Z Commit: cf7153fe6e25b664e8693c24944bf2b00355d109
2026-08-14T20:36:14.5958568Z Build Date: 2026-07-29T19:17:02Z
2026-08-14T20:36:14.5959273Z Worker ID: {96f8a53d-ef73-4ed8-9479-a4d3e78ec6c6}
2026-08-14T20:36:14.5959976Z Azure Region: westcentralus
2026-08-14T20:36:14.5960581Z ##[endgroup]
2026-08-14T20:36:14.5962316Z ##[group]Operating System
2026-08-14T20:36:14.5962986Z Ubuntu
2026-08-14T20:36:14.5963512Z 24.04.4
2026-08-14T20:36:14.5964031Z LTS
2026-08-14T20:36:14.5964573Z ##[endgroup]
2026-08-14T20:36:14.5965113Z ##[group]Runner Image
2026-08-14T20:36:14.5965724Z Image: ubuntu-24.04
2026-08-14T20:36:14.5966329Z Version: 20260810.271.1
2026-08-14T20:36:14.5967560Z Included Software: https://github.com/actions/runner-images/blob/ubuntu24/20260810.271/images/ubuntu/Ubuntu2404-Readme.md
2026-08-14T20:36:14.5969007Z Image Release: https://github.com/actions/runner-images/releases/tag/ubuntu24%2F20260810.271
2026-08-14T20:36:14.5969929Z ##[endgroup]
2026-08-14T20:36:14.5973130Z ##[group]GITHUB_TOKEN Permissions
2026-08-14T20:36:14.5975719Z Actions: write
2026-08-14T20:36:14.5976455Z ArtifactMetadata: write
2026-08-14T20:36:14.5977067Z Attestations: write
2026-08-14T20:36:14.5977615Z Checks: write
2026-08-14T20:36:14.5978453Z CodeQuality: write
2026-08-14T20:36:14.5979059Z Contents: write
2026-08-14T20:36:14.5979603Z CopilotRequests: write
2026-08-14T20:36:14.5980176Z Deployments: write
2026-08-14T20:36:14.5980728Z Discussions: write
2026-08-14T20:36:14.5981287Z Drives: write
2026-08-14T20:36:14.5982155Z Issues: write
2026-08-14T20:36:14.5982684Z Metadata: read
2026-08-14T20:36:14.5983419Z Models: read
2026-08-14T20:36:14.5983939Z Packages: write
2026-08-14T20:36:14.5984503Z Pages: write
2026-08-14T20:36:14.5985086Z PullRequests: write
2026-08-14T20:36:14.5985682Z RepositoryProjects: write
2026-08-14T20:36:14.5986277Z SecurityEvents: write
2026-08-14T20:36:14.5986850Z Statuses: write
2026-08-14T20:36:14.5987388Z VulnerabilityAlerts: read
2026-08-14T20:36:14.5987978Z ##[endgroup]
2026-08-14T20:36:14.5990040Z Secret source: Actions
2026-08-14T20:36:14.5990996Z Prepare workflow directory
2026-08-14T20:36:14.6332999Z Prepare all required actions
2026-08-14T20:36:14.6390725Z Getting action download info
2026-08-14T20:36:15.0552308Z Download action repository 'actions/checkout@v4' (SHA:11d5960a326750d5838078e36cf38b85af677262)
2026-08-14T20:36:15.1967242Z Download action repository 'actions/setup-python@v5' (SHA:a26af69be951a213d495a4c3e4e4022e16d87065)
2026-08-14T20:36:15.3793413Z Complete job name: check
2026-08-14T20:36:15.4470506Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-14T20:36:15.4479341Z ##[group]Run actions/checkout@v4
2026-08-14T20:36:15.4480146Z with:
2026-08-14T20:36:15.4480912Z   repository: sajjadisr/ESL-Telegram-channel-automation
2026-08-14T20:36:15.4485611Z   token: ***
2026-08-14T20:36:15.4486251Z   ssh-strict: true
2026-08-14T20:36:15.4486823Z   ssh-user: git
2026-08-14T20:36:15.4487407Z   persist-credentials: true
2026-08-14T20:36:15.4488073Z   clean: true
2026-08-14T20:36:15.4488658Z   sparse-checkout-cone-mode: true
2026-08-14T20:36:15.4489346Z   fetch-depth: 1
2026-08-14T20:36:15.4489914Z   fetch-tags: false
2026-08-14T20:36:15.4490553Z   show-progress: true
2026-08-14T20:36:15.4491126Z   lfs: false
2026-08-14T20:36:15.4491958Z   submodules: false
2026-08-14T20:36:15.4492554Z   set-safe-directory: true
2026-08-14T20:36:15.4493227Z   allow-unsafe-pr-checkout: false
2026-08-14T20:36:15.4494054Z ##[endgroup]
2026-08-14T20:36:15.5453808Z Syncing repository: sajjadisr/ESL-Telegram-channel-automation
2026-08-14T20:36:15.5457473Z ##[group]Getting Git version info
2026-08-14T20:36:15.5459405Z Working directory is '/home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation'
2026-08-14T20:36:15.5462214Z [command]/usr/bin/git version
2026-08-14T20:36:15.5472688Z git version 2.54.0
2026-08-14T20:36:15.5490089Z ##[endgroup]
2026-08-14T20:36:15.5502461Z Temporarily overriding HOME='/home/runner/work/_temp/bed374ba-1f63-4615-b294-c65e4499f35a' before making global git config changes
2026-08-14T20:36:15.5504850Z Adding repository directory to the temporary git global config as a safe directory
2026-08-14T20:36:15.5507474Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-14T20:36:15.5552897Z Deleting the contents of '/home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation'
2026-08-14T20:36:15.5556342Z ##[group]Initializing the repository
2026-08-14T20:36:15.5562614Z [command]/usr/bin/git init /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-14T20:36:15.5655413Z hint: Using 'master' as the name for the initial branch. This default branch name
2026-08-14T20:36:15.5665860Z hint: will change to "main" in Git 3.0. To configure the initial branch name
2026-08-14T20:36:15.5667690Z hint: to use in all of your new repositories, which will suppress this warning,
2026-08-14T20:36:15.5669133Z hint: call:
2026-08-14T20:36:15.5670070Z hint:
2026-08-14T20:36:15.5671060Z hint: 	git config --global init.defaultBranch <name>
2026-08-14T20:36:15.5673573Z hint:
2026-08-14T20:36:15.5675278Z hint: Names commonly chosen instead of 'master' are 'main', 'trunk' and
2026-08-14T20:36:15.5683377Z hint: 'development'. The just-created branch can be renamed via this command:
2026-08-14T20:36:15.5692667Z hint:
2026-08-14T20:36:15.5693810Z hint: 	git branch -m <name>
2026-08-14T20:36:15.5694895Z hint:
2026-08-14T20:36:15.5696042Z hint: Disable this message with "git config set advice.defaultBranchName false"
2026-08-14T20:36:15.5698251Z Initialized empty Git repository in /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation/.git/
2026-08-14T20:36:15.5702093Z [command]/usr/bin/git remote add origin https://github.com/sajjadisr/ESL-Telegram-channel-automation
2026-08-14T20:36:15.5715011Z ##[endgroup]
2026-08-14T20:36:15.5716511Z ##[group]Disabling automatic garbage collection
2026-08-14T20:36:15.5720543Z [command]/usr/bin/git config --local gc.auto 0
2026-08-14T20:36:15.5754875Z ##[endgroup]
2026-08-14T20:36:15.5756353Z ##[group]Setting up auth
2026-08-14T20:36:15.5762228Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
2026-08-14T20:36:15.5795066Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
2026-08-14T20:36:15.6114179Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
2026-08-14T20:36:15.6150365Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
2026-08-14T20:36:15.6350267Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
2026-08-14T20:36:15.6384580Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
2026-08-14T20:36:15.6575380Z [command]/usr/bin/git config --local http.https://github.com/.extraheader AUTHORIZATION: basic ***
2026-08-14T20:36:15.6609819Z ##[endgroup]
2026-08-14T20:36:15.6611691Z ##[group]Fetching the repository
2026-08-14T20:36:15.6621258Z [command]/usr/bin/git -c protocol.version=2 fetch --no-tags --prune --no-recurse-submodules --depth=1 origin +0b1c39df2506c339a1f77d7ddceff20b436ea7ac:refs/remotes/origin/main
2026-08-14T20:36:16.4287156Z From https://github.com/sajjadisr/ESL-Telegram-channel-automation
2026-08-14T20:36:16.4289898Z  * [new ref]         0b1c39df2506c339a1f77d7ddceff20b436ea7ac -> origin/main
2026-08-14T20:36:16.4318884Z ##[endgroup]
2026-08-14T20:36:16.4321480Z ##[group]Determining the checkout info
2026-08-14T20:36:16.4323830Z ##[endgroup]
2026-08-14T20:36:16.4326278Z [command]/usr/bin/git sparse-checkout disable
2026-08-14T20:36:16.4368529Z [command]/usr/bin/git config --local --unset-all extensions.worktreeConfig
2026-08-14T20:36:16.4395960Z ##[group]Checking out the ref
2026-08-14T20:36:16.4399106Z [command]/usr/bin/git checkout --progress --force -B main refs/remotes/origin/main
2026-08-14T20:36:16.4678288Z Switched to a new branch 'main'
2026-08-14T20:36:16.4681228Z branch 'main' set up to track 'origin/main'.
2026-08-14T20:36:16.4689533Z ##[endgroup]
2026-08-14T20:36:16.4740975Z [command]/usr/bin/git log -1 --format=%H
2026-08-14T20:36:16.4761726Z 0b1c39df2506c339a1f77d7ddceff20b436ea7ac
2026-08-14T20:36:16.5129720Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-14T20:36:16.5135916Z ##[group]Run actions/setup-python@v5
2026-08-14T20:36:16.5137271Z with:
2026-08-14T20:36:16.5138263Z   python-version: 3.12
2026-08-14T20:36:16.5139469Z   check-latest: false
2026-08-14T20:36:16.5149157Z   token: ***
2026-08-14T20:36:16.5150254Z   update-environment: true
2026-08-14T20:36:16.5151640Z   allow-prereleases: false
2026-08-14T20:36:16.5152839Z   freethreaded: false
2026-08-14T20:36:16.5153941Z ##[endgroup]
2026-08-14T20:36:16.6473809Z ##[group]Installed versions
2026-08-14T20:36:16.6571467Z (node:2297) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
2026-08-14T20:36:16.6575261Z (Use `node --trace-deprecation ...` to show where the warning was created)
2026-08-14T20:36:16.6577147Z Successfully set up CPython (3.12.13)
2026-08-14T20:36:16.6579237Z ##[endgroup]
2026-08-14T20:36:16.6776281Z ##[group]Run pip install -r requirements.txt
2026-08-14T20:36:16.6777892Z [36;1mpip install -r requirements.txt[0m
2026-08-14T20:36:16.6823642Z shell: /usr/bin/bash -e {0}
2026-08-14T20:36:16.6824779Z env:
2026-08-14T20:36:16.6826000Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-14T20:36:16.6828201Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-14T20:36:16.6830058Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-14T20:36:16.6831897Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-14T20:36:16.6833549Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-14T20:36:16.6835255Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-14T20:36:16.6836735Z ##[endgroup]
2026-08-14T20:36:17.6450262Z Collecting google-genai==2.14.0 (from -r requirements.txt (line 1))
2026-08-14T20:36:17.7405894Z   Downloading google_genai-2.14.0-py3-none-any.whl.metadata (55 kB)
2026-08-14T20:36:17.8168671Z Collecting requests==2.32.3 (from -r requirements.txt (line 2))
2026-08-14T20:36:17.8407944Z   Downloading requests-2.32.3-py3-none-any.whl.metadata (4.6 kB)
2026-08-14T20:36:17.8708675Z Collecting feedparser==6.0.11 (from -r requirements.txt (line 3))
2026-08-14T20:36:17.8903387Z   Downloading feedparser-6.0.11-py3-none-any.whl.metadata (2.4 kB)
2026-08-14T20:36:18.1088330Z Collecting Pillow==11.0.0 (from -r requirements.txt (line 4))
2026-08-14T20:36:18.1294958Z   Downloading pillow-11.0.0-cp312-cp312-manylinux_2_28_x86_64.whl.metadata (9.1 kB)
2026-08-14T20:36:18.1784026Z Collecting arabic-reshaper==3.0.0 (from -r requirements.txt (line 5))
2026-08-14T20:36:18.2000582Z   Downloading arabic_reshaper-3.0.0-py3-none-any.whl.metadata (12 kB)
2026-08-14T20:36:18.2756841Z Collecting python-bidi==0.6.3 (from -r requirements.txt (line 6))
2026-08-14T20:36:18.2960037Z   Downloading python_bidi-0.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (4.9 kB)
2026-08-14T20:36:18.3363823Z Collecting telethon==1.36.0 (from -r requirements.txt (line 7))
2026-08-14T20:36:18.3559292Z   Downloading Telethon-1.36.0.tar.gz (606 kB)
2026-08-14T20:36:18.4319847Z      ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 606.3/606.3 kB 9.4 MB/s  0:00:00
2026-08-14T20:36:18.4847449Z   Installing build dependencies: started
2026-08-14T20:36:19.5618866Z   Installing build dependencies: finished with status 'done'
2026-08-14T20:36:19.5625877Z   Getting requirements to build wheel: started
2026-08-14T20:36:20.1216311Z   Getting requirements to build wheel: finished with status 'done'
2026-08-14T20:36:20.1224641Z   Preparing metadata (pyproject.toml): started
2026-08-14T20:36:20.3195683Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-14T20:36:20.3522878Z Collecting anyio<5.0.0,>=4.8.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:20.3726093Z   Downloading anyio-4.14.2-py3-none-any.whl.metadata (4.6 kB)
2026-08-14T20:36:20.4140683Z Collecting google-auth<3.0.0,>=2.56.0 (from google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:20.4332754Z   Downloading google_auth-2.56.3-py3-none-any.whl.metadata (6.0 kB)
2026-08-14T20:36:20.4699960Z Collecting httpx<1.0.0,>=0.28.1 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:20.4883303Z   Downloading httpx-0.28.1-py3-none-any.whl.metadata (7.1 kB)
2026-08-14T20:36:20.5848824Z Collecting pydantic<3.0.0,>=2.12.5 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:20.6035883Z   Downloading pydantic-2.13.4-py3-none-any.whl.metadata (109 kB)
2026-08-14T20:36:20.6392952Z Collecting tenacity<9.2.0,>=8.2.3 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:20.6578539Z   Downloading tenacity-9.1.4-py3-none-any.whl.metadata (1.2 kB)
2026-08-14T20:36:20.7526348Z Collecting websockets<17.0,>=13.0.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:20.7718134Z   Downloading websockets-16.1.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl.metadata (6.8 kB)
2026-08-14T20:36:20.8188280Z Collecting typing-extensions<5.0.0,>=4.14.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:20.8375971Z   Downloading typing_extensions-4.16.0-py3-none-any.whl.metadata (3.3 kB)
2026-08-14T20:36:20.8643592Z Collecting distro<2,>=1.7.0 (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:20.8855990Z   Downloading distro-1.9.0-py3-none-any.whl.metadata (6.8 kB)
2026-08-14T20:36:20.9148917Z Collecting sniffio (from google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:20.9335660Z   Downloading sniffio-1.3.1-py3-none-any.whl.metadata (3.9 kB)
2026-08-14T20:36:21.0446427Z Collecting charset-normalizer<4,>=2 (from requests==2.32.3->-r requirements.txt (line 2))
2026-08-14T20:36:21.0634222Z   Downloading charset_normalizer-3.5.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl.metadata (44 kB)
2026-08-14T20:36:21.0952563Z Collecting idna<4,>=2.5 (from requests==2.32.3->-r requirements.txt (line 2))
2026-08-14T20:36:21.1137238Z   Downloading idna-3.18-py3-none-any.whl.metadata (6.1 kB)
2026-08-14T20:36:21.1485467Z Collecting urllib3<3,>=1.21.1 (from requests==2.32.3->-r requirements.txt (line 2))
2026-08-14T20:36:21.1670714Z   Downloading urllib3-2.7.0-py3-none-any.whl.metadata (6.9 kB)
2026-08-14T20:36:21.1997799Z Collecting certifi>=2017.4.17 (from requests==2.32.3->-r requirements.txt (line 2))
2026-08-14T20:36:21.2185655Z   Downloading certifi-2026.7.22-py3-none-any.whl.metadata (2.5 kB)
2026-08-14T20:36:21.2454855Z Collecting sgmllib3k (from feedparser==6.0.11->-r requirements.txt (line 3))
2026-08-14T20:36:21.2657486Z   Downloading sgmllib3k-1.0.0.tar.gz (5.8 kB)
2026-08-14T20:36:21.2731135Z   Installing build dependencies: started
2026-08-14T20:36:21.7283171Z   Installing build dependencies: finished with status 'done'
2026-08-14T20:36:21.7285724Z   Getting requirements to build wheel: started
2026-08-14T20:36:22.0288795Z   Getting requirements to build wheel: finished with status 'done'
2026-08-14T20:36:22.0296199Z   Preparing metadata (pyproject.toml): started
2026-08-14T20:36:22.1911412Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-14T20:36:22.2311604Z Collecting pyaes (from telethon==1.36.0->-r requirements.txt (line 7))
2026-08-14T20:36:22.2512303Z   Downloading pyaes-1.6.1.tar.gz (28 kB)
2026-08-14T20:36:22.2572858Z   Installing build dependencies: started
2026-08-14T20:36:22.7150933Z   Installing build dependencies: finished with status 'done'
2026-08-14T20:36:22.7155402Z   Getting requirements to build wheel: started
2026-08-14T20:36:23.0108357Z   Getting requirements to build wheel: finished with status 'done'
2026-08-14T20:36:23.0115531Z   Preparing metadata (pyproject.toml): started
2026-08-14T20:36:23.1724320Z   Preparing metadata (pyproject.toml): finished with status 'done'
2026-08-14T20:36:23.2007915Z Collecting rsa (from telethon==1.36.0->-r requirements.txt (line 7))
2026-08-14T20:36:23.2196620Z   Downloading rsa-4.9.1-py3-none-any.whl.metadata (5.6 kB)
2026-08-14T20:36:23.2573275Z Collecting pyasn1-modules>=0.2.1 (from google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:23.2773855Z   Downloading pyasn1_modules-0.4.2-py3-none-any.whl.metadata (3.5 kB)
2026-08-14T20:36:23.4514907Z Collecting cryptography>=38.0.3 (from google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:23.4699959Z   Downloading cryptography-50.0.0-cp311-abi3-manylinux_2_34_x86_64.whl.metadata (4.3 kB)
2026-08-14T20:36:23.5044864Z Collecting httpcore==1.* (from httpx<1.0.0,>=0.28.1->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:23.5231108Z   Downloading httpcore-1.0.9-py3-none-any.whl.metadata (21 kB)
2026-08-14T20:36:23.5523387Z Collecting h11>=0.16 (from httpcore==1.*->httpx<1.0.0,>=0.28.1->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:23.5708816Z   Downloading h11-0.16.0-py3-none-any.whl.metadata (8.3 kB)
2026-08-14T20:36:23.5985403Z Collecting annotated-types>=0.6.0 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:23.6177419Z   Downloading annotated_types-0.8.0-py3-none-any.whl.metadata (15 kB)
2026-08-14T20:36:24.1637435Z Collecting pydantic-core==2.46.4 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:24.1827188Z   Downloading pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (6.6 kB)
2026-08-14T20:36:24.2106512Z Collecting typing-inspection>=0.4.2 (from pydantic<3.0.0,>=2.12.5->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:24.2295017Z   Downloading typing_inspection-0.4.4-py3-none-any.whl.metadata (2.6 kB)
2026-08-14T20:36:24.3281258Z Collecting cffi>=2.0.0 (from cryptography>=38.0.3->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:24.3467959Z   Downloading cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl.metadata (2.5 kB)
2026-08-14T20:36:24.3920779Z Collecting pycparser (from cffi>=2.0.0->cryptography>=38.0.3->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:24.4110524Z   Downloading pycparser-3.0-py3-none-any.whl.metadata (8.2 kB)
2026-08-14T20:36:24.4463707Z Collecting pyasn1<0.7.0,>=0.6.1 (from pyasn1-modules>=0.2.1->google-auth<3.0.0,>=2.56.0->google-auth[requests]<3.0.0,>=2.56.0->google-genai==2.14.0->-r requirements.txt (line 1))
2026-08-14T20:36:24.4712837Z   Downloading pyasn1-0.6.4-py3-none-any.whl.metadata (8.4 kB)
2026-08-14T20:36:24.5001909Z Downloading google_genai-2.14.0-py3-none-any.whl (1.0 MB)
2026-08-14T20:36:24.5471089Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1.0/1.0 MB 20.1 MB/s  0:00:00
2026-08-14T20:36:24.5655581Z Downloading requests-2.32.3-py3-none-any.whl (64 kB)
2026-08-14T20:36:24.5878666Z Downloading feedparser-6.0.11-py3-none-any.whl (81 kB)
2026-08-14T20:36:24.6114289Z Downloading pillow-11.0.0-cp312-cp312-manylinux_2_28_x86_64.whl (4.4 MB)
2026-08-14T20:36:24.6992327Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.4/4.4 MB 48.5 MB/s  0:00:00
2026-08-14T20:36:24.7178264Z Downloading arabic_reshaper-3.0.0-py3-none-any.whl (20 kB)
2026-08-14T20:36:24.7399559Z Downloading python_bidi-0.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (286 kB)
2026-08-14T20:36:24.7656803Z Downloading anyio-4.14.2-py3-none-any.whl (125 kB)
2026-08-14T20:36:24.7870014Z Downloading charset_normalizer-3.5.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl (247 kB)
2026-08-14T20:36:24.8101828Z Downloading distro-1.9.0-py3-none-any.whl (20 kB)
2026-08-14T20:36:24.8310331Z Downloading google_auth-2.56.3-py3-none-any.whl (259 kB)
2026-08-14T20:36:24.8529118Z Downloading httpx-0.28.1-py3-none-any.whl (73 kB)
2026-08-14T20:36:24.8886018Z Downloading httpcore-1.0.9-py3-none-any.whl (78 kB)
2026-08-14T20:36:24.9097030Z Downloading idna-3.18-py3-none-any.whl (65 kB)
2026-08-14T20:36:24.9317828Z Downloading pydantic-2.13.4-py3-none-any.whl (472 kB)
2026-08-14T20:36:25.0163119Z Downloading pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (2.1 MB)
2026-08-14T20:36:25.0370838Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.1/2.1 MB 98.2 MB/s  0:00:00
2026-08-14T20:36:25.0558266Z Downloading tenacity-9.1.4-py3-none-any.whl (28 kB)
2026-08-14T20:36:25.0767099Z Downloading typing_extensions-4.16.0-py3-none-any.whl (45 kB)
2026-08-14T20:36:25.0985461Z Downloading urllib3-2.7.0-py3-none-any.whl (131 kB)
2026-08-14T20:36:25.1294347Z Downloading websockets-16.1.1-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl (187 kB)
2026-08-14T20:36:25.1509177Z Downloading annotated_types-0.8.0-py3-none-any.whl (13 kB)
2026-08-14T20:36:25.1718408Z Downloading certifi-2026.7.22-py3-none-any.whl (136 kB)
2026-08-14T20:36:25.1938916Z Downloading cryptography-50.0.0-cp311-abi3-manylinux_2_34_x86_64.whl (4.7 MB)
2026-08-14T20:36:25.2441491Z    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 4.7/4.7 MB 93.2 MB/s  0:00:00
2026-08-14T20:36:25.2625912Z Downloading cffi-2.1.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (221 kB)
2026-08-14T20:36:25.2859990Z Downloading h11-0.16.0-py3-none-any.whl (37 kB)
2026-08-14T20:36:25.3071654Z Downloading pyasn1_modules-0.4.2-py3-none-any.whl (181 kB)
2026-08-14T20:36:25.3291107Z Downloading pyasn1-0.6.4-py3-none-any.whl (84 kB)
2026-08-14T20:36:25.3680431Z Downloading typing_inspection-0.4.4-py3-none-any.whl (14 kB)
2026-08-14T20:36:25.3893516Z Downloading pycparser-3.0-py3-none-any.whl (48 kB)
2026-08-14T20:36:25.4101174Z Downloading rsa-4.9.1-py3-none-any.whl (34 kB)
2026-08-14T20:36:25.4313899Z Downloading sniffio-1.3.1-py3-none-any.whl (10 kB)
2026-08-14T20:36:25.5145072Z Building wheels for collected packages: telethon, pyaes, sgmllib3k
2026-08-14T20:36:25.5150816Z   Building wheel for telethon (pyproject.toml): started
2026-08-14T20:36:25.8437513Z   Building wheel for telethon (pyproject.toml): finished with status 'done'
2026-08-14T20:36:25.8454045Z   Created wheel for telethon: filename=telethon-1.36.0-py3-none-any.whl size=680976 sha256=4494803c24d63d7cbc88c10ab632db5552edcb2bc5e591c7a466295fb18ad907
2026-08-14T20:36:25.8455599Z   Stored in directory: /home/runner/.cache/pip/wheels/24/5b/1e/aa9bdcbb6e03ba1af024040fc49464b8b7c5ec432ce1916aa2
2026-08-14T20:36:25.8484213Z   Building wheel for pyaes (pyproject.toml): started
2026-08-14T20:36:26.0408795Z   Building wheel for pyaes (pyproject.toml): finished with status 'done'
2026-08-14T20:36:26.0414791Z   Created wheel for pyaes: filename=pyaes-1.6.1-py3-none-any.whl size=26422 sha256=56044fc89b5a8c2d5a752055cc46d649f32fa8fde03036122713796b363d125b
2026-08-14T20:36:26.0416918Z   Stored in directory: /home/runner/.cache/pip/wheels/d9/43/32/ec313dd557e88e419489b9df40c04dad7b99576bde162496f8
2026-08-14T20:36:26.0436517Z   Building wheel for sgmllib3k (pyproject.toml): started
2026-08-14T20:36:26.2361248Z   Building wheel for sgmllib3k (pyproject.toml): finished with status 'done'
2026-08-14T20:36:26.2366585Z   Created wheel for sgmllib3k: filename=sgmllib3k-1.0.0-py3-none-any.whl size=6090 sha256=ed9c9121ed94cfe7bea3bf481703ef9b123dd090130a6009aae469ed9665c141
2026-08-14T20:36:26.2368185Z   Stored in directory: /home/runner/.cache/pip/wheels/03/f5/1a/23761066dac1d0e8e683e5fdb27e12de53209d05a4a37e6246
2026-08-14T20:36:26.2383021Z Successfully built telethon pyaes sgmllib3k
2026-08-14T20:36:26.2952892Z Installing collected packages: sgmllib3k, python-bidi, pyaes, arabic-reshaper, websockets, urllib3, typing-extensions, tenacity, sniffio, pycparser, pyasn1, Pillow, idna, h11, feedparser, distro, charset-normalizer, certifi, annotated-types, typing-inspection, rsa, requests, pydantic-core, pyasn1-modules, httpcore, cffi, anyio, telethon, pydantic, httpx, cryptography, google-auth, google-genai
2026-08-14T20:36:29.5924415Z 
2026-08-14T20:36:29.5950857Z Successfully installed Pillow-11.0.0 annotated-types-0.8.0 anyio-4.14.2 arabic-reshaper-3.0.0 certifi-2026.7.22 cffi-2.1.1 charset-normalizer-3.5.0 cryptography-50.0.0 distro-1.9.0 feedparser-6.0.11 google-auth-2.56.3 google-genai-2.14.0 h11-0.16.0 httpcore-1.0.9 httpx-0.28.1 idna-3.18 pyaes-1.6.1 pyasn1-0.6.4 pyasn1-modules-0.4.2 pycparser-3.0 pydantic-2.13.4 pydantic-core-2.46.4 python-bidi-0.6.3 requests-2.32.3 rsa-4.9.1 sgmllib3k-1.0.0 sniffio-1.3.1 telethon-1.36.0 tenacity-9.1.4 typing-extensions-4.16.0 typing-inspection-0.4.4 urllib3-2.7.0 websockets-16.1.1
2026-08-14T20:36:29.7261691Z ##[group]Run python scripts/check_daily_completion.py
2026-08-14T20:36:29.7262216Z [36;1mpython scripts/check_daily_completion.py[0m
2026-08-14T20:36:29.7287956Z shell: /usr/bin/bash -e {0}
2026-08-14T20:36:29.7288364Z env:
2026-08-14T20:36:29.7288813Z   pythonLocation: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-14T20:36:29.7289366Z   PKG_CONFIG_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib/pkgconfig
2026-08-14T20:36:29.7289935Z   Python_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-14T20:36:29.7290399Z   Python2_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-14T20:36:29.7290838Z   Python3_ROOT_DIR: /opt/hostedtoolcache/Python/3.12.13/x64
2026-08-14T20:36:29.7291492Z   LD_LIBRARY_PATH: /opt/hostedtoolcache/Python/3.12.13/x64/lib
2026-08-14T20:36:29.7292235Z   TELEGRAM_BOT_TOKEN: ***
2026-08-14T20:36:29.7292647Z   TELEGRAM_CHANNEL_ID: ***
2026-08-14T20:36:29.7293084Z   GEMINI_API_KEY: ***
2026-08-14T20:36:29.7293455Z   TELEGRAM_ADMIN_CHAT_ID: ***
2026-08-14T20:36:29.7293958Z ##[endgroup]
2026-08-14T20:36:32.0045030Z ALERT sent: only 0/3 posts today (2026-08-15).
2026-08-14T20:36:32.1633940Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-14T20:36:32.1635302Z Post job cleanup.
2026-08-14T20:36:32.2776666Z (node:2424) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
2026-08-14T20:36:32.2777954Z (Use `node --trace-deprecation ...` to show where the warning was created)
2026-08-14T20:36:32.2959809Z Node 20 is being deprecated. This workflow is running with Node 24 by default. If you need to temporarily use Node 20, you can set the ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true environment variable. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
2026-08-14T20:36:32.2961044Z Post job cleanup.
2026-08-14T20:36:32.3855129Z [command]/usr/bin/git version
2026-08-14T20:36:32.3909737Z git version 2.54.0
2026-08-14T20:36:32.3967783Z Temporarily overriding HOME='/home/runner/work/_temp/b08c1838-4732-44c6-90d5-b408023e1052' before making global git config changes
2026-08-14T20:36:32.3969223Z Adding repository directory to the temporary git global config as a safe directory
2026-08-14T20:36:32.3975710Z [command]/usr/bin/git config --global --add safe.directory /home/runner/work/ESL-Telegram-channel-automation/ESL-Telegram-channel-automation
2026-08-14T20:36:32.4023306Z [command]/usr/bin/git config --local --name-only --get-regexp core\.sshCommand
2026-08-14T20:36:32.4064040Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'core\.sshCommand' && git config --local --unset-all 'core.sshCommand' || :"
2026-08-14T20:36:32.4309887Z [command]/usr/bin/git config --local --name-only --get-regexp http\.https\:\/\/github\.com\/\.extraheader
2026-08-14T20:36:32.4337705Z http.https://github.com/.extraheader
2026-08-14T20:36:32.4348964Z [command]/usr/bin/git config --local --unset-all http.https://github.com/.extraheader
2026-08-14T20:36:32.4382886Z [command]/usr/bin/git submodule foreach --recursive sh -c "git config --local --name-only --get-regexp 'http\.https\:\/\/github\.com\/\.extraheader' && git config --local --unset-all 'http.https://github.com/.extraheader' || :"
2026-08-14T20:36:32.4594320Z [command]/usr/bin/git config --local --name-only --get-regexp ^includeIf\.gitdir:
2026-08-14T20:36:32.4635398Z [command]/usr/bin/git submodule foreach --recursive git config --local --show-origin --name-only --get-regexp remote.origin.url
2026-08-14T20:36:32.5068690Z Cleaning up orphan processes
2026-08-14T20:36:32.5317937Z ##[warning]Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: actions/checkout@v4, actions/setup-python@v5. For more information see: https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/





[۲۰۲۶-۰۷-۲۳ ۰۷:۵۰] سجادی: /start
[۲۰۲۶-۰۷-۲۵ ۲۳:۴۱] InEnglish Admin Bot: 📊 گزارش هفتگی هوشمندی کانال
هنوز هیچ کوییز/نظرسنجی‌ای بسته و امتیازدهی نشده — امتیاز ترکیبی فعلاً موجود نیست.
آزمایش فعال «Quiz/poll hook style: statement vs question»: statement_hook: n=0، میانگین رأی=None، میانگین امتیاز=None؛ direct_question_hook: n=0، میانگین رأی=None، میانگین امتیاز=None
یادآوری: آمار بالا فقط از تلگرامه. ایتا و بله فعلاً فقط وضعیت ارسال (موفق/ناموفق) رو گزارش می‌دن، نه رأی یا تعامل واقعی — این دو تا رو کنار آمار تلگرام به‌عنوان چیز قابل‌مقایسه نبین.
[۲۰۲۶-۰۷-۲۶ ۱۶:۰۷] InEnglish Admin Bot: 🔴 اجرای امروز کلاً با خطا شکست خورد و هیچ پستی منتشر نشد: 401 UNAUTHENTICATED. {'error': {'code': 401, 'message': 'Request had invalid authentication credentials. Expected OAuth 2 access token, login cookie or other valid authentication credential. See https://developers.google.com/identity/sign-in/web/devconsole-project.', 'status': 'UNAUTHENTICATED', 'details': [{'@type': 'type.googleapis.com/google.rpc.ErrorInfo', 'reason': 'ACCESS_TOKEN_TYPE_UNSUPPORTED', 'metadata': {'method': 'google.ai.generativelanguage.v1beta.GenerativeService.GenerateContent', 'service': 'generativelanguage.googleapis.com'}}]}}
این با هشدارهای معمولی (مثل کمبود موضوع) فرق داره — این یعنی خودِ پایپ‌لاین مشکل داره (مثلاً کلید API، quota، یا یه خطای غیرمنتظره). لاگ اجرا رو توی تب Actions گیت‌هاب چک کن.
[۲۰۲۶-۰۷-۲۶ ۲۱:۴۷] InEnglish Admin Bot: 🔴 اجرای امروز کلاً با خطا شکست خورد و هیچ پستی منتشر نشد: 401 UNAUTHENTICATED. {'error': {'code': 401, 'message': 'Request had invalid authentication credentials. Expected OAuth 2 access token, login cookie or other valid authentication credential. See https://developers.google.com/identity/sign-in/web/devconsole-project.', 'status': 'UNAUTHENTICATED', 'details': [{'@type': 'type.googleapis.com/google.rpc.ErrorInfo', 'reason': 'ACCESS_TOKEN_TYPE_UNSUPPORTED', 'metadata': {'method': 'google.ai.generativelanguage.v1beta.GenerativeService.GenerateContent', 'service': 'generativelanguage.googleapis.com'}}]}}
این با هشدارهای معمولی (مثل کمبود موضوع) فرق داره — این یعنی خودِ پایپ‌لاین مشکل داره (مثلاً کلید API، quota، یا یه خطای غیرمنتظره). لاگ اجرا رو توی تب Actions گیت‌هاب چک کن.
[۲۰۲۶-۰۷-۲۶ ۲۱:۵۵] InEnglish Admin Bot: 🔴 اجرای امروز کلاً با خطا شکست خورد و هیچ پستی منتشر نشد: 401 UNAUTHENTICATED. {'error': {'code': 401, 'message': 'Request had invalid authentication credentials. Expected OAuth 2 access token, login cookie or other valid authentication credential. See https://developers.google.com/identity/sign-in/web/devconsole-project.', 'status': 'UNAUTHENTICATED', 'details': [{'@type': 'type.googleapis.com/google.rpc.ErrorInfo', 'reason': 'ACCESS_TOKEN_TYPE_UNSUPPORTED', 'metadata': {'service': 'generativelanguage.googleapis.com', 'method': 'google.ai.generativelanguage.v1beta.GenerativeService.GenerateContent'}}]}}
این با هشدارهای معمولی (مثل کمبود موضوع) فرق داره — این یعنی خودِ پایپ‌لاین مشکل داره (مثلاً کلید API، quota، یا یه خطای غیرمنتظره). لاگ اجرا رو توی تب Actions گیت‌هاب چک کن.
[۲۰۲۶-۰۷-۲۶ ۲۲:۰۱] InEnglish Admin Bot: 🔴 اجرای امروز شکست خورد: خطای احراز هویت Gemini (نه quota، نه شبکه).

Gemini call to gemini-3.5-flash-lite failed with an authentication error on the configured key: 401 UNAUTHENTICATED. {'error': {'code': 401, 'message': 'Request had invalid authentication credentials. Expected OAuth 2 access token, login cookie or other valid authentication credential. See https://developers.google.com/identity/sign-in/web/devconsole-project.', 'status': 'UNAUTHENTICATED', 'details': [{'@type': 'type.googleapis.com/google.rpc.ErrorInfo', 'reason': 'ACCESS_TOKEN_TYPE_UNSUPPORTED', 'metadata': {'service': 'generativelanguage.googleapis.com', 'method': 'google.ai.generativelanguage.v1beta.GenerativeService.GenerateContent'}}]}}

این معمولاً یعنی گوگل کلید رو به فرمت جدید «AQ.» تغییر داده (به‌جای «AIza»)، و اون فرمت جدید فعلاً توسط API رد میشه — حتی از طریق SDK رسمی.

برای رفع:
۱) توی Google AI Studio پیشوند کلید رو چک کن — اگر با AQ. شروع میشه، همینه.
۲) یه کلید جدید بساز و سکرت GEMINI_API_KEY رو توی گیت‌هاب آپدیت کن (بعضی وقتا کلید جدید بازم AIza میده).
۳) اگه یه اکانت گوگل جداگانه داری، کلیدش رو به‌عنوان سکرت جدید GEMINI_API_KEY_BACKUP اضافه کن — پایپ‌لاین خودکار روش fallback می‌کنه.
[۲۰۲۶-۰۷-۲۷ ۱۲:۲۹] InEnglish Admin Bot: ⚠️ فقط 2 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۷-۲۷ ۱۷:۱۵] InEnglish Admin Bot: ⚠️ فقط 2 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۷-۲۷ ۱۸:۳۹] InEnglish Admin Bot: ⚠️ فقط 1 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۷-۲۸ ۱۱:۱۴] InEnglish Admin Bot: ⚠️ فقط 1 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۷-۲۸ ۱۱:۳۸] InEnglish Admin Bot: ⚠️ فقط 1 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۷-۲۸ ۱۶:۳۳] InEnglish Admin Bot: ⚠️ فقط 1 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۷-۲۹ ۱۱:۱۹] InEnglish Admin Bot: ⚠️ فقط 1 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۷-۲۹ ۱۱:۴۲] InEnglish Admin Bot: ⚠️ فقط 1 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۷-۲۹ ۱۶:۴۱] InEnglish Admin Bot: ℹ️ امروز به‌جای «شوخی تصویری» پست مرور پیشرفت (هر 14 پست) منتشر می‌شه.
[۲۰۲۶-۰۷-۳۰ ۱۱:۰۹] InEnglish Admin Bot: ⚠️ فقط 1 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۷-۳۰ ۱۱:۳۰] InEnglish Admin Bot: ⚠️ فقط 1 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۷-۳۰ ۱۶:۲۶] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۷-۳۱ ۱۱:۵۴] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۷-۳۱ ۱۶:۳۹] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۷-۳۱ ۱۸:۰۵] InEnglish Admin Bot: 📊 گزارش هفتگی هوشمندی کانال
میانگین امتیاز ترکیبی اخیر (تعامل + یادگیری) بر اساس فرمت: کوییز: 0.5
پوشش دسته‌ها (آخرین بار هر دسته کِی پوشش داده شده): Common mistakes: 0 روز پیش، Grammar: 4 روز پیش، Idioms: 2 روز پیش، Persian transfer errors: هنوز پوشش نداده، Phrasal verbs: هنوز پوشش نداده، Vocabulary: 1 روز پیش
آزمایش فعال «Quiz/poll hook style: statement vs question»: statement_hook: n=1، میانگین رأی=0.0، میانگین امتیاز=0.5؛ direct_question_hook: n=0، میانگین رأی=None، میانگین امتیاز=None
یادآوری: آمار بالا فقط از تلگرامه. ایتا و بله فعلاً فقط وضعیت ارسال (موفق/ناموفق) رو گزارش می‌دن، نه رأی یا تعامل واقعی — این دو تا رو کنار آمار تلگرام به‌عنوان چیز قابل‌مقایسه نبین.
[۲۰۲۶-۰۸-۰۱ ۱۱:۰۴] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۱ ۱۱:۲۴] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۱ ۱۵:۴۵] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۲ ۱۱:۰۷] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۲ ۱۱:۲۶] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۲ ۱۵:۴۷] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۳ ۱۲:۰۷] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۳ ۱۲:۲۲] InEnglish Admin Bot: ℹ️ امروز به‌جای «میکرو-صحنه» پست مرور پیشرفت (هر 14 پست) منتشر می‌شه.
[۲۰۲۶-۰۸-۰۳ ۱۷:۲۵] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۴ ۱۱:۱۵] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۴ ۱۱:۴۱] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۴ ۱۶:۴۳] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۵ ۱۱:۱۶] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۵ ۱۱:۳۹] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۵ ۱۶:۳۴] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۶ ۱۱:۱۵] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۶ ۱۱:۳۸] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۶ ۱۶:۳۴] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۷ ۰۴:۲۴] InEnglish Admin Bot: 🔴 امروز (2026-08-07) فقط 1 از 3 پست منتشر شد.

یعنی امروز حداقل یکی از اجراهای زمان‌بندی‌شده‌ی daily_post.yml (اصلی یا جبرانی) اصلاً اجرا نشده یا با خطا شکست خورده — چیزی فراتر از یه تاخیر ساده. تب Actions گیت‌هاب رو چک کن؛ اگه لازم بود، از دکمه‌ی «Run workflow» روی daily_post.yml برای جبران دستی باقی‌مونده‌ی امروز استفاده کن.
[۲۰۲۶-۰۸-۰۷ ۰۹:۴۲] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۷ ۱۰:۲۵] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۷ ۱۷:۱۰] InEnglish Admin Bot: 📊 گزارش هفتگی هوشمندی کانال
میانگین امتیاز ترکیبی اخیر (تعامل + یادگیری) بر اساس فرمت: کوییز: 0.5
پوشش دسته‌ها (آخرین بار هر دسته کِی پوشش داده شده): Common mistakes: 2 روز پیش، Grammar: 3 روز پیش، Idioms: 1 روز پیش، Persian transfer errors: هنوز پوشش نداده، Phrasal verbs: هنوز پوشش نداده، Vocabulary: 0 روز پیش
آزمایش فعال «Quiz/poll hook style: statement vs question»: statement_hook: n=1، میانگین رأی=0.0، میانگین امتیاز=0.5؛ direct_question_hook: n=1، میانگین رأی=0.0، میانگین امتیاز=0.5
یادآوری: آمار بالا فقط از تلگرامه. ایتا و بله فعلاً فقط وضعیت ارسال (موفق/ناموفق) رو گزارش می‌دن، نه رأی یا تعامل واقعی — این دو تا رو کنار آمار تلگرام به‌عنوان چیز قابل‌مقایسه نبین.
[۲۰۲۶-۰۸-۰۸ ۰۹:۲۰] InEnglish Admin Bot: ℹ️ امروز به‌جای «میکرو-صحنه» پست مرور پیشرفت (هر 14 پست) منتشر می‌شه.
[۲۰۲۶-۰۸-۰۸ ۰۹:۵۷] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۸ ۱۵:۱۸] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۹ ۰۹:۲۳] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۹ ۱۰:۰۲] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۹ ۱۰:۰۲] InEnglish Admin Bot: 🔴 اجرای امروز کلاً با خطا شکست خورد و هیچ پستی منتشر نشد: The read operation timed out
این با هشدارهای معمولی (مثل کمبود موضوع) فرق داره — این یعنی خودِ پایپ‌لاین مشکل داره (مثلاً quota، یا یه خطای غیرمنتظره). لاگ اجرا رو توی تب Actions گیت‌هاب چک کن.
[۲۰۲۶-۰۸-۰۹ ۱۵:۱۹] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۰۹ ۱۶:۴۱] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۱۰ ۰۹:۴۷] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۱۰ ۱۰:۳۰] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۱۰ ۱۵:۳۳] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۱۱ ۰۹:۲۹] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۱۱ ۱۰:۱۰] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۱۱ ۱۵:۳۱] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۱۲ ۰۰:۲۴] InEnglish Admin Bot: 🔴 امروز (2026-08-12) فقط 0 از 3 پست منتشر شد.

یعنی امروز حداقل یکی از اجراهای زمان‌بندی‌شده‌ی daily_post.yml (اصلی یا جبرانی) اصلاً اجرا نشده یا با خطا شکست خورده — چیزی فراتر از یه تاخیر ساده. تب Actions گیت‌هاب رو چک کن؛ اگه لازم بود، از دکمه‌ی «Run workflow» روی daily_post.yml برای جبران دستی باقی‌مونده‌ی امروز استفاده کن.
[۲۰۲۶-۰۸-۱۲ ۰۹:۵۱] InEnglish Admin Bot: ⚠️ فقط 0 داستان تازه (شروع‌نشده) توی data/reader_library.json باقی مونده. وقتی به صفر برسه، فرمت «داستان مرحله‌ای» خودش رو رد می‌کنه تا موجودی تمدید بشه — یه نگاه بنداز و چندتا داستان جدید (از قبل بخش‌بندی‌شده به چند تکه) اضافه کن.
[۲۰۲۶-۰۸-۱۲ ۱۷:۰۹] InEnglish Admin Bot: ⚠️ پستِ «نورافکن واژگان» امروز بعد از 3 تلاش هم از مرحله‌ی بازبینی رد نشد و منتشر نشد: متن بیشتر به زبان فارسی روایت شده و بخش انگلیسی آن بسیار کم است (خلاف بند ۷). همچنین کلمه هدف (its) بیش از یک بار با تگ bold مشخص شده است (خلاف بند ۱۰).
لازم نیست کاری بکنی — این دور فقط پستی منتشر نشد، فردا دوباره تلاش می‌شه.
[۲۰۲۶-۰۸-۱۳ ۰۰:۲۳] InEnglish Admin Bot: 🔴 امروز (2026-08-13) فقط 0 از 3 پست منتشر شد.

یعنی امروز حداقل یکی از اجراهای زمان‌بندی‌شده‌ی daily_post.yml (اصلی یا جبرانی) اصلاً اجرا نشده یا با خطا شکست خورده — چیزی فراتر از یه تاخیر ساده. تب Actions گیت‌هاب رو چک کن؛ اگه لازم بود، از دکمه‌ی «Run workflow» روی daily_post.yml برای جبران دستی باقی‌مونده‌ی امروز استفاده کن.
[۲۰۲۶-۰۸-۱۳ ۱۰:۳۴] InEnglish Admin Bot: ⚠️ پستِ «پیام صوتی» امروز بعد از 3 تلاش هم از مرحله‌ی بازبینی رد نشد و منتشر نشد: استفاده از نویسه‌های الفبای کره‌ای (타임) در بخش تلفظ مغایر با بند ۷ است. همچنین طبق بند ۹، نام دسته‌بندی یعنی «Numbers and time» (یا معادل فارسی آن) در متن نوشته و بولد نشده است.
لازم نیست کاری بکنی — این دور فقط پستی منتشر نشد، فردا دوباره تلاش می‌شه.
[۲۰۲۶-۰۸-۱۳ ۱۵:۳۳] InEnglish Admin Bot: ⚠️ پستِ «پیام صوتی» امروز بعد از 3 تلاش هم از مرحله‌ی بازبینی رد نشد و منتشر نشد: ۱. بیشتر متن به زبان فارسی نوشته شده و بخش انگلیسی بسیار کوتاه است (عدم رعایت تعادل زبان). ۲. عبارت «Numbers and time» (یا معادل آن) در متن وجود ندارد و بولد نشده است. ۳. از نظر علمی و زبانی اشتباه فاحشی وجود دارد؛ کلمه o'clock اصلاً حرف s در آخر خود ندارد که بگوییم تلفظ نمی‌شود!
لازم نیست کاری بکنی — این دور فقط پستی منتشر نشد، فردا دوباره تلاش می‌شه.
[۲۰۲۶-۰۸-۱۳ ۱۷:۱۰] InEnglish Admin Bot: ⚠️ پستِ «پیام صوتی» امروز بعد از 3 تلاش هم از مرحله‌ی بازبینی رد نشد و منتشر نشد: بیشتر متن به زبان فارسی روایت شده و جملات انگلیسی بسیار کمی دارد که تعادل زبانی را به هم می‌زند (نقض بند ۶). همچنین عبارت دسته‌بندی «Numbers and time» در متن وجود ندارد تا طبق بند ۹ دقیقاً یک‌بار بولد شود.
لازم نیست کاری بکنی — این دور فقط پستی منتشر نشد، فردا دوباره تلاش می‌شه.
[۲۰۲۶-۰۸-۱۳ ۲۱:۵۱] InEnglish Admin Bot: 🔴 اجرای امروز کلاً با خطا شکست خورد: The read operation timed out
این با هشدارهای معمولی (مثل کمبود موضوع) فرق داره — این یعنی خودِ پایپ‌لاین مشکل داره (مثلاً quota، یا یه خطای غیرمنتظره).
⚠️ توجه: این خطا ممکنه بعد از ارسال موفق پست به تلگرام/ایتا/بله رخ داده باشه (مثلاً توی مرحله‌ی ثبت/آنالیتیکس) — لطفاً قبل از فکر کردن به «امروز پستی نرفت»، خودِ کانال رو چک کن. لاگ اجرا رو توی تب Actions گیت‌هاب هم ببین.
[۲۰۲۶-۰۸-۱۳ ۲۳:۰۱] InEnglish Admin Bot: ⚠️ پستِ «پیام صوتی» امروز بعد از 3 تلاش هم از مرحله‌ی بازبینی رد نشد و منتشر نشد: ۱. عبارت دسته‌بندی «Numbers and time» (یا معادل آن) در متن وجود ندارد و با تگ b پررنگ نشده است. ۲. تعادل زبانی رعایت نشده است؛ بیشتر متن به زبان فارسی روایت شده و بخش انگلیسی بسیار کوتاه و محدود به یک عبارت و یک جمله ساده است.
لازم نیست کاری بکنی — این دور فقط پستی منتشر نشد، فردا دوباره تلاش می‌شه.
[۲۰۲۶-۰۸-۱۴ ۰۰:۲۰] InEnglish Admin Bot: 🔴 امروز (2026-08-14) فقط 0 از 3 پست منتشر شد.

یعنی امروز حداقل یکی از اجراهای زمان‌بندی‌شده‌ی daily_post.yml (اصلی یا جبرانی) اصلاً اجرا نشده یا با خطا شکست خورده — چیزی فراتر از یه تاخیر ساده. تب Actions گیت‌هاب رو چک کن؛ اگه لازم بود، از دکمه‌ی «Run workflow» روی daily_post.yml برای جبران دستی باقی‌مونده‌ی امروز استفاده کن.
[۲۰۲۶-۰۸-۱۴ ۱۰:۳۰] InEnglish Admin Bot: ℹ️ امروز به‌جای «کوییز» پست مرور پیشرفت (هر 14 پست) منتشر می‌شه.
[۲۰۲۶-۰۸-۱۴ ۱۰:۳۱] InEnglish Admin Bot: ⚠️ پستِ «مرور پیشرفت» امروز بعد از 3 تلاش هم از مرحله‌ی بازبینی رد نشد و منتشر نشد: متن این پست عمدتاً به زبان فارسی روایت شده و بخش انگلیسی آن بسیار محدود به چند کلمه و یک جمله کوتاه است. طبق معیار ۶، تعادل زبانی رعایت نشده و بیشتر متن باید به زبان انگلیسی باشد (با گلاس یا توضیح کوتاه فارسی).
لازم نیست کاری بکنی — این دور فقط پستی منتشر نشد، فردا دوباره تلاش می‌شه.
[۲۰۲۶-۰۸-۱۴ ۱۵:۳۱] InEnglish Admin Bot: ℹ️ امروز به‌جای «کوییز» پست مرور پیشرفت (هر 14 پست) منتشر می‌شه.
[۲۰۲۶-۰۸-۱۴ ۱۵:۳۲] InEnglish Admin Bot: ⚠️ پستِ «مرور پیشرفت» امروز بعد از 3 تلاش هم از مرحله‌ی بازبینی رد نشد و منتشر نشد: بخش عمده متن به زبان فارسی نوشته شده و بخش انگلیسی فقط به چند واژه محدود شده است (عدم رعایت تعادل زبان). همچنین غلط املایی در واژه «بیینید» (ببینید) وجود دارد و عبارت «اشتباهش می‌کشن» از نظر نگارش فارسی عامیانه، نامأنوس است (بهتر است «اشتباه می‌نویسن» یا «اشتباه می‌گیرن» باشد).
لازم نیست کاری بکنی — این دور فقط پستی منتشر نشد، فردا دوباره تلاش می‌شه.
[۲۰۲۶-۰۸-۱۴ ۱۷:۰۵] InEnglish Admin Bot: ℹ️ امروز به‌جای «کوییز» پست مرور پیشرفت (هر 14 پست) منتشر می‌شه.
[۲۰۲۶-۰۸-۱۴ ۱۷:۰۶] InEnglish Admin Bot: ⚠️ پستِ «مرور پیشرفت» امروز بعد از 3 تلاش هم از مرحله‌ی بازبینی رد نشد و منتشر نشد: بخش عمده‌ی متن به زبان فارسی نوشته شده و کلمات انگلیسی فقط به صورت تک‌واژه در پرانتز قرار دارند، در حالی که طبق معیارها باید بدنه اصلی متن یا دیالوگ به انگلیسی باشد. همچنین غلط املایی در واژه «بیینین» (ببینین) وجود دارد.
لازم نیست کاری بکنی — این دور فقط پستی منتشر نشد، فردا دوباره تلاش می‌شه.
[۲۰۲۶-۰۸-۱۴ ۱۷:۱۳] InEnglish Admin Bot: 📊 گزارش هفتگی هوشمندی کانال
میانگین امتیاز ترکیبی اخیر (تعامل + یادگیری) بر اساس فرمت: کوییز: 0.5
نمونه‌های اخیر پست برای بررسی دستی: «Under the weather»، «Royal Golden Guernsey Goats join conservation herd»، «Family: grandfather»
پوشش دسته‌ها (آخرین بار هر دسته کِی پوشش داده شده): Common mistakes: 3 روز پیش، Grammar: 10 روز پیش، Idioms: 2 روز پیش، Persian transfer errors: هنوز پوشش نداده، Phrasal verbs: هنوز پوشش نداده، Vocabulary: 3 روز پیش
آزمایش فعال «Quiz/poll hook style: statement vs question»: statement_hook: n=2، میانگین رأی=0.0، میانگین امتیاز=0.5؛ direct_question_hook: n=1، میانگین رأی=0.0، میانگین امتیاز=0.5
یادآوری: آمار بالا فقط از تلگرامه. ایتا و بله فعلاً فقط وضعیت ارسال (موفق/ناموفق) رو گزارش می‌دن، نه رأی یا تعامل واقعی — این دو تا رو کنار آمار تلگرام به‌عنوان چیز قابل‌مقایسه نبین.
[۲۰۲۶-۰۸-۱۴ ۲۱:۵۹] InEnglish Admin Bot: ℹ️ امروز به‌جای «کوییز» پست مرور پیشرفت (هر 14 پست) منتشر می‌شه.
[۲۰۲۶-۰۸-۱۴ ۲۲:۰۲] InEnglish Admin Bot: ⚠️ پستِ «مرور پیشرفت» امروز بعد از 3 تلاش هم از مرحله‌ی بازبینی رد نشد و منتشر نشد: بیشتر متن این پست به زبان فارسی نوشته شده و بخش انگلیسی آن بسیار ناچیز است (تنها یک جمله کوتاه و چند کلمه مجزا). طبق معیار تعادل زبان (بند ۶)، روایت یا دیالوگ اصلی باید به انگلیسی باشد و فارسی فقط برای ترجمه یا توضیح کلمات سخت به کار رود.
لازم نیست کاری بکنی — این دور فقط پستی منتشر نشد، فردا دوباره تلاش می‌شه.
[۲۰۲۶-۰۸-۱۴ ۲۲:۵۳] InEnglish Admin Bot: ℹ️ امروز به‌جای «کوییز» پست مرور پیشرفت (هر 14 پست) منتشر می‌شه.
[۲۰۲۶-۰۸-۱۴ ۲۲:۵۵] InEnglish Admin Bot: ⚠️ پستِ «مرور پیشرفت» امروز بعد از 3 تلاش هم از مرحله‌ی بازبینی رد نشد و منتشر نشد: چند ایراد گرامری وجود دارد (مثلاً "We talked about the night sky and asking" و "a strange news"). پست یک قلاب جذاب یا تعاملی ندارد و بیشتر به‌صورت مرور خشک است. علاوه‌براین برخی واژگان (مانند "hosepipe ban", "conservation herd") برای سطح A1‑A2 کمی پیشرفته‌اند.
لازم نیست کاری بکنی — این دور فقط پستی منتشر نشد، فردا دوباره تلاش می‌شه.
[۲۰۲۶-۰۸-۱۵ ۰۰:۰۶] InEnglish Admin Bot: 🔴 امروز (2026-08-15) فقط 0 از 3 پست منتشر شد.

یعنی امروز حداقل یکی از اجراهای زمان‌بندی‌شده‌ی daily_post.yml (اصلی یا جبرانی) اصلاً اجرا نشده یا با خطا شکست خورده — چیزی فراتر از یه تاخیر ساده. تب Actions گیت‌هاب رو چک کن؛ اگه لازم بود، از دکمه‌ی «Run workflow» روی daily_post.yml برای جبران دستی باقی‌مونده‌ی امروز استفاده کن.
[۲۰۲۶-۰۸-۱۵ ۰۹:۰۳] InEnglish Admin Bot: ℹ️ امروز به‌جای «میکرو-صحنه» پست مرور پیشرفت (هر 14 پست) منتشر می‌شه.
[۲۰۲۶-۰۸-۱۵ ۰۹:۰۴] InEnglish Admin Bot: ⚠️ پستِ «مرور پیشرفت» امروز بعد از 3 تلاش هم از مرحله‌ی بازبینی رد نشد و منتشر نشد: متن بیشتر به فارسی است و فقط چند جمله کوتاه انگلیسی دارد؛ بنابر معیار تعادل زبان باید بیشتر به انگلیسی باشد. همچنین از تگ‌های HTML (<b>) استفاده شده که جایگزین Markdown نیست.
لازم نیست کاری بکنی — این دور فقط پستی منتشر نشد، فردا دوباره تلاش می‌شه.
[۲۰۲۶-۰۸-۱۵ ۰۹:۴۴] InEnglish Admin Bot: ℹ️ امروز به‌جای «میکرو-صحنه» پست مرور پیشرفت (هر 14 پست) منتشر می‌شه.
[۲۰۲۶-۰۸-۱۵ ۰۹:۴۵] InEnglish Admin Bot: ⚠️ پستِ «مرور پیشرفت» امروز بعد از 3 تلاش هم از مرحله‌ی بازبینی رد نشد و منتشر نشد: متن بیشتر به فارسی نوشته شده و فقط چند مثال انگلیسی داخل آن هستند؛ تعادل زبان مورد نیاز (بیشتر انگلیسی) رعایت نشده. علاوه بر این از تگ‌های <tg-spoiler> (HTML‑like) استفاده شده که خلاف استفاده از Markdown است.
لازم نیست کاری بکنی — این دور فقط پستی منتشر نشد، فردا دوباره تلاش می‌شه.
[۲۰۲۶-۰۸-۱۵ ۱۳:۱۴] InEnglish Admin Bot: ℹ️ امروز به‌جای «میکرو-صحنه» پست مرور پیشرفت (هر 14 پست) منتشر می‌شه.
[۲۰۲۶-۰۸-۱۵ ۱۳:۱۵] InEnglish Admin Bot: ⚠️ پستِ «مرور پیشرفت» امروز بعد از 3 تلاش هم از مرحله‌ی بازبینی رد نشد و منتشر نشد: برخی از واژگان و جملات استفاده شده در بندهای ۴ و ۶ (مانند hosepipe ban، conservation herd و Royal Golden Guernsey Goats) بسیار فراتر از سطح مبتدی (A1-A2) و در حد متوسط به بالا (B2/C1) هستند که برای زبان‌آموز مبتدی گنگ و دلسردکننده است.
لازم نیست کاری بکنی — این دور فقط پستی منتشر نشد، فردا دوباره تلاش می‌شه.
[۲۰۲۶-۰۸-۱۵ ۱۵:۰۸] InEnglish Admin Bot: ℹ️ امروز به‌جای «میکرو-صحنه» پست مرور پیشرفت (هر 14 پست) منتشر می‌شه.
[۲۰۲۶-۰۸-۱۵ ۱۵:۱۱] InEnglish Admin Bot: ⚠️ پستِ «مرور پیشرفت» امروز بعد از 3 تلاش هم از مرحله‌ی بازبینی رد نشد و منتشر نشد: بیشتر متن به زبان فارسی روایت شده و بخش انگلیسی آن بسیار ناچیز و در حد چند کلمه کوتاه است. طبق معیار ۶، برای حفظ تعادل زبانی، بدنه اصلی متن یا دیالوگ‌ها باید به انگلیسی باشند و فارسی فقط برای توضیحات کوتاه یا معنی کلمات به کار رود.
لازم نیست کاری بکنی — این دور فقط پستی منتشر نشد، فردا دوباره تلاش می‌شه.
[۲۰۲۶-۰۸-۱۵ ۱۶:۲۵] InEnglish Admin Bot: ℹ️ امروز به‌جای «میکرو-صحنه» پست مرور پیشرفت (هر 14 پست) منتشر می‌شه.
[۲۰۲۶-۰۸-۱۵ ۱۶:۲۵] InEnglish Admin Bot: ⚠️ پستِ «مرور پیشرفت» امروز بعد از 3 تلاش هم از مرحله‌ی بازبینی رد نشد و منتشر نشد: بخش عمده‌ی متن به زبان فارسی نوشته شده و جملات انگلیسی بسیار کمی در آن به کار رفته است (عدم رعایت تعادل زبانی به نفع انگلیسی). همچنین یک غلط املایی در عبارت «ک کلی هم» وجود دارد که احتمالاً منظور «و کلی هم» بوده است.
لازم نیست کاری بکنی — این دور فقط پستی منتشر نشد، فردا دوباره تلاش می‌شه.
[۲۰۲۶-۰۸-۱۵ ۲۱:۲۳] InEnglish Admin Bot: ℹ️ امروز به‌جای «میکرو-صحنه» پست مرور پیشرفت (هر 14 پست) منتشر می‌شه.
[۲۰۲۶-۰۸-۱۵ ۲۱:۲۵] InEnglish Admin Bot: ⚠️ پستِ «مرور پیشرفت» امروز بعد از 3 تلاش هم از مرحله‌ی بازبینی رد نشد و منتشر نشد: بخش عمده متن به زبان فارسی نوشته شده و انگلیسی بسیار کمی دارد. طبق معیار تعادل زبان، بیشتر متن (روایت یا دیالوگ اصلی) باید به انگلیسی باشد و فارسی فقط برای توضیح کلمات سخت یا یک جمله کوتاه به کار رود.
لازم نیست کاری بکنی — این دور فقط پستی منتشر نشد، فردا دوباره تلاش می‌شه.
[۲۰۲۶-۰۸-۱۵ ۲۲:۲۱] InEnglish Admin Bot: ℹ️ امروز به‌جای «میکرو-صحنه» پست مرور پیشرفت (هر 14 پست) منتشر می‌شه.
[۲۰۲۶-۰۸-۱۵ ۲۲:۲۲] InEnglish Admin Bot: ⚠️ پستِ «مرور پیشرفت» امروز بعد از 3 تلاش هم از مرحله‌ی بازبینی رد نشد و منتشر نشد: بخش عمده متن به زبان فارسی روایت شده و عبارات انگلیسی فقط به صورت کلمات یا مثال‌های پراکنده در آن قرار گرفته‌اند. طبق معیار ۶، روایت یا بدنه اصلی پست باید به انگلیسی باشد و فارسی فقط برای توضیحات بسیار کوتاه یا ترجمه کلمات سخت به کار رود.
لازم نیست کاری بکنی — این دور فقط پستی منتشر نشد، فردا دوباره تلاش می‌شه.




[۲۰۲۶-۰۷-۲۳ ۲۲:۱۹] In English: ☕ قسمت ۳: ماجرای من و منوی گیج‌کننده!

سارا منوی کافه رو می‌کوبه رو میز و با خجالت میگه: «الکس، من حتی نمی‌تونم بگم هر روز چیکار می‌کنم، چه برسه به سفارش قهوه!» 

الکس می‌خنده و میگه: «نگران نباش سارا! قرار نیست کتاب بنویسی. فقط کافیه کارهای روزمره‌ت رو ساده تعریف کنی.»

سارا کنجکاو میشه و می‌پرسه: «چطوری؟ مثلاً همین بیدار شدن و قهوه خوردن؟»

الکس سرشو تکون میده و میگه: «دقیقاً! اولِ هر روز ما یه کارهای ثابتی داریم که بهشون می‌گیم Daily Routine (کارهای روزمره). خیلی هم ساده‌ان.»

و روی دستمال کاغذی میز می‌نویسه:

• Wake up (بیدار شدن)
• Drink coffee (قهوه خوردن)
• Go to work (رفتن سر کار)

سارا با ذوق نگاه می‌کنه و میگه: «اِ، همین؟ پس بذار من بگم: I wake up at 8, then I drink coffee!»

الکس دست می‌زنه و میگه: «آفرین! حالا برای ناهار چی کار می‌کنی؟»

سارا یه نگاه شیطنت‌آمیز به ساعت می‌کنه و… 

چند ثانیه بعد، الکس از تعجب شاخ درمیاره! سارا قراره چه کارِ عجیبی برای ناهار بگه که الکس این‌قدر تعجب می‌کنه؟ 

👇 فردا تو قسمت بعدی می‌فهمیم!
[۲۰۲۶-۰۷-۲۵ ۰۲:۰۷] In English: 📢 یادت باشه @InEnglish رو فقط اینجا دنبال نکن!

این کانال روی چند پلتفرم دیگه هم با همین محتوا فعاله — هرکدوم که برات راحت‌تره:
🔹 تلگرام: همین‌جا
🔹 بله و ایتا: همون آیدی @InEnglish

اگه یکی از دوستات فقط تو یکی از این پلتفرم‌هاست، این پست رو براش فوروارد کن 🙌
[۲۰۲۶-۰۷-۲۵ ۰۲:۰۷] In English: [ Poll : الکس می‌خواد بگه «من هر روز صبح قهوه می‌نوشم». به نظرت کدوم جمله درسته؟ ]
- I drink coffee every morning.
- I drinks coffee every morning.
- I am drink coffee every morning.
- I drinking coffee every morning.
[۲۰۲۶-۰۷-۲۵ ۱۱:۰۲] In English: سارا داره تو آشپزخونه با تلفن حرف می‌زنه و داد می‌زنه:

"Wait, be quiet! I am cooking dinner right now!"

داوود از اتاق اون‌ورتر داد می‌زنه:
"Really? But the kitchen is burning!" (واقعاً؟ ولی آشپزخونه داره می‌سوزه!)

یا خدا! سارا سریع دوید سمت گاز. 🏃‍♀️🍳

🟢 نکته‌ی اصلی:
وقتی کاری همین الان، تو همین ثانیه‌ای که داریم حرف می‌زنیم داره اتفاق می‌افته، از am/is/are + فعل با ing- استفاده می‌کنیم.

🟡 توی بافت:
• Look! It is raining. (نگاه کن! داره بارون میاد.)
• He is sleeping right now. (اون همین الان داره می‌خوابه.)

🔴 یه نکته‌ی کوچیک:
به جای right now (همین الان)، می‌تونی فقط از کلمه‌ی now (الان) هم استفاده کنی.

تو الان داری چیکار می‌کنی؟ تو کامنت‌ها برامون بنویس (مثلاً: I am learning English). 👇
[۲۰۲۶-۰۷-۲۵ ۲۳:۰۸] In English: 📢 یادت باشه @InEnglish رو فقط اینجا دنبال نکن!

این کانال روی چند پلتفرم دیگه هم با همین محتوا فعاله — هرکدوم که برات راحت‌تره:
🔹 تلگرام: همین‌جا (@InEnglish)
🔹 بله: @InEnglish
🔹 ایتا: @InEnglish

اگه یکی از دوستات فقط تو یکی از این پلتفرم‌هاست، این پست رو براش فوروارد کن 🙌
[۲۰۲۶-۰۷-۲۵ ۲۳:۴۴] In English: آیا می‌خوایم باز هم همون اشتباهِ قدیمی رو روی میزِ کافه تکرار کنیم؟ ☕️

یادته توی Present simple tense قرار بود چطوری حرف بزنیم؟

سارا با اعتمادبه‌نفس به الکس نگاه می‌کنه و میگه:

"Look, Alex! I am drinking coffee every morning (من هر روز صبح قهوه می‌نوشم)."

الکس سرش رو تکون میده و میگه: «نه سارا، اینجا یه جای کار می‌لنگه!»

به نظرت کدوم تیکه از این جمله غلطه و چرا؟ 🤔

اشتباه اینجاست که برای عادت‌های همیشگی و کارهای روزمره، نباید از am drinking استفاده کنی. 

کلمه‌ی every morning یعنی کارِ هر روز؛ پس باید بگویید:
I drink coffee every morning. 

(توی حال ساده، برای کارهای تکراری افعال رو با -ing صدا نمی‌زنیم!)

این جمله رو امشب برای خودت تکرار کن و برای یه دوستِ مبتدی هم بفرستش تا اونم این اشتباه رو نکنه.
[۲۰۲۶-۰۷-۲۶ ۱۱:۲۵] In English: وقتی گارسون منو رو (menu) جلومون می‌ذاره، اول از همه دنبال چی می‌گردی؟ 👀

این روزا داریم روی جمله‌سازی‌های ساده کار می‌کنیم، ولی امروز بیایید یه کلمه‌ی پرکاربرد رو یاد بگیریم که توی هر رستورانی به کارتون می‌آید.

🟢 order (سفارش دادن / سفارش)

🟡 Look at the table! The waiter is ready, and we need to order (سفارش بدیم).

🔴 نکته: حواست باشه که همین کلمه هم اسمه و هم فعل. مثلاً می‌تونی بگویید "I want to order a pizza" (می‌خوام یه پیتزا سفارش بدم) یا بگویید "Here is our order" (این سفارش ماست).

حالا توی دلت فکر کن ببین آخرین باری که رفتی بیرون، چی رو با این کلمه سفارش دادی؟ 🤔

این پست رو بفرست برای اون دوستی که همیشه توی رستوران زبونش بند می‌آِید! 🍕
[۲۰۲۶-۰۷-۲۶ ۲۲:۴۸] In English: یادته چند روز پیش درباره‌ی کارهای روزمره حرف زدیم؟ بیا ببینم اون یکی رو درست یادت مونده یا نه!

سارا به ساعت نگاه می‌کنه و با تعجب میگه: «الکس، تو باز دوباره این اشتباه رو کردی!»

جمله‌ی الکس اینه:
«Every morning, I am drinking coffee.»

به نظرت این جمله درسته یا غلط؟ 🤔


این جمله غلطه! ❌

چرا؟ چون برای کارهای همیشگی و روتین (Daily routine words) باید از حال ساده استفاده کنیم، نه حال استمراری.

✅ شکل درستش:
«Every morning, I drink coffee.»
(هر روز صبح قهوه می‌نوشم.)


این اشتباه رو تو هم تکرار می‌کنی؟ این پست رو بفرست واسه اون دوستت که مدام افعال ingدار رو قاطی می‌کنه! 😉
[۲۰۲۶-۰۷-۲۷ ۱۲:۳۰] In English: Sara looks at her phone, shakes her head, and sighs: "Alex, seriously? You text my mother (مامانم) every single day at 7 AM just to ask if she's awake?!"

Alex smiles and replies: "Well, I just want to make sure she's having breakfast!"

🟢 نکته‌ی اصلی — وقتی می‌خوایم درباره‌ی اعضای خانواده حرف بزنیم، کلمه‌ی mother خیلی رسمیه. 

🟡 توی بافت — مردم توی صحبت‌های روزمره معمولاً از این کلمه استفاده می‌کنن:
"My mum (مامان) makes the best tea."

🔴 یه نکته‌ی کوچیک — حواست باشه، توی انگلیسیِ آمریکایی معمولاً می‌نویسن mom، ولی توی انگلیسیِ بریتیش بهش می‌گن mum.

حالا توی ذهنت مرور کن ببین آخرین باری که با مامانت حرف زدی، کی بود؟ این جمله رو همین امروز تو دلت برای خودت تکرار کن.
[۲۰۲۶-۰۷-۲۷ ۱۷:۱۶] In English: تابستون گرمه و ملخ داره ساز می‌زنه، ولی مورچه بیچاره داره هلاک میشه! 🐜🎵

تا اینجا توی این هفته درباره‌ی کارهای روزمره و حال ساده حرف زدیم، حالا بیا این داستان قدیمی رو با هم به انگلیسیِ خیلی ساده بخونیم. آماده‌ای؟

It is a hot summer day. An ant (مورچه) is working hard. She is carrying food to her home, one small piece at a time. 

A grasshopper (ملخ) is sitting near her. He is playing music and singing. 

The grasshopper says: "Why do you work so much? Come and sing with me!"

The ant says: "I am saving food for winter. Winter is cold, and there is no food then."

The grasshopper laughs. He says: "Winter is far away. Today is for fun!"

The ant does not answer. She just keeps working.

فکر می‌کنی وقتی زمستون بیاد، ملخ پشیمون میشه یا نه؟ 🤔 فردا قسمت دوم رو می‌ذارم تا ببینیم چی میشه!
[۲۰۲۶-۰۷-۲۷ ۱۸:۴۰] In English: یادته چند روز پیش با هم دیدیم چطور کارای الان رو بگیم؟ بیا ببینم این یکی رو هنوز یادت مونده یا نه! 🤔

سارا وسط اتاق نشسته و با عصبانیت به کف زمین نگاه می‌کنه:

"Stop! Why am I stepping on your wet paint?!" (چرا دارم روی رنگ خیسِ تو پا می‌ذارم؟!)

الکس از گوشه‌ی اتاق با خونسردی میگه:
"Oops, sorry!"

به نظرت جمله‌ی سارا درسته یا اشکال داره؟ 

جمله‌ی سارا کاملاً درسته! وقتی داریم کاری رو همین الان انجام می‌دیم، از am/is/are به‌اضافه‌ی فعل با ing استفاده می‌کنیم. توی این جور جمله‌ها، حواست باشه که فعل کمکی (مثل am) رو فراموش نکنی.

این جمله رو امشب توی ذهن‌ت مرور کن و ببین کجاها می‌تونی ازش استفاده کنی. فوروارد کردن این پست برای دوست‌هات یادت نره!
[۲۰۲۶-۰۷-۲۸ ۱۱:۱۴] In English: چرا الکس همیشه این اشتباهِ ریز رو موقع حرف زدن تکرار می‌کنه؟ بیا چک کنیم! 🧐

Sara looks at Alex and says: "Please don't say that again!"

Alex looks confused and asks: "Wait, why? Did I make a mistake?"

Yes! Here is what Alex said:
"Can you tell to me the truth?"

خطای کار کجاست؟ 🤔

جمله‌ی درست اینه:
"Can you tell me the truth?"

نکته: بعد از tell مستقیماً اسم یا ضمیر شخص (مثل me یا you) می‌آید، بدون نیاز به حرف اضافه (to). ولی بعد از say برای اشاره به مخاطب باید از to استفاده کنیم (مثل say to me).

حالا توی دلت به یک نفر بگو که این اشتباه رو دیگه تکرار نمی‌کنی و این پست رو برای یه دوست مبتدی بفرست! 💛
[۲۰۲۶-۰۷-۲۸ ۱۱:۳۸] In English: تابستون تموم شد و ملخ بی‌چاره تازه فهمید بازی چقدر گرون تموم میشه! 🐜🥶

تا اینجا دیدیم ملخ فقط داشت زیر آفتاب ساز می‌زد. حالا بیا ببینیم تو سرما چه خبره:

Weeks pass. The weather changes. The wind is cold now (باد حالا سرد است), and the trees have no leaves. Winter has arrived (زمستان رسیده است). 

The grasshopper has no food and no home. He is very cold and very hungry (خیلی سردش است و خیلی گرسنه است). 

He remembers the ant's small house, full of food. He walks slowly to her door and knocks (در می‌زند). 

"Please," he says, "can you help me? I have no food."

The ant opens the door. She looks at the grasshopper for a long moment.

به نظرت مورچه در رو محکم می‌کنه به روش یا دعوتش می‌کنه داخل؟ توی ذهنت حدس بزن تا فردا که قسمت آخر رو با هم بخونیم! 🤫
[۲۰۲۶-۰۷-۲۸ ۱۶:۳۴] In English: یادته چند روز پیش توی کافه داشتیم درباره‌ی اسم غذاها حرف می‌زدیم؟ بیا ببینیم هنوز اون اشتباهِ رایجِ کافه‌ای رو انجام می‌دی یا نه! ☕️

Leo sits at the table, looks at the waiter, and says: "I want a water."

Waiter looks confused: "A water? A bottle or a glass?"

اشتباه اینجاست: کلمه‌ی water شمارش‌پذیر نیست! پس نباید قبلش a بذاری.

جمله‌ی درست:
"I want some water." یا "I want a glass of water." (یک لیوان آب می‌خوام.)

امروز این جمله‌ی درست رو چند بار بلند برای خودت تکرار کن و حواست به این اشتباه ریز باشه. اگه فکر می‌کنی این نکته به کار بقیه هم می‌آاد، براشون بفرست!
[۲۰۲۶-۰۷-۲۹ ۱۱:۲۰] In English: [ Photo ]

وقتی تو یه جمعِ ساکت و یخ‌زده گیر می‌افتی، چطور همه‌چیز رو رو به راه می‌کنی؟ 🧊😅

Leo walks into the new office. Everyone is quiet. Nobody looks at him. 

He smiles, takes a deep breath, and tells a funny joke. The room starts to laugh. 

He just wants to break the ice (یخ جمع رو باز کردن / شروع یه ارتباط راحت تو جمع غریبه).

🟢 یادت باشه: معنی تحت‌اللفظی یعنی شکستن تکه یخ، ولی کاربردش برای وقتاییه که می‌خوای سکوت سنگینِ یه جمع جدید رو بشکنی!

این جمله‌ی تازه رو امشب توی اولین جمعی که بودی امتحان کن و ببین چقدر فضا رو صمیمی‌تر می‌کنه.
[۲۰۲۶-۰۷-۲۹ ۱۱:۴۲] In English: یادته توی قسمت‌های قبل دیدیم ملخ بی‌چاره چطور تمام تابستون رو فقط داشت زیر آفتاب ساز می‌زد؟ 🐜❄️

تا اینجا دیدیم زمستون اومد و ملخ سردش بود. حالا بیا ببینیم مورچه مهربون چکار می‌کنه:

The ant looks at the grasshopper. She remembers her hard work, and she remembers his music. 

She says: "You sang all summer instead of working. Now it is winter (الان زمستونه)." 

But she also sees that he is cold and hungry (گرسنه‌ست), and she has enough food for both of them (برای هردوشون). 

She invites him in (دعوتش می‌کنه بیاد تو) and gives him something warm to eat (چیز گرمی برای خوردن). 

"Next summer," she says, "maybe you can work a little, and sing a little too." 

The grasshopper nods. He understands now: it is good to enjoy today (لذت بردن از امروز)، but it is also wise to prepare for tomorrow (آماده شدن برای فردا).
[۲۰۲۶-۰۷-۲۹ ۱۶:۴۲] In English: Hey guys! Ready to check how much English you know now? 👀

Let's look at what we did together these weeks:

First, we talked about family and learned words like mother (مادر). 
Then, we started our fun story about The Ant and the Grasshopper (مورچه و ملخ) step by step! 🐜🦗

We practiced how to talk about right now using Present continuous tense (حال استمراری), and learned when to use Say vs tell (گفتن). 
We also ordered food with Food and restaurant vocabulary (کلمات مربوط به غذا و رستوران) 🍕, and learned how to Break the ice (یخ رو بشکنیم / ارتباط برقرار کنیم).

Look at you! You know all of this now. 🎉

Think about which one was your favorite part, and share this with a friend who is starting to learn English too!
[۲۰۲۶-۰۷-۳۰ ۱۱:۱۱] In English: هی، خیلیا فکر می‌کنن تلفظ این کلمه خیلی سخته! 

گوش کن: father. 
دوباره: father (بابا / پدر).

بگو: "My father is cooking." 
(بابام داره آشپزی می‌کنه.)

خیلیا اشتباهی میگن «فادر»، ولی حواست باشه صدای «ث» توی گلوش یه خورده نرم‌تر تلفظ می‌شه. 

حالا تو هم با صدای بلند یه بار بگو و توی خونه امتحانش کن!
[۲۰۲۶-۰۷-۳۰ ۱۱:۳۰] In English: تا حالا شده یکی بهت بگه «تو هیچ‌وقت نمی‌تونی برنده بشی»؟ 🐢💨

اونم وقتی حریف یه خرگوشِ مغرور باشه! آماده‌ای بریم سراغ یه داستانِ جدید؟

A hare and a tortoise live in the same forest (جنگل). 

The hare is very fast, and he knows it. Every day, he laughs at the slow tortoise (لاک‌پشت کند). 

"You are so slow!" he says. "You will never win a race (مسابقه) against me."

The tortoise is calm. One day, he says something surprising: 

"Let's race, then. From this tree to the river (رودخونه)."

All the animals come to watch (تماشا کردن). Nobody thinks the tortoise can win, but everyone wants to see the race. 

Ready, steady...

به نظرت لاک‌پشتِ کند چطور می‌خواد با سریع‌ترین حیوان جنگل مسابقه بده؟ توی ذهنت حدس بزن تا فردا که قسمت دوم رو می‌ذاریم.
[۲۰۲۶-۰۷-۳۰ ۱۶:۲۷] In English: یادته دفعه‌ی قبل داشتیم درباره‌ی mother (مامان) حرف می‌زدیم و کلی مثال زدیم؟ 

بیا ببینیم هنوز همون اشتباهِ رایج رو موقع استفاده ازش تکرار می‌کنی یا نه! ☕️

فلورنس با تعجب به دوستش نگاه می‌کنه و می‌گه:

"Look at this sentence. Is it correct?"

🟢 My mother drink tea every morning.

به نظرت این جمله درسته یا یه جای کار می‌لنگه؟ 

جمله‌ی بالا غلطه! ❌
چون فاعل «My mother» سوم‌شخص مفرد (she) محسوب میشه، فعل حال ساده باید پسوند s بگیره.
پس شکل درستش اینه:
My mother drinks tea every morning. ☕️ (مامان من هر روز صبح چای می‌نوشه.)

حالا تو همین جمله‌ی درست رو توی ذهن‌ت با یه موقعیت واقعی از خودت مرور کن و ببین چقدر راحت تو ذهن می‌مونه! ✨
[۲۰۲۶-۰۷-۳۱ ۱۱:۵۴] In English: فکر می‌کنی خرگوشِ مغرور بعد از اون شروعِ تند، توی مسابقه برنده می‌شه یا نه؟ 🐢

تا اینجا دیدیم خرگوش و لاک‌پشت توی یه جنگل زندگی می‌کنن. حالا مسابقه شروع می‌شه:

The race begins. 

The hare runs very fast (خیلی تند), and soon he is far ahead of the tortoise. 

He looks back and sees the tortoise walking slowly, far behind (خیلی عقب). 

The hare thinks: 'I have so much time. I can rest a little under this tree.' 

He lies down in the cool shade (سایه‌ی خنک) and closes his eyes, just for a minute. 

But the minute becomes an hour, and the hare falls asleep (خوابش می‌بره). 

The tortoise keeps walking, slowly and steadily, one step after another.

به نظرت وقتی خرگوش خوابه، لاک‌پشت می‌تونه ازش رد بشه؟ توی ذهنت حدس بزن و آماده شو برای قسمت بعد!
[۲۰۲۶-۰۷-۳۱ ۱۶:۴۰] In English: یادته گفتیم فرق say و tell کجاست؟ بیا این اشتباه ریز رو یک بار برای همیشه حل کنیم! 😉

سارا با تعجب به گوشی‌ش نگاه می‌کنه و میگه:
"Wait! Did he just tell me a lie?" (صبر کن! الان بهم دروغ گفت؟)

🟢 نکته‌ی اصلی:
وقتی می‌خوایم بگیم کسی به «یکی دیگر» چیزی رو گفت، از tell استفاده می‌کنیم؛ یعنی شخصِ مقابل بلافاصله بعدش میاد (مثل tell me، tell him). اما موقع استفاده از say، نیازی به آوردن شخص نیست (مثل say sorry).

🟡 توی بافت:
Alex looks at Sara and says: "Please don't be angry." (الکس به سارا نگاه می‌کنه و میگه: «لطفاً عصبانی نباش.»)

🔴 یه نکته‌ی کوچیک:
عبارت tell a lie (دروغ گفتن) یکی از رایج‌ترین ترکیب‌هاست که همیشه با tell میاد، هیچ‌وقت نمی‌گیم say a lie.

چند بار این جمله رو بلند برای خودت تکرار کن تا ملکه‌ی ذهنت بشه! ✨
[۲۰۲۶-۰۸-۰۱ ۱۱:۰۴] In English: علی با خندة بلند به گوشیش نگاه می‌کنه و به دوستش میگه:
"Look at this! My cat played piano yesterday!" (ببین اینو! گربه‌م دیروز پیانو زد!)

دوستش می‌خنده و میگه: 
"Sure, and my dog drives a car!" (معلومه، سگِ منم رانندگی می‌کنه!)

🟢 نکته‌ی اصلی: وقتی می‌خوایم درباره‌ی یه کاری بگیم که تموم شده و رفته، از گذشته‌ی ساده استفاده می‌کنیم (Past simple tense). برای بیشتر فعل‌ها، فقط کافیه یه -ed به آخرشون اضافه کنیم. مثل play که می‌شه played (بازی کرد / نواخت).

🟡 توی بافت:
Yesterday, Ali watched a funny video. (دیروز، علی یه ویدیوی خنده‌دار تماشا کرد.)

🔴 یه نکته‌ی کوچیک مرتبط: کلماتی مثل yesterday (دیروز) یا last night (دیشب) بهمون کمک می‌کنن بفهمیم کار توی گذشته اتفاق افتاده.

حالا تو به یه نفر پیام بده و بگو دیروز چیکار کردی (مثلاً: I walked yesterday). این جمله رو امروز توی زندگی واقعی‌ت امتحان کن! 😉
[۲۰۲۶-۰۸-۰۱ ۱۱:۲۴] In English: فکر می‌کنی سرعت بالا همیشه برنده مسابقه‌ست یا آهسته و پیوسته بودن؟ 🐢🏁

تا اینجا دیدیم خرگوشِ مغرور وسط راه خوابش برد. حالا قسمت آخر و نتیجه کار:

The tortoise (لاک‌پشت) walks past the sleeping hare (خرگوش خواب‌زده). He does not run, but he does not stop. 

Finally, the hare wakes up. He looks around and sees the tortoise near the finish line! 

The hare runs as fast as he can, but it is too late (خیلی دیره). The tortoise wins the race. 

All the animals cheer (هورا می‌کشن). 

The hare learns a big lesson that day: being fast means nothing (سرعت زیاد هیچ معنی‌ای نداره) if you don't finish.

داستان قشنگمون اینجا تموم شد. به نظرت تو زندگیِ واقعی کدوم‌یکی بیشتر به درد می‌خوره: تند تند کارها رو انجام دادن یا آرام و بااستادگی جلو رفتن؟ این رو برای خودت تو خلوتت مرور کن.
[۲۰۲۶-۰۸-۰۱ ۱۵:۴۶] In English: یادته گفتیم چطور توی یه جمعِ ساکت و یخ‌زده، فضا رو عوض کنی؟ 🧊😅 بیا ببینیم این اصطلاح رو هنوز درست یادت مونده یا نه!

Sam walks into the elevator. Everyone looks at the floor. Nobody talks. 

Sam wants to break the ice (یخ جمع رو بشکنه / سر صحبت رو باز کنه). 

کدوم جمله درباره کار سام درسته؟ به نظرت کدوم اشتباهه؟

❌ Sam breaked the ice with a funny joke.

جواب درست: Sam broke the ice with a funny joke. (سام با یه جوک باحال سر صحبت رو باز کرد.)

اشتباه رایج: فعل break بی‌قاعده‌ست؛ توی گذشته ساده نمی‌شه بهشed اضافه کرد. باید بشه broke!

این جمله رو امسال توی یه جمعِ تازه امتحان کن! 😉 فوروارد کن برای دوستت که زبان می‌خونه.
[۲۰۲۶-۰۸-۰۲ ۱۱:۰۸] In English: تا حالا دقت کردی بعضی وقت‌ها یه کلمه‌ی ساده توی فیلم‌ها برعکسِ کتاب‌ها استفاده میشه؟ 🤔

رعایت قوانین و استفاده از انگلیسیِ روان یعنی این! بیا فقط روی یه کلمه تمرکز کنیم:

🟢 نکته‌ی اصلی:
کلمه‌ی sister (خواهر) توی جمله‌های روزمره کلی کاربرد داره.

🟡 توی بافت:
Sara looks at her phone and smiles. She says:
"My sister calls me every night." (خواهرَم هر شب بهم زنگ می‌زنه.)

🔴 یه نکته‌ی کوچیک مرتبط:
موقع صحبت کردن، خیلی‌وقت‌ها به‌جای این کلمه از اسم کوچیک طرف استفاده می‌کنیم یا توی جمع‌های دوستانه بهش میگیم sis (آبجی / خواهر جون).

حالا تو هم همین الان توی ذهن خودت یه جمله با همین کلمه برای یه نفر از دوستات بساز و بلند تکرارش کن! 🗣️
[۲۰۲۶-۰۸-۰۲ ۱۱:۲۷] In English: یادته گفتیم تلفظ این کلمه چقدر توی ذهن آدم می‌مونه؟ 🤔 بیا یه چالش ریز داشته باشیم!

آرش به عکس قدیمی روی میز اشاره می‌کنه و به رفیقش میگه:

"Look at this old photo! My father was so young here." 
(ببین این عکس قدیمی رو! بابام اینجا خیلی جوون بود.)

حالا تو به این جمله نگاه کن. به نظرت این جمله درسته یا غلط؟ 👇

"He is my best friend and my father helps me every day."

این جمله کاملاً اشتباهه! ❌ 
چرا؟ چون «father» یعنی پدر واقعی، نه هر کس دیگه‌ای. برای اینکه بگی «بابام هر روز کمکم می‌کنه»، همون جمله‌ی آرش درسته: "My father helps me every day." (بابام هر روز کمکم می‌کنه.)

حالا توی ذهنت یه جمله با این کلمه بساز و برای خودت تکرارش کن!
[۲۰۲۶-۰۸-۰۲ ۱۵:۴۷] In English: یادته گفتیم برای کارهای دیروز از کدوم شکل فعل استفاده می‌کنیم؟ 🤔 بیا ببینیم این اشتباه رایج رو هنوز انجام می‌دی یا نه!

Sara looks at her messy room and says:
"Yesterday, I cleaned (تمیز کردم) my room for two hours."

Now, look at this sentence from her brother:
"She didn't cleaned (تمیز نکرد) her room."

جمله‌ی برادر سارا غلطه! توی جمله‌ی منفی یا سوالیِ Past simple tense، بعد از didn't باید از فعل ساده (بدون ed) استفاده کنیم.

شکل درستش اینه:
"She didn't clean her room."

🟢 نکته:
وقتی didn't میاد، خودش گذشته رو نشون میده؛ پس فعل اصلی می‌ره حالت ساده!
[۲۰۲۶-۰۸-۰۳ ۱۲:۰۸] In English: یخچال خالیه و تو گرسنه‌ای، ولی فقط یه دونه تخم‌مرغ مونده! حالا چطور به دوستت می‌گی؟ 🍳😅

سارا در یخچال رو باز می‌کنه و به علی میگه:

"Oh no! There is (هست / وجود دارد) only one egg in the fridge (یخچال)."

علی می‌خنده و جواب میده:
"No problem! We can make coffee (قهوه) instead."

🟢 نکته‌ی اصلی:
برای نشون دادن وجودِ یک چیز از There is (برای مفرد) استفاده می‌کنیم. برای چند تا چیز (جمع) هم می‌گیم There are.

🟡 توی بافت:
There is a book on the table (روی میز).

🔴 نکته‌ی کوچیک:
وقتی می‌خوای بگی «چیزی وجود نداره»، خیلی راحت کلمه‌ی not رو اضافه می‌کنی: 
There is not (یا There isn't).

فکر کن همین الان توی اتاقتی؛ یه چیز رو انتخاب کن و با همین ساختار توی دلت بگو توی اتاقت چی هست یا چی نیست. این پست رو هم برای اون دوستت که عاشق گرامرِ ساده‌ست بفرست!
[۲۰۲۶-۰۸-۰۳ ۱۲:۲۲] In English: چقدر سریع گذشت، مگه نه؟ (یا شاید هم برعکس، حس می‌کنی خیلی طول کشیده؟) 

Let’s take a quick look back. What did we learn together recently?

First, we started a fun journey with The Tortoise and the Hare (لاک‌پشت و خرگوش) and saw how simple words make a great story. 

Then, we learned how to talk about our family members like sister (خواهر) and father (پدر). 

We also practiced how to break the ice (یخ رو بشکنیم / سر صحبت رو باز کنیم) in a friendly chat.

In grammar, we checked out There is / there are (وجود داشتن) and practiced talking about the past using Past simple tense (زمان گذشته ساده).

Look at you now! You know much more than a few weeks ago. 

فراموش نکن که یادت بمونه: پیشرفت توی زبان انگلیسی یه مسابقه‌ی دو نیست، مثل همون لاک‌پشته که آهسته و پیوسته رفت و برد! 🐢

این پیام رو برای یه دوست که اونم داره انگلیسی یاد می‌گیره بفرست تا با هم مرور کنید.
[۲۰۲۶-۰۸-۰۳ ۱۷:۲۷] In English: یادته سارا رو؟ همون دختر خجالتیِ داستان‌های ما که هر روز کلی ماجرا داره؟ 🤔 بیا ببینیم این بار توی اتاقش چه خبره!

Sara opens her small wardrobe and looks at the shelves. She wants to find a nice shirt for her party tonight. 

She turns to her sister (خواهرِ) and says:

"Hey! Can I borrow your blue shirt? Mine is dirty."

اما وایسا! این وسط یه اشتباه رایج بین فارسی‌زبان‌ها هست که خیلی وقت‌ها پیش میاد. به نظرت کدوم جمله درست‌تره؟

جمله درست همینه که بالا خوندی! اشتباه رایج اینه که بعضیا اول جمله از کلمات اضافه‌تر استفاده می‌کنن یا فعل رو جا میذارن. توی سطح مبتدی، فقط کافیه مستقیم بگی چی می‌خوای: "Can I borrow your...?" و بعد اسم وسیله رو بیاری.

این اصطلاح رو امشب برای یه نفر بفرست که همیشه لباس‌هاش رو از بقیه قرض می‌گیره! 😉
[۲۰۲۶-۰۸-۰۴ ۱۱:۱۶] In English: امروز ببینیم کدوم جمله درسته! 🧐  

❌ She does a cake for her brother.  

✅ She makes a cake for her brother.  

We use **make** when we create or produce something (like a cake, a plan).  
We use **do** for tasks, chores, or general activities.  
Here we are creating a cake, so “makes” is the right choice.
[۲۰۲۶-۰۸-۰۴ ۱۱:۴۲] In English: یادته اون مبحث مهمی که گفتیم برای شمارش چیزها تو خونه استفاده می‌کنی؟ 🤔 بیا ببینیم این بار توی این جمله گاف می‌دی یا نه!

سارا داره برای مهمونی امشب خونه رو مرتب می‌کنه و به دوستش میا میگه:

"Quick! Help me! There is (هست / وجود دارد) three apples on the table, but we need more!"

❌

جمله غلطه! 
اشتباه رایج اینه که چون «سیب‌ها» جمع هستن، فکر می‌کنی باید از is استفاده کنی، در حالی که وقتی اسم جمع داریم، باید از are استفاده کنیم. 

جمله درست:
"Quick! Help me! There are three apples on the table, but we need more!"

تو هم همین الان بلند شو و یه جمله با این ساختار برای وسایل دور و برت بساز! این پست رو هم برای اون دوستی که همیشه این اشتباه رو می‌کنه، بفرست.
[۲۰۲۶-۰۸-۰۴ ۱۶:۴۷] In English: گوشی‌هاتون آماده‌ست؟ 📱 یه هوش مصنوعیِ تازه اومده که خودش کارها رو انجام میده، بدون اینکه تو بهش بگی چی کار کن!

این روزها دنیای Tech Life (زندگیِ تکنولوژی) خیلی سریع عوض می‌شه. حالا یک هوش مصنوعیِ جدید اومده که اسمش Agentic AI (هوش مصنوعیِ عامل) هست. 

توی گذشته، ما به کامپیوتر می‌گفتیم چی کار کن. اما این هوش مصنوعیِ جدید خودش فکر می‌کنه، کار رو شروع می‌کنه و تا آخرش رو خودش می‌ره (خیلی راحت!).

🟢 نکته‌ی اصلی: اسم این تکنولوژیِ جدید «Agentic AI» هست. توی دنیای تکنولوژی امروز، این کلمه رو زیاد می‌شنوی.

🟡 توی بافت: 
"My new phone has Agentic AI. It helps me every day (تلفن همراهم هوش مصنوعیِ عامل داره. هر روز کمکم می‌کنه)."

🔴 یه نکته‌ی کوچیک: کلمه‌ی «Agent» یعنی کسی که یه کاری رو برای شما انجام میده. پس این هوش مصنوعی مثل یه دوستِ کمکی تو گوشیته.

فکر کن گوشیت فردا خودش همه‌ی کارهای خسته‌کننده رو انجام بده! این جمله‌ی انگلیسی رو امروز توی ذهن‌ت مرور کن: 
"My phone is smart now."

برای دوستت که عاشق تکنولوژی‌ه فورواردش کن تا اونم عقب نمونه!
[۲۰۲۶-۰۸-۰۵ ۱۱:۱۶] In English: [ Photo ]

تا حالا فکر کردی چرا یه موقع یه کار خیلی راحت رو با کیک مقایسه می‌کنن؟ 🍰 قضیه کیک چیه واقعاً؟!

Tom looks at the big math test and smiles. 

He finishes all the questions in five minutes and tells his friend:

"Don't worry about the exam, it's a piece of cake (مثل آب خوردن / خیلی آسونه)."

حالا نوبت توئه؛ این اصطلاح بامزه رو توی زندگیِ واقعیِ امروزت استفاده کن و ببین چقدر کارها رو برات روون‌تر می‌کنه. فردا توی کانال کلی سورپرایز دیگه داریم، این پست رو برای دوستت هم بفرست تا اونم یاد بگیره!
[۲۰۲۶-۰۸-۰۵ ۱۱:۴۲] In English: یادته چند روز پیش گفتیم تفاوت do و make چیه؟ 🤔 بیا یه بار دیگه با یه مثال تازه مرور کنیم ببینیم یادت مونده یا نه!

Sara is sitting at her desk. She has a big math test tomorrow, so she wants to make a plan (برنامه‌ریزی کردن) for studying.

🟢 نکته‌ی اصلی:
وقتی می‌خوایم بگیم یه چیزی رو از صفر می‌سازیم یا خلق می‌کنیم (مثل غذا، کیک یا برنامه‌ریزی)، از make استفاده می‌کنیم.

🟡 توی بافت:
She looks at her notebook and writes down every single study hour.

🔴 یه نکته‌ی کوچیک:
حواست باشه که شکل گذشته‌ی این فعل made (ساخت / درست کرد) هست، نه doid! 

این جمله‌ی تازه رو امشب تو ذهنه‌ت مرور کن و ببین کجاها می‌تونی ازش استفاده کنی. فردا با یه ماجرای دیگه برمی‌گردیم!
[۲۰۲۶-۰۸-۰۵ ۱۶:۳۷] In English: ایلان ماسک به سرمایه‌گذارها چی گفت؟ 🤔 خبرهای دنیای پول و شرکت‌ها گاهی خیلی عجیب و پر از کلمه‌های جدیده. 

بیا یه خبر واقعی رو با هم به انگلیسیِ ساده بخونیم:

Elon Musk has a big space company. The company makes rockets. People buy parts of the company. These are shares (سهام). 

Today, the news says: SpaceX shares sink after first earnings report reveals huge AI spending plans (ارزش سهام اسپیس‌ایکس بعد از اولین گزارش درآمد و مشخص شدن برنامه‌های بزرگ برای خرج کردن روی هوش مصنوعی، افت کرد).

بررسی این خبر توی سه تا لایه:

🟢 نکته‌ی اصلی:
کلمه‌ی sink توی این خبر معنیِ غرق‌شدن نمی‌ده؛ یعنی قیمت یا ارزشِ یه چیزی پایین اومده (افت کردن).

🟡 توی بافت:
The price can sink when people are not happy (وقتی مردم راضی نیستن، قیمت می‌تونه افت کنه).

🔴 یه نکته‌ی کوچیک مرتبط:
توی خبرها به‌جای sink ممکنه کلمه‌ی fall رو هم ببینی که اونم دقیقاً همین معنیِ پایین اومدن رو میده.

این جمله‌ی خبری رو توی ذهنه‌ت نگه دار و ببین توی خبرهای اقتصادی دیگه هم می‌تونی کلمه‌ی sink رو پیدا کنی یا نه. این پست رو واسه دوستت که عاشق اخبار دنیای تکنولوژی و فضاست بفرست!
[۲۰۲۶-۰۸-۰۶ ۱۱:۱۶] In English: 🎙️ یه کلمه‌ای که خیلیا تو تلفظش گیر می‌کنن! گوش کن: brother... brother (برادر).

تکرار کن: brother. 

حالا این جمله رو بلند بگو: 
"My brother plays football."

خیلیا به جای صدای «ث» وسطش، اشتباهی «ت» یا «د» میگن؛ حواست باشه نوک زبونت بین دندون‌هات باشه. 

این جمله رو امشب توی خونه بلند برای خودت تکرار کن و ببین چقدر راحت تو دهنت می‌چرخه!
[۲۰۲۶-۰۸-۰۶ ۱۱:۳۹] In English: یادته گفتیم چجوری یه کار خیلی راحت رو با کیک مقایسه می‌کنن؟ 🍰 بیا ببینیم هنوز اون اصطلاح یادت مونده یا نه!

Sara looks at her messy room and sighs. There are clothes everywhere. 

She wants to clean it fast. 

She says, "Cleaning my room is a piece of cake (مثل آب خوردن / خیلی آسونه)."

🟢 حواست باشه! خیلیا اشتباهی می‌گن: "Cleaning is a piece of water." این کاملاً غلطه! 

به نظرت کدوم جمله درسته؟ جمله‌ی زیر رو نگاه کن و حدس بزن اشکالش کجاست:

"My English homework is an easy piece of cake."

جمله‌ی درست اینه: "My English homework is a piece of cake." وقتی از این اصطلاح استفاده می‌کنی، کلمه‌ی an یا easy رو قبلش نیار؛ خودِ اصطلاح یعنی خیلی آسونه!
[۲۰۲۶-۰۸-۰۶ ۱۶:۳۶] In English: دکترا دارن با روبات کار می‌کنن! 🤖 باورتون می‌شه؟ جراح‌ها از راه دور دارن دو تا روباتِ شبیه به آدم رو کنترل می‌کنن.

توی دنیای Tech Life (زندگیِ تکنولوژی) هر روز چیزهای عجیبی می‌بینیم. بیا این خبر واقعی رو با هم به انگلیسیِ ساده بخونیم:

🟢 دو تا روباتِ شبیه به آدم توی اتاق عمل هستن.
Two human-like robots are in an operating theatre (اتاق عمل). 

🟡 دکترها توی خونه یا جای دیگه نشستن و دارن با دست‌هاشون این روبات‌ها رو تکون میدن.
Doctors remotely control (از راه دور کنترل می‌کنن) the robots to help people.

🔴 کلمه‌ی remotely یعنی از راه دور، بدون اینکه لازم باشه پات رو بذاری اونجا. مثلاً کار کردن از خونه رو می‌گن کارِ ریموت!

امروز یه بار این جمله رو بلند تکرار کن و ببین تکنولوژی چقدر جلو رفته. این پست رو برای یه دوستِ اهلِ تکنولوژی بفرست تا اونم بخونه!
[۲۰۲۶-۰۸-۰۷ ۰۳:۴۹] In English: [ Poll : کدوم کلمه برای کامل کردن این جمله درسته؟
"I always ___ my homework after school." ]
- do
- make
- take
- give
[۲۰۲۶-۰۸-۰۷ ۰۹:۴۳] In English: چند وقت پیش درباره‌ی brother (برادر) گفتیم؛ یادت مونده چجوری توی جمله استفاده می‌شد؟ 🤔

بیا یه جمله‌ی پر از اشتباه رو ببینیم که خیلی از زبان‌آموزا به فارسی فکر می‌کنن و این‌جوری می‌نویسن:

"My brother he is playing football."

به نظرت کجاش اشتباهه؟ 🤔

اشتباهش اینه که هم از اسم (brother) استفاده کردیم و هم از ضمیر (he). تو انگلیسی یا اسم رو میاریم یا ضمیر رو. 

جمله‌ی درست اینه:
"My brother is playing football." (برادرم داره فوتبال بازی می‌کنه.)

حالا این جمله‌ی درست رو بلند برای خودت تکرار کن تا توی ذهنت بمونه.
[۲۰۲۶-۰۸-۰۷ ۱۰:۲۵] In English: روبات‌ها دارن توی بازی‌های ویدیویی قهرمان می‌شن! 🤖 باورتون می‌شه؟ رایانه‌ها حالا مثل انسان‌ها بازی می‌کنن.

توی دنیای Tech Now (تکنولوژیِ امروز) هر روز خبرهای عجیبی می‌شنویم. بیایید یه خبر جالب رو با هم به انگلیسیِ ساده بخونیم:

A new computer program plays a popular video game. It learns very fast. Now, the computer wins against professional human players in Paris. 

دنیای بازی‌ها هر روز جذاب‌تر می‌شه.

🟢 نکته‌ی اصلی:
کلمه‌ی computer (رایانه / کامپیوتر) یعنی دستگاهی که کارهای سخت رو برامون انجام میده.

🟡 توی بافت:
My computer is old, but it works fine (رایانه‌م قدیمیه، ولی خوب کار می‌کنه).

🔴 یه نکته‌ی کوچیک:
توی انگلیسیِ روزمره، خیلی‌وقت‌ها به جای کلمه‌ی کاملِ computer، فقط می‌گیم PC.

حالا به این فکر کن: دوست داری با یه روبات بازی کنی یا با یه دوست واقعی؟ 🤔 این پست رو برای کسی بفرست که عاشق بازی‌های ویدیوییه!
[۲۰۲۶-۰۸-۰۸ ۰۹:۲۱] In English: سلام بچه‌ها! یادتونه از کجا شروع کردیم؟ 

چند وقت پیش با هم رفتیم سراغ family (خانواده) و کلمه‌های ساده‌ای مثل sister (خواهر) و brother (برادر) رو یاد گرفتیم. 

بعدش دیدیم موقع صحبت کردن چطور بگیم یه چیزی جایی هست یا نیست:
There is a book on the desk (یک کتاب روی میز هست).
There are two apples in the bag (دو تا سیب توی کیف هست).

کلی هم تمرین کردیم تا بفهمیم تفاوت do (انجام دادن) و make (درست کردن/ساختن) توی جمله‌های روزمره چیه.

حالا توی این مسیر، به خودمون ثابت کردیم که یادگیری انگلیسی اون‌قدرها هم سخت نیست؛ فقط یه کم تمرین می‌خواد.

حالا تو به من بگو: از بین چیزهایی که تا حالا یاد گرفتی، کدوم یکی برات از همه کاربردی‌تر بوده؟ این رو برای خودت مرور کن و حتماً این پست رو واسه اون دوستی که تازه میخواد زبان رو شروع کنه، فوروارد کن!
[۲۰۲۶-۰۸-۰۸ ۰۹:۵۷] In English: چند روز دیگه آسمون یه سورپرایز جالب داره! 🌙☀️

Look at the sky on Wednesday evening. Many people are ready for a special show. The moon moves in front of the sun. But it does not hide the sun completely. 

This is a partial solar eclipse (خورشیدگرفتگی جزئی). 

🟢 What can we see during the partial solar eclipse? (چی می‌تونیم توی خورشیدگرفتگی جزئی ببینیم؟)
We can see a dark shape on the sun. It looks like a cookie with a bite out of it! 🍪

🟡 People go outside with special glasses. They want to watch the sun safely. 
"Don't look at the sun without glasses!" a teacher says. 

🔴 Safety first! 
Never look at the sun with your naked eyes (چشم غیرمسلح / بدون عینک). Use special glasses to protect your eyes. 

حالا فکر کن فردا عصر قراره این پدیده رو ببینی؛ به نظرت هوا چقدر تاریک می‌شه؟ 

این پست رو برای کسی بفرست که عاشق دیدن آسمون و ستاره‌هاست! ✨
[۲۰۲۶-۰۸-۰۸ ۱۵:۱۸] In English: خبرهای مهم دنیا رو می‌تونیم با جمله‌های خیلی ساده بخونیم! 📰 بیا ببینیم امروز سیاست آمریکا چه خبره.

A big man gets a new job today. 

The boss of the country chooses a helper for the law. 

Many people talk about this for a long time. 

Finally, one man makes the final choice. Now, the new worker starts his big job.

🟢 نکته‌ی اصلی:
وقتی یه نفر کار مهمی رو می‌گیره، می‌گیم اون تأیید شد (confirmed). 

🟡 توی بافت:
He is confirmed (تأیید شد) for the big job.

🔴 یه نکته‌ی کوچیک:
وقتی می‌خوایم بگیم کسی کار جدیدی رو شروع می‌کنه، از کلمه‌ی رایج start (شروع کردن) استفاده می‌کنیم. مثل: He starts work today.

به نظرت خوندن خبرهای انگلیسی چقدر می‌تونه به یادگیریِ کلمه‌های جدید کمک کنه؟ می‌تونی این پست رو برای دوستی که تازه انگلیسی رو شروع کرده بفرستی تا اونم بخونه.
[۲۰۲۶-۰۸-۰۹ ۰۹:۲۳] In English: مادربزرگت رو چجوری صدا می‌زنی؟ 👵 بیا یک کلمه‌ی خیلی صمیمی یاد بگیریم که توی همه‌ی داستان‌ها هست.

توی ادامه‌ی بحث‌های این هفته درباره‌ی خانواده، امروز می‌ریم سراغ قدیمی‌ترین و مهربون‌ترین عضو خونه.

🟢 grandmother (مادربزرگ)

🟡 She drinks hot tea with her grandmother every Friday afternoon. (اون هر جمعه بعدازظهر با مادربزرگش چای داغ می‌خوره.)

🔴 حواست باشه، توی صحبت‌های روزمره و خودمانی، انگلیسی‌ها به جای این کلمه‌ی طولانی از کلمه‌ی کوتاه‌ترِ grandma (مامان‌بزرگ) استفاده می‌کنن.

امروز وقتی با خونواده نشستی، سعی کن یه جمله‌ی ساده با این کلمه برای خودت بسازی و بلند بگیش. اینجوری توی ذهنت می‌مونه!
[۲۰۲۶-۰۸-۰۹ ۱۵:۲۰] In English: آسمون تابستون یه مهمون خیلی خاص داره! ✨ بیا ببینیم چطور می‌تونیم یه خبر جذاب رو با جمله‌های خیلی ساده بخونیم.

August 12 is a big night for the sky. 

Many people wait for this day. 

They want to look up and watch the stars. 

It is the best day of the year for stargazing (بهترین روز سال برای ستاره‌گردی و تماشای آسمون).

🟢 نکته‌ی اصلی
عبارت stargazing یعنی تماشای ستاره‌ها و آسمون شب. از دو تا کلمه‌ی ساده ساخته شده: star (ستاره) و gaze (خیره نگاه کردن).

🟡 توی بافت
I like stargazing with my friend in the garden. 
(من دوست دارم با دوستم توی باغ به ستاره‌ها نگاه کنم.)

🔴 یه نکته‌ی کوچیک
وقتی می‌خوایم بگیم امشب آسمون چه شکلیه، خیلی راحت می‌گیم: The night is clear (امشب آسمون صافه).

فردا شب که رفتی توی حیاط یا بالکن، یه لحظه سرت رو بالا بیار و به آسمون نگاه کن. این جمله رو هم یادت نره برای خودت زمزمه کنی!
[۲۰۲۶-۰۸-۰۹ ۱۶:۴۲] In English: زمین کشاورزی قدیمی پیر مرده؟ نه بابا، قراره یه جنگل و خونه‌ی حیوانات بشه! 🦊 بیا ببینیم چطور می‌شه یه خبر واقعی رو با جمله‌های خیلی ساده خوند.

A old farm in a quiet town is getting a big change today. 

Two people take their family farm. They want to make it a safe home for birds and small animals. 

This work takes thirty years. They plant many trees and make water places for wild animals. 

🟢 Couple turning inherited farm into nature site (زوجی که دارن زمین کشاورزی به ارث رسیده رو به زیستگاه طبیعی تبدیل می‌کنن).

🟡 They work hard on the land. (اون‌ها روی زمین سخت کار می‌کنن.)

🔴 وقتی می‌خوایم بگیم چیزی رو از بزرگترها یا خانواده‌مون بعد از فوت‌شون داریم، از کلمه‌ی inherited (به ارث رسیده) استفاده می‌کنیم. یه کلمه‌ی خیلی کاربردی برای داستان‌ها و خبرهاست.

این خبر رو برای کسی بفرست که عاشق طبیعت و حیوون‌هاست! 🌲
[۲۰۲۶-۰۸-۱۰ ۰۹:۴۹] In English: پدربزرگت چقدر داستان قدیمی بلده؟ 👴 بیا یک کلمه‌ی پرکاربرد دیگه یاد بگیریم که روز توی هر داستانی پیدا می‌شه.

توی ادامه‌ی بحث‌های این هفته درباره‌ی خانواده، امروز می‌ریم سراغ باسوادترین و صمیمی‌ترین مرد خونه.

"Look at this old photo," says Leo. "That is my grandfather (پدربزرگ)."

🟢 نکته‌ی اصلی: وقتی می‌خوایم به پدرِ پدر یا پدرِ مادر اشاره کنیم، از این کلمه استفاده می‌کنیم. توی حرف زدن روزمره خیلی وقت‌ها کوتاهش می‌کنن و می‌گن grandpa.

🟡 توی بافت:
My grandfather drinks tea on the porch every afternoon (پدربزرگ من هر بعدازظهر روی ایوان چای می‌نوشه).

🔴 یه نکته‌ی کوچیک: کلمه‌ی grandma (مادربزرگ) رو که چند روز پیش دیدیم، یادت نره؛ این دوتا همیشه توی عکسای قدیمی کنار همن.

فکر کن پدربزرگت الان چه داستانی از گذشته برات تعریف می‌کنه؟ این کلمه رو امروز توی یه جمله‌ی ساده‌ی انگلیسی برای خودت تکرار کن.
[۲۰۲۶-۰۸-۱۰ ۱۰:۳۱] In English: یادته درباره‌ی خانواده حرف می‌زدیم؟ 👵 بیا ببینیم این جمله‌ی انگلیسیِ پایین چقدر برات آشناست و چطور می‌تونیم اشتباه رایجش رو درست کنیم.

مادربزرگ من هر روز صبح چای می‌خوره (My grandmother drinks tea every morning).

به نظرت کدوم یکی از این جمله‌ها درست‌تره و کدوم یکی اشتباه رایج ما فارسی‌زبان‌هاست؟

جمله‌ی اول:
My grandmother drink tea.

جمله‌ی دوم:
My grandmother drinks tea.

جمله‌ی دوم درسته! چون وقتی داریم درباره‌ی مادربزرگ (سوم شخص مفرد) حرف می‌زنیم، فعل حتماً باید یه دونه s بگیره (drinks). اشتباه رایج ما اینه که یادمون می‌ره این s رو بذاریم.

این نکته‌ی کوچیک رو امشب روی یه کاغذ بنویس و به یه نفر نشون بده تا توی ذهنت بمونه.
[۲۰۲۶-۰۸-۱۰ ۱۵:۳۳] In English: لوله آب شهر خرابه و داره آب هدر می‌ره، ولی شهروندان جریمه می‌شن اگه به گل‌هاشون آب بدن! 🚰 منطقیه به نظرتون؟

بیینیم این خبر واقعی رو چطور میشه با جمله‌های خیلی ساده خوند:

Linda says: "I called the water company in June. The pipe is broken and water is going out every day."

She is angry because the city stops people from using a hosepipe (شلنگ آب) in the garden. But the city's own pipe is broken for months!

🟢 نکته‌ی اصلی:
وقتی می‌خوایم بگیم یه چیزی از گذشته تا حالا خراب بوده و هنوزم خرابه، از این ساختار استفاده می‌کنیم:
"It has been broken since June" (از ماه ژوئن تا حالا خرابه).

🟡 توی بافت:
The water pipe has been broken since June.

🔴 یه نکته‌ی کوچیک:
کلمه‌ی leak (نشتی / چکه کردن) توی اخبار خیلی برای لوله‌های آب یا گاز استفاده می‌شه. مثلاً وقتی آب از یه جایی چکه می‌کنه، می‌گویند: "There is a water leak."

این خبر رو برای کسی بفرست که عاشق گل و گیاهه و همیشه نگران کم‌آبیه! 🌱
[۲۰۲۶-۰۸-۱۱ ۰۹:۲۹] In English: دیوار گچی همیشه یه جای کارش لنگ می‌زنه، مگه نه؟ 🧱 بیا ببینیم این جمله‌ی انگلیسیِ پایین کجاش ایراد داره.

اینجا رو ببین:

The cat lost it's toy under the sofa.

به نظرت این جمله درسته یا غلط؟ 🤔

این جمله غلطه! ❌

جواب درست:
The cat lost its toy under the sofa. (گربه‌اش اسباب‌بازیش رو زیر مبل گم کرد.)

نکته:
🟢 کلمه‌ی its (بدون آپاستروف) نشون میده یه چیزی مالِ یه شیء یا حیوونه (مالِ خودش).
🟡 ولی it's مخففِ it is یا it has هست (یعنی «هست» یا «دارد»). هر وقت خواستی جای اینا رو عوض کنی، جمله‌ت اشتباه از آب درمیاد!

برای یه دوستت که مدام این دو تا رو اشتباه می‌نویسه، فورواردش کن.
[۲۰۲۶-۰۸-۱۱ ۱۰:۱۱] In English: پدربزرگت همیشه توی جیبش شکلات داره یا فقط مال ما اینطوریه؟ 🍬 بیا یه بار دیگه همون کلمه‌ی خانواده رو که چند روز پیش دیدیم، با هم مرور کنیم تا خوب یادت بمونه.

Remember this sentence?

My grandfather (پدربزرگ) tells the best stories by the fireplace.

به نظرت اگه بخوایم بگیم «پدربزرگ من هر روز عصر روزنامه می‌خونه»، کدوم جمله درسته و کدوم یکی غلطه؟ 🤔

جمله‌ی اول:
My grandfather read the newspaper every evening.

جمله‌ی دوم:
My grandfather reads the newspaper every evening.

به نظرت کدومش اشتباهه و چرا؟ (تو ذهنت بهش فکر کن!)

جمله‌ی اول غلطه! چون صحبت از هر روزه (حال ساده)، برای «پدربزرگ» که یک نفره (He)، باید به فعل s بدیم: reads.

اینم از مرور امروز. امشب از این کلمه توی یه جمله‌ی ساده برای خودت استفاده کن!
[۲۰۲۶-۰۸-۱۱ ۱۵:۳۲] In English: بزهای کوچولو رفتن توی یه مزرعه‌ی بزرگ تا نسلشون حفظ بشه! 🐐 بیا ببینیم این خبر جالب رو چطور می‌تونیم با انگلیسیِ ساده بخونیم.

دو تا بز شش‌ماهه توی جزیره یه خونه‌ی جدید پیدا کردن. فرماندار هم بهشون خوش‌آمد گفت!

اینجوری می‌گیم:

The baby goats are in the green field. The Governor says hello to them. They join a conservation herd (به یه گله‌ی حفاظتی ملحق می‌شن).

🟢 نکته‌ی اصلی:
وقتی می‌خوای بگی یه حیوون یا آدم به یک گروه اضافه می‌شه، از فعل join استفاده کن.

🟡 توی بافت:
The little animal wants to join the group. (این حیوون کوچولو می‌خواد به گروه ملحق بشه.)

🔴 یه نکته‌ی کوچیک:
حواست باشه قبل از اسمِ گروه‌ها معمولاً a یا the می‌ذاریم؛ مثلاً a conservation herd (یه گله‌ی حفاظتی). توی خبرها گاهی این کلمه‌ها رو برمی‌دارن، ولی تو همیشه با a یا the استفاده کن تا درست باشه.

به این فکر کن: تو دوست داری به چه جور گروهی ملحق بشی؟ 🤔 این جمله‌ی ساده رو توی ذهنت با انگلیسی مرور کن.
[۲۰۲۶-۰۸-۱۲ ۰۹:۵۲] In English: [ Photo ]

هوای ابری و دلگیر امروز بهانه‌ی خوبی شد برای یه اصطلاح باحال! 🌧️ بیا ببینیم چرا انگلیسی‌ها وقتی حالشون خوب نیست، یاد آب‌وهوا می‌افتن.

Tom: "Hey, can you come to work today?"
Sam: "No, sorry. I'm under the weather (حالم خوب نیست/پخشم)."
Tom: "Oh! Rest and drink some tea."

حالا تو بهمون بگو، آخرین باری که کی حالتش under the weather بود رو یادت میاد؟ این پست رو بفرست برای اون دوستی که همیشه این موقع‌ها سرما می‌خوره!
[۲۰۲۶-۰۸-۱۳ ۱۹:۴۳] In English: 📢 یادت باشه @InEnglish_Tel رو فقط اینجا دنبال نکن!

این کانال روی چند پلتفرم دیگه هم با همین محتوا فعاله — هرکدوم که برات راحت‌تره:
🔹 تلگرام: همین‌جا (@InEnglish_Tel)
🔹 بله: @InEnglish
🔹 ایتا: @InEnglish

اگه یکی از دوستات فقط تو یکی از این پلتفرم‌هاست، این پست رو براش فوروارد کن 🙌
[۲۰۲۶-۰۸-۱۴ ۰۹:۵۱] In English: [ Poll : خیلیا این اصطلاح کاربردی رو اشتباه معنی می‌کنن! اگه امروز یکم بی‌حال باشی و حالت خوب نباشه، چطور توی جمله اینو می‌گی؟

"I'm feeling a bit ________ today." ]
- under the weather
- in the weather
- under the rain
- on the weather




