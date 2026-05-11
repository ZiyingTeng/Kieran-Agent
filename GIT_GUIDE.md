# Git 使用指南 —— Chatjoy2.0 项目

## 一、核心概念（先理解这三个）

```
本地代码  ──git add──▶  暂存区  ──git commit──▶  本地仓库  ──git push──▶  GitHub
```

- **暂存区**：你选中"准备提交"的文件放在这里
- **本地仓库**：commit 之后，改动被记录在你电脑本地的历史里
- **GitHub**：push 之后，改动上传到云端，别人可以看到

每次改完代码，标准流程是：`add → commit → push`，三步缺一不可。

---

## 二、日常更新代码（最常用）

### 查看当前状态（先看清楚再操作）

```bash
git status
```

输出说明：
- `modified: xxx.py` —— 这个文件被改动了，还没 add
- `new file: xxx.py` —— 新文件，还没 add
- `deleted: xxx.py` —— 文件被删了，还没 add
- 绿色 = 已 add（在暂存区），红色 = 还没 add

---

### 标准三步提交流程

**第一步：add（选择要提交的文件）**

```bash
# 添加某个具体文件（推荐，精确）
git add app.py
git add llm_service.py database.py   # 同时添加多个

# 添加当前目录所有改动（偷懒用，但要小心别把不该提交的文件加进去）
git add .
```

**第二步：commit（写一条说明，记录做了什么）**

```bash
git commit -m "feat: 添加用户黑名单功能"
```

commit 消息格式建议：
| 前缀 | 含义 | 例子 |
|------|------|------|
| `feat:` | 新功能 | `feat: 添加群聊背景设置` |
| `fix:` | 修 bug | `fix: 修复消息重复发送问题` |
| `chore:` | 杂项维护 | `chore: 更新依赖版本` |
| `refactor:` | 重构代码 | `refactor: 简化 session 管理逻辑` |

**第三步：push（上传到 GitHub）**

```bash
git push
```

推送成功后，打开 GitHub 仓库页面就能看到最新代码。

---

### 完整例子

```bash
# 改完 app.py 和 llm_service.py 之后

git status                          # 确认哪些文件改了
git add app.py llm_service.py       # 选中这两个文件
git status                          # 再确认一下，应该变绿了
git commit -m "fix: 修复 LTM 写入过滤逻辑"
git push
```

---

## 三、查看历史记录

```bash
# 查看提交历史（每条一行，简洁）
git log --oneline

# 查看最近 5 条
git log --oneline -5

# 查看某个文件的改动历史
git log --oneline app.py

# 查看某次提交具体改了什么（把 abc1234 换成实际 commit ID）
git show abc1234
```

输出示例：
```
a047e52 chore: exclude release archives from version control
63f7a93 feat: initial commit
```
左边那串字母数字是 commit ID，右边是你写的说明。

---

## 四、撤销操作

### 还没 add，想撤销文件改动

```bash
# 把 app.py 恢复到上次 commit 的状态（改动会丢失！）
git restore app.py
```

### 已经 add，想取消暂存（文件改动保留）

```bash
git restore --staged app.py
```

### 已经 commit，想撤销最后一次提交（改动保留，退回到 add 之前）

```bash
git reset HEAD~1
```

### 已经 push 到 GitHub，想撤销（谨慎！）

不建议直接撤销已推送的 commit，更好的做法是再提交一次修正：

```bash
# 改好代码之后
git add xxx.py
git commit -m "fix: 修正上次提交的问题"
git push
```

---

## 五、分支管理（进阶，适合功能开发）

分支的用途：开发新功能时不影响主线代码，开发完测试没问题再合并。

```bash
# 查看当前所有分支（* 号是当前分支）
git branch

# 创建并切换到新分支
git checkout -b feature/group-background

# 切回主分支
git checkout main

# 把功能分支合并到 main
git checkout main
git merge feature/group-background

# 删除已合并的分支
git branch -d feature/group-background
```

