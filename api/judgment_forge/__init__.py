"""
为何存在：研判工坊 API 进程的包根（后续承载认证、项目、研判 run 等）。
谁调用：uvicorn、pytest，以及任何 judgment_forge.* 导入。
调用谁：包级不接线；具体接线由子模块负责。
"""

__version__ = "0.1.0"
