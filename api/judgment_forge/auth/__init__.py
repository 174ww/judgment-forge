"""
为何存在：认证包边界——注册/登录/登出与「当前用户」依赖的聚合出口。
谁调用：judgment_forge.app（挂路由）、后续需鉴权的业务路由。
调用谁：auth.routes、auth.deps（包外通常只 import router / get_current_user）。
"""
