"""
Account 模块路由——12 个接口。Router 只管调 Service，不碰数据细节。
"""
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.exc import IntegrityError

from app.dependencies import get_account_service
from app.middleware.jwt_auth import get_current_user
from app.schemas.account import (
    RegisterRequest, LoginRequest, RefreshRequest,
    ChangePasswordRequest, FindByIDRequest, FindByUsernameRequest,
    RenameRequest, UpdateProfileRequest, GetProfileRequest,
    AccountInfo, LoginResponse, GetProfileResponse,
)
from app.services.account_service import AccountService

public_router = APIRouter()
protected_router = APIRouter(dependencies=[Depends(get_current_user)])


# ═══════════ 公开接口 ═══════════

@public_router.post("/register")
async def register(req: RegisterRequest,
                   service: AccountService = Depends(get_account_service)):
    try:
        await service.register(req.username, req.password)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="username already exists")
    return {"message": "account created"}


@public_router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest,
                service: AccountService = Depends(get_account_service)):
    try:
        token, refresh, user = await service.login(req.username, req.password)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return LoginResponse(
        token=token, refresh_token=refresh,
        account_id=user["id"], username=user["username"],
    )


@public_router.post("/refresh", response_model=LoginResponse)
async def refresh(req: RefreshRequest,
                  service: AccountService = Depends(get_account_service)):
    try:
        new_token, account_id, username = await service.refresh_access_token(
            req.refresh_token, req.access_token,
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="invalid refresh token")
    return LoginResponse(token=new_token, refresh_token="", account_id=account_id, username=username)


@public_router.post("/changePassword")
async def change_password(req: ChangePasswordRequest,
                          service: AccountService = Depends(get_account_service)):
    try:
        await service.change_password(req.username, req.old_password, req.new_password)
    except ValueError:
        raise HTTPException(status_code=400, detail="unsuccessfully password changed")
    return {"message": "successfully password changed"}


@public_router.post("/findByID", response_model=AccountInfo)
async def find_by_id(req: FindByIDRequest,
                     service: AccountService = Depends(get_account_service)):
    try:
        user = await service.find_by_id(req.id)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return AccountInfo(**{k: v for k, v in user.items() if k in ("id", "username", "avatar_url", "bio")})


@public_router.post("/findByUsername", response_model=AccountInfo)
async def find_by_username(req: FindByUsernameRequest,
                           service: AccountService = Depends(get_account_service)):
    try:
        user = await service.find_by_username(req.username)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return AccountInfo(**{k: v for k, v in user.items() if k in ("id", "username", "avatar_url", "bio")})


@public_router.post("/getProfile", response_model=GetProfileResponse)
async def get_profile(req: GetProfileRequest,
                      service: AccountService = Depends(get_account_service)):
    if req.account_id == 0:
        raise HTTPException(status_code=400, detail="account_id is required")
    try:
        user = await service.find_by_id(req.account_id)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return GetProfileResponse(
        account=AccountInfo(**{k: v for k, v in user.items() if k in ("id", "username", "avatar_url", "bio")}),
        video_count=0, total_likes=0, follower_count=0, vlogger_count=0,
    )


# ═══════════ 需登录的接口 ═══════════

@protected_router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user),
                 service: AccountService = Depends(get_account_service)):
    try:
        await service.logout(current_user["account_id"])
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"message": "account logged out"}


@protected_router.post("/rename")
async def rename(req: RenameRequest,
                 current_user: dict = Depends(get_current_user),
                 service: AccountService = Depends(get_account_service)):
    try:
        new_token = await service.rename(current_user["account_id"], req.new_username)
    except ValueError as e:
        msg = str(e)
        if "already exists" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=500, detail=msg)
    return {"token": new_token}


@protected_router.post("/uploadAvatar")
async def upload_avatar(file: UploadFile = File(...),
                        current_user: dict = Depends(get_current_user),
                        service: AccountService = Depends(get_account_service)):
    account_id = current_user["account_id"]
    contents = await file.read()
    if len(contents) == 0 or len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="invalid file size")
    _, ext = os.path.splitext(file.filename or "")
    ext = ext.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(status_code=400, detail="only .jpg/.jpeg/.png/.webp allowed")
    dir_path = os.path.join("uploads", "avatars", str(account_id))
    os.makedirs(dir_path, exist_ok=True)
    filename = secrets.token_hex(16) + ext
    with open(os.path.join(dir_path, filename), "wb") as f:
        f.write(contents)
    avatar_url = f"http://localhost:8080/static/avatars/{account_id}/{filename}"
    await service.update_avatar(account_id, avatar_url)
    return {"avatar_url": avatar_url}


@protected_router.post("/updateProfile")
async def update_profile(req: UpdateProfileRequest,
                         current_user: dict = Depends(get_current_user),
                         service: AccountService = Depends(get_account_service)):
    try:
        await service.update_profile(current_user["account_id"], req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "profile updated"}
