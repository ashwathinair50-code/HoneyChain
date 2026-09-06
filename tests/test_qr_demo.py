from sqlalchemy import select,func
from backend.qr_demo import ensure_qr_demo,DEMO_BATCH_ID
from backend.models import Release

def test_named_qr_demo_is_verified_and_idempotent(env):
    app,client,credentials=env
    for _ in range(2):
        result=ensure_qr_demo(app,credentials)
        assert result["batch_id"]==DEMO_BATCH_ID
        assert result["status"]=="VERIFIED"
        assert result["passport"]["origin"]=="Nashik, Maharashtra"
        assert result["passport"]["synthetic_demo"] is True
        assert result["passport"]["lab"]["status"]=="LAB_RESULT_FINALIZED"
        assert all(result["evidence"].values())
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Release).where(Release.batch_id==DEMO_BATCH_ID))==1
    response=client.get("/api/public/batches/"+DEMO_BATCH_ID+"/qr")
    assert response.status_code==200 and response.content.startswith(b"\x89PNG")
