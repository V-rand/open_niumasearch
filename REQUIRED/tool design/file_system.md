# 轻量文件与命令工具层设计说明（供 Codex 编码）

## 1. 目标

本文档用于指导 Codex 为 Deep Research Agent 实现一套**轻量、可控、可审计**的本地工具层。
先实现必需的，可选的功能先不开发
设计目标不是“给 Agent 尽可能多的工具”，而是：

1. 提供最少但足够的文件增删改查能力。
2. 提供一个受控的命令执行出口，用于调用 bash 与基础命令。
3. 让关键状态变更尽量走结构化工具，而不是散落在 shell 命令中。
4. 让工具层容易实现、容易记录日志、容易限制权限。
5. 底线是让agent拥有对.md文件进行创建，增删改查的能力
本文档默认：

- 不使用 MCP。
- 不使用 LangChain 等 Agent 框架。
- 允许在本地 Python Runtime 中实现工具注册与调度。
- 允许复用系统基础命令与少量 Python 标准库/轻量依赖。

---

## 2. 总体原则

### 2.1 底层基础设施直接复用，项目语义不要外包给 shell

底层基础设施可以直接复用成熟组件：

- Python 标准库：`pathlib`、`subprocess`、`shutil`
- 系统命令：GNU coreutils
- 文本搜索：`ripgrep (rg)`
- 文件查找：`fd`
- JSON 处理：`jq`（可选）

但 Deep Research 项目的关键对象操作，不应直接依赖 shell 拼接实现，例如：

- research todo 状态迁移
- checkpoint 生成
- note/evidence 写入
- runtime log 更新

这些应由上层项目工具实现。本文档只定义**底层文件与命令工具层**。

### 2.2 Agent 默认走结构化工具，不默认走 shell

shell 不是主业务接口，而是基础设施层与兜底出口。

默认顺序：

1. 能用结构化工具完成的，优先用结构化工具。
2. 需要通用系统能力时，才用 `run_command`。
3. 若涉及项目核心对象状态，禁止直接让 agent 用 shell 修改状态文件。

### 2.3 工具数量严格控制

V1 不应给 Agent 暴露超过 8 个底层工具。

推荐暴露 **7 个核心工具 + 1 个兜底工具**。

如果实现资源有限，也可以先只实现前 6 个，后续再补。

---

## 3. 推荐底层依赖

## 3.1 必选依赖

### Python 标准库

1. `pathlib`
   - 用于路径拼接、目录遍历、文件存在性检查、文件读写封装。
   - 采用面向对象的路径接口，适合作为本地工具层的路径抽象。

2. `subprocess`
   - 用于运行受控外部命令。
   - 必须替代 `os.system` 这类不利于捕获输出与返回码的方式。

3. `shutil`
   - 用于复制、移动、递归删除、目录树处理等高层文件操作。

### 系统命令

1. GNU coreutils
   - 作为基础文件/文本命令集合存在。
   - 主要通过 `run_command` 间接使用。

2. `ripgrep (rg)`
   - 用于递归文本搜索。
   - 默认行为适合代码与文档工作区搜索。

3. `fd`
   - 用于文件/目录快速查找。
   - 比直接暴露 `find` 更适合 Agent 使用。

## 3.2 可选依赖

1. `jq`
   - 用于命令行级 JSON 过滤与调试。
   - 可选，不应成为项目主业务逻辑依赖。

2. `Send2Trash`
   - 用于安全删除。
   - 推荐优先于永久删除，尤其适合 agent 首版。

## 3.3 当前不建议引入

1. 不建议引入大而全的 Agent 工具框架。
2. 不建议引入十几个零散的第三方文件工具包。
3. 不建议引入“所有操作都走 shell”的设计。
4. 不建议把 Plumbum 作为首版必需依赖；如果开发体验需要，后续可选加入。

---

## 4. 暴露给 Agent 的最小工具集合

以下是推荐给 Agent 的最小工具集合。

目标：既覆盖文件增删改查，也覆盖文本搜索和命令执行，但不把工具数量做大。

---

## 4.1 `fs_list`

### 职责

列出目录内容或文件树。

### 主要用途

- 查看某个目录下有哪些文件
- 查看 research/writing 目录结构
- 检查工具执行后是否生成了预期文件

### 推荐参数

