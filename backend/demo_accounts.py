"""Publicly documented SIH-only credentials; never enabled outside DEMO_MODE."""
from sqlalchemy import select
from .models import User, DemoAccount
from .security import hash_password, verify_password

ACCOUNTS = [
    ("KVIC-MH-NAS-001", "KvicDemo@2026", "officer.nas", "KVIC_ADMIN"),
    ("NHM-MH-88492", "BeeDemo@2026", "beekeeper.1", "BEEKEEPER"),
    ("LAB-MH-0042", "LabDemo@2026", "lab.1", "LAB_OPERATOR"),
]
def install(db):
    for username,password,principal,role in ACCOUNTS:
        user=db.scalar(select(User).where(User.username==principal))
        if not user or user.role!=role: raise RuntimeError("Missing synthetic demo principal")
        row=db.get(DemoAccount,username)
        if not row:
            db.add(DemoAccount(username=username,user_id=user.id,password_hash=hash_password(password)))
        elif row.user_id!=user.id:
            raise RuntimeError("Demo account mapping conflict")
    db.commit()
def public_accounts():
    return [{"username":name,"role":role} for name,_,_,role in ACCOUNTS]
if __name__=="__main__":
    from .app import create_app
    app=create_app()
    if not app.state.settings.demo_mode: raise RuntimeError("Enable DEMO_MODE for SIH setup")
    with app.state.sessions() as db: install(db)
    print("Three SIH demo logins installed with Argon2 password hashes.")
