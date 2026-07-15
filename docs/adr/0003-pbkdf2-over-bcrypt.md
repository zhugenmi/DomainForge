# ADR 0003:密码哈希用 PBKDF2(SHA256, 600k 迭代)而非 bcrypt

> 状态:已采纳 | 日期:2026-06-27

## 背景

Phase 3 安全加固需选密码哈希算法。生态主流:bcrypt、argon2、PBKDF2。

## 决策

用 stdlib `hashlib.pbkdf2_hmac`(sha256, 600k 迭代),**不引入 bcrypt/argon2 外部依赖**。

## 理由

### 备选方案与拒绝原因

| 方案 | 拒绝原因 |
|---|---|
| bcrypt | 未在 `pyproject.toml` 依赖中;引入增加 ~1MB + C 扩展编译;部分受限环境(无编译器)装不上 |
| argon2 | 同样需 C 扩展(argon2-cffi);密码学参数更复杂,首版无需其强度优势 |

### 选 PBKDF2 的理由

1. **stdlib 零依赖**:`hashlib.pbkdf2_hmac` 是 Python 标准库,无新依赖,任何环境可跑。
2. **Django 默认方案**:Django 的 `PBKDF2PasswordHasher` 即此实现,工业验证。
3. **NIST 推荐**:NIST SP 800-63B 推荐 PBKDF2 ≥ 600k 迭代(OWASP 2023 同步)。
4. **性能可接受**:单次哈希 ~100ms,登录场景(低频)无压力。
5. **格式兼容 Django**:存储格式 `pbkdf2_sha256$600000$<salt>$<key>`,将来切 bcrypt 可平滑迁移(Django 同款迁移路径)。

## 后果

- **正面**:零依赖;跨环境可跑;迁移路径清晰。
- **负面**:PBKDF2 抗 GPU/ASIC 攻击弱于 bcrypt/argon2(但 600k 迭代下实践安全);未来若需更高强度可切 argon2。
- **参数**:迭代数 600k 是 OWASP 2023 下限,后续可调高(改 `_ITERATIONS` 常量,旧哈希用存储的迭代数验证,新哈希用新迭代数)。
- **验证**:`verify_password` 用 `hmac.compare_digest` 防时序攻击;算法名校验(`algo != _ALGO`)防降级攻击;畸形哈希 `try/except` 返回 False 不崩。