- `path: str`
- `recursive: bool = false`
- `max_depth: int | null = null`
- `include_hidden: bool = false`
- `kind: "all" | "file" | "dir" = "all"`

### 返回

- 条目列表（路径、类型、大小、修改时间）

### 实现建议

- 优先使用 `pathlib`
- 仅在性能或兼容性需要时考虑 `fd`

---

## 4.2 `fs_read`

### 职责

读取文件内容。

### 主要用途

- 读取 markdown、json、yaml、py、txt 等文本文件
- 读取 research note、todo、checkpoint、runtime log

### 推荐参数

- `path: str`
- `start_line: int | null = null`
- `end_line: int | null = null`
- `max_chars: int | null = null`

### 返回

- 文件内容
- 元信息（路径、编码、总行数、截断标记）

### 实现建议

- 默认只支持文本文件
- 二进制文件后续另做专门处理，不放进首版

---

## 4.3 `fs_write`

### 职责

创建或覆盖写入文件。

### 主要用途

- 创建 note/checkpoint/log 文件
- 写入 markdown/json/yaml
- 受控地更新中间产物

### 推荐参数

- `path: str`
- `content: str`
- `mode: "overwrite" | "append" | "create_only" = "overwrite"`
- `mkdir_parents: bool = true`

### 返回

- 写入是否成功
- 最终路径
- 写入字节数

### 约束

- `create_only` 模式下若文件已存在则报错
- 不负责部分编辑；部分编辑交给 `fs_patch`

---

## 4.4 `fs_patch`

### 职责

对已有文本文件进行受控修改。

### 主要用途

- 更新 markdown 里的某一段
- 替换 todo 条目中的某个字段
- 更新 checkpoint 中某个 section

### 推荐参数

- `path: str`
- `operation: "replace" | "insert_before" | "insert_after"`
- `target: str`
- `content: str`
- `occurrence: "first" | "last" | "all" = "first"`

### 返回

- 是否成功
- 替换次数
- 修改摘要

### 约束

- 首版只支持文本级 patch，不做 AST 级编辑
- 如果未匹配到 target，必须返回明确失败

---

## 4.5 `fs_move`

### 职责

负责复制、移动、重命名。

### 主要用途

- 将抓取结果归档到 raw/
- 调整文件组织结构
- 复制模板文件到新位置

### 推荐参数

- `src: str`
- `dst: str`
- `action: "move" | "copy" | "rename"`
- `overwrite: bool = false`
- `mkdir_parents: bool = true`

### 返回

- 操作是否成功
- 实际执行动作
- 最终路径

### 实现建议

- 基于 `shutil` 与 `pathlib`
- `rename` 可视为同文件系统下 move 的特例

---

## 4.6 `fs_remove`

### 职责

删除路径，默认安全删除。

### 主要用途

- 清理临时文件
- 移除废弃中间产物
- 处理误生成文件

### 推荐参数

- `path: str`
- `mode: "trash" | "permanent" = "trash"`
- `recursive: bool = false`

### 返回

- 操作是否成功
- 删除模式
- 被删除目标摘要

### 实现建议

- 优先使用 `Send2Trash`
- 永久删除应显式要求，不能作为默认行为

---

## 4.7 `fs_search`

### 职责

在工作区内查找文件或搜索文本。

### 主要用途

- 在 notes/ 或 drafts/ 中找某个关键词
- 查找某类文件路径
- 判断某个 source id 是否已经存在

### 推荐参数

- `mode: "text" | "path"`
- `query: str`
- `root: str`
- `glob: str | null = null`
- `max_results: int = 50`
- `case_sensitive: bool = false`

### 返回

- 搜索结果列表
- 对 text 模式返回匹配行与文件位置
- 对 path 模式返回路径列表

### 实现建议

- `mode=text` 用 `rg`
- `mode=path` 用 `fd`

---

## 4.8 `run_command`

### 职责

运行受控 shell 命令。它是兜底工具，不是默认主路径。

### 主要用途

- 调用系统基础命令
- 运行小型脚本或诊断命令
- 做结构化工具未覆盖的通用系统操作

### 推荐参数

- `command: str[]`
- `cwd: str | null = null`
- `timeout_sec: int = 30`
- `env: dict | null = null`
- `capture_output: bool = true`

### 返回

- `return_code`
- `stdout`
- `stderr`
- 执行时长

### 强约束

