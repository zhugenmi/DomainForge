# SQLite 测试库与 JSONB/pgvector 的兼容性

> 日期:2026-06-17
> 类型:测试基础设施兼容性
> 影响范围:测试套件 `tests/` 全量

## 1. 问题现象

测试使用 SQLite 内存数据库,但 PostgreSQL 的 `JSONB` 和 `pgvector` 类型在 SQLite 中不可用。`Base.metadata.create_all` 报错 `UnsupportedCompilationError`,所有涉及 `document_chunks` / `memories` 表的测试无法启动。

## 2. 根因分析

### 直接原因

`app/database/models/chunk.py` 直接 `from pgvector.sqlalchemy import Vector` 并声明 `embedding: Vector(1024)`。SQLite 不识别 pgvector 类型,SQLAlchemy 编译 DDL 时抛 `UnsupportedCompilationError`。

### 根本原因

测试与生产使用不同数据库方言(SQLite vs PostgreSQL),但模型层硬编码了 PG 专属类型,未做方言无关的容错。设计上应让模型定义在 import 时不强依赖 pgvector。

## 3. 解决方案

### 3.1 JSONB -> JSON 通用类型

`JSONB` 替换为 `JSON`(SQLAlchemy 通用类型):
- PostgreSQL 上自动映射为 JSONB(保持生产性能)
- SQLite 上映射为 TEXT(测试可跑)

### 3.2 pgvector 延迟导入 + fallback

`app/database/models/chunk.py::_vector_type()`:

```python
def _vector_type():
    try:
        from pgvector.sqlalchemy import Vector
        from app.configs.settings import settings
        return Vector(settings.EMBEDDING_DIMENSION)
    except Exception:
        return Text
```

导入成功用 `Vector(1024)`,失败 fallback 为 `Text`。这让无 pgvector 的环境(CI、本地 SQLite)仍能建表。

## 4. 验证

- `tests/` 全量绿,SQLite 内存库可建所有表。
- 生产 PostgreSQL 上 `embedding` 列仍为 `vector(1024)`,`metadata_` 列为 JSONB。

## 5. 复盘

- **触发条件**:任何 SQLAlchemy 模型直接 import 方言专属类型。
- **预防**:模型层用通用类型 + 延迟导入方言专属类型;CI 用与生产不同的方言时,类型定义必须双方可解析。
- **复用**:后续新增 PG 专属类型(hstore、tsvector 等)同理用延迟导入 + fallback 模式。`tsv` 列也走此模式(用 `TypeDecorator` 或延迟导入)。
