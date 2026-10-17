---
name: verify-delivery
description: 交付物验收技能——交付文案的写作判据、AI 味词表、输出语言、图与 HTML 出口、改动说明格式。写简历条目、交付说明或复核交付文案时读这一份。
---

# verify-delivery —— 交付验收（文案 · 语言 · 图 · 改动说明）

> 用法：交付前逐节过一遍。能机械判的跑 helper，判不了的按本节问句逐条答，答不上就重写。
> 真源关系：这五件事的唯一真源是本技能；`AGENTS.md` 与 `CODING_STANDARDS.md` 只放指针、不复制本节内容（两份原文必然漂移）。
> helper：`skills/verify-delivery/check_copy.py`（只用标准库，仓库根下运行），判据表在它里面，本节写怎么用。

## 1 文案判据（F08）

格式只有一种：**用什么解决了什么问题**。逐条过四个问句：

| 问句 | 不合格的样子 | 处置 |
| --- | --- | --- |
| 这条说的是哪个真问题？ | 泛泛的「提升了系统性能」 | 换成具体故障或具体代价 |
| 「用什么」写出来了吗？ | 只有结果、没有手段 | 补动作（引入 / 重构 / 拆分 / 接入 / 降级…） |
| 有意思吗？ | 换个人、换家公司也成立 | 删掉，别凑数 |
| 数字有出处吗？ | 凭印象写的百分比 | 有就摆出处，没有就不写数字 |

长度：一条一行；技术名词堆叠成串就是「太技术化」，拆成一句人话。

机械判据（可判的那部分）：

```bash
python3 skills/verify-delivery/check_copy.py <文件>        # C1 西文成句 / C4 量化无数字 / C5 缺手段
```

## 2 AI 味词表（F08）

- 词表唯一真源是 helper 里的 `FLAVOR_WORDS`（本节不复述，防两份漂移）；判据 C2 命中即改写。
- 命中后不是换同义词：回到 §1，把它换成「什么问题 + 什么手段 + 什么结果」。
- 括号注释（判据 C3）不用：要解释就写成第二句。
- 加词：往 `FLAVOR_WORDS` 加一条再跑 `--selftest`；自检里有「词表每条都真的会被认出来」，空转的词会红。

```bash
python3 skills/verify-delivery/check_copy.py <文件>
```

## 3 中文（F10）

- 语言约束的真源是 `AGENTS.md` §开发规范（全部使用简体中文）；本节只写**怎么判定**，不复述那条规则。
- 判据 C1：一行里 3 个及以上西文词（不在 helper 的 `ALLOWED_TERMS` 白名单）就是「成句西文」→ 改成中文句子；白名单里的专业名词保留原文。
- 判定命令同 §1；退出码非 0 就是不合口径，它逐条点名 行号 + 判据 + 原文。

## 4 图 · HTML 出口（F09）

- 结论需要人「一眼看懂结构 / 对比 / 分布」时，出口是一份**单文件 HTML**：内联 CSS、零外链、零构建步骤。
- 跑：直接写文件（例如 `var/reports/<主题>.html`），路径写在回报首行，双击即可看。
- 分工：命令与结论留在 markdown；结构、对比、模块地图给 HTML。
- 现成样例读它的排版约定（不复制源码、不手改生成物）：`docs/audit/MODULE-AUDIT.html`。
- 交付前三问：双击能打开吗（无外链 / 无 CDN）？图例与中文标注在正文里吗？数据口径（分子分母）写了吗？

## 5 改动说明格式（F16）

交付物之后固定给四栏；`--kind changelog` 判字段在不在（G1）与改动栏有没有引证（G2）：

| 栏 | 写什么 |
| --- | --- |
| 改动： | `文件:行号` + 一句为什么 |
| 影响面： | 被波及的调用点 / 文档 / 契约；没有写「无」 |
| 未验证： | 没跑到的部分；没有写「无」 |
| 证据： | 可复跑命令 + 原始输出读数 |

```bash
python3 skills/verify-delivery/check_copy.py <改动说明文件> --kind changelog
```

- 引证必须带 `文件:行号`；被引用的文件改了就要重锚，行号漂移即失效。
- 命令要能原样复跑：不写「跑通即可」「无报错」。

## 自证（先红后绿）

```bash
python3 skills/verify-delivery/check_copy.py --selftest
```

自检读的是 helper 自带的样本：词表不空转、每条判据各有一个必红的坏样本、合规样本必绿、
改动说明缺栏与缺引证各判一次。拿真实样例复核时：

```bash
mkdir -p /tmp/verify-delivery && cat > /tmp/verify-delivery/bad.md <<"EOF"
- 赋能业务闭环，打造一站式面试平台
- 优化系统性能（响应更快）
- 重构 interview_engine 与 QuestionService 的读写路径，修正 restore 写库
EOF
python3 skills/verify-delivery/check_copy.py /tmp/verify-delivery/bad.md; echo "EXIT=$?"
```

上面三行每行都会被点名（C2/C3/C5、C4/C5、C1），退出码 1。