- 不允许 `shell=True`
- 仅接受数组形式命令，不接受拼接字符串命令
- 默认捕获 stdout/stderr
- 必须记录日志

### 限制建议

- 可以配置 allowlist，例如只允许 `bash`, `python`, `rg`, `fd`, `jq`, `git`, `cat`, `sed`, `awk`, `head`, `tail`
- 对危险命令增加单独开关或环境限制

---

## 5. 为什么是这 8 个，而不是更多

这 8 个工具覆盖了最小必需能力：

- 看目录：`fs_list`
- 读文件：`fs_read`
- 写文件：`fs_write`
- 改文件：`fs_patch`
- 搬文件：`fs_move`
- 删文件：`fs_remove`
- 搜文件/文本：`fs_search`
- 兜底执行命令：`run_command`

它们已经足够支撑：

- 文件增删改查
- 工作区搜索
- 中间产物归档
- 调试与诊断
- 少量 shell 基础设施调用

如果再继续加，例如 `read_json`、`write_json`、`mkdir`、`exists`、`stat` 等，很快会让工具表面积变大，而这些能力其实可以内嵌到上述工具的返回值或实现中。

结论：

**首版先暴露 8 个，不再增加。**

---

## 6. 不建议直接暴露给 Agent 的能力

以下能力不建议作为独立工具暴露：

1. `mkdir`
   - 应由 `fs_write` / `fs_move` 的 `mkdir_parents` 吸收。

2. `exists`
   - 应由 `fs_list` / `fs_read` 的错误码或元信息吸收。

3. `read_json` / `write_json`
   - 首版直接走 `fs_read` / `fs_write` + Python 内部序列化。

4. `git_*`
   - 首版不建议暴露一组 git 工具；有需要时用 `run_command`。

5. 原始 `bash`
   - 不要把一个“任意 bash 执行器”直接当主接口。
   - 应通过受控 `run_command` 暴露。

6. 数据库、网络下载、HTTP 请求等非当前必要工具
   - 另立工具层，不放在文件管理工具层里。

---

## 7. Codex 实现建议

## 7.1 技术栈建议

首版建议直接使用：

- `pathlib`
- `subprocess`
- `shutil`
- 可选：`Send2Trash`

命令行工具依赖：

- `rg`
- `fd`
- 可选：`jq`

不强制要求引入额外第三方 Python 包。

## 7.2 目录边界控制

所有文件工具都必须运行在**受控工作区根目录**内。

要求：

- 所有输入路径在解析后必须位于 workspace root 之下
- 禁止路径穿越（例如 `../` 跳出工作区）
- 默认不允许访问 home 目录以外的任意系统路径

## 7.3 日志要求

每次工具调用都必须进入 runtime log。

至少记录：

- tool name
- 输入参数
- 是否成功
- 返回摘要
- 若有文件变化，记录变更路径
- 若有 stdout/stderr，记录摘要和 blob 引用

## 7.4 错误模型

工具返回必须结构化，不能只抛异常字符串。

推荐统一返回：

```json
{
  "ok": true,
  "data": {...},
  "error": null
}
```

失败时：

```json
{
  "ok": false,
  "data": null,
  "error": {
    "type": "FileNotFound",
    "message": "...",
    "details": {...}
  }
}
```

---

## 8. V1 与后续扩展

## 8.1 V1 必做

- `fs_list`
- `fs_read`
- `fs_write`
- `fs_patch`
- `fs_move`
- `fs_remove`
- `fs_search`
- `run_command`

## 8.2 V1.1 可选增强

- 对 JSON/YAML 的语义级 patch
- `git diff` 与工作区变更摘要封装
- 文件 watcher 自动归档
- 更细的权限配置

## 8.3 暂不做

- 多协议远程文件系统
- MCP server 接入
- 大而全工具市场
- 自动决定几十种文件操作工具的复杂编排

---

## 9. 最终建议

对于当前 Deep Research Agent 项目，推荐方案是：

1. 复用成熟基础设施：`pathlib + subprocess + shutil + rg + fd`。
2. 只暴露 8 个轻量底层工具给 Agent。
3. shell 仅作为兜底出口，不作为主业务接口。
4. 项目核心对象状态不要让 Agent 直接靠 shell 修改。
5. 首版优先实现“少工具、强约束、好记录日志”。

一句话总结：

**底层复用现成基础设施，上层只给 Agent 暴露少量、清晰、可审计的文件与命令工具。**
