"""
为何存在：研判 run 的 HTTP 表面（启动 / HITL 决定 / 取消 / 查状态 / 事件·Trace / 取备忘录）。
谁调用：create_app 挂载本 router；TestClient / 前端。
调用谁：runs.service；auth.deps.get_current_user。

人机决定入口：POST /projects/{project_id}/runs/{run_id}/hitl
  body: {gate: "web"|"checklist", decision: "approve"|"deny"} → RunService.decide_hitl
  - gate=web：第一道闸（联网）；gate=checklist：第二道闸（行动清单定稿）
  - resume 接续检查点（thread_id=run_id），非整图重跑；deny 仍 resume，cancel 才放弃。

取消入口：POST /projects/{project_id}/runs/{run_id}/cancel
  → RunService.cancel；仅 running / waiting_for_human → cancelled。

Trace 入口（工单 11）：GET .../trace 与 GET .../events
  → RunService.list_trace_for_owner；有序全量时间线（node/tool/llm/HITL/critic_bounce）。
  /events 与 /trace 同形，便于旧客户端与时间线 UI。

清单开关：StartRunRequest.produce_checklist → service.start → 图状态；
  批准后清单落在 memo.checklist；拒绝 / opt-out 无该字段；无外部 tracker 集成。

所有权：只把 current_user.id 交给 RunService；跨用户 → 404（与真缺失同形）。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from judgment_forge.auth.deps import get_current_user
from judgment_forge.auth.service import PublicUser
from judgment_forge.runs.service import (
    HitlGateMismatchError,
    HitlNotPendingError,
    MemoNotFoundError,
    ProjectNotFoundForRunError,
    PublicRun,
    RunNotCancellableError,
    RunNotFoundError,
    RunService,
)
from judgment_forge.runs.state import PublicDecisionMemo

router = APIRouter(prefix="/projects/{project_id}/runs", tags=["runs"])


class StartRunRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    produce_checklist: bool = False


class HitlDecisionRequest(BaseModel):
    gate: Literal["web", "checklist"] = "web"
    decision: Literal["approve", "deny"]


class RunResponse(BaseModel):
    id: UUID
    project_id: UUID
    question: str
    produce_checklist: bool
    web_enabled: bool
    status: str
    error_message: str | None = None
    critic_bounce_count: int = 0
    pending_hitl: dict[str, Any] | None = None
    hitl_events: list[dict[str, Any]] = Field(default_factory=list)


class RunEventsResponse(BaseModel):
    events: list[dict[str, Any]]


class RunTraceResponse(BaseModel):
    """有序 Run Trace；与 RunEventsResponse 同形，专供时间线 UI。"""

    events: list[dict[str, Any]]


class MemoClaimAnchorResponse(BaseModel):
    material_id: str | None = None
    location_hint: str | None = None
    url: str | None = None
    retrieved_at: str | None = None


class MemoClaimResponse(BaseModel):
    text: str
    presented_as: str
    anchors: list[MemoClaimAnchorResponse] = Field(default_factory=list)


class MemoResponse(BaseModel):
    conclusion: str
    options: str
    risks_unknowns: str
    next_steps: str
    claims: list[MemoClaimResponse]
    # opt-in 且 checklist 闸批准后为 3–8 条；拒绝 / opt-out 为 null。
    checklist: list[str] | None = None


def get_run_service(request: Request) -> RunService:
    """从 app.state 取出共享的 RunService（create_app 时注入，含同一 checkpointer）。"""
    return request.app.state.run_service


def _to_run_response(run: PublicRun) -> RunResponse:
    return RunResponse(
        id=run.id,
        project_id=run.project_id,
        question=run.question,
        produce_checklist=run.produce_checklist,
        web_enabled=run.web_enabled,
        status=run.status,
        error_message=run.error_message,
        critic_bounce_count=run.critic_bounce_count,
        pending_hitl=run.pending_hitl,
        hitl_events=list(run.hitl_events),
    )


def _to_memo_response(memo: PublicDecisionMemo) -> MemoResponse:
    return MemoResponse(
        conclusion=memo.conclusion,
        options=memo.options,
        risks_unknowns=memo.risks_unknowns,
        next_steps=memo.next_steps,
        claims=[
            MemoClaimResponse(
                text=c.text,
                presented_as=c.presented_as,
                anchors=[
                    MemoClaimAnchorResponse(
                        material_id=a.material_id or None,
                        location_hint=a.location_hint or None,
                        url=a.url or None,
                        retrieved_at=a.retrieved_at or None,
                    )
                    for a in c.anchors
                ],
            )
            for c in memo.claims
        ],
        checklist=list(memo.checklist) if memo.checklist else None,
    )


def _http_project_or_run_not_found(
    exc: ProjectNotFoundForRunError | RunNotFoundError | MemoNotFoundError,
) -> HTTPException:
    if isinstance(exc, ProjectNotFoundForRunError):
        detail = "project not found"
    elif isinstance(exc, MemoNotFoundError):
        detail = "memo not found"
    else:
        detail = "run not found"
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RunResponse)
def start_run(
    project_id: UUID,
    body: StartRunRequest,
    user: Annotated[PublicUser, Depends(get_current_user)],
    service: Annotated[RunService, Depends(get_run_service)],
) -> RunResponse:
    """
    所有者启动研判 run；图跑到 web_gate 后进入 waiting_for_human（web 默认关）。

    produce_checklist=true 时，过联网闸后还会在 Writer 之后停在 checklist 闸。
    人经 POST .../hitl 提交各闸决定后才会续跑到完成。
    """
    try:
        run = service.start(
            user.id,
            project_id,
            body.question,
            produce_checklist=body.produce_checklist,
        )
    except ProjectNotFoundForRunError as exc:
        raise _http_project_or_run_not_found(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _to_run_response(run)


@router.post("/{run_id}/hitl", response_model=RunResponse)
def decide_hitl(
    project_id: UUID,
    run_id: UUID,
    body: HitlDecisionRequest,
    user: Annotated[PublicUser, Depends(get_current_user)],
    service: Annotated[RunService, Depends(get_run_service)],
) -> RunResponse:
    """
    接收人机决定并 resume 检查点（thread_id=run_id，非整图重跑）。

    gate=web：approve → web_enabled，Researcher 可调联网；deny → 材料-only（仍续跑）。
    gate=checklist：approve → 备忘录带 3–8 条清单；deny → 仅备忘录、无清单。
    deny ≠ cancel：要放弃整次 run 请 POST .../cancel。两闸均不触发外部工单写入。
    """
    try:
        run = service.decide_hitl(
            user.id,
            project_id,
            run_id,
            gate=body.gate,
            decision=body.decision,
        )
    except ProjectNotFoundForRunError as exc:
        raise _http_project_or_run_not_found(exc) from exc
    except RunNotFoundError as exc:
        raise _http_project_or_run_not_found(exc) from exc
    except HitlNotPendingError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="run is not waiting for a human decision",
        ) from exc
    except HitlGateMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _to_run_response(run)


@router.post("/{run_id}/cancel", response_model=RunResponse)
def cancel_run(
    project_id: UUID,
    run_id: UUID,
    user: Annotated[PublicUser, Depends(get_current_user)],
    service: Annotated[RunService, Depends(get_run_service)],
) -> RunResponse:
    """
    取消进行中的 run（running 或 waiting_for_human）→ cancelled。

    与 HITL deny 不同：不 resume 图；检查点遗弃；之后不可再提交 hitl。
    """
    try:
        run = service.cancel(user.id, project_id, run_id)
    except ProjectNotFoundForRunError as exc:
        raise _http_project_or_run_not_found(exc) from exc
    except RunNotFoundError as exc:
        raise _http_project_or_run_not_found(exc) from exc
    except RunNotCancellableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="run cannot be cancelled in its current status",
        ) from exc
    return _to_run_response(run)


@router.get("/{run_id}", response_model=RunResponse)
def get_run(
    project_id: UUID,
    run_id: UUID,
    user: Annotated[PublicUser, Depends(get_current_user)],
    service: Annotated[RunService, Depends(get_run_service)],
) -> RunResponse:
    """查询 run 状态（含 waiting_for_human / pending_hitl / hitl_events）。"""
    try:
        run = service.get_for_owner(user.id, project_id, run_id)
    except (ProjectNotFoundForRunError, RunNotFoundError) as exc:
        raise _http_project_or_run_not_found(exc) from exc
    return _to_run_response(run)


@router.get("/{run_id}/events", response_model=RunEventsResponse)
def get_run_events(
    project_id: UUID,
    run_id: UUID,
    user: Annotated[PublicUser, Depends(get_current_user)],
    service: Annotated[RunService, Depends(get_run_service)],
) -> RunEventsResponse:
    """拉取有序全量时间线（与 /trace 同；兼容工单 08 的 HITL 过滤用法）。"""
    try:
        events = service.list_events_for_owner(user.id, project_id, run_id)
    except (ProjectNotFoundForRunError, RunNotFoundError) as exc:
        raise _http_project_or_run_not_found(exc) from exc
    return RunEventsResponse(events=events)


@router.get("/{run_id}/trace", response_model=RunTraceResponse)
def get_run_trace(
    project_id: UUID,
    run_id: UUID,
    user: Annotated[PublicUser, Depends(get_current_user)],
    service: Annotated[RunService, Depends(get_run_service)],
) -> RunTraceResponse:
    """
    所有者拉取 Run Trace（node/tool/llm/HITL/critic_bounce，按 seq 有序）。

    跨用户与真缺失同形 404；粗粒度 token/latency 在可测事件上附带。
    """
    try:
        events = service.list_trace_for_owner(user.id, project_id, run_id)
    except (ProjectNotFoundForRunError, RunNotFoundError) as exc:
        raise _http_project_or_run_not_found(exc) from exc
    return RunTraceResponse(events=events)


@router.get("/{run_id}/memo", response_model=MemoResponse)
def get_memo(
    project_id: UUID,
    run_id: UUID,
    user: Annotated[PublicUser, Depends(get_current_user)],
    service: Annotated[RunService, Depends(get_run_service)],
) -> MemoResponse:
    """读取决策备忘录；未完成或越权 → 404。"""
    try:
        memo = service.get_memo_for_owner(user.id, project_id, run_id)
    except (
        ProjectNotFoundForRunError,
        RunNotFoundError,
        MemoNotFoundError,
    ) as exc:
        raise _http_project_or_run_not_found(exc) from exc
    return _to_memo_response(memo)
