"""
为何存在：projects 包的公开入口标记；具体能力由 repository / service / routes 提供。
谁调用：judgment_forge.app 等导入子模块时作为包边界。
调用谁：无（空包初始化）。
"""
