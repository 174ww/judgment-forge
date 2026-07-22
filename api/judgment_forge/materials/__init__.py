"""
为何存在：材料上传→存储→解析→切块→索引 与项目内检索的包入口。
谁调用：judgment_forge.app 挂载 routes；后续 Researcher 经 retrieval.search_project_chunks
        （或 MaterialService.search）取证。
调用谁：本包内 service / repository / storage / ingest / retrieval（路由经 service）。
"""
