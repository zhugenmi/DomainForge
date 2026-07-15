# Skill 卸载路径穿越防护

> 日期:2026-06-28
> 类型:安全防护
> 影响范围:`app/skills/service.py::uninstall`

## 1. 问题现象

`uninstall(name)` 删除 `installed_path` 指向的目录。若 DB 行被篡改使 `installed_path` 指向 `installed_root` 之外(如 `/etc` 或 `../../`),`shutil.rmtree` 会误删系统目录或项目根。

## 2. 根因分析

### 直接原因

`uninstall` 直接读 DB 的 `installed_path` 字段,`shutil.rmtree(row.installed_path)` 无边界校验。

### 根本原因

`installed_path` 来自 DB,不可信。任何能写 DB 的路径(SQL 注入、管理员误操作、migration bug)都可能让 `installed_path` 指向任意路径。安全原则:外部输入(DB、HTTP、env)在执行破坏性操作前必须校验边界。

## 3. 解决方案

`uninstall` 先 resolve 再校验相对关系:

```python
async def uninstall(self, name: str) -> None:
    row = await self.repo.get(name)
    if row is None:
        raise SkillNotFoundError(name)
    target = Path(row.installed_path).resolve()
    root = self.installed_root.resolve()
    try:
        target.relative_to(root)  # 若 target 不在 root 之内抛 ValueError
    except ValueError:
        raise SkillUninstallError(f"path traversal: {target} not under {root}")
    shutil.rmtree(target)
    ...
```

`resolve()` 处理符号链接(符号链接可能指向 root 之外,resolve 后暴露真实路径)。

## 4. 验证

`tests/skills/test_service.py::test_uninstall_rejects_path_traversal`:模拟篡改 DB 行,把 `installed_path` 设为 `/etc` 或 `../../`,断言 `uninstall` 抛错且不执行 rmtree。

## 5. 复盘

- **触发条件**:任何"删文件/删目录"操作读外部输入路径(DB、HTTP 参数、配置文件)且无边界校验。
- **预防**:
  - 破坏性操作(rmtree、delete file)前必须 `target.relative_to(root)` 校验边界。
  - `resolve()` 处理符号链接,避免 `ln -s /etc /skills/installed/evil` 绕过。
  - DB 字段不可信--即使内部写入,也可能被 migration/运维/SQL 注入污染。
- **复用**:`file_tool.py` 的沙箱读写同理校验 `data/uploads/` 边界;`knowledge.py` 的文档删除走 DB FK 级联,无路径操作,不受此问题影响。
