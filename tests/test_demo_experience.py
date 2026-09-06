from backend.demo_accounts import install,ACCOUNTS
from backend.models import DemoAccount
from backend.qr_demo import ensure_qr_demo,DEMO_BATCH_ID
def test_demo_logins_roles_and_restrictions(env):
    app,c,creds=env
    app.state.settings.demo_mode=True
    with app.state.sessions() as db:
        install(db)
        for name,password,_,_ in ACCOUNTS:
            assert db.get(DemoAccount,name).password_hash.startswith("$argon2")
            assert db.get(DemoAccount,name).password_hash!=password
    headers={}
    for name,password,_,role in ACCOUNTS:
        r=c.post("/api/auth/login",json={"username":name,"password":password})
        assert r.status_code==200,r.text
        assert r.json()["user"]["role"]==role
        headers[role]={"Authorization":"Bearer "+r.json()["access_token"]}
    assert c.get("/api/beekeeper/hives",headers=headers["BEEKEEPER"]).status_code==200
    assert c.get("/api/kvic/overview",headers=headers["KVIC_ADMIN"]).status_code==200
    assert c.get("/api/lab/batches/assigned",headers=headers["LAB_OPERATOR"]).status_code==200
    assert c.get("/api/lab/batches/assigned",headers=headers["BEEKEEPER"]).status_code==403
    assert c.get("/api/kvic/overview",headers=headers["BEEKEEPER"]).status_code==403
    payload={"expected_version":1,"finalized_result_id":"x"}
    assert c.post("/api/kvic/batches/x/approve",headers=headers["LAB_OPERATOR"],json=payload).status_code==403
    from test_lab_security import result_body
    assert c.post("/api/lab/batches/x/results",headers=headers["KVIC_ADMIN"],json=result_body()).status_code==403
    config=c.get("/api/config").json()
    assert config["demo_mode"] and len(config["demo_accounts"])==3
    assert all(password not in str(config) for _,password,_,_ in ACCOUNTS)
    app.state.settings.demo_mode=False
    assert c.get("/api/config").json()=={"demo_mode":False}
    for name,password,_,_ in ACCOUNTS:
        assert c.post("/api/auth/login",json={"username":name,"password":password}).status_code==401
def test_verify_route_and_real_qr(env):
    app,c,creds=env
    result=ensure_qr_demo(app,creds)
    assert result["status"]=="VERIFIED"
    assert c.get("/verify?batch="+DEMO_BATCH_ID).status_code==200
    assert c.get("/api/public/batches/"+DEMO_BATCH_ID+"/qr").content.startswith(b"\x89PNG")
