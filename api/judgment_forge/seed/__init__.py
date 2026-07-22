"""
为何存在：金路径种子包的包根——把「可上传材料 + 金问题常量」与业务 HTTP 解耦。
谁调用：tests/test_golden_seed、scripts/seed_golden_project、面试演示前的播种流程。
调用谁：仅标准库 pathlib；不触库、不调 Provider。
"""
