from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from .auth import SECRET_KEY, ALGORITHM
from .models import User, Role
from .database import SessionLocal
from typing import Generator, List

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class CurrentUser:
    def __init__(self, id:int, email:str, name:str, roles:list[str]):
        self.id=id; self.email=email; self.name=name; self.roles=roles

async def get_current_user(token: str = Depends(oauth2_scheme), db=Depends(get_db)) -> CurrentUser:
    cred_err = HTTPException(status_code=401, detail="Kimlik doğrulama gerekli")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        uid = int(payload.get("sub"))
    except Exception:
        raise cred_err
    user = db.query(User).filter(User.id==uid, User.is_active==True).first()
    if not user: raise cred_err
    role_names = []
    for ur in user.roles:
        r = db.query(Role).get(ur.role_id)
        if r: role_names.append(r.name)
    return CurrentUser(user.id, user.email, user.name, role_names)

def require_roles(required: List[str]):
    def checker(current: CurrentUser = Depends(get_current_user)):
        if not set(current.roles).intersection(required):
            raise HTTPException(status_code=403, detail="EaLabs / Iris AI kullanmak için AI Director olmalısınız.")
        return current
    return checker