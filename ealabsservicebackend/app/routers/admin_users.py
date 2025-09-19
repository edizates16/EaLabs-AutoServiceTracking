from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..deps import get_db, require_roles
from ..schemas import CreateUserIn, UserOut
from ..models import User, Role, UserRole
from ..auth import hash_password

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_roles(["OWNER"]))])

@router.post("/users", response_model=UserOut)
def create_user(body: CreateUserIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="Bu e-posta zaten kayıtlı")
    u = User(email=body.email, name=body.name, password_hash=hash_password(body.password))
    db.add(u)
    for rn in body.roles:
        role = db.query(Role).filter(Role.name == rn).first()
        if not role:
            role = Role(name=rn); db.add(role); db.flush()
        db.add(UserRole(user=u, role=role))
    db.commit(); db.refresh(u)
    return UserOut(id=u.id, email=u.email, name=u.name, roles=body.roles)
