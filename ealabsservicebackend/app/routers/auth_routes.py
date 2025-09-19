from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..schemas import LoginIn, Token, UserOut
from ..models import User
from ..auth import create_access_token, verify_password
from ..deps import get_db, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=Token)
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == body.email).first()
    if not u or not verify_password(body.password, u.password_hash) or not u.is_active:
        raise HTTPException(status_code=401, detail="E-posta veya şifre hatalı")
    return {"access_token": create_access_token({"sub": str(u.id)})}

@router.get("/me", response_model=UserOut)
def me(current=Depends(get_current_user)):
    return UserOut(id=current.id, email=current.email, name=current.name, roles=current.roles)