**日常小改动**不需要建分支，直接在 main 上改就行。建分支适合：开发周期超过 1 天、或者改动较大风险较高的功能。

---

## 六、从 GitHub 同步代码（多台机器或协作时用）

```bash
# 拉取 GitHub 上的最新代码，合并到本地
git pull

# 如果提示冲突，手动解决冲突后：
git add <冲突文件>
git commit -m "fix: 解决合并冲突"
```

---

## 七、.gitignore —— 哪些文件不上传

`.gitignore` 文件列出了"不需要上传到 GitHub 的文件"，本项目已配置好：

- `.env` —— 密码、API Key（绝对不能上传）
- `*.tar.gz` —— 打包文件（体积大）
- `logs/` —— 运行日志
- `__pycache__/` —— Python 编译缓存
- `node_modules/` —— 前端依赖包

**如果你新增了不想上传的文件**，编辑 `.gitignore`，加一行：

```
# 比如不想上传 data/ 目录
data/

# 不想上传某个特定文件
secret_config.json
```

加完之后记得提交 `.gitignore` 本身：
```bash
git add .gitignore
git commit -m "chore: 更新 .gitignore"
git push
```

---

## 八、从 GitHub 上删除已上传的文件

文件已经 push 上去了，光改 `.gitignore` 没用，需要用 `git rm --cached` 告诉 git 停止跟踪它。

**只删 GitHub 上的，本地文件保留：**

```bash
git rm --cached 文件名
git commit -m "chore: 移除 xxx 文件"
git push
```

**同时删掉本地文件：**

```bash
git rm 文件名
git commit -m "chore: 删除 xxx 文件"
git push
```

**删整个目录：**

```bash
git rm --cached -r 目录名/
git commit -m "chore: 移除 xxx 目录"
git push
```

---

## 九、GitHub 仓库页面说明

打开 `https://github.com/ZiyingTeng/Chatjoy2.0`：

| 区域 | 说明 |
|------|------|
| **Code 标签** | 浏览当前代码，默认显示 main 分支 |
| **Commits** | 点击可看所有历史提交记录，相当于 `git log` |
| **x commits** | 右侧文件列表上方，点击查看提交数和历史 |
| **Branches** | 查看所有分支 |
| **Settings → Danger Zone** | 可以设置仓库公开/私有、删除仓库 |
| **Settings → Collaborators** | 添加协作者（给别人写入权限） |

---

## 十、SSH Key 说明

SSH Key 是你的机器和 GitHub 之间的"通行证"，已经配置好了：

- 私钥：`~/.ssh/id_ed25519`（留在你的电脑上，不能泄露）
- 公钥：`~/.ssh/id_ed25519.pub`（已上传到 GitHub）

只要在同一台机器上操作，`git push` 不需要输密码。如果换了新机器，需要重新生成 SSH Key 并上传到 GitHub（重复本次配置流程）。

---

## 十一、常见问题

**Q: push 提示 "Everything up-to-date"**
A: 没有新的 commit，不需要推送。检查是否忘记 `git commit` 了。

**Q: push 提示 "Updates were rejected"**
A: GitHub 上有你本地没有的新 commit（比如在另一台机器提交过）。先 `git pull`，再 `git push`。

**Q: 不小心把大文件 add 进去了怎么办**
A: 在 commit 之前执行 `git restore --staged <大文件名>`，然后把文件加进 `.gitignore`。

**Q: 想看某个文件现在和上次提交相比改了什么**
A: `git diff app.py`

---

## 十二、快速参考卡

```bash
git status                    # 查看当前状态（最常用）
git add <文件>                 # 添加到暂存区
git commit -m "说明"           # 提交到本地仓库
git push                      # 推送到 GitHub
git pull                      # 从 GitHub 拉取最新代码
git log --oneline -10         # 查看最近 10 条历史
git diff <文件>                # 查看文件改动内容
git restore <文件>             # 撤销未 add 的改动
git restore --staged <文件>    # 取消 add（保留改动）
```
